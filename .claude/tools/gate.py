#!/usr/bin/env python3
"""gate.py — the single point of truth for "green" (workflow v3, spec §5.1).

One stdlib-only script that decides GREEN/RED by verifying BOTH the toolchain result AND
the integrity of its inputs against the change's git baseline (principle S8: hooks are
ergonomics; trust is this post-hoc check).

Usage:
    gate.py [--criteria] [--baseline <ref>] [--change <context>/NNN] [tree]

  tree        root of the work tree to gate (default: cwd). Must be the root of a git
              work tree for the integrity block to run.
  --change    change id; locates specs/<context>/changes/NNN-*/ and the baseline tag.
              Without it, a single specs/*/changes/*/ directory is auto-detected.
  --baseline  explicit baseline ref, overriding the tag convention below.
  --criteria  additionally cross-check criteria.md flips against this run's junit report.

Baseline convention (consumed by the /implement runner, T09):
  The red-tests commit on the change branch is tagged `baseline/<context>-NNN` at the
  moment the test-author's red commit lands (step 1 of /implement). gate.py resolves the
  baseline as: (1) --baseline if given; (2) else the tag for the change id; (3) else — no
  baseline: every integrity check is SKIPPED LOUDLY (legal only for a greenfield tree
  before its first change), never silently.

Outputs (machine consumers: the implementer's SubagentStop hook §5.3, the evaluator,
accept.py, the human):
  - human summary: one line per check, FAIL details inline, every SKIP loudly annotated;
  - machine block at the end: `failed:`/`skipped:` lists and a final `GATE: GREEN|RED`;
  - `.gate/verdict.json` in the tree: sha, dirty flag, baseline, per-check status, and
    `docker_exempt` (integration node-ids the daemon-absence carve-out let skip, T04b);
  - `.gate/last-run.xml` in the tree: junit-xml of the pytest run (backs --criteria);
  - exit code 0 only on GREEN; exit code 2 when the gate could not run at all (an unresolvable
    --change/--baseline, a toolchain missing from the project's environment) — that is an
    abort, not a verdict: no `.gate/verdict.json` is left behind for anyone to misread.

Environment contract:
  - GATE_DOCKER=0 force-skips the Docker tier (reported loudly as DOCKER SKIPPED).
  - The Docker tier hands the migration DSN to `alembic upgrade head` via DATABASE_URL
    (and GATE_DATABASE_URL); the app's alembic env.py must honour it when set.
  - PYTEST_ADDOPTS / PYTEST_PLUGINS / MYPYPATH are stripped from subprocess environments
    (config suppression from the caller's environment is part of the E-05 class).

The toolchain config (mypy strictness, ruff select incl. B006/B904, pinned pytest flags)
lives HERE as constants — the `conventions` skill cites gate.py, never the other way
around (spec §5, V-04).

One check is keyed on the change's declared CLASS: `invisible.openapi-diff` compares the
constructed app's OpenAPI operation set against the baseline commit's, because §3.1 makes that
diff the `invisible` class's whole proof (T20). Every other check is class-independent.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

sys.dont_write_bytecode = True  # never litter bytecode into protected trees

GATE_DIR_NAME = ".gate"
JUNIT_NAME = "last-run.xml"
VERDICT_NAME = "verdict.json"
INVENTORY_NAME = "inventory.json"
PLUGIN_MODULE = "gate_ac_plugin"

# ---------------------------------------------------------------------------------------
# Toolchain config — pinned here, the single point of truth (spec §5.1; V-04: config
# source must not be circular with the skills; E-05: pinned config defeats suppression
# via conftest/pyproject).
# ---------------------------------------------------------------------------------------

# mypy: strict house style; explicit bases handle the src-layout without installation.
# `plugins = pydantic.mypy` is not optional decoration: under strict mypy pydantic models
# synthesize a typed `__init__`, so the universal pydantic-settings pattern
# `Settings(password="raw")` (a `str` coerced to a `SecretStr` field at validation time) is a
# hard `arg-type` error without the plugin — a wall EVERY pydantic-settings app hits, in
# tests the implementer cannot edit. Likewise `testcontainers` ships no `py.typed`, so its
# import is `import-untyped` in every integration conftest. Both are universal stack facts, so
# per C6/C7 they live here (the one config home), never as per-app `# type: ignore` (which the
# grep gate bans anyway). See notes/18 for the users/001 ESCALATE that paid for this.
MYPY_CONFIG = """\
[mypy]
strict = True
warn_unreachable = True
mypy_path = src
explicit_package_bases = True
namespace_packages = True
plugins = pydantic.mypy

[mypy-testcontainers.*]
ignore_missing_imports = True
"""

# The ruff selection below includes B (hence B006 mutable-default and B904 raise-from — spec
# §5.1). Do not open this comment with the literal `ruff:` prefix: ruff parses `# ruff: <word>` as
# a file-level suppression directive and reports the prose as RUF103 (T04f).
RUFF_SELECT = "E,W,F,I,N,UP,B,C4,SIM,RUF"
RUFF_LINE_LENGTH = "120"
RUFF_TARGET = "py312"


def project_package(tree: Path) -> str | None:
    """The project's own import package: pyproject [project] name with `-`→`_`, or None."""
    pyproject = tree / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("project", {}).get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip().replace("-", "_")


def ruff_common(tree: Path) -> list[str]:
    """The pinned ruff CLI flags shared by every ruff invocation (C7: one home).

    Includes `lint.isort.known-first-party=[<pkg>]` pinned to the project's own package.
    Without it, ruff's isort auto-detects first-party by whether the package is on disk, so a
    `tests/**` import block is clean at the red baseline (src absent → own pkg sorts as
    third-party) yet `I001`-dirty at the gate (src present → own pkg sorts first-party). That
    drift lands in tests/**, the implementer's blocked lane — an unfixable, deadlocking RED.
    Pinning makes the classification src-independent, so baseline and gate agree by
    construction. red_check.lint_tests calls this so the two are byte-identical."""
    common = ["--isolated", "--line-length", RUFF_LINE_LENGTH, "--target-version", RUFF_TARGET]
    pkg = project_package(tree)
    if pkg:
        common += ["--config", f'lint.isort.known-first-party=["{pkg}"]']
    return common


# pytest: pinned config — `--override-ini=addopts=` + fixed rootdir + no cacheprovider,
# so silencing through conftest/pyproject addopts does not work (E-05). The rest of the
# ini surface is covered by pyproject.toml being a protected tree (E-02).
PYTEST_PINNED = ("--override-ini=addopts=", "-o", "junit_family=xunit2", "-p", "no:cacheprovider")

# ---------------------------------------------------------------------------------------
# Grep gates (spec §5.1) — every pattern traces to a paid-for finding.
# ---------------------------------------------------------------------------------------

GREP_GATES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # F-023: `# type: ignore` on content modules laundered real contract drift.
    ("grep.type-ignore", re.compile(r"#\s*type:\s*ignore"), "F-023"),
    # N-03: `from __future__ import annotations` breaks runtime introspection (DI/FastAPI).
    ("grep.future-annotations", re.compile(r"^\s*from\s+__future__\s+import\s+annotations"), "N-03"),
    # §5.1: a `noqa`-suppressed F401 hides unused-import debris instead of removing it.
    ("grep.noqa-f401", re.compile(r"#\s*noqa:[^#]*\bF401\b"), "§5.1"),
    # V-04: `raise NotImplementedError` in src/** is green for mypy but an A4-class stub.
    ("grep.not-implemented", re.compile(r"\braise\s+NotImplementedError\b"), "V-04"),
    # T08-5: SQLAlchemy Core is the house style; the ORM (declarative_base / DeclarativeBase /
    # Mapped[...] / mapped_column / relationship()) is banned. Was ADVICE (notes/17); flipped
    # to a gate per S4 — a clean deterministic signature belongs in the gate, not in prose.
    (
        "grep.no-orm",
        re.compile(r"\bdeclarative_base\b|\bDeclarativeBase\b|\bMapped\[|\bmapped_column\b|\brelationship\("),
        "§5.1",
    ),
)

# Test-tier grep gates (spec §5.1) — scan the target app's tests/** (never .claude/tools/).
TEST_GREP_GATES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # T08-5: the no-mocks contract — fakes for unit, real backends via testcontainers for
    # integration. The mock family only — unittest.mock / MagicMock / AsyncMock / @patch /
    # mock.patch / mocker. — is banned (zero sanctioned uses). Was ADVICE (notes/17); flipped
    # to a gate per S4. NOT monkeypatch: the house style sanctions monkeypatch.setenv in
    # settings tests and monkeypatch.setattr for non-dependencies (T04d, T04c finding 5), so
    # monkeypatch-misuse (patching a handler dependency) stays ADVICE — the "is this attr a
    # dependency" question is semantic and has no clean grep signature.
    (
        "grep.no-mocks",
        re.compile(r"\bunittest\.mock\b|\bMagicMock\b|\bAsyncMock\b|@patch\b|\bmock\.patch\b|\bmocker\."),
        "§5.1",
    ),
)

# Protected trees for the integrity diff vs baseline (E-01/E-02/E-12).
PROTECTED_PATHS = (".claude/tools", ".claude/hooks", ".claude/settings.json", "pyproject.toml")

# Integration suite root (house convention: path-based collection, testcontainer-backed
# tests live here — see the test-integration-* skills). The Docker-skip carve-out in the
# inventory check (spec §5.1, T04b) keys on this rootdir-relative prefix, NEVER on a test's
# skip-reason string.
INTEGRATION_TEST_PREFIX = "tests/integration/"

# Files whose worktree content must match git HEAD for the gate to trust the enforcement
# layer (E-02, widened by T18). Paths are PLUGIN-ROOT-relative — the plugin root is the
# directory that holds `tools/`: `.claude/` in this repo, the repository top in a
# `git subtree split --prefix=.claude` plugin repo (notes/21 §1).
#
# Why this is not just gate.py: once the workflow is INSTALLED, it lives outside the
# consumer's repository, and the two other protections both go blind there —
# `bash_guard` anchors to the consumer's root (so a write to the plugin's own files
# resolves outside it and is allowed, deliberately, T06e) and `integrity.protected-trees`
# diffs `.claude/tools|hooks|settings.json` INSIDE the consumer tree, where they do not
# exist, so it passes vacuously (notes/20 F-02). Self-hash is the only check that follows
# `__file__` back to where the workflow actually lives, so everything a consumer's trust
# rests on has to be anchored HERE or nowhere.
#
# An anchor is a file whose content DECIDES something: the tools a verdict comes out of,
# the four hooks, and the two manifests that decide which components are wired at all
# (tamper with `plugin.json` and every hook silently unhooks). Expressed as globs so a new
# tool or hook is anchored by construction rather than by remembering to extend a list.
#
# Deliberately NOT anchored:
#   * `tools/test_*.py` — they ship (notes/21 §1) but no enforcement decision reads them:
#     a tampered test cannot change a verdict, while anchoring them would turn every
#     uncommitted edit to the meta layer's own suite into a RED gate;
#   * skills / agents / commands / templates — knowledge and prompts. Their drift is a
#     review question, not an integrity one, and freezing them would make editing a skill
#     require a commit before any gate run.
SELF_INTEGRITY_GLOBS = (
    "tools/*.py",  # gate.py, criteria_lint.py (imported by --criteria), accept.py, red_check.py
    "hooks/*.py",  # the four hooks: ergonomics, but a tampered one lies to its reader
    "hooks/*.json",  # hooks.json — the hook wiring of an INSTALLED load
    "bin/*.py",  # the one sanctioned invocation form (notes/21 §3): tamper it and "the gate" is a fake
    ".claude-plugin/*.json",  # plugin.json names the components
    "settings.json",  # the hook wiring of a CHECKED-OUT / symlinked load — every trial so far
)
# Applied to an anchor candidate's basename (see the exclusion note above).
SELF_INTEGRITY_SKIP = re.compile(r"^test_.*\.py$")

CAPABILITY_REF = re.compile(r"\(verified by:\s*([^)]+)\)")  # L-06
CREATE_APP_DEF = re.compile(r"^def create_app\(", re.MULTILINE)  # A4 construct-smoke
TABLE_CALL = re.compile(r"\bTable\(")  # F-012 table metadata-import smoke
SQLALCHEMY_MENTION = re.compile(r"\bsqlalchemy\b")

# Pytest plugin injected via -p from OUTSIDE the tree (never the tree's own config): it
# records the collected node-id inventory + outcomes (E-05) and stamps `ac` markers into
# junit testcase properties (E-07/V-10/O-11).
AC_PLUGIN_SOURCE = '''\
"""Injected by gate.py: inventory + ac-marker junit properties. Not part of the tree."""

import json
import os

_collected = []
_outcomes = {}


def pytest_configure(config):
    config.addinivalue_line("markers", "ac(criterion_id): links a test to an acceptance criterion (AC-n)")


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        _collected.append(item.nodeid)
        for mark in item.iter_markers("ac"):
            for arg in mark.args:
                item.user_properties.append(("ac", str(arg)))


def pytest_runtest_logreport(report):
    if report.when == "setup":
        if report.skipped:
            _outcomes[report.nodeid] = "xfail" if hasattr(report, "wasxfail") else "skipped"
        elif report.failed:
            _outcomes[report.nodeid] = "error"
    elif report.when == "call":
        if report.skipped:
            _outcomes[report.nodeid] = "xfail" if hasattr(report, "wasxfail") else "skipped"
        elif report.failed:
            _outcomes[report.nodeid] = "failed"
        elif report.passed:
            _outcomes[report.nodeid] = "passed"


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("GATE_INVENTORY_PATH")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"collected": _collected, "outcomes": _outcomes}, fh, indent=2)
'''


@dataclass
class Check:
    id: str
    status: str  # PASS | FAIL | SKIP
    detail: str


class GateError(Exception):
    """Internal: a check could not even run; carries the loud detail."""


def _tail(text: str, limit: int = 1500) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 900,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _run_bytes(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> tuple[int, bytes]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, b""
    return proc.returncode, proc.stdout


def _git(tree: Path, *args: str) -> tuple[int, str]:
    return _run(["git", "-C", str(tree), *args], timeout=120)


def _criteria_lint() -> ModuleType:
    """The `criteria_lint` sibling module — stdlib-only import, one grammar one home (C7)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import criteria_lint

    return criteria_lint


def _src_files(tree: Path) -> list[Path]:
    src = tree / "src"
    return sorted(src.rglob("*.py")) if src.is_dir() else []


def _test_files(tree: Path) -> list[Path]:
    # The target app's tests/** only. The meta-layer tooling's own tests live under
    # .claude/tools/ and are NEVER scanned — that is what scopes no-mocks to the app (T04c).
    tests = tree / "tests"
    return sorted(tests.rglob("*.py")) if tests.is_dir() else []


def _module_name(py_file: Path, src_root: Path) -> str:
    rel = py_file.relative_to(src_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def capability_files(tree: Path) -> list[Path]:
    """The CANONICAL spec files of the tree: capability files + context overviews.

    Excluded: `use-cases/` (BA sources, verbatim input material) and `changes/` (a delta living
    on its own branch, deleted at acceptance). One home for the corpus rule (C7) — this gate's
    invariant-provenance check and the §5.5 drift check must not disagree about which files are
    the living spec.
    """
    specs = tree / "specs"
    if not specs.is_dir():
        return []
    return [p for p in sorted(specs.rglob("*.md")) if "use-cases" not in p.parts and "changes" not in p.parts]


def app_import_env(tree: Path) -> dict[str, str]:
    """The environment under which the app's own modules are importable in a subprocess.

    ONE home for the import conditions the tools give the app (C7): `resolve_context` builds the
    gate's full env on top of this (it adds the injected pytest plugin + inventory path), and
    `drift.py` reuses it to construct the app for its §5.5 route inventory. See the A4 note above
    `plan_package_import` for why the `PYTHONPATH=src` injection stays and how the import claim is
    checked with it stripped.
    """
    env = os.environ.copy()
    for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "MYPYPATH"):  # E-05 class: caller-side suppression
        env.pop(var, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    path_parts = [str(tree / "src")] if (tree / "src").is_dir() else []
    if os.environ.get("PYTHONPATH"):
        path_parts.append(os.environ["PYTHONPATH"])
    if path_parts:
        env["PYTHONPATH"] = os.pathsep.join(path_parts)
    return env


# ---------------------------------------------------------------------------------------
# Context resolution: tree, change dir, baseline ref
# ---------------------------------------------------------------------------------------


@dataclass
class GateContext:
    tree: Path
    gate_dir: Path
    plugin_dir: Path
    env: dict[str, str]
    sha: str
    dirty: bool
    git_root: Path | None
    change_id: str | None  # "<context>/NNN"
    change_dir: Path | None  # specs/<context>/changes/NNN-<slug>
    baseline: str | None  # resolved ref, None when unavailable
    baseline_reason: str  # why baseline is None (loud SKIP text)


def _detect_change(tree: Path, change_arg: str | None) -> tuple[str | None, Path | None, str]:
    """Return (change_id, change_dir, error). error is non-empty on unresolvable --change."""
    if change_arg:
        match = re.fullmatch(r"([A-Za-z0-9_-]+)/(\d+)", change_arg)
        if not match:
            return None, None, f"--change must look like <context>/NNN, got {change_arg!r}"
        context, nnn = match.group(1), match.group(2)
        changes = tree / "specs" / context / "changes"
        candidates = sorted(changes.glob(f"{nnn}-*")) + sorted(changes.glob(nnn))
        dirs = [c for c in candidates if c.is_dir()]
        if not dirs:
            return None, None, f"change directory specs/{context}/changes/{nnn}-* not found"
        return f"{context}/{nnn}", dirs[0], ""
    dirs = sorted(d for d in tree.glob("specs/*/changes/*") if d.is_dir())
    if len(dirs) == 1:
        nnn = dirs[0].name.split("-", 1)[0]
        context = dirs[0].parent.parent.name
        if nnn.isdigit():
            return f"{context}/{nnn}", dirs[0], ""
    return None, None, ""


def resolve_context(tree: Path, change_arg: str | None, baseline_arg: str | None) -> GateContext:
    gate_dir = tree / GATE_DIR_NAME
    gate_dir.mkdir(exist_ok=True)
    plugin_dir = gate_dir / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / f"{PLUGIN_MODULE}.py").write_text(AC_PLUGIN_SOURCE, encoding="utf-8")
    (gate_dir / "mypy.ini").write_text(MYPY_CONFIG + f"cache_dir = {gate_dir / 'mypy-cache'}\n", encoding="utf-8")
    for stale in (JUNIT_NAME, INVENTORY_NAME, VERDICT_NAME):
        # a leftover artifact from a previous run must never back THIS run (E-07 freshness)
        (gate_dir / stale).unlink(missing_ok=True)

    env = app_import_env(tree)
    path_parts = [str(plugin_dir)]
    if env.get("PYTHONPATH"):
        path_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(path_parts)
    env["GATE_INVENTORY_PATH"] = str(gate_dir / INVENTORY_NAME)

    rc, out = _git(tree, "rev-parse", "--show-toplevel")
    git_root = Path(out.strip()).resolve() if rc == 0 else None
    sha, dirty = "UNKNOWN", False
    if git_root is not None:
        rc, out = _git(tree, "rev-parse", "HEAD")
        sha = out.strip() if rc == 0 else "UNKNOWN"
        rc, out = _git(tree, "status", "--porcelain")
        dirty = bool(out.strip())

    change_id, change_dir, err = _detect_change(tree, change_arg)
    if err:
        raise GateError(err)

    baseline: str | None = None
    reason = ""
    if git_root is None:
        reason = "tree is not inside a git work tree"
    elif git_root != tree:
        reason = f"tree {tree} is not the root of its git work tree ({git_root})"
    elif baseline_arg:
        rc, out = _git(tree, "rev-parse", "--verify", f"{baseline_arg}^{{commit}}")
        if rc != 0:
            raise GateError(f"--baseline {baseline_arg!r} does not resolve to a commit: {out.strip()}")
        baseline = baseline_arg
    elif change_id:
        tag = "baseline/" + change_id.replace("/", "-")
        rc, _ = _git(tree, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        if rc == 0:
            baseline = tag
        else:
            reason = f"tag {tag} not found and no --baseline given"
    else:
        reason = "no --baseline, no --change, and no single specs/*/changes/* directory to derive them from"

    return GateContext(
        tree=tree,
        gate_dir=gate_dir,
        plugin_dir=plugin_dir,
        env=env,
        sha=sha,
        dirty=dirty,
        git_root=git_root,
        change_id=change_id,
        change_dir=change_dir,
        baseline=baseline,
        baseline_reason=reason,
    )


# ---------------------------------------------------------------------------------------
# 0. Toolchain preflight — a PRECONDITION, not a check row (T12b)
# ---------------------------------------------------------------------------------------

# The gate invokes its toolchain as `sys.executable -m <tool>` inside the PROJECT's own
# interpreter (the tools must see the project's code and dependencies). A project whose
# environment lacks one of them used to get a raw `No module named mypy` out of a subprocess,
# attributed to whichever check happened to run it — three FAILs and not one sentence saying
# what to install (the first consumer-project run, T16).
#
# This is a precondition, not a check: with the tool absent the gate cannot answer GREEN/RED at
# all, so it aborts loudly (exit 2, no verdict.json) rather than occupying a check row — the
# same shape accept.py gives an input it cannot determine (T10f). It still fails closed:
# resolve_context() has already deleted any stale .gate/verdict.json, so no downstream consumer
# (SubagentStop, accept.py) can read a previous run's answer as this one's.
TOOLCHAIN_FIX = (
    # "the workflow's scripts", not "gate.py": red_check.py prints this same sentence (T06j).
    "the workflow's scripts run each of them as `<python> -m <tool>` in the project's own interpreter, so they must be "
    'installed in the project\'s environment: add them to `[dependency-groups] dev` ("Dev (always present)" '
    "in the `conventions` skill, block D) and run `uv sync`."
)


def required_toolchain(tree: Path, *, docker_available: bool) -> list[str]:
    """The modules THIS run is about to invoke — the preflight's scope.

    Conditioned exactly like the checks that invoke them, so a tree whose checks would SKIP
    anyway never aborts over a tool it was never going to run (an empty greenfield tree)."""
    needed: list[str] = []
    if (tree / "src").is_dir() or (tree / "tests").is_dir():
        needed += ["mypy", "ruff"]  # check_mypy / check_ruff
    if (tree / "tests").is_dir():
        needed.append("pytest")  # check_pytest
    if docker_available and (tree / "alembic.ini").exists():
        needed.append("alembic")  # check_docker_tier
    return needed


def missing_toolchain(modules: list[str], env: dict[str, str], cwd: Path) -> list[str]:
    """Which of `modules` the gate's own interpreter cannot import. A probe that cannot be
    run at all is a loud GateError — "could not ask" must never read as "nothing missing"."""
    if not modules:
        return []
    probe = (
        "import importlib.util, json, sys\n"
        "missing = []\n"
        "for name in sys.argv[1:]:\n"
        "    try:\n"
        "        found = importlib.util.find_spec(name) is not None\n"
        "    except (ImportError, ValueError):\n"
        "        found = False\n"
        "    if not found:\n"
        "        missing.append(name)\n"
        "print(json.dumps(missing))\n"
    )
    rc, out = _run([sys.executable, "-c", probe, *modules], cwd=cwd, env=env, timeout=120)
    if rc != 0:
        raise GateError(f"toolchain preflight could not run under {sys.executable}:\n{_tail(out)}")
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise GateError(f"toolchain preflight returned no answer under {sys.executable}:\n{_tail(out)}") from None
    return [str(name) for name in result]


def toolchain_missing_message(missing: list[str]) -> str:
    """The one actionable sentence for an absent toolchain — one home for it (C7).

    red_check.py runs the same preflight before its baseline lint (T06j) and reuses this
    wording rather than restating it, so the consumer reads the same sentence whichever of
    the two scripts the workflow happens to run first."""
    return (
        f"toolchain missing from this project's environment ({sys.executable}): "
        + ", ".join(missing)
        + "\n"
        + TOOLCHAIN_FIX
    )


def preflight_toolchain(ctx: GateContext, *, docker_available: bool) -> None:
    missing = missing_toolchain(required_toolchain(ctx.tree, docker_available=docker_available), ctx.env, ctx.tree)
    if missing:
        raise GateError(toolchain_missing_message(missing))


# ---------------------------------------------------------------------------------------
# 1. Toolchain (spec §5.1: mypy / ruff check / ruff format / pytest with pinned config)
# ---------------------------------------------------------------------------------------


def check_mypy(ctx: GateContext) -> Check:
    targets = [d for d in ("src", "tests") if (ctx.tree / d).is_dir()]
    if not targets:
        return Check("toolchain.mypy", "SKIP", "no src/ or tests/ in tree — nothing to type-check")
    cmd = [sys.executable, "-m", "mypy", "--config-file", str(ctx.gate_dir / "mypy.ini"), *targets]
    rc, out = _run(cmd, cwd=ctx.tree, env=ctx.env)
    if rc == 0:
        return Check("toolchain.mypy", "PASS", f"mypy strict clean on {', '.join(targets)}")
    return Check("toolchain.mypy", "FAIL", _tail(out))


def check_ruff(ctx: GateContext) -> list[Check]:
    targets = [d for d in ("src", "tests") if (ctx.tree / d).is_dir()]
    if not targets:
        skip = "no src/ or tests/ in tree — nothing to lint"
        return [Check("toolchain.ruff-check", "SKIP", skip), Check("toolchain.ruff-format", "SKIP", skip)]
    common = ruff_common(ctx.tree)
    checks: list[Check] = []
    rc, out = _run(
        [sys.executable, "-m", "ruff", "check", *common, "--no-cache", "--select", RUFF_SELECT, *targets],
        cwd=ctx.tree,
        env=ctx.env,
    )
    checks.append(
        Check("toolchain.ruff-check", "PASS", f"ruff select {RUFF_SELECT} clean")
        if rc == 0
        else Check("toolchain.ruff-check", "FAIL", _tail(out))
    )
    rc, out = _run(
        [sys.executable, "-m", "ruff", "format", "--check", *common, *targets],
        cwd=ctx.tree,
        env=ctx.env,
    )
    checks.append(
        Check("toolchain.ruff-format", "PASS", "formatting canonical")
        if rc == 0
        else Check("toolchain.ruff-format", "FAIL", _tail(out))
    )
    return checks


# Localization of a RED gate to the implementer's blocked lane (tests/**). See notes/18: a
# static-toolchain RED confined to tests/** (own-package import order after src exists, conftest
# typing against a package that only now exists) can NEVER be cleared by a src/** edit — looping
# the implementer to the ESCALATE ceiling burns the whole cycle on an unwinnable hold. When this
# fires, /implement hands back to the test-author instead (D4: tests/** is their lane) and the
# SubagentStop hook releases the implementer without spending a block. Deliberately narrow — it
# fires ONLY when every failure is the static per-file toolchain AND that same toolchain is clean
# over src/ ALONE, so a src bug, a pytest/behaviour failure, or an integrity breach is never
# mis-routed away from the implementer.
_TESTS_HANDBACK_CHECKS = frozenset({"toolchain.mypy", "toolchain.ruff-check", "toolchain.ruff-format"})


def _src_only_static_clean(ctx: GateContext) -> bool:
    """True iff mypy + ruff-check + ruff-format are all clean over src/ ALONE."""
    if not (ctx.tree / "src").is_dir():
        return False
    common = ruff_common(ctx.tree)
    runs = (
        [sys.executable, "-m", "mypy", "--config-file", str(ctx.gate_dir / "mypy.ini"), "src"],
        [sys.executable, "-m", "ruff", "check", *common, "--no-cache", "--select", RUFF_SELECT, "src"],
        [sys.executable, "-m", "ruff", "format", "--check", *common, "src"],
    )
    return all(_run(cmd, cwd=ctx.tree, env=ctx.env)[0] == 0 for cmd in runs)


def red_localized_to(ctx: GateContext, checks: list[Check]) -> str | None:
    """ "tests" when a RED gate's failures are entirely in tests/** — an implementer-unfixable
    handback to the test-author; None for a GREEN gate or a normal implementer-fixable RED."""
    failed = [c for c in checks if c.status == "FAIL"]
    if not failed or any(c.id not in _TESTS_HANDBACK_CHECKS for c in failed):
        return None
    if not (ctx.tree / "tests").is_dir():
        return None
    return "tests" if _src_only_static_clean(ctx) else None


def check_pytest(ctx: GateContext) -> Check:
    # E-05: pinned config (`--override-ini=addopts=`, fixed rootdir, plugin injected from
    # outside the tree) — suppression through conftest/pyproject addopts does not work.
    if not (ctx.tree / "tests").is_dir():
        return Check("toolchain.pytest", "SKIP", "no tests/ in tree — nothing to run")
    junit = ctx.gate_dir / JUNIT_NAME
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        f"--rootdir={ctx.tree}",
        *PYTEST_PINNED,
        "-p",
        PLUGIN_MODULE,
        f"--junit-xml={junit}",
        "-q",
    ]
    rc, out = _run(cmd, cwd=ctx.tree, env=ctx.env, timeout=1800)
    if rc == 0:
        return Check("toolchain.pytest", "PASS", f"pytest green, junit at {GATE_DIR_NAME}/{JUNIT_NAME}")
    if rc == 5:
        return Check("toolchain.pytest", "FAIL", "tests/ exists but pytest collected no tests")
    return Check("toolchain.pytest", "FAIL", _tail(out))


# ---------------------------------------------------------------------------------------
# 2. Grep gates (F-023 / N-03 / noqa:F401 / V-04)
# ---------------------------------------------------------------------------------------


def grep_hits(files: list[Path], tree: Path, pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(tree)}:{line_no}: {line.strip()}")
    return hits


def check_greps(ctx: GateContext) -> list[Check]:
    checks: list[Check] = []
    src_files = _src_files(ctx.tree)
    for check_id, pattern, ref in GREP_GATES:
        if not src_files:
            checks.append(Check(check_id, "SKIP", "no src/ in tree — grep gate not applicable"))
            continue
        hits = grep_hits(src_files, ctx.tree, pattern)
        if hits:
            checks.append(Check(check_id, "FAIL", f"forbidden pattern ({ref}):\n" + "\n".join(hits)))
        else:
            checks.append(Check(check_id, "PASS", f"no {pattern.pattern!r} in src/** ({ref})"))
    test_files = _test_files(ctx.tree)
    for check_id, pattern, ref in TEST_GREP_GATES:
        if not test_files:
            checks.append(Check(check_id, "SKIP", "no tests/ in tree — grep gate not applicable"))
            continue
        hits = grep_hits(test_files, ctx.tree, pattern)
        if hits:
            checks.append(Check(check_id, "FAIL", f"forbidden pattern ({ref}):\n" + "\n".join(hits)))
        else:
            checks.append(Check(check_id, "PASS", f"no {pattern.pattern!r} in tests/** ({ref})"))
    return checks


# ---------------------------------------------------------------------------------------
# 3. Construct smoke (A4) + table metadata-import smoke (F-012)
# ---------------------------------------------------------------------------------------


def check_construct_smoke(ctx: GateContext) -> Check:
    # A4: mypy/ruff/unit tests all stay green while create_app() raises — so the gate
    # actually constructs the app and builds the OpenAPI schema.
    files = _src_files(ctx.tree)
    if not files:
        return Check("smoke.construct", "SKIP", "no src/ in tree — construct smoke not applicable")
    src_root = ctx.tree / "src"
    factories = [f for f in files if CREATE_APP_DEF.search(f.read_text(encoding="utf-8", errors="replace"))]
    if not factories:
        return Check("smoke.construct", "SKIP", "no create_app() found under src/ — construct smoke SKIPPED (loud)")
    for factory in factories:
        module = _module_name(factory, src_root)
        code = (
            "import importlib, sys\n"
            f"m = importlib.import_module({module!r})\n"
            "app = m.create_app()\n"
            "schema = app.openapi()\n"
            "sys.exit(0 if schema else 1)\n"
        )
        rc, out = _run([sys.executable, "-c", code], cwd=ctx.tree, env=ctx.env, timeout=300)
        if rc != 0:
            return Check("smoke.construct", "FAIL", f"{module}.create_app()/openapi() failed (A4):\n{_tail(out)}")
    return Check("smoke.construct", "PASS", f"create_app() + openapi() constructed: {len(factories)} factory module(s)")


def check_table_smoke(ctx: GateContext) -> Check:
    # F-012: every module defining sqlalchemy Table(...) must import cleanly, so the
    # table metadata actually registers (alembic autogenerate saw an empty MetaData).
    files = _src_files(ctx.tree)
    if not files:
        return Check("smoke.table-metadata", "SKIP", "no src/ in tree — table smoke not applicable")
    src_root = ctx.tree / "src"
    table_modules = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if TABLE_CALL.search(text) and SQLALCHEMY_MENTION.search(text):
            table_modules.append(_module_name(path, src_root))
    if not table_modules:
        return Check("smoke.table-metadata", "SKIP", "no sqlalchemy Table( modules under src/ — smoke SKIPPED (loud)")
    code = "import importlib\n" + "".join(f"importlib.import_module({m!r})\n" for m in sorted(table_modules))
    rc, out = _run([sys.executable, "-c", code], cwd=ctx.tree, env=ctx.env, timeout=300)
    if rc != 0:
        return Check("smoke.table-metadata", "FAIL", f"table module import failed (F-012):\n{_tail(out)}")
    return Check("smoke.table-metadata", "PASS", f"imported {len(table_modules)} table module(s) (F-012)")


# ---------------------------------------------------------------------------------------
# 3a. The OBSERVABLE SURFACE of a tree: which operations the constructed app serves
# ---------------------------------------------------------------------------------------
#
# The same machinery as the construct smoke above (same factory discovery, same import
# environment) with the schema kept instead of discarded. It lives HERE, in the gate, because
# gate.py is the one tool that already builds the app and owns the import conditions
# (`app_import_env`) — and because two readers need exactly one answer to "what does this tree's
# app serve" (C7):
#
#   * `check_invisible_surface` below — the `invisible` class's before/after diff (spec §3.1);
#   * `drift.py` — the §5.5 route⊆described-operation comparison (T17), which CALLS this.
#
# The direction is deliberate and pinned by a test: `drift.py` imports the gate, never the other
# way round (test_drift.test_no_decider_runs_this_script — a script that only SURFACES drift must
# not be reachable from anything that can deny). So the extraction lives in the decider and the
# reporter borrows it.

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE")

ROUTE_MARKER = "__ADW_ROUTES__"


@dataclass
class Route:
    method: str
    path: str
    module: str

    @property
    def operation(self) -> str:
        """`METHOD /path` — the identity a surface comparison uses."""
        return f"{self.method} {self.path}"


@dataclass
class Surface:
    routes: list[Route] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    undetermined: str = ""  # a surface that EXISTS and could not be read (T10f)
    absent: str = ""  # there is no HTTP surface in this tree at all (the loud-SKIP case)

    @property
    def operations(self) -> list[str]:
        return sorted({route.operation for route in self.routes})


def route_inventory(tree: Path) -> Surface:
    """Construct every `create_app()` factory under `src/**` and read `app.openapi()`.

    Two negatives, kept apart on purpose (the same distinction this file draws everywhere between
    a loud SKIP and a FAIL):
      * ABSENT — no `src/`, or no `create_app()` in it: the tree has no HTTP surface to describe.
      * UNDETERMINED — a factory exists and will not construct, or yields no route list. The
        surface is then UNKNOWN, never empty: reading a broken import as "no routes" would let a
        caller conclude "nothing changed" from "nothing known" (notes/19's fail-open class).
    """
    files = _src_files(tree)
    if not files:
        return Surface(absent=f"no src/ under {tree} — this tree serves no HTTP surface")
    src_root = tree / "src"
    factories = [f for f in files if CREATE_APP_DEF.search(f.read_text(encoding="utf-8", errors="replace"))]
    if not factories:
        return Surface(absent="no create_app() found under src/ — this tree serves no constructible HTTP surface")
    env = app_import_env(tree)
    surface = Surface()
    for factory in sorted(factories):
        module = _module_name(factory, src_root)
        code = (
            "import importlib, json, sys\n"
            f"methods = {list(HTTP_METHODS)!r}\n"
            f"m = importlib.import_module({module!r})\n"
            "app = m.create_app()\n"
            "schema = app.openapi()\n"
            "paths = schema.get('paths') if isinstance(schema, dict) else None\n"
            "if not isinstance(paths, dict):\n"
            "    sys.exit('app.openapi() returned no `paths` mapping')\n"
            "out = []\n"
            "for path, ops in paths.items():\n"
            "    if isinstance(ops, dict):\n"
            "        out += [[str(k).upper(), str(path)] for k in ops if str(k).upper() in methods]\n"
            f"print({ROUTE_MARKER!r} + json.dumps(sorted(out)))\n"
        )
        rc, out = _run([sys.executable, "-c", code], cwd=tree, env=env, timeout=300)
        payload = [line for line in out.splitlines() if line.startswith(ROUTE_MARKER)]
        if rc != 0 or not payload:
            return Surface(undetermined=f"{module}.create_app()/openapi() did not yield a route list:\n{_tail(out)}")
        surface.modules.append(module)
        for method, path in json.loads(payload[-1][len(ROUTE_MARKER) :]):
            surface.routes.append(Route(method, path, module))
    return surface


# ---------------------------------------------------------------------------------------
# 3b. Package-import smoke (A4, T12b): the app must import with the gate's injection stripped
# ---------------------------------------------------------------------------------------

# resolve_context() puts `<tree>/src` on PYTHONPATH for every subprocess the gate spawns, so
# mypy/pytest/the construct smoke all reach the app under an import path ONLY the gate provides.
# A project that is not installable therefore passed every other check while `uv run uvicorn …` died
# with ModuleNotFoundError — the gate supplying the conditions that hide the failure mode is
# exactly what A4 forbids. The injections stay (the editable install's .pth holds an ABSOLUTE
# path to one tree's src, and collect_baseline_inventory needs one to reach the extracted
# baseline tree — removing them would trade this A4 hole for an integrity hole); instead ONE
# check asks the question with the injection stripped.
#
# It can only ask it of a project that claims to be importable, so the trigger is the project's
# own `[build-system]` declaration: present -> the claim is checked and a failure is RED; absent
# -> the project says it is not installable and the SKIP says so out loud (this repo's permanent,
# honest case — see the T12b task file). Never silent either way.


@dataclass
class PackageImportPlan:
    kind: str  # "import" | "skip" | "fail"
    package: str | None
    reason: str


def plan_package_import(tree: Path) -> PackageImportPlan:
    """Decide what the import smoke can ask of this tree, from pyproject.toml alone."""
    pyproject = tree / "pyproject.toml"
    if not pyproject.is_file():
        return PackageImportPlan("skip", None, "no pyproject.toml in tree — the project declares no packaging to check")
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        # unreadable input for a check that guards trust: FAIL, never a quiet pass (T10f).
        return PackageImportPlan("fail", None, f"pyproject.toml could not be read: {exc}")
    if not isinstance(data.get("build-system"), dict):
        return PackageImportPlan(
            "skip",
            None,
            "pyproject.toml declares no [build-system], so the project is not installable: nothing outside "
            "gate.py (uvicorn, a plain `python -c import`) can reach src/** — the gate injects PYTHONPATH=src "
            "itself. Add [build-system] (`conventions` skill, block D) to have this checked",
        )
    package = project_package(tree)
    if not package:
        return PackageImportPlan(
            "fail",
            None,
            "pyproject.toml declares [build-system] but no [project] name — the import package cannot be determined",
        )
    return PackageImportPlan("import", package, "")


def import_without_injection(package: str, env: dict[str, str], cwd: Path) -> tuple[int, str]:
    """`import <package>` under `-I`: no PYTHONPATH, no cwd on sys.path, no user site — only
    what the interpreter's own environment installs, which is all `uvicorn` gets."""
    clean = {k: v for k, v in env.items() if k != "PYTHONPATH"}
    return _run([sys.executable, "-I", "-c", f"import {package}"], cwd=cwd, env=clean, timeout=300)


def check_package_import(ctx: GateContext) -> Check:
    plan = plan_package_import(ctx.tree)
    if plan.kind == "skip":
        return Check("smoke.package-import", "SKIP", f"PACKAGE IMPORT SKIPPED — {plan.reason}")
    if plan.kind == "fail" or plan.package is None:
        return Check("smoke.package-import", "FAIL", plan.reason)
    rc, out = import_without_injection(plan.package, ctx.env, ctx.tree)
    if rc == 0:
        return Check(
            "smoke.package-import",
            "PASS",
            f"`import {plan.package}` succeeds with the gate's PYTHONPATH=src injection stripped (A4)",
        )
    return Check(
        "smoke.package-import",
        "FAIL",
        f"the project declares [build-system] but `import {plan.package}` fails without the gate's own "
        f"PYTHONPATH=src injection — the app is unstartable outside gate.py (A4). Install the project into "
        f"its environment (`uv sync`) and check that src/{plan.package}/ is the package the build backend "
        f"builds:\n{_tail(out)}",
    )


# ---------------------------------------------------------------------------------------
# 3c. The change-class register, as the tools read it (spec §3.1)
# ---------------------------------------------------------------------------------------
#
# One home for "which class did this change declare" (C7): the gate needs it for the `invisible`
# proof below, `red_check.py` needs it to pick the baseline property (redness / mutation /
# green-at-baseline), and both must never disagree. HTML comments are stripped first, because the
# change.md template enumerates every class name inside its own comment — a change that keeps the
# comment declares the DEFAULT, not the last name the template happens to mention.

DEFAULT_CHANGE_CLASS = "behavioral"  # spec §3.1: the register's default
CLASS_HARDENING = "hardening"  # no red phase — proved by mutation (T09g)
CLASS_INVISIBLE = "invisible"  # no red phase — proved by a green gate + an unchanged surface (T20)

CLASS_LINE = re.compile(r"(?im)^Class:[ \t]*([A-Za-z][A-Za-z0-9_-]*)")


def parse_change_class(change_md: str) -> str:
    """The change's declared `Class:` (lowercased); `behavioral` when the line is absent."""
    stripped = "\n".join(_criteria_lint().strip_html_comments(change_md.splitlines()))
    match = CLASS_LINE.search(stripped)
    return match.group(1).lower() if match else DEFAULT_CHANGE_CLASS


# ---------------------------------------------------------------------------------------
# 3d. `Class: invisible` — the before/after OpenAPI diff that IS this class's proof (§3.1, T20)
# ---------------------------------------------------------------------------------------
#
# Spec §3.1 gives the `invisible` class (refactor / dependency upgrade / performance) a
# deterministic proof instead of new observable behaviour: «полный gate зелёный + diff
# OpenAPI-схемы до/после пуст». Until T20 the second half existed in no script at all — the
# promise was prose, which under S4 means the class had no proof and, since `red_check` had no
# `Class:` parse either, could not even obtain a baseline tag. This check is that half, and
# putting it INSIDE the gate collapses the two halves into one sentence: for an invisible change,
# "the gate is green" now includes "the app serves exactly the operations it served at baseline".
#
# What it compares, and why not more: the METHOD+path operation set, sorted, from
# `app.openapi()`. That is the whole observable HTTP surface a client can discover, and it is
# deterministic (route order and dict order cannot affect a sorted set). A full schema diff would
# additionally fire on an internal Pydantic model rename — устройство, not behaviour (S1) — and
# would train the route-around reflex a gate must never train. The narrower half is not left
# unguarded: every baseline test must still be collected AND pass (E-05 + the pytest check), so a
# changed response body is caught by the tests, while an ADDED or REMOVED endpoint — the one
# surface change no existing test can notice — is caught here.
#
# Reading the class from the WORK TREE copy of change.md is safe and attested: `change.md` is
# frozen against the baseline commit (E-12), so re-declaring `invisible` as `behavioral` to dodge
# this check makes `integrity.change-frozen` FAIL instead.
#
# The before side comes from `git archive <baseline>` extracted to a temp dir — never a
# `git worktree`, so this works in the detached worktrees acceptance runs use — and is
# constructed with the CURRENT environment's packages. That is a real limit worth naming: a
# breaking dependency upgrade whose baseline source cannot import under the new package versions
# reports UNDETERMINED, i.e. FAIL. Such a change cannot be proved by this comparison at all, and
# saying so out loud is the honest answer; silently passing it would be notes/19's fail-open class
# in the one place where the class has no other proof.


def _surface_of_baseline(ctx: GateContext, into: Path) -> Surface:
    """The baseline commit's own surface: its tracked tree extracted to `into`, then constructed.

    Pristine on purpose — unlike `collect_baseline_inventory`, which hybridises the baseline tree
    with the CURRENT `src/` so red-committed tests can import today's modules. Here the baseline's
    own `src/` IS the question: it is the "before" of the diff.
    """
    rc, tar_bytes = _run_bytes(["git", "-C", str(ctx.tree), "archive", "--format=tar", str(ctx.baseline)], timeout=300)
    if rc != 0:
        return Surface(undetermined=f"git archive {ctx.baseline} failed — the baseline surface cannot be read")
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        tar.extractall(into, filter="data")
    return route_inventory(into)


def check_invisible_surface(ctx: GateContext) -> Check:
    check_id = "invisible.openapi-diff"
    if ctx.change_dir is None:
        return Check(check_id, "SKIP", "no change directory resolved — the class register applies to a change (§3.1)")
    change_md = ctx.change_dir / "change.md"
    if not change_md.is_file():
        return Check(
            check_id,
            "SKIP",
            f"no {change_md.relative_to(ctx.tree)} — the declared class is unreadable (a change.md missing "
            "against a baseline is RED at integrity.change-frozen, E-12)",
        )
    declared = parse_change_class(change_md.read_text(encoding="utf-8", errors="replace"))
    if declared != CLASS_INVISIBLE:
        return Check(
            check_id,
            "SKIP",
            f"Class: {declared} — the before/after OpenAPI diff is the `invisible` class's proof (§3.1)",
        )
    if ctx.baseline is None:
        return Check(
            check_id,
            "FAIL",
            f"Class: invisible, but there is no baseline to compare against ({ctx.baseline_reason}) — this "
            "class's whole proof is that the surface did not change, so without a BEFORE side it has no "
            "proof at all (§3.1). Tag the baseline (red_check) or re-classify the change.",
        )
    with tempfile.TemporaryDirectory(prefix="gate-invisible-") as tmp:
        before = _surface_of_baseline(ctx, Path(tmp).resolve())
        after = route_inventory(ctx.tree)
    for side, surface in (("baseline", before), ("work tree", after)):
        if surface.undetermined:
            return Check(
                check_id,
                "FAIL",
                f"the {side}'s OpenAPI surface could not be determined, so the before/after diff did not "
                f"run — undetermined is not 'unchanged' (§3.1):\n{surface.undetermined}",
            )
    if before.absent and after.absent:
        return Check(
            check_id,
            "SKIP",
            f"Class: invisible with no constructible HTTP surface on either side ({after.absent}) — the diff "
            "has nothing to compare, so this change's proof rests on the green gate plus the baseline test "
            "inventory alone (§3.1)",
        )
    if bool(before.absent) != bool(after.absent):
        gone, gained = (before, after) if after.absent else (after, before)
        return Check(
            check_id,
            "FAIL",
            f"Class: invisible, but the app's HTTP surface itself appeared or disappeared since the baseline "
            f"— one side serves {len(gained.routes)} operation(s) and the other serves none "
            f"({gone.absent}). That is a behavioural change (§3.1).",
        )
    added = [op for op in after.operations if op not in set(before.operations)]
    removed = [op for op in before.operations if op not in set(after.operations)]
    if added or removed:
        return Check(
            check_id,
            "FAIL",
            "Class: invisible, but the OpenAPI operation set changed since the baseline "
            f"{ctx.baseline} — an invisible change must serve exactly the same surface (§3.1):\n"
            + "\n".join([f"+ {op} (served now, absent at baseline)" for op in added])
            + ("\n" if added and removed else "")
            + "\n".join([f"- {op} (served at baseline, gone now)" for op in removed])
            + "\nA surface change is behaviour: re-spec it as a behavioral change, or revert it.",
        )
    return Check(
        check_id,
        "PASS",
        f"Class: invisible — all {len(after.operations)} OpenAPI operation(s) identical to the baseline "
        f"{ctx.baseline} (§3.1)",
    )


# ---------------------------------------------------------------------------------------
# 4. Docker tier (O-06): postgres container + `alembic upgrade head`; loud DOCKER SKIPPED
# ---------------------------------------------------------------------------------------


@dataclass
class DockerProbe:
    # The gate's OWN environment fact about Docker — computed ONCE per run and shared by the
    # Docker tier AND the inventory carve-out (spec §5.1, T04b): one probe, one truth. The
    # carve-out keys on `available`, never on any per-test skip-reason string.
    available: bool
    reason: str  # loud DOCKER SKIPPED text when unavailable
    docker_bin: str | None


def probe_docker() -> DockerProbe:
    if os.environ.get("GATE_DOCKER") == "0":
        return DockerProbe(False, "DOCKER SKIPPED (forced off via GATE_DOCKER=0)", None)
    docker = shutil.which("docker")
    if not docker:
        return DockerProbe(False, "DOCKER SKIPPED (no docker binary on PATH)", None)
    rc, _ = _run([docker, "info"], timeout=30)
    if rc != 0:
        return DockerProbe(False, "DOCKER SKIPPED (docker daemon unavailable)", docker)
    return DockerProbe(True, "docker daemon available", docker)


def check_docker_tier(ctx: GateContext, probe: DockerProbe) -> Check:
    if not probe.available:
        return Check("docker.alembic", "SKIP", probe.reason)
    docker = probe.docker_bin
    assert docker is not None  # available implies a resolved binary
    if not (ctx.tree / "alembic.ini").exists():
        return Check("docker.alembic", "SKIP", "docker available, but no alembic.ini in tree — migration tier n/a")
    rc, out = _run(
        [
            docker,
            "run",
            "-d",
            "--rm",
            "-e",
            "POSTGRES_USER=gate",
            "-e",
            "POSTGRES_PASSWORD=gate",
            "-e",
            "POSTGRES_DB=gate",
            "-p",
            "127.0.0.1:0:5432",
            "postgres:16-alpine",
        ],
        timeout=900,
    )
    if rc != 0:
        return Check("docker.alembic", "FAIL", f"could not start postgres container:\n{_tail(out)}")
    cid = out.strip().splitlines()[-1]
    try:
        rc, out = _run([docker, "port", cid, "5432/tcp"], timeout=30)
        if rc != 0 or ":" not in out:
            return Check("docker.alembic", "FAIL", f"could not resolve container port:\n{_tail(out)}")
        port = out.strip().splitlines()[0].rsplit(":", 1)[1]
        for _ in range(90):
            rc, _ = _run([docker, "exec", cid, "pg_isready", "-U", "gate", "-d", "gate"], timeout=30)
            if rc == 0:
                break
            time.sleep(1)
        else:
            return Check("docker.alembic", "FAIL", "postgres container never became ready (90s)")
        dsn = f"postgresql://gate:gate@127.0.0.1:{port}/gate"
        env = dict(ctx.env, DATABASE_URL=dsn, GATE_DATABASE_URL=dsn)
        rc, out = _run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ctx.tree, env=env, timeout=600)
        if rc != 0:
            return Check("docker.alembic", "FAIL", f"alembic upgrade head failed (O-06):\n{_tail(out)}")
        return Check("docker.alembic", "PASS", "alembic upgrade head green against postgres:16-alpine (O-06)")
    finally:
        _run([docker, "rm", "-f", cid], timeout=60)


# ---------------------------------------------------------------------------------------
# 5. --criteria: junit cross-check of flips (E-07 / V-10 / O-11); [m] needs verdict.md
# ---------------------------------------------------------------------------------------


def junit_passed_ac_ids(junit_path: Path) -> set[str]:
    passed: set[str] = set()
    root = ET.parse(junit_path).getroot()
    for tc in root.iter("testcase"):
        broken = any(tc.find(t) is not None for t in ("failure", "error", "skipped"))
        if broken:
            continue
        for prop in tc.iter("property"):
            if prop.get("name") == "ac" and prop.get("value"):
                passed.add(str(prop.get("value")))
    return passed


def manual_violations(manual_ids: list[str], verdict_text: str | None) -> list[str]:
    if not manual_ids:
        return []
    if verdict_text is None:
        return [f"{ac_id}: [m] set but verdict.md does not exist" for ac_id in manual_ids]
    blocks: dict[str, str] = {}
    matches = list(re.finditer(r"(?m)^-\s*(AC-\d+)\b", verdict_text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(verdict_text)
        blocks[match.group(1)] = blocks.get(match.group(1), "") + verdict_text[match.start() : end]
    out = []
    for ac_id in manual_ids:
        block = blocks.get(ac_id)
        if block is None:
            out.append(f"{ac_id}: [m] set but verdict.md has no entry for it")
        elif "manual" not in block.lower():
            out.append(f"{ac_id}: [m] set but its verdict.md entry records no manual acceptance/reason")
    return out


def check_criteria(ctx: GateContext) -> list[Check]:
    lint = _criteria_lint()
    if ctx.change_dir is None:
        detail = "cannot locate the change directory — pass --change <context>/NNN"
        return [Check("criteria.junit-backing", "FAIL", detail), Check("criteria.manual-verdict", "FAIL", detail)]
    criteria_path = ctx.change_dir / "criteria.md"
    if not criteria_path.exists():
        detail = f"{criteria_path.relative_to(ctx.tree)} does not exist"
        return [Check("criteria.junit-backing", "FAIL", detail), Check("criteria.manual-verdict", "FAIL", detail)]
    lines = lint.strip_html_comments(criteria_path.read_text(encoding="utf-8").splitlines())
    criteria = lint.iter_criteria(lines)
    checked = [c.ac_id for c in criteria if c.state == "x"]
    manual = [c.ac_id for c in criteria if c.state == "m"]
    checks: list[Check] = []

    # E-07/V-10/O-11: every [x] must be backed by a PASSED ac-marked test in THIS run's junit.
    junit_path = ctx.gate_dir / JUNIT_NAME
    if not checked:
        checks.append(Check("criteria.junit-backing", "PASS", "no [x] criteria to back"))
    elif not junit_path.exists():
        checks.append(
            Check("criteria.junit-backing", "FAIL", f"{len(checked)} [x] criteria but no junit report from this run")
        )
    else:
        backed = junit_passed_ac_ids(junit_path)
        unbacked = [ac_id for ac_id in checked if ac_id not in backed]
        if unbacked:
            checks.append(
                Check(
                    "criteria.junit-backing",
                    "FAIL",
                    "flip without junit backing (E-07/V-10/O-11): "
                    + ", ".join(f"{a} has no passed @pytest.mark.ac({a!r}) test in this run" for a in unbacked),
                )
            )
        else:
            checks.append(Check("criteria.junit-backing", "PASS", f"{len(checked)} [x] criteria junit-backed"))

    # O-04/E-07: [m] is legal only with a recorded manual-acceptance entry in verdict.md.
    verdict_path = ctx.change_dir / "verdict.md"
    verdict_text = verdict_path.read_text(encoding="utf-8") if verdict_path.exists() else None
    violations = manual_violations(manual, verdict_text)
    if violations:
        checks.append(Check("criteria.manual-verdict", "FAIL", "\n".join(violations)))
    else:
        checks.append(Check("criteria.manual-verdict", "PASS", f"{len(manual)} [m] criteria have verdict.md entries"))
    return checks


# ---------------------------------------------------------------------------------------
# 6. Spec invariants reference living tests (L-06)
# ---------------------------------------------------------------------------------------


def check_invariant_tests(ctx: GateContext) -> Check:
    if not (ctx.tree / "specs").is_dir():
        return Check("spec.invariant-tests", "SKIP", "no specs/ in tree")
    lint = _criteria_lint()
    refs: list[tuple[Path, str]] = []
    for path in capability_files(ctx.tree):
        # A comment is not content (T10j). The criteria check strips HTML comments before
        # parsing; this one did not, so accept.py's capability birth — which copies the
        # template's own comment documenting the provenance form — handed the BASE branch a
        # rotted reference to a test named `<test-id>`, i.e. the acceptance script breaking S9.
        # Any capability file may legitimately carry a comment; the strip is the real fix, and
        # one grammar keeps one home (C7).
        text = "\n".join(lint.strip_html_comments(path.read_text(encoding="utf-8", errors="replace").splitlines()))
        for match in CAPABILITY_REF.finditer(text):
            refs.extend((path, token.strip()) for token in match.group(1).split(",") if token.strip())
    if not refs:
        return Check("spec.invariant-tests", "PASS", "no (verified by: ...) references in specs (L-06)")
    test_files = sorted((ctx.tree / "tests").rglob("*.py")) if (ctx.tree / "tests").is_dir() else []
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in test_files)
    missing: list[str] = []
    for spec_path, token in refs:
        name = token.split("::")[-1].strip()
        file_part = token.split("::")[0].strip() if "::" in token else None
        file_missing = file_part is not None and not (ctx.tree / file_part).exists()
        def_missing = not re.search(rf"\bdef\s+{re.escape(name)}\s*\(", corpus)
        if file_missing or def_missing:
            missing.append(f"{spec_path.relative_to(ctx.tree)}: (verified by: {token}) — test not found")
    if missing:
        return Check("spec.invariant-tests", "FAIL", "invariant references rotted (L-06):\n" + "\n".join(missing))
    return Check("spec.invariant-tests", "PASS", f"{len(refs)} invariant reference(s) resolve to living tests (L-06)")


# ---------------------------------------------------------------------------------------
# 7. Integrity against the red-commit baseline (S8: the trust anchor)
# ---------------------------------------------------------------------------------------


def _baseline_blob(ctx: GateContext, rel_path: str) -> bytes | None:
    """The baseline content of `rel_path`, or None when git would not hand it over.

    None conflates two facts — "the baseline tree has no such path" and "git could not read
    it" — which is why every caller pairs it with `_baseline_paths()` and reports the second
    case as a git failure (`_baseline_blob_problem`, T04f).
    """
    rc, out = _run_bytes(["git", "-C", str(ctx.tree), "show", f"{ctx.baseline}:{rel_path}"])
    return out if rc == 0 else None


def _baseline_blob_problem(ctx: GateContext, rel: str, *, in_baseline_tree: bool) -> str:
    """Why `_baseline_blob(ctx, rel)` came back None, said truthfully.

    A path the baseline tree LISTS cannot have been "created after the baseline commit"; if its
    blob is unreadable, git failed. Naming the wrong cause is how the swallowed rc in
    `_baseline_paths()` stayed invisible — the check failed closed, so only its message lied
    (T04f, notes/19's fail-open class).
    """
    if in_baseline_tree:
        return f"{rel}: listed in the baseline tree but `git show {ctx.baseline}:{rel}` failed — baseline unreadable"
    return f"{rel}: created after the baseline commit"


def _baseline_paths(ctx: GateContext, prefix: str) -> list[str]:
    """The baseline tree's paths under `prefix` — raising when git could not answer.

    "The baseline commit carries no such path" and "the baseline commit is unreadable" are
    different facts, and only the first is a legitimate empty list: an empty list from an
    unanswerable git call is read by every caller as "nothing to compare", i.e. it fails OPEN
    by construction (notes/19's single root cause; T04f). Callers turn the GateError into a
    FAIL naming the git failure — never an abort, because a broken baseline is a verdict about
    the tree, not a reason to leave no verdict at all.
    """
    rc, out = _git(ctx.tree, "ls-tree", "-r", "--name-only", str(ctx.baseline), "--", prefix)
    if rc != 0:
        raise GateError(f"git ls-tree {ctx.baseline} -- {prefix} failed (rc={rc}):\n{_tail(out)}")
    return [line for line in out.splitlines() if line.strip()]


def check_protected_trees(ctx: GateContext) -> Check:
    # E-01: Bash/Write bypass every prevention hook — so the gate diffs the protected
    # trees against the baseline commit instead of trusting the hooks.
    # E-02: the enforcement infra itself (.claude/tools|hooks, settings, pyproject) is in
    # the protected list. E-12: change.md freeze is checked separately below.
    rc, out = _git(ctx.tree, "diff", "--name-only", str(ctx.baseline), "--", *PROTECTED_PATHS)
    if rc != 0:
        return Check("integrity.protected-trees", "FAIL", f"git diff against baseline failed:\n{_tail(out)}")
    drifted = [line for line in out.splitlines() if line.strip()]
    rc, out = _git(ctx.tree, "ls-files", "--others", "--exclude-standard", "--", *PROTECTED_PATHS)
    if rc != 0:
        return Check("integrity.protected-trees", "FAIL", f"git ls-files failed:\n{_tail(out)}")
    added = [f"{line} (untracked, new since baseline)" for line in out.splitlines() if line.strip()]
    if drifted or added:
        return Check(
            "integrity.protected-trees",
            "FAIL",
            "protected trees diverged from baseline (E-01/E-02):\n" + "\n".join(drifted + added),
        )
    return Check("integrity.protected-trees", "PASS", "protected trees identical to baseline (E-01/E-02)")


def criteria_flip_violations(base_lines: list[str], work_lines: list[str]) -> list[str]:
    # E-03: reword-under-same-checkboxes — only the state character may change.
    lint = _criteria_lint()
    if len(base_lines) != len(work_lines):
        return [f"line count changed ({len(base_lines)} -> {len(work_lines)}) — items added or removed"]
    violations = []
    for line_no, (base, work) in enumerate(zip(base_lines, work_lines, strict=True), start=1):
        if base == work:
            continue
        base_match, work_match = lint.AC_LINE.match(base), lint.AC_LINE.match(work)
        if (
            base_match
            and work_match
            and base_match.group("acid") == work_match.group("acid")
            and base_match.group("text") == work_match.group("text")
        ):
            continue  # a legal state flip
        violations.append(f"line {line_no}: changed beyond a state flip: {work.strip()!r}")
    return violations


def check_criteria_flips(ctx: GateContext) -> Check:
    work_files = {str(p.relative_to(ctx.tree)) for p in ctx.tree.glob("specs/*/changes/*/criteria.md")}
    try:
        base_files = {p for p in _baseline_paths(ctx, "specs") if p.endswith("/criteria.md") and "/changes/" in p}
    except GateError as exc:
        return Check("integrity.criteria-flips", "FAIL", f"baseline criteria.md set unknown (E-03): {exc}")
    problems: list[str] = []
    for rel in sorted(work_files | base_files):
        blob = _baseline_blob(ctx, rel)
        if blob is None:
            problems.append(f"{_baseline_blob_problem(ctx, rel, in_baseline_tree=rel in base_files)} (E-03)")
            continue
        if rel not in work_files:
            problems.append(f"{rel}: existed at baseline but is gone from the work tree")
            continue
        work_lines = (ctx.tree / rel).read_text(encoding="utf-8").splitlines()
        base_lines = blob.decode("utf-8", errors="replace").splitlines()
        problems.extend(f"{rel}: {v}" for v in criteria_flip_violations(base_lines, work_lines))
    if problems:
        return Check("integrity.criteria-flips", "FAIL", "\n".join(problems))
    return Check("integrity.criteria-flips", "PASS", "criteria.md changed only by legal state flips (E-03)")


def check_change_frozen(ctx: GateContext) -> Check:
    # E-12: change.md hash is frozen at the red commit — the task text cannot be bent
    # to fit the implementation afterwards.
    work_files = {str(p.relative_to(ctx.tree)) for p in ctx.tree.glob("specs/*/changes/*/change.md")}
    try:
        base_files = {p for p in _baseline_paths(ctx, "specs") if p.endswith("/change.md") and "/changes/" in p}
    except GateError as exc:
        return Check("integrity.change-frozen", "FAIL", f"baseline change.md set unknown (E-12): {exc}")
    problems: list[str] = []
    for rel in sorted(work_files | base_files):
        blob = _baseline_blob(ctx, rel)
        if blob is None:
            problems.append(_baseline_blob_problem(ctx, rel, in_baseline_tree=rel in base_files))
        elif rel not in work_files:
            problems.append(f"{rel}: existed at baseline but is gone from the work tree")
        elif (ctx.tree / rel).read_bytes() != blob:
            problems.append(f"{rel}: content differs from the baseline commit")
    if problems:
        return Check(
            "integrity.change-frozen", "FAIL", "change.md frozen-hash violated (E-12):\n" + "\n".join(problems)
        )
    return Check("integrity.change-frozen", "PASS", "change.md identical to baseline (E-12)")


@dataclass(frozen=True)
class EscalateState:
    """What git knows about a branch's `ESCALATE` locks, relative to an anchor commit."""

    known: tuple[str, ...]  # ESCALATE paths carried by the anchor tree OR committed since it
    missing: tuple[str, ...]  # of `known`, those the work tree no longer has
    error: str | None  # a git call that could not be answered — never read as "no ESCALATE"


def _escalate_lines(text: str) -> set[str]:
    return {ln.strip() for ln in text.splitlines() if ln.strip().endswith("/ESCALATE") and "/changes/" in ln}


def escalate_state(tree: Path, anchor: str) -> EscalateState:
    """Every `specs/*/changes/*/ESCALATE` git knows for this branch since `anchor`, and which of
    them the work tree no longer has. One implementation, shared with accept.py (C7).

    Two git questions, because a lock enters history two ways: the anchor commit may carry it
    (`ls-tree`), or — the shipped flow — some commit in `anchor..HEAD` may have added it
    (`log`). The hook fires at the *implementer's* ceiling, i.e. AFTER the red baseline is
    committed and tagged, so a real ESCALATE is never in the baseline tree; a baseline-vs-HEAD
    tree comparison therefore sees "absent" at both ends and passes. That is exactly why T04e's
    baseline-only check could not fire in the shipped flow (notes/19, the corrected Question-3
    row) — the question has to be about the branch's HISTORY, not about two trees.

    Both calls are guarded: an unanswerable git result becomes `error`, never an empty list a
    caller would read as "no ESCALATE" (notes/19's fail-open class).
    """
    rc, out = _git(tree, "ls-tree", "-r", "--name-only", anchor, "--", "specs")
    if rc != 0:
        return EscalateState((), (), f"git ls-tree against {anchor} failed:\n{_tail(out)}")
    known = _escalate_lines(out)
    rc, out = _git(tree, "log", "--pretty=format:", "--name-only", f"{anchor}..HEAD", "--", "specs")
    if rc != 0:
        return EscalateState((), (), f"git log {anchor}..HEAD failed:\n{_tail(out)}")
    known |= _escalate_lines(out)
    ordered = tuple(sorted(known))
    return EscalateState(ordered, tuple(rel for rel in ordered if not (tree / rel).exists()), None)


def check_escalate_intact(ctx: GateContext) -> Check:
    # §5.3 / E-08: the iteration-ceiling `ESCALATE` file is a human-only lock — accept.py
    # denies while it exists and "снять файл может только человек". That was prose: the
    # change directory is deliberately NOT in PROTECTED_PATHS (criteria.md flips and
    # verdict.md writes are legal cycle traffic, so a blanket freeze would deadlock the very
    # cycle the lock guards), so an agent that hit its ceiling could delete the file and be
    # invisible to both scripts. The disappearance is therefore checked on its own: an
    # ESCALATE git knows about — carried by the baseline commit or COMMITTED by the hook since
    # it (T06h) — must still be in the work tree.
    #
    # The asymmetry is deliberate: a lock that still STANDS is not a gate failure (its presence
    # is accept.py's business, §5.3/§5.4) — the gate judges only its removal. Making a live lock
    # RED would leave an escalated change un-gateable, i.e. unable to show the human whether the
    # tree is otherwise green.
    #
    # The legal human path is unchanged in kind from every other baseline-anchored fact
    # (S4/S8): clear the file, commit that deletion alone, then move the baseline over it
    # (`red_check.py --change <ctx>/NNN --clear-escalate`) — the new baseline is the removal
    # commit, so the range is empty and the check goes quiet. The gate cannot tell a human from
    # an agent at the filesystem (neither can criteria_guard); it only makes the removal
    # visible, which is what turns clearing a lock into a deliberate, recorded act.
    state = escalate_state(ctx.tree, str(ctx.baseline))
    if state.error:
        return Check("integrity.escalate-intact", "FAIL", state.error)
    if not state.known:
        return Check(
            "integrity.escalate-intact",
            "PASS",
            "no ESCALATE file at the baseline commit or committed since it (§5.3/E-08)",
        )
    if state.missing:
        return Check(
            "integrity.escalate-intact",
            "FAIL",
            "ESCALATE removed since the baseline — only a human may clear it, and clearing it means "
            "re-baselining the change over the removal commit "
            f"(`red_check.py --change {ctx.change_id or '<ctx>/NNN'} --clear-escalate`, §5.3/E-08):\n"
            + "\n".join(state.missing),
        )
    return Check(
        "integrity.escalate-intact",
        "PASS",
        f"{len(state.known)} ESCALATE file(s) known to git on this branch are still present (§5.3/E-08)",
    )


def _is_integration_node(node_id: str) -> bool:
    # node-ids are rootdir-relative (the gate pins rootdir); the integration suite lives
    # under tests/integration/ by house convention (path-based collection).
    return node_id.split("::", 1)[0].startswith(INTEGRATION_TEST_PREFIX)


def inventory_violations(
    baseline_ids: set[str],
    collected: set[str],
    outcomes: dict[str, str],
    allowed_removals_text: str,
    *,
    docker_available: bool,
) -> tuple[list[str], list[str]]:
    # E-05: collected node-ids must be a superset of the baseline inventory; a baseline
    # test that is missing, skipped or xfailed = RED (deletion / deselect / conftest
    # silencing all collapse into this one check). Legal removals exist only when the
    # change.md (frozen at baseline) lists the node-id.
    #
    # Sole carve-out (spec §5.1, T04b): a COLLECTED baseline test under tests/integration/
    # reported `skipped` is NOT RED when the gate's own Docker probe found the daemon absent
    # — it is listed loudly in the DOCKER SKIPPED block instead. The key is the probe (an
    # environment fact) + the directory, never a skip-reason string. A deselected/deleted
    # integration test (not collected) is still RED (finding 4: the deselect bypass); with
    # the daemon present there is no exemption at all; a non-integration skip is RED; and
    # only `skipped` is exempt (an xfail or a setup error still fails).
    violations = []
    docker_skipped = []
    for node_id in sorted(baseline_ids):
        if node_id not in collected:
            if node_id in allowed_removals_text:
                continue
            violations.append(f"{node_id}: in baseline inventory but not collected in this run")
            continue
        outcome = outcomes.get(node_id)
        if outcome in ("passed", "failed"):
            continue
        if outcome == "skipped" and not docker_available and _is_integration_node(node_id):
            docker_skipped.append(node_id)
            continue
        violations.append(f"{node_id}: baseline test was {outcome or 'collected but not run'} in this run")
    return violations, docker_skipped


def collect_baseline_inventory(ctx: GateContext) -> set[str]:
    """Collect the baseline test inventory: baseline tree (its conftest environment
    included) hybridised with the CURRENT src/, so red-committed tests that import
    not-yet-implemented modules now resolve. Collection errors are loud failures."""
    rc, tar_bytes = _run_bytes(["git", "-C", str(ctx.tree), "archive", "--format=tar", str(ctx.baseline)], timeout=300)
    if rc != 0:
        raise GateError(f"git archive {ctx.baseline} failed")
    with tempfile.TemporaryDirectory(prefix="gate-baseline-") as tmp:
        tmp_path = Path(tmp).resolve()  # macOS: /var/... is a symlink; node-ids must match the real-path run
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
            tar.extractall(tmp_path, filter="data")
        if (ctx.tree / "src").is_dir():
            shutil.rmtree(tmp_path / "src", ignore_errors=True)
            shutil.copytree(ctx.tree / "src", tmp_path / "src")
        if not (tmp_path / "tests").is_dir():
            return set()
        inventory_path = tmp_path / "baseline-inventory.json"
        env = dict(ctx.env)
        env["GATE_INVENTORY_PATH"] = str(inventory_path)
        path_parts = [str(ctx.plugin_dir)]
        if (tmp_path / "src").is_dir():
            path_parts.append(str(tmp_path / "src"))
        env["PYTHONPATH"] = os.pathsep.join(path_parts)
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--collect-only",
            f"--rootdir={tmp_path}",
            *PYTEST_PINNED,
            "-p",
            PLUGIN_MODULE,
            "-q",
        ]
        rc, out = _run(cmd, cwd=tmp_path, env=env, timeout=600)
        if rc == 5:
            return set()
        if rc != 0 or not inventory_path.exists():
            raise GateError(f"baseline test collection failed (rc={rc}):\n{_tail(out)}")
        data = json.loads(inventory_path.read_text(encoding="utf-8"))
        return set(data.get("collected", []))


def check_test_inventory(ctx: GateContext, pytest_check: Check, *, docker_available: bool) -> tuple[Check, list[str]]:
    # The legal-removal allowance is READ OUT of the baseline change.md, so an unreadable
    # baseline must not silently shrink it to "" — that would turn a legal removal into a
    # violation, i.e. blame the tests for a git failure (T04f).
    try:
        baseline_ids = collect_baseline_inventory(ctx)
        allowed = ""
        for rel in _baseline_paths(ctx, "specs"):
            if rel.endswith("/change.md") and "/changes/" in rel:
                blob = _baseline_blob(ctx, rel)
                if blob is None:
                    raise GateError(_baseline_blob_problem(ctx, rel, in_baseline_tree=True))
                allowed += blob.decode("utf-8", errors="replace")
    except GateError as exc:
        return Check("integrity.test-inventory", "FAIL", str(exc)), []
    inventory_path = ctx.gate_dir / INVENTORY_NAME
    if pytest_check.status == "SKIP" or not inventory_path.exists():
        if baseline_ids:
            return (
                Check(
                    "integrity.test-inventory",
                    "FAIL",
                    f"baseline has {len(baseline_ids)} tests but this run collected none (E-05)",
                ),
                [],
            )
        return Check("integrity.test-inventory", "PASS", "baseline inventory empty; nothing to protect (E-05)"), []
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    collected = set(data.get("collected", []))
    outcomes = dict(data.get("outcomes", {}))
    violations, docker_skipped = inventory_violations(
        baseline_ids, collected, outcomes, allowed, docker_available=docker_available
    )
    if violations:
        return (
            Check(
                "integrity.test-inventory",
                "FAIL",
                "test inventory is not a superset of the baseline (E-05):\n" + "\n".join(violations),
            ),
            docker_skipped,
        )
    exempt_note = ""
    if docker_skipped:
        exempt_note = f"; {len(docker_skipped)} integration test(s) DOCKER SKIPPED (see block below)"
    return (
        Check(
            "integrity.test-inventory",
            "PASS",
            f"all {len(baseline_ids)} baseline tests collected and run (E-05){exempt_note}",
        ),
        docker_skipped,
    )


def plugin_root() -> Path:
    """Where the workflow's own files live: the parent of the tools directory.

    `.claude/` in this repository, the repository top in a split plugin repo — i.e. what
    Claude Code passes as `${CLAUDE_PLUGIN_ROOT}`. Unrelated to `GateContext.plugin_dir`,
    which is the injected *pytest* plugin's scratch directory.

    Resolved through symlinks on purpose — a consumer may attach `.claude` by symlink
    (notes/20 §2), and the question this answers is "where is the workflow REALLY", not
    "how was it reached".
    """
    return Path(__file__).resolve().parent.parent


def self_integrity_anchors(candidates: list[str]) -> list[str]:
    """The plugin-root-relative paths in `candidates` that SELF_INTEGRITY_GLOBS anchors (E-02).

    Matching is component-wise (directory part equal, basename fnmatch'ed), so `tools/*.py`
    means exactly the files in `tools/` and never something nested under it.
    """
    anchors = set()
    for rel in candidates:
        parent, _, name = rel.rpartition("/")
        if SELF_INTEGRITY_SKIP.match(name):
            continue
        for glob in SELF_INTEGRITY_GLOBS:
            glob_parent, _, glob_name = glob.rpartition("/")
            if parent == glob_parent and fnmatch.fnmatchcase(name, glob_name):
                anchors.add(rel)
                break
    return sorted(anchors)


def _worktree_anchor_candidates(root: Path) -> list[str]:
    """Every file under `root` that the anchor globs could match, as it is on disk.

    Read together with the HEAD listing so that an ADDED enforcement file (an untracked
    `tools/helper.py` dropped next to the gate) is a violation too, not an invisible one.
    """
    candidates = []
    for glob in SELF_INTEGRITY_GLOBS:
        parent, _, name = glob.rpartition("/")
        base = root / parent if parent else root
        if not base.is_dir():
            continue
        candidates.extend(f"{parent}/{p.name}" if parent else p.name for p in sorted(base.glob(name)) if p.is_file())
    return candidates


def check_self_hash(ctx: GateContext) -> Check:
    """E-02: the enforcement layer must match git HEAD of the repository it is installed from.

    What that asserts, precisely: *the work tree agrees with the plugin repo's LOCAL `HEAD`*
    — nothing more. The anchor is the plugin's own git history, so this catches every tamper
    nobody committed there (the accidental edit, the agent that patched a tool and moved on)
    and catches nothing an actor with commit access to the plugin directory chose to record:
    `bash_guard` allows writes to the plugin (it anchors to the CONSUMER's root, T06e), and
    the same access runs `git -C <plugin> commit -a`, after which work tree == HEAD and this
    check PASSes. Measured on a clone, not assumed (T19).

    T19 ruled that limit **stated, not closed**, and rejected the cheap middle option —
    comparing against the `{name}--v{version}` release tag — on two measurements: an
    installed plugin's marketplace clone is *shallow* and fetches `+refs/heads/main` only, so
    it carries no tags at all (the comparison would be inoperative exactly where it is
    needed), while a dev checkout goes stale against its own tag on the next commit touching
    any anchor — and `claude plugin tag` cuts that tag in the enclosing repo, i.e. in THIS
    one. Closing it needs a reference the local actor cannot author: a published commit
    (network — forbidden, a gate that needs the internet to say "green" is a worse property),
    a signed manifest, or a checksum pinned outside the plugin. Argument, reproduction and
    what a human can do instead: notes/20 F-02.
    """
    # E-02 (widened by T18): the gate does not trust the file system about the ENFORCEMENT
    # LAYER — every tool, hook and manifest under the plugin root must match git HEAD of the
    # repository the workflow is installed from. gate.py itself was the original coverage;
    # `accept.py`, `red_check.py`, the hooks and `plugin.json` are anchors for the same
    # reason, and in a consumer they have no other protection at all (see the note on
    # SELF_INTEGRITY_GLOBS). The toolchain config is constants inside gate.py, so this
    # covers it too.
    #
    # The anchor set is the union of what HEAD carries and what the work tree has, and both
    # git calls are guarded: an unanswerable git result is a FAIL, never an empty set a
    # caller would read as "nothing to check" (notes/19's fail-open class).
    #
    # No provenance means no verdict: an installed plugin that is not a git repository FAILs
    # rather than degrading, because a trust anchor that quietly stops anchoring is worse
    # than an absent one. The legitimate install modes all keep `.git` — the one that does
    # not is a `git-subdir` marketplace source, which is forbidden for exactly this reason
    # (notes/21 §5).
    root = plugin_root()
    rc, out = _run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], timeout=60)
    if rc != 0:
        return Check(
            "integrity.self-hash",
            "FAIL",
            f"the workflow's own files ({root}) are not inside a git repository — self-integrity is "
            "unverifiable, so no verdict from this run can be trusted (E-02). Install the workflow "
            "from a WHOLE-REPO source (a `github`/`url` marketplace source, never `git-subdir`): a "
            "subdirectory source is a content copy with no `.git` (notes/21 §5).",
        )
    top = Path(out.strip()).resolve()
    prefix = "" if root == top else root.relative_to(top).as_posix() + "/"
    rc, listing = _git(top, "ls-tree", "-r", "--name-only", "HEAD", "--", prefix or ".")
    if rc != 0:
        return Check(
            "integrity.self-hash",
            "FAIL",
            f"cannot list the workflow's own files at HEAD of {top} — self-integrity unverifiable "
            f"(E-02):\n{_tail(listing)}",
        )
    tracked = [line[len(prefix) :] for line in listing.splitlines() if line.startswith(prefix) and line.strip()]
    anchors = set(self_integrity_anchors(tracked)) | set(self_integrity_anchors(_worktree_anchor_candidates(root)))
    # Fail-closed floor: whatever the globs see, the gate and the criteria grammar it imports
    # are ALWAYS anchored. E-02's original coverage must not be able to shrink because a
    # layout moved a file out of a glob's reach.
    tools_dir = Path(__file__).resolve().parent
    tools_prefix = "" if tools_dir == root else tools_dir.relative_to(root).as_posix() + "/"
    anchors |= {f"{tools_prefix}gate.py", f"{tools_prefix}criteria_lint.py"}
    problems = []
    for rel in sorted(anchors):
        file_path = root / rel
        rc, blob = _run_bytes(["git", "-C", str(top), "show", f"HEAD:{prefix}{rel}"])
        if rc != 0:
            problems.append(f"{rel}: not committed at HEAD — the gate cannot vouch for it")
        elif not file_path.exists():
            problems.append(
                f"{rel}: committed at HEAD but missing from the work tree — an enforcement file was removed"
            )
        elif file_path.read_bytes() != blob:
            problems.append(f"{rel}: work-tree content differs from HEAD — the enforcement layer was modified")
    if problems:
        return Check("integrity.self-hash", "FAIL", "self-integrity violated (E-02):\n" + "\n".join(problems))
    return Check("integrity.self-hash", "PASS", f"all {len(anchors)} enforcement anchor(s) match git HEAD (E-02)")


# ---------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------


def run_gate(tree: Path, *, criteria: bool, baseline_arg: str | None, change_arg: str | None) -> int:
    ctx = resolve_context(tree, change_arg, baseline_arg)
    # one probe per run, shared by the Docker tier, the inventory carve-out AND the preflight
    # (the alembic tier is the one toolchain user whose invocation depends on the daemon).
    docker_probe = probe_docker()
    preflight_toolchain(ctx, docker_available=docker_probe.available)
    checks: list[Check] = []

    checks.append(check_mypy(ctx))
    checks.extend(check_ruff(ctx))
    pytest_check = check_pytest(ctx)
    checks.append(pytest_check)
    checks.extend(check_greps(ctx))
    checks.append(check_construct_smoke(ctx))
    checks.append(check_table_smoke(ctx))
    checks.append(check_package_import(ctx))
    # Class-keyed, and present in EVERY run's list so the class register is legible from the
    # report: a non-invisible change gets a loud SKIP naming its class, never silence (§3.1/T20).
    checks.append(check_invisible_surface(ctx))
    checks.append(check_docker_tier(ctx, docker_probe))
    if criteria:
        checks.extend(check_criteria(ctx))
    else:
        skip = "not requested (run with --criteria to cross-check criteria.md flips)"
        checks.append(Check("criteria.junit-backing", "SKIP", skip))
        checks.append(Check("criteria.manual-verdict", "SKIP", skip))
    checks.append(check_invariant_tests(ctx))

    docker_exempt: list[str] = []
    if ctx.baseline is None:
        skip = (
            f"INTEGRITY SKIPPED — {ctx.baseline_reason}; this run is NOT verified against "
            "a red-test baseline (legal only for a greenfield tree before its first change)"
        )
        for check_id in (
            "integrity.protected-trees",
            "integrity.criteria-flips",
            "integrity.change-frozen",
            "integrity.escalate-intact",
            "integrity.test-inventory",
        ):
            checks.append(Check(check_id, "SKIP", skip))
    else:
        checks.append(check_protected_trees(ctx))
        checks.append(check_criteria_flips(ctx))
        checks.append(check_change_frozen(ctx))
        checks.append(check_escalate_intact(ctx))
        inventory_check, docker_exempt = check_test_inventory(
            ctx, pytest_check, docker_available=docker_probe.available
        )
        checks.append(inventory_check)
    checks.append(check_self_hash(ctx))

    failed = [c.id for c in checks if c.status == "FAIL"]
    skipped = [c.id for c in checks if c.status == "SKIP"]
    result = "GREEN" if not failed else "RED"
    localized = red_localized_to(ctx, checks) if failed else None

    print(f"gate.py — workflow v3 gate run on {ctx.tree}")
    print(f"sha: {ctx.sha}{' (dirty work tree)' if ctx.dirty else ''}")
    print(f"change: {ctx.change_id or '-'} · baseline: {ctx.baseline or f'NONE ({ctx.baseline_reason})'}")
    print()
    for check in checks:
        first, _, rest = check.detail.partition("\n")
        print(f"[{check.status}] {check.id} — {first}")
        if rest and check.status == "FAIL":
            for line in rest.splitlines():
                print(f"       {line}")
    print()
    print("== GATE ==")
    print(f"sha: {ctx.sha}")
    docker_detail = next(c.detail for c in checks if c.id == "docker.alembic")
    print(f"docker: {docker_detail.splitlines()[0]}")
    if docker_exempt:
        # loud, never silent: the integration tests the daemon-absence carve-out let skip
        print(f"docker-exempt integration tests (skipped, not RED): {', '.join(docker_exempt)}")
    print(f"failed: {', '.join(failed) or '-'}")
    print(f"skipped: {', '.join(skipped) or '-'}")
    print(f"GATE: {result}")
    if localized == "tests":
        print("red localized to: tests/** — implementer-unfixable; test-author handback, not an ESCALATE (notes/18)")

    verdict = {
        "tree": str(ctx.tree),
        "sha": ctx.sha,
        "dirty": ctx.dirty,
        "change": ctx.change_id,
        "baseline": ctx.baseline,
        "baseline_reason": ctx.baseline_reason or None,
        "criteria_requested": criteria,
        "result": result,
        "failed": failed,
        "red_localized_to": localized,  # "tests" ⇒ implementer-unfixable, test-author handback (notes/18)
        "skipped": skipped,
        "docker_exempt": docker_exempt,  # integration node-ids skipped under daemon-absence (T04b; accept.py surfaces)
        "junit": f"{GATE_DIR_NAME}/{JUNIT_NAME}",
        "checks": [{"id": c.id, "status": c.status, "detail": c.detail} for c in checks],
    }
    (ctx.gate_dir / VERDICT_NAME).write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return 0 if result == "GREEN" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gate.py",
        description="workflow v3: decide GREEN/RED for a work tree — toolchain, grep gates, "
        "smokes, Docker tier, criteria cross-check, and integrity against the git baseline.",
    )
    parser.add_argument("tree", nargs="?", default=".", help="work-tree root to gate (default: cwd)")
    parser.add_argument(
        "--criteria", action="store_true", help="cross-check criteria.md flips against this run's junit"
    )
    parser.add_argument("--baseline", metavar="REF", help="baseline ref (overrides the baseline/<context>-NNN tag)")
    parser.add_argument("--change", metavar="CTX/NNN", help="change id, e.g. meetings/003")
    args = parser.parse_args(argv)

    tree = Path(args.tree).resolve()
    if not tree.is_dir():
        print(f"error: tree {tree} is not a directory", file=sys.stderr)
        return 2
    try:
        return run_gate(tree, criteria=args.criteria, baseline_arg=args.baseline, change_arg=args.change)
    except GateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
