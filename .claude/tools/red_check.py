#!/usr/bin/env python3
"""red_check.py — the red-baseline script step of /implement (workflow v3, spec §6 step 1).

The test-author's tests must be RED before any code exists: a test that is green before the
implementation is suspicious (it asserts nothing, or the behaviour already exists — a
collusion / green-before-code smell). This script makes that a machine check, not a judgment
call, and — once every criterion is pinned by a red test — tags the red commit as the
integrity baseline the rest of the cycle checks against (`baseline/<context>-NNN`, the tag
convention gate.py consumes, spec §5.1).

It runs the change's tests with a pinned pytest invocation (config suppression via
conftest/pyproject does not work, E-05 class), then asserts:
  1. coverage — every `AC-n` in criteria.md carries at least one `@pytest.mark.ac("AC-n")` test;
  2. redness — every ac-marked test is RED (failed or errored). A **passed** marked test is
     flagged as green-before-implementation; a skipped/xfail one cannot prove redness either.
  3. tests-only baseline — the commit about to be tagged touches `tests/**` only. The
     test-author's `disallowedTools` denies Edit/Write on `src/**`, but a Bash/Write escape
     (`echo > src/foo.py`) bypasses it and a *partial* src seed can leave the tests red and
     still slip code into the baseline. Catch the artifact, not the actor (S8): any non-`tests/`
     path in the baseline commit → refuse to tag (anti-collusion, spec §4 / D3).
  4. lint screen — the baseline's `tests/**` is ruff-clean (ruff-check + ruff-format --check,
     gate.py's config imported not restated, C7). The implementer is tool-blocked from
     `tests/**` and ruff is per-file, so a lint defect the test-author left there could never
     be cleared by any `src/**` edit — it would deadlock the implementer. Screen it here, at
     baseline time, so the test-author fixes it at author time (S4). NOT mypy — a greenfield
     first change imports a not-yet-written package, which is the intended redness.

Before any of that it runs a toolchain preflight (pytest + ruff; mypy too under `--rebaseline`,
where it is invoked): on a project's first change this is the very first script the workflow
runs, so an environment missing a tool must meet the actionable sentence here — in gate.py's own
words (C7) — and not a raw `No module named ruff` from a subprocess (T06j).

On a project's FIRST-EVER change there is no app shell yet, so the tests fail to *collect*
(their module-level import of the not-yet-written package raises `ModuleNotFoundError`) and the
marked items never register. A narrow greenfield fallback (`apply_greenfield_fallback`) then
static-scans those files' `ac` markers and counts the collection failure as RED — but only when
the missing module is the project's OWN package and `src/<pkg>/` does not exist yet, so a broken
brownfield test (a real import typo, package present) is never masked.

Usage:
    red_check.py [--change <context>/NNN] [--no-tag] [--force-tag] [--rebaseline] [tree]

  tree          root of the change work tree (default: cwd); must be a git work tree to tag.
  --change      change id <context>/NNN; else a single specs/*/changes/*/ dir is auto-detected.
  --no-tag      run the checks only, do not create the baseline tag (used by callers/tests).
  --force-tag   move an existing baseline tag (legal only during the red phase, before code).
  --rebaseline  move an existing baseline tag onto HEAD after a TESTS-HANDBACK: verifies the
                corrected tests in a throwaway worktree (redness, where src/ is absent) AND in
                the live tree (mypy, where src/ is present), refusing any move that drops an
                ac-marked test or writes outside tests/**. See the section note and notes/18.

Exit code 0 only when coverage + redness both hold (and the tag step, if any, succeeded).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True

RED_OUTCOMES = frozenset({"failed", "error"})
PLUGIN_MODULE = "red_check_plugin"
# Pinned like gate.py: no addopts from the tree, xunit2 junit, no cache plugin (E-05).
PYTEST_PINNED = ("--override-ini=addopts=", "-p", "no:cacheprovider")

# Injected from OUTSIDE the tree (never the tree's own config): records collected node-ids,
# their outcomes, and their `ac` markers. Same shape the gate's plugin uses, plus markers.
PLUGIN_SOURCE = '''\
"""Injected by red_check.py: node-id inventory + outcomes + ac markers. Not part of the tree."""

import json
import os

_collected = []
_outcomes = {}
_markers = {}
_collect_errors = []


def pytest_configure(config):
    config.addinivalue_line("markers", "ac(criterion_id): links a test to an acceptance criterion (AC-n)")


def pytest_collectreport(report):
    # A module that fails to import at collection (greenfield: the target package is not
    # written yet) never yields its items, so its ac markers are lost to the runtime hooks.
    # Record the failure so red_check can static-scan that file's markers as a fallback.
    if report.failed:
        _collect_errors.append({"nodeid": report.nodeid, "longrepr": str(report.longrepr)})


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        _collected.append(item.nodeid)
        acs = []
        for mark in item.iter_markers("ac"):
            for arg in mark.args:
                acs.append(str(arg))
        if acs:
            _markers[item.nodeid] = acs


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
    path = os.environ.get("RED_CHECK_INVENTORY_PATH")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "collected": _collected,
                    "outcomes": _outcomes,
                    "markers": _markers,
                    "collect_errors": _collect_errors,
                },
                fh,
                indent=2,
            )
'''


class RedCheckError(Exception):
    """A precondition could not even be evaluated; carries the loud detail."""


# ---------------------------------------------------------------------------------------
# Parsing criteria.md — one grammar, one home: reuse criteria_lint (C7).
# ---------------------------------------------------------------------------------------


def _criteria_lint():  # noqa: ANN202 — stdlib-only sibling import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import criteria_lint

    return criteria_lint


def _gate():  # noqa: ANN202 — stdlib-only sibling import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    return gate


def parse_ac_ids(criteria_text: str) -> list[str]:
    """Ordered, de-duplicated AC ids declared in criteria.md (HTML comments stripped)."""
    cl = _criteria_lint()
    lines = cl._strip_html_comments(criteria_text.splitlines())
    seen: list[str] = []
    for crit in cl.iter_criteria(lines):
        if crit.ac_id not in seen:
            seen.append(crit.ac_id)
    return seen


# ---------------------------------------------------------------------------------------
# Toolchain preflight — the same precondition gate.py applies, scoped to what THIS runs (T06j)
# ---------------------------------------------------------------------------------------
#
# red_check invokes its tools as `sys.executable -m <tool>` inside the PROJECT's interpreter,
# exactly as gate.py does. On a project's first change red_check is the very first script the
# workflow runs, so a consumer whose environment lacks the toolchain used to meet it as a raw
# `No module named ruff` (or a "pytest produced no inventory" misattribution) at baseline time,
# before the gate's sentence could ever be reached. Ask the same question here, in the same
# words (gate.toolchain_missing_message — one home, C7), and abort with the fix.
#
# The required set is NOT the gate's. red_check runs pytest + ruff; it deliberately does not run
# mypy at baseline time (a greenfield first change imports a not-yet-written package — that is
# the intended redness, T09f), so demanding mypy here would resurrect the deadlock that screen
# exists to prevent. Only --rebaseline runs mypy, and only where mypy_tests() itself would: a
# live tree with src/ present. Each entry is conditioned exactly like the call that needs it.


def required_toolchain(tree: Path, *, rebaseline: bool = False) -> list[str]:
    """The modules THIS run is about to invoke — the preflight's scope."""
    needed: list[str] = []
    if (tree / "tests").is_dir():
        needed += ["pytest", "ruff"]  # run_tests / lint_tests
    if rebaseline and (tree / "src").is_dir():
        needed.append("mypy")  # mypy_tests, which itself skips when src/ is absent
    return needed


def preflight_toolchain(tree: Path, *, rebaseline: bool = False) -> None:
    """Raise RedCheckError naming what to install; return silently when the tools are there."""
    gate = _gate()
    try:
        missing = gate.missing_toolchain(required_toolchain(tree, rebaseline=rebaseline), os.environ.copy(), tree)
    except gate.GateError as exc:  # "could not ask" must never read as "nothing missing"
        raise RedCheckError(str(exc)) from None
    if missing:
        raise RedCheckError(gate.toolchain_missing_message(missing))


# ---------------------------------------------------------------------------------------
# Change resolution
# ---------------------------------------------------------------------------------------


def resolve_change(tree: Path, change_arg: str | None) -> tuple[str, Path]:
    """Return (change_id "<ctx>/NNN", change_dir). Raise RedCheckError if unresolvable."""
    if change_arg:
        match = re.fullmatch(r"([A-Za-z0-9_-]+)/(\d+)", change_arg)
        if not match:
            raise RedCheckError(f"--change must look like <context>/NNN, got {change_arg!r}")
        context, nnn = match.group(1), match.group(2)
        changes = tree / "specs" / context / "changes"
        dirs = [c for c in sorted(changes.glob(f"{nnn}-*")) + sorted(changes.glob(nnn)) if c.is_dir()]
        if not dirs:
            raise RedCheckError(f"change directory specs/{context}/changes/{nnn}-* not found")
        return f"{context}/{nnn}", dirs[0]
    dirs = sorted(d for d in tree.glob("specs/*/changes/*") if d.is_dir())
    if len(dirs) != 1:
        raise RedCheckError("no --change given and the tree does not contain exactly one specs/*/changes/* directory")
    nnn = dirs[0].name.split("-", 1)[0]
    context = dirs[0].parent.parent.name
    if not nnn.isdigit():
        raise RedCheckError(f"cannot derive NNN from change directory {dirs[0].name!r}")
    return f"{context}/{nnn}", dirs[0]


# ---------------------------------------------------------------------------------------
# Running the tests
# ---------------------------------------------------------------------------------------


def run_tests(tree: Path) -> dict:
    """Run the tree's tests/ under the pinned invocation; return the inventory dict."""
    tests_dir = tree / "tests"
    if not tests_dir.is_dir():
        raise RedCheckError(f"no tests/ directory under {tree}")
    with tempfile.TemporaryDirectory(prefix="red_check_") as tmp:
        plugin_dir = Path(tmp)
        (plugin_dir / f"{PLUGIN_MODULE}.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
        inventory = plugin_dir / "inventory.json"

        env = os.environ.copy()
        for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "MYPYPATH"):  # E-05 class
            env.pop(var, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        path_parts = [str(plugin_dir)]
        if (tree / "src").is_dir():
            path_parts.append(str(tree / "src"))
        if os.environ.get("PYTHONPATH"):
            path_parts.append(os.environ["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(path_parts)
        env["RED_CHECK_INVENTORY_PATH"] = str(inventory)

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(tests_dir),
            *PYTEST_PINNED,
            "-p",
            PLUGIN_MODULE,
        ]
        subprocess.run(cmd, cwd=str(tree), env=env, capture_output=True, text=True, timeout=900)
        try:
            return json.loads(inventory.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RedCheckError(f"pytest produced no inventory (collection error?): {exc}") from None


# ---------------------------------------------------------------------------------------
# Baseline lint screen — refuse a lint-dirty RED baseline before tagging (T09f)
# ---------------------------------------------------------------------------------------
#
# The implementer is tool-blocked from tests/** and ruff is per-file, so a lint defect the
# test-author left in tests/** (e.g. an `I001` split-import block in conftest.py) can never
# be cleared by any src/** edit — it deadlocks the one agent whose job is to green the gate.
# Per S4 the fix belongs in the gate that runs at baseline time: screen tests/** for lint
# HERE, before tagging, so the test-author fixes it at author time.
#
# NOT mypy: at a greenfield first change the tests import a not-yet-written package, so mypy
# would fail import-resolution by design (that is the intended redness this whole script
# confirms). The screen is ruff-check + ruff-format --check only — do not "complete" it with
# mypy. The whole ruff config comes from gate.ruff_common() so "lint-clean at baseline" is
# byte-identical to what gate.py later enforces (C7: one home for the config); this screen
# never restates the select string. Crucially ruff_common pins isort's known-first-party to
# the project package, so the baseline's own-package import classification does NOT drift once
# src/ exists at gate time (the seam that ESCALATEd users/001 — see notes/18).


def lint_tests(tree: Path) -> list[str]:
    """Run the gate's ruff-check + ruff-format --check over the tree's tests/; return failures.

    Each returned element is a human-readable failure block (the ruff output naming the
    offending file); an empty list means the baseline is lint-clean. No tests/ dir → clean.
    """
    tests_dir = tree / "tests"
    if not tests_dir.is_dir():
        return []
    gate = _gate()
    common = gate.ruff_common(tree)
    env = os.environ.copy()
    for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "MYPYPATH"):  # E-05 class
        env.pop(var, None)
    failures: list[str] = []
    check = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *common, "--no-cache", "--select", gate.RUFF_SELECT, str(tests_dir)],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        failures.append("ruff check:\n" + (check.stdout or check.stderr).strip())
    fmt = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", *common, str(tests_dir)],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
    )
    if fmt.returncode != 0:
        failures.append("ruff format --check:\n" + (fmt.stdout or fmt.stderr).strip())
    return failures


# ---------------------------------------------------------------------------------------
# Greenfield fallback — a module-absent collection error is a real RED, not a missing marker
# ---------------------------------------------------------------------------------------
#
# On a project's first-ever change there is no app shell to import: the test-author's tests
# import `<pkg>.restapi.main` etc. at module scope, so pytest fails to *collect* them — the
# items never register and their `@pytest.mark.ac` markers are lost, making "every AC has a
# marked test" spuriously fail. This fallback restores those markers by a static AST scan of
# the failing files and counts the collection failure as RED for them.
#
# It is deliberately narrow (do not mask a broken brownfield test):
#   * the collection failure must be a `ModuleNotFoundError` whose top-level package is the
#     PROJECT'S OWN package (`pyproject.toml` [project] name, `-`→`_`) — not a third-party
#     dep the test-author forgot to declare (that must still fail);
#   * `src/<pkg>/` must not exist yet — a true greenfield first change. In brownfield the
#     package is present, so a collection error there (a real import typo) is never masked.


def project_package(tree: Path) -> str | None:
    """The project's own import package. Delegates to gate (C7: one home for the derivation)."""
    return _gate().project_package(tree)


_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([\w.]+)['\"]")


def missing_module_of(longrepr: str) -> str | None:
    """The dotted module name from a `ModuleNotFoundError` longrepr, or None if not one."""
    match = _MISSING_MODULE_RE.search(longrepr or "")
    return match.group(1) if match else None


def _ac_ids_of_decorator(node: ast.expr) -> list[str]:
    """The AC ids of a `@pytest.mark.ac("AC-n", ...)` decorator, else []."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ac"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
    ):
        return [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return []


def scan_ac_markers(source: str, relpath: str) -> dict[str, list[str]]:
    """Static scan: pytest-style `nodeid -> [AC ids]` for every `@pytest.mark.ac`-marked test.

    Mirrors the runtime plugin's `iter_markers("ac")` shape, but works without collecting the
    module (used when its import failed). Handles top-level test functions and class methods.
    """
    try:
        module = ast.parse(source)
    except SyntaxError:
        return {}
    found: dict[str, list[str]] = {}

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for child in body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                acs = [ac for dec in child.decorator_list for ac in _ac_ids_of_decorator(dec)]
                if acs:
                    found[f"{relpath}::{prefix}{child.name}"] = acs
            elif isinstance(child, ast.ClassDef):
                visit(child.body, f"{prefix}{child.name}::")

    visit(module.body, "")
    return found


def apply_greenfield_fallback(tree: Path, inventory: dict, pkg: str | None) -> dict:
    """Fold module-absent collection errors into the inventory as RED, ac-marked entries.

    Applies only when `pkg` is the project's own package, `src/<pkg>/` does not exist yet, and
    the collection error is a `ModuleNotFoundError` for that package (see the module note)."""
    if not pkg or (tree / "src" / pkg).exists():
        return inventory
    markers = inventory.setdefault("markers", {})
    outcomes = inventory.setdefault("outcomes", {})
    for err in inventory.get("collect_errors", []):
        missing = missing_module_of(err.get("longrepr", ""))
        if not missing or missing.split(".")[0] != pkg:
            continue  # not the project's own absent package → not a greenfield first change
        relpath = err.get("nodeid", "").strip()
        source_path = tree / relpath
        if not relpath or not source_path.is_file():
            continue
        for nodeid, acs in scan_ac_markers(source_path.read_text(encoding="utf-8"), relpath).items():
            markers.setdefault(nodeid, acs)
            outcomes.setdefault(nodeid, "error")  # a collection failure is a real RED
    return inventory


# ---------------------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------------------


@dataclass
class RedCheckResult:
    ac_ids: list[str]
    ac_to_tests: dict[str, list[str]]
    missing_acs: list[str] = field(default_factory=list)
    green_before_impl: list[str] = field(default_factory=list)  # marked node-ids that PASSED
    not_red_other: list[str] = field(default_factory=list)  # marked node-ids skipped/xfail/absent
    red_tests: list[str] = field(default_factory=list)  # marked node-ids that are RED

    @property
    def ok(self) -> bool:
        return not self.missing_acs and not self.green_before_impl and not self.not_red_other


def analyze(ac_ids: list[str], inventory: dict) -> RedCheckResult:
    outcomes: dict[str, str] = inventory.get("outcomes", {})
    markers: dict[str, list[str]] = inventory.get("markers", {})

    ac_to_tests: dict[str, list[str]] = {ac: [] for ac in ac_ids}
    for nodeid, acs in markers.items():
        for ac in acs:
            ac_to_tests.setdefault(ac, []).append(nodeid)

    result = RedCheckResult(ac_ids=ac_ids, ac_to_tests=ac_to_tests)
    result.missing_acs = [ac for ac in ac_ids if not ac_to_tests.get(ac)]

    marked_nodeids = sorted(markers)
    for nodeid in marked_nodeids:
        outcome = outcomes.get(nodeid, "missing")
        if outcome in RED_OUTCOMES:
            result.red_tests.append(nodeid)
        elif outcome == "passed":
            result.green_before_impl.append(nodeid)
        else:  # skipped / xfail / missing — cannot prove redness
            result.not_red_other.append(nodeid)
    return result


# ---------------------------------------------------------------------------------------
# Reporting + tagging
# ---------------------------------------------------------------------------------------


def format_report(change_id: str, result: RedCheckResult, lint_failures: list[str] | None = None) -> str:
    lines = [f"red_check: {change_id}", ""]
    lines.append(f"criteria: {len(result.ac_ids)} AC ({', '.join(result.ac_ids) or 'none'})")
    for ac in result.ac_ids:
        tests = result.ac_to_tests.get(ac) or []
        mark = "OK  " if tests else "MISS"
        lines.append(f"  [{mark}] {ac}: {len(tests)} marked test(s)")
    if result.missing_acs:
        lines.append(f"MISSING MARKER: {', '.join(result.missing_acs)} — every AC needs an ac-marked test")
    if result.green_before_impl:
        lines.append("GREEN BEFORE IMPLEMENTATION (a test that passes before code is suspicious):")
        lines.extend(f"    {nodeid}" for nodeid in result.green_before_impl)
    if result.not_red_other:
        lines.append("NOT RED (skipped/xfail/uncollected — cannot prove the behaviour is absent):")
        lines.extend(f"    {nodeid}" for nodeid in result.not_red_other)
    lines.append("")
    lines.append(f"RED-CHECK: {'RED-CONFIRMED' if result.ok else 'FAILED'}")
    if lint_failures is not None:  # the lint screen ran (redness was confirmed)
        if lint_failures:
            lines.append("")
            lines.append("BASELINE LINT: FAILED — tests/** must be lint-clean before tagging (T09f);")
            lines.append("the implementer cannot fix tests/**, so a lint-dirty baseline would deadlock it:")
            for block in lint_failures:
                lines.extend(f"    {ln}" for ln in block.splitlines())
        else:
            lines.append("BASELINE LINT: clean (ruff-check + ruff-format over tests/)")
    return "\n".join(lines)


def baseline_commit_paths(tree: Path) -> list[str]:
    """Paths the commit about to be tagged (HEAD) touches, relative to the tree root.

    `diff-tree --root` lists every file for a root commit; for a normal commit it is the diff
    against its parent — either way, exactly what the baseline commit introduced (deletions
    included, so a removal-class change deleting tests still shows only `tests/` paths).
    """
    proc = subprocess.run(
        ["git", "-C", str(tree), "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RedCheckError(f"could not inspect the baseline commit (HEAD): {(proc.stderr or proc.stdout).strip()}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def non_tests_paths(paths: list[str]) -> list[str]:
    """The baseline-commit paths that are NOT under tests/ (order preserved)."""
    return [p for p in paths if p != "tests" and not p.startswith("tests/")]


def tag_baseline(tree: Path, change_id: str, *, force: bool) -> str:
    tag = "baseline/" + change_id.replace("/", "-")
    args = ["git", "-C", str(tree), "tag"]
    if force:
        args.append("-f")
    args.append(tag)
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RedCheckError(
            f"could not create tag {tag}: {(proc.stderr or proc.stdout).strip()} "
            "(already tagged? re-run with --force-tag during the red phase, or delete it)"
        )
    return tag


# ---------------------------------------------------------------------------------------
# Re-baseline — move the tag onto a corrected tests commit after a TESTS-HANDBACK (notes/18)
# ---------------------------------------------------------------------------------------
#
# When gate.py reports `red_localized_to: "tests"`, /implement hands back to the test-author,
# who fixes tests/** while the implementer's `src/` sits UNCOMMITTED in the work tree. The
# baseline tag must then move onto the corrected tests commit — and doing that by hand means a
# stash dance, because the two checks that matter want opposite worlds:
#
#   * redness needs `src/` ABSENT (with the package present the tests pass and prove nothing);
#   * mypy over tests/** needs `src/` PRESENT (the conftest annotates app types, so without src
#     every annotation is an unresolved import — the very reason red_check skips mypy at the
#     original baseline).
#
# So run each check in the world where it is meaningful, and never touch the live work tree:
# redness + lint in an isolated `git worktree` OF THE CANDIDATE COMMIT (where `src/` is absent
# by construction — the implementer commits only on green), and mypy in the LIVE tree (where
# `src/` exists). That last check is the one whose absence let the users/001 baseline through:
# at re-baseline time it is finally decidable, so a handback cannot re-tag a conftest that the
# gate will still reject.
#
# A baseline move must not WEAKEN what gate.py later checks against it, so two integrity
# conditions guard it: the candidate commit touches tests/** only (anti-collusion, §4/D3 — the
# same check the first tagging makes), and no ac-marked test present at the old baseline has
# disappeared (otherwise moving the tag would silently legitimise a dropped test, which
# gate.py's `integrity.test-inventory` could no longer see).


@contextlib.contextmanager
def worktree_at(tree: Path, ref: str) -> Iterator[Path]:
    """A throwaway detached `git worktree` of `ref`; removed on exit. The live tree is untouched."""
    with tempfile.TemporaryDirectory(prefix="red_check_wt_") as tmp:
        path = Path(tmp) / "wt"
        proc = subprocess.run(
            ["git", "-C", str(tree), "worktree", "add", "--detach", "--quiet", str(path), ref],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RedCheckError(f"could not create a worktree at {ref}: {(proc.stderr or proc.stdout).strip()}")
        try:
            yield path
        finally:
            subprocess.run(
                ["git", "-C", str(tree), "worktree", "remove", "--force", str(path)],
                capture_output=True,
                text=True,
            )


def ac_inventory_at(tree: Path, ref: str) -> dict[str, list[str]]:
    """`nodeid -> [AC ids]` for every ac-marked test in tests/** at `ref`, by static AST scan.

    Static on purpose: at the old baseline the tests may not even collect (greenfield), so
    running pytest there would prove nothing. `git show` of each blob keeps it worktree-free."""
    listing = subprocess.run(
        ["git", "-C", str(tree), "ls-tree", "-r", "--name-only", ref, "tests/"],
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        raise RedCheckError(f"could not list tests/ at {ref}: {(listing.stderr or listing.stdout).strip()}")
    found: dict[str, list[str]] = {}
    for rel in (line.strip() for line in listing.stdout.splitlines()):
        if not rel.endswith(".py"):
            continue
        blob = subprocess.run(["git", "-C", str(tree), "show", f"{ref}:{rel}"], capture_output=True, text=True)
        if blob.returncode == 0:
            found.update(scan_ac_markers(blob.stdout, rel))
    return found


def mypy_tests(tree: Path) -> list[str] | None:
    """The gate's mypy findings that land in tests/**; None when `src/` is absent (undecidable).

    Runs the gate's exact `MYPY_CONFIG` over `src tests` — the invocation gate.py will make —
    then keeps only the tests/** lines, since src/** belongs to the implementer, not this screen."""
    if not (tree / "src").is_dir():
        return None
    gate = _gate()
    with tempfile.TemporaryDirectory(prefix="red_check_mypy_") as tmp:
        config = Path(tmp) / "mypy.ini"
        config.write_text(gate.MYPY_CONFIG + f"cache_dir = {Path(tmp) / 'cache'}\n", encoding="utf-8")
        env = os.environ.copy()
        for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "MYPYPATH"):  # E-05 class
            env.pop(var, None)
        proc = subprocess.run(
            [sys.executable, "-m", "mypy", "--config-file", str(config), "src", "tests"],
            cwd=str(tree),
            env=env,
            capture_output=True,
            text=True,
        )
    if proc.returncode == 0:
        return []
    return [line for line in (proc.stdout or proc.stderr).splitlines() if line.startswith("tests/")]


def rebaseline(tree: Path, change_id: str, ac_ids: list[str]) -> int:
    """Move `baseline/<ctx>-NNN` onto HEAD after a TESTS-HANDBACK. Return a process exit code."""
    tag = "baseline/" + change_id.replace("/", "-")
    resolved = subprocess.run(["git", "-C", str(tree), "rev-parse", "--verify", tag], capture_output=True, text=True)
    if resolved.returncode != 0:
        raise RedCheckError(f"no existing tag {tag} to move — a first baseline uses the normal red_check path")
    old_sha = resolved.stdout.strip()
    head = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    print(f"red_check --rebaseline: {change_id}")
    print(f"  {tag}: {old_sha[:8]} -> {head[:8]} (HEAD)")
    print()
    if old_sha == head:
        print("nothing to do — the tag already points at HEAD")
        return 0

    failures: list[str] = []

    # (a) the candidate commit must touch tests/** only — anti-collusion (§4/D3)
    offenders = non_tests_paths(baseline_commit_paths(tree))
    if offenders:
        failures.append(
            "the re-baseline commit writes outside tests/** (anti-collusion, §4/D3):\n"
            + "\n".join(f"    {p}" for p in offenders)
        )

    # (b) no ac-marked test may vanish across the move
    dropped = sorted(set(ac_inventory_at(tree, old_sha)) - set(ac_inventory_at(tree, head)))
    if dropped:
        failures.append(
            "ac-marked tests present at the old baseline are gone — a baseline move must not "
            "drop a test (it would blind gate.py's integrity.test-inventory):\n"
            + "\n".join(f"    {nodeid}" for nodeid in dropped)
        )

    # (c) redness + AC coverage + lint, judged where `src/` is ABSENT: a worktree of HEAD
    with worktree_at(tree, head) as wt:
        inventory = apply_greenfield_fallback(wt, run_tests(wt), project_package(wt))
        result = analyze(ac_ids, inventory)
        lint_failures = lint_tests(wt) if result.ok else None
    print(format_report(change_id, result, lint_failures))
    print()
    if not result.ok:
        failures.append("the corrected tests are no longer a valid RED baseline (see above)")
    if lint_failures:
        failures.append("tests/** is still lint-dirty (see above)")

    # (d) mypy over tests/**, judged where `src/` is PRESENT: the live tree
    mypy_failures = mypy_tests(tree)
    if mypy_failures is None:
        print("BASELINE MYPY: SKIPPED — no src/ in the live tree, so tests/** annotations are undecidable")
    elif mypy_failures:
        print("BASELINE MYPY: FAILED — tests/** must type-check against the existing src/ before")
        print("re-tagging, or the implementer inherits a gate it cannot turn green (notes/18):")
        for line in mypy_failures:
            print(f"    {line}")
        failures.append("tests/** does not type-check under the gate's mypy (see above)")
    else:
        print("BASELINE MYPY: clean (gate config, tests/** findings only)")

    if failures:
        print()
        print("RE-BASELINE: REFUSED")
        for item in failures:
            print(f"  - {item}")
        return 1

    tag_baseline(tree, change_id, force=True)
    print()
    print(f"RE-BASELINE: OK — moved {tag} -> {head[:8]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confirm the red baseline and tag it.")
    parser.add_argument("tree", nargs="?", default=".")
    parser.add_argument("--change", dest="change", default=None)
    parser.add_argument("--no-tag", action="store_true")
    parser.add_argument("--force-tag", action="store_true")
    parser.add_argument(
        "--rebaseline",
        action="store_true",
        help="move an existing baseline tag onto HEAD after a TESTS-HANDBACK (notes/18)",
    )
    args = parser.parse_args(argv)

    tree = Path(args.tree).resolve()
    try:
        change_id, change_dir = resolve_change(tree, args.change)
        criteria_path = change_dir / "criteria.md"
        if not criteria_path.is_file():
            raise RedCheckError(f"no criteria.md at {criteria_path}")
        ac_ids = parse_ac_ids(criteria_path.read_text(encoding="utf-8"))
        if not ac_ids:
            raise RedCheckError(f"no AC-n items found in {criteria_path}")
        preflight_toolchain(tree, rebaseline=args.rebaseline)
        if args.rebaseline:
            return rebaseline(tree, change_id, ac_ids)
        inventory = run_tests(tree)
        inventory = apply_greenfield_fallback(tree, inventory, project_package(tree))
    except RedCheckError as exc:
        print(f"red_check: ERROR — {exc}", file=sys.stderr)
        return 2

    result = analyze(ac_ids, inventory)

    # The lint screen runs only after redness is confirmed (a not-yet-red baseline already
    # fails); it is reported alongside the RED-CHECK verdict and blocks the tag on any finding.
    lint_failures = lint_tests(tree) if result.ok else None
    print(format_report(change_id, result, lint_failures))

    if not result.ok:
        return 1
    if lint_failures:
        return 1

    if not args.no_tag:
        try:
            offenders = non_tests_paths(baseline_commit_paths(tree))
        except RedCheckError as exc:
            print(f"red_check: ERROR — {exc}", file=sys.stderr)
            return 2
        if offenders:
            print(
                "red_check: FAILED — the red-tests commit wrote code — anti-collusion, §4/D3.\n"
                "the baseline commit must touch tests/** only; these paths do not:",
                file=sys.stderr,
            )
            for path in offenders:
                print(f"    {path}", file=sys.stderr)
            return 1
        try:
            tag = tag_baseline(tree, change_id, force=args.force_tag)
        except RedCheckError as exc:
            print(f"red_check: ERROR — {exc}", file=sys.stderr)
            return 2
        print(f"tagged baseline: {tag} -> HEAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
