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
  - exit code 0 only on GREEN.

Environment contract:
  - GATE_DOCKER=0 force-skips the Docker tier (reported loudly as DOCKER SKIPPED).
  - The Docker tier hands the migration DSN to `alembic upgrade head` via DATABASE_URL
    (and GATE_DATABASE_URL); the app's alembic env.py must honour it when set.
  - PYTEST_ADDOPTS / PYTEST_PLUGINS / MYPYPATH are stripped from subprocess environments
    (config suppression from the caller's environment is part of the E-05 class).

The toolchain config (mypy strictness, ruff select incl. B006/B904, pinned pytest flags)
lives HERE as constants — the `conventions` skill cites gate.py, never the other way
around (spec §5, V-04).
"""

from __future__ import annotations

import argparse
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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

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
MYPY_CONFIG = """\
[mypy]
strict = True
warn_unreachable = True
mypy_path = src
explicit_package_bases = True
namespace_packages = True
"""

# ruff: select includes B (hence B006 mutable-default and B904 raise-from — spec §5.1).
RUFF_SELECT = "E,W,F,I,N,UP,B,C4,SIM,RUF"
RUFF_LINE_LENGTH = "120"
RUFF_TARGET = "py312"

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
    # integration. unittest.mock / MagicMock / AsyncMock / @patch / mocker. / monkeypatch are
    # banned. Was ADVICE (notes/17); flipped to a gate per S4.
    (
        "grep.no-mocks",
        re.compile(
            r"\bunittest\.mock\b|\bMagicMock\b|\bAsyncMock\b|@patch\b|\bmock\.patch\b|\bmocker\.|\bmonkeypatch\b"
        ),
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

# Files whose worktree content must match git HEAD for the gate to trust itself (E-02).
# criteria_lint.py is imported by --criteria, so it is part of the trust base (C7).
SELF_INTEGRITY_FILES = ("gate.py", "criteria_lint.py")

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


def _criteria_lint():  # noqa: ANN202 — stdlib-only sibling import, one grammar one home (C7)
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

    env = os.environ.copy()
    for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "MYPYPATH"):  # E-05 class: caller-side suppression
        env.pop(var, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    path_parts = [str(plugin_dir)]
    if (tree / "src").is_dir():
        path_parts.append(str(tree / "src"))
    if os.environ.get("PYTHONPATH"):
        path_parts.append(os.environ["PYTHONPATH"])
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
    common = ["--isolated", "--line-length", RUFF_LINE_LENGTH, "--target-version", RUFF_TARGET]
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
    lines = lint._strip_html_comments(criteria_path.read_text(encoding="utf-8").splitlines())
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
    specs = ctx.tree / "specs"
    if not specs.is_dir():
        return Check("spec.invariant-tests", "SKIP", "no specs/ in tree")
    refs: list[tuple[Path, str]] = []
    for path in sorted(specs.rglob("*.md")):
        if "use-cases" in path.parts or "changes" in path.parts:
            continue
        for match in CAPABILITY_REF.finditer(path.read_text(encoding="utf-8", errors="replace")):
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
    rc, out = _run_bytes(["git", "-C", str(ctx.tree), "show", f"{ctx.baseline}:{rel_path}"])
    return out if rc == 0 else None


def _baseline_paths(ctx: GateContext, prefix: str) -> list[str]:
    rc, out = _git(ctx.tree, "ls-tree", "-r", "--name-only", str(ctx.baseline), "--", prefix)
    return [line for line in out.splitlines() if line.strip()] if rc == 0 else []


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
    base_files = {p for p in _baseline_paths(ctx, "specs") if p.endswith("/criteria.md") and "/changes/" in p}
    problems: list[str] = []
    for rel in sorted(work_files | base_files):
        blob = _baseline_blob(ctx, rel)
        if blob is None:
            problems.append(f"{rel}: created after the baseline commit (E-03)")
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
    base_files = {p for p in _baseline_paths(ctx, "specs") if p.endswith("/change.md") and "/changes/" in p}
    problems: list[str] = []
    for rel in sorted(work_files | base_files):
        blob = _baseline_blob(ctx, rel)
        if blob is None:
            problems.append(f"{rel}: created after the baseline commit")
        elif rel not in work_files:
            problems.append(f"{rel}: existed at baseline but is gone from the work tree")
        elif (ctx.tree / rel).read_bytes() != blob:
            problems.append(f"{rel}: content differs from the baseline commit")
    if problems:
        return Check(
            "integrity.change-frozen", "FAIL", "change.md frozen-hash violated (E-12):\n" + "\n".join(problems)
        )
    return Check("integrity.change-frozen", "PASS", "change.md identical to baseline (E-12)")


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
    try:
        baseline_ids = collect_baseline_inventory(ctx)
    except GateError as exc:
        return Check("integrity.test-inventory", "FAIL", str(exc)), []
    allowed = ""
    for rel in _baseline_paths(ctx, "specs"):
        if rel.endswith("/change.md") and "/changes/" in rel:
            blob = _baseline_blob(ctx, rel)
            if blob:
                allowed += blob.decode("utf-8", errors="replace")
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


def check_self_hash(ctx: GateContext) -> Check:
    # E-02: the gate does not trust the file system about ITSELF — gate.py and the
    # criteria grammar it imports must match git HEAD of the repo they live in. The
    # toolchain config is constants inside gate.py, so this hash covers it too.
    tools_dir = Path(__file__).resolve().parent
    rc, out = _run(["git", "-C", str(tools_dir), "rev-parse", "--show-toplevel"], timeout=60)
    if rc != 0:
        return Check(
            "integrity.self-hash", "FAIL", "gate.py is not inside a git repository — self-integrity unverifiable"
        )
    top = Path(out.strip()).resolve()
    problems = []
    for name in SELF_INTEGRITY_FILES:
        file_path = tools_dir / name
        rel = file_path.relative_to(top).as_posix()
        rc, blob = _run_bytes(["git", "-C", str(top), "show", f"HEAD:{rel}"])
        if rc != 0:
            problems.append(f"{rel}: not committed at HEAD — the gate cannot vouch for itself")
        elif not file_path.exists() or file_path.read_bytes() != blob:
            problems.append(f"{rel}: work-tree content differs from HEAD — the gate itself was modified")
    if problems:
        return Check("integrity.self-hash", "FAIL", "self-integrity violated (E-02):\n" + "\n".join(problems))
    return Check("integrity.self-hash", "PASS", f"{', '.join(SELF_INTEGRITY_FILES)} match git HEAD (E-02)")


# ---------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------


def run_gate(tree: Path, *, criteria: bool, baseline_arg: str | None, change_arg: str | None) -> int:
    ctx = resolve_context(tree, change_arg, baseline_arg)
    checks: list[Check] = []

    checks.append(check_mypy(ctx))
    checks.extend(check_ruff(ctx))
    pytest_check = check_pytest(ctx)
    checks.append(pytest_check)
    checks.extend(check_greps(ctx))
    checks.append(check_construct_smoke(ctx))
    checks.append(check_table_smoke(ctx))
    docker_probe = probe_docker()  # one probe per run, shared by the tier and the carve-out
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
            "integrity.test-inventory",
        ):
            checks.append(Check(check_id, "SKIP", skip))
    else:
        checks.append(check_protected_trees(ctx))
        checks.append(check_criteria_flips(ctx))
        checks.append(check_change_frozen(ctx))
        inventory_check, docker_exempt = check_test_inventory(
            ctx, pytest_check, docker_available=docker_probe.available
        )
        checks.append(inventory_check)
    checks.append(check_self_hash(ctx))

    failed = [c.id for c in checks if c.status == "FAIL"]
    skipped = [c.id for c in checks if c.status == "SKIP"]
    result = "GREEN" if not failed else "RED"

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
