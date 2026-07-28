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
  3. tests-only baseline — the commit about to be tagged touches `tests/**` only, and no commit
     between the change's own boundary and it wrote anything outside the pre-baseline lanes
     (`tests/**`, the declared deps files, `specs/**`). `criteria_guard`/`bash_guard` deny the
     test-author's writes to `src/**` on both the editor and the shell path, but a hook is
     porous by construction (it can be bypassed, and it does not run where it is not wired),
     and a *partial* src seed can leave the tests red and still slip code into the baseline.
     Catch the artifact, not the actor (S8): any offending path in the range → refuse to tag
     (anti-collusion, spec §4 / D3). See the pre-baseline-screen section note for the anchor,
     the lanes and what the screen honestly does not reach (T09i).
  4. lint screen — the baseline's `tests/**` is ruff-clean (ruff-check + ruff-format --check,
     gate.py's config imported not restated, C7). The implementer is hook-blocked from
     `tests/**` and ruff is per-file, so a lint defect the test-author left there could never
     be cleared by any `src/**` edit — it would deadlock the implementer. Screen it here, at
     baseline time, so the test-author fixes it at author time (S4). NOT mypy — a greenfield
     first change imports a not-yet-written package, which is the intended redness.

Two change classes have no red phase at all, and the script therefore reads the `Class:` line and
asks each one its own question (spec §3.1):

  * **`hardening`** — the tests get STRONGER while behaviour stays identical, lifted from a prior
    change's adversarial pass. Its tests are green on arrival, so redness cannot be its baseline
    property; `run_hardening_checks` asks a strictly stronger pair instead: GREEN-on-clean (every
    ac-marked test passes at the candidate commit) AND RED-on-mutation (with each mutation from
    change.md's `## Mutations` applied in a throwaway worktree, the AC ids that mutation names go
    RED).
  * **`invisible`** — a refactor / dependency upgrade / performance change: behaviour does not
    change, so its ACs describe behaviour that already holds and its tests also pass on arrival.
    `run_invisible_checks` asks for GREEN-AT-BASELINE (this change's ac-marked tests pass against
    the code as it stands) plus a CONSTRUCTIBLE before-surface, which is what makes the gate's
    `invisible.openapi-diff` — this class's declared proof — answerable at all.

Both then tag exactly as the red path does. See each section note below for what the substitution
buys, what it costs, and what it honestly cannot cover.

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
    red_check.py [--change <context>/NNN] [--no-tag] [--force-tag] [--rebaseline]
                 [--clear-escalate] [tree]

  tree          root of the change work tree (default: cwd); must be a git work tree to tag.
  --change      change id <context>/NNN; else a single specs/*/changes/*/ dir is auto-detected.
  --no-tag      run the checks only, do not create the baseline tag (used by callers/tests).
  --force-tag   move an existing baseline tag (legal only during the red phase, before code).
  --rebaseline  move an existing baseline tag onto HEAD after a TESTS-HANDBACK: verifies the
                corrected tests in a throwaway worktree (redness — or, for a `hardening` /
                `invisible` change, that class's question — where src/ is absent) AND in the live
                tree (mypy, where src/ is present), refusing any move that drops an ac-marked test
                or writes outside tests/**. See the section note and notes/18.
  --clear-escalate
                the human's sanctioned way to clear a §5.3 `ESCALATE`: move the baseline tag over
                the COMMITTED removal of the lock, and only over that. Without it, clearing a lock
                would leave gate.py's `integrity.escalate-intact` RED forever, since --rebaseline
                refuses a commit outside tests/**. See the section note (T06h).

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


def _criteria_lint():  # stdlib-only sibling import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import criteria_lint

    return criteria_lint


def _gate():  # stdlib-only sibling import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    return gate


def parse_ac_ids(criteria_text: str) -> list[str]:
    """Ordered, de-duplicated AC ids declared in criteria.md (HTML comments stripped)."""
    cl = _criteria_lint()
    lines = cl.strip_html_comments(criteria_text.splitlines())
    seen: list[str] = []
    for crit in cl.iter_criteria(lines):
        if crit.ac_id not in seen:
            seen.append(crit.ac_id)
    return seen


# ---------------------------------------------------------------------------------------
# Parsing change.md — the declared Class and, for `hardening`, the mutations
# ---------------------------------------------------------------------------------------
#
# Only two facts are read from change.md here: the `Class:` line (which baseline property
# applies) and the `## Mutations` section (the `hardening` class's proof). Both are read from
# the file the gate already freezes: `change.md`'s hash is part of gate.py's protected-tree
# integrity check at the baseline commit (E-12), so a mutation cannot be rewritten after the
# fact without the gate seeing it — the attestation comes for free.
#
# The `Class:` PARSE itself lives in gate.py and is called, never restated (C7): the gate reads
# the same line for the `invisible` class's before/after surface diff, and the two tools must
# never disagree about what a change declared. The class NAMES are spec §3.1 vocabulary.
#
# HTML comments are stripped first, everywhere: the templates carry their own instructions
# (including an EXAMPLE mutation diff) inside comments, and a change that keeps the comment
# must not read as a declaration. Same discipline as accept.classify_removal.
#
# ONE stripper for this file, and it is the shared `criteria_lint.strip_html_comments` (C7 —
# T10k made it public precisely because "a comment is not content" is a rule of the whole
# enforcement layer). This module carried a second, private grammar next to the call below — a
# `re.sub` that DELETED each comment span; the two disagree in two ways, and the shared one wins
# both:
#   * it BLANKS spans in place instead of deleting them, so a multi-line comment does not join
#     the text before it to the text after it onto one line — a `## Mutations <!-- … -->` whose
#     closer is followed by `### M-9 …` keeps the M-9 heading on its own line instead of being
#     swallowed into the heading's `[^\n]*$` tail (which silently renamed the mutation `M-1`);
#   * an UNTERMINATED `<!--` blanks the rest of the document rather than nothing at all, so a
#     malformed comment hides the mutation declarations instead of leaking them. For a screen
#     that REFUSES a baseline when a declaration is missing, that is the fail-closed direction —
#     and it is the grammar gate.py already applies to the same change.md (its legal-removal
#     allowance and its capability-provenance check both read it blanked).

HARDENING_CLASS = "hardening"  # spec §3.1: no red phase — proved by mutation instead
INVISIBLE_CLASS = "invisible"  # spec §3.1: no red phase — the tests pin behaviour that ALREADY holds

_AC_TOKEN = re.compile(r"\bAC-\d+\b")
_MUTATION_TOKEN = re.compile(r"\bM-\d+\b")
_FENCE = re.compile(r"(?ms)^```[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*?)^```[ \t]*$")
_DIFF_PATH = re.compile(r"(?m)^(?:---|\+\+\+)[ \t]+(?:[ab]/)?(\S+)")


def parse_change_class(change_md: str) -> str:
    """The change's declared `Class:` — gate.py's derivation, cited not restated (C7)."""
    return str(_gate().parse_change_class(change_md))


@dataclass(frozen=True)
class Mutation:
    """One mutation from change.md: a unified diff plus the AC ids it must kill."""

    mid: str
    ac_ids: tuple[str, ...]
    diff: str

    @property
    def paths(self) -> tuple[str, ...]:
        """The files the diff touches (`/dev/null` sides dropped), in first-seen order."""
        seen: list[str] = []
        for path in _DIFF_PATH.findall(self.diff):
            if path != "/dev/null" and path not in seen:
                seen.append(path)
        return tuple(seen)


def section_body(text: str, name: str) -> str | None:
    """The body of the `#+ <name>` section, or None. Terminates at a same-or-shallower heading.

    Matched at ANY heading depth and terminated at same-or-shallower, so a `### M-1 …`
    subheading inside `## Mutations` does not truncate its own parent section (the trap a naive
    `#+` terminator falls into) and a `### Mutations` still parses.
    """
    heading = re.compile(rf"(?m)^(#+)[ \t]*{re.escape(name)}\b[^\n]*$")
    match = heading.search(text)
    if not match:
        return None
    rest = text[match.end() :]
    nxt = re.search(rf"(?m)^#{{1,{len(match.group(1))}}}[ \t]", rest)
    return rest[: nxt.start()] if nxt else rest


def parse_mutations(change_md: str) -> list[Mutation]:
    """The `## Mutations` section's mutations, in file order.

    Grammar (deliberately prose-tolerant, like the rest of the spec format): one fenced block
    per mutation carrying the unified diff; the AC ids it must kill are the `AC-n` tokens in the
    text between the previous fence and this one (a `### M-2 — must kill AC-8, AC-9` heading, or
    a plain sentence). An `M-n` token there names the mutation; else it is numbered by position.
    """
    stripped = "\n".join(_criteria_lint().strip_html_comments(change_md.splitlines()))
    body = section_body(stripped, "Mutations")
    if body is None:
        return []
    mutations: list[Mutation] = []
    cursor = 0
    for index, match in enumerate(_FENCE.finditer(body), start=1):
        preamble = body[cursor : match.start()]
        cursor = match.end()
        ids = _MUTATION_TOKEN.findall(preamble)
        mutations.append(
            Mutation(
                mid=ids[-1] if ids else f"M-{index}",
                ac_ids=tuple(dict.fromkeys(_AC_TOKEN.findall(preamble))),
                diff=match.group(1),
            )
        )
    return mutations


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
# The implementer is hook-blocked from tests/** and ruff is per-file, so a lint defect the
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


def map_ac_to_tests(ac_ids: list[str], markers: dict[str, list[str]]) -> dict[str, list[str]]:
    """`AC-n -> [node-ids marked with it]`, every declared AC present (empty list = uncovered)."""
    ac_to_tests: dict[str, list[str]] = {ac: [] for ac in ac_ids}
    for nodeid, acs in sorted(markers.items()):
        for ac in acs:
            ac_to_tests.setdefault(ac, []).append(nodeid)
    return ac_to_tests


def analyze(ac_ids: list[str], inventory: dict) -> RedCheckResult:
    outcomes: dict[str, str] = inventory.get("outcomes", {})
    markers: dict[str, list[str]] = inventory.get("markers", {})

    ac_to_tests = map_ac_to_tests(ac_ids, markers)

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


# ---------------------------------------------------------------------------------------
# The pre-baseline screen — the whole range, not just the commit being tagged (T09i)
# ---------------------------------------------------------------------------------------
#
# The property this screen exists to buy is "nothing but the tests and the change's declared
# deps entered the tree before the baseline". Until T09i it inspected HEAD alone, so it proved
# something strictly weaker: "the commit being TAGGED is tests-only". Since T12 a change branch
# legitimately carries earlier commits — the `/adw:spec` commit that creates the change dir, then
# the test-author's `deps:` commit (/implement §1) — and nothing forced the shape of those. A
# test-author committing `conftest.py` (or `src/`) FIRST and the tests SECOND got the first commit
# unexamined, and the baseline tag then anchored a tree carrying unreviewed non-test content.
# `gate.py` cannot catch it afterwards either: `src/**` is deliberately NOT in its protected trees
# (it is the implementer's lane after the baseline, D4), so such a file is invisible to both
# scripts — the shape D3 exists to prevent.
#
# So the screen walks a RANGE, per commit (never a net tree diff: an intermediate commit that
# writes code must not be able to hide behind a later revert), with three lanes allowed before
# the baseline and NOTHING else — plus the strictest rule of all on the commit being tagged:
#
#   * `tests/**`                    — the test-author's own lane (D4);
#   * `pyproject.toml` / `uv.lock`  — the pre-baseline `deps:` commit (/implement §1, T12);
#   * `specs/**`                    — the `/adw:spec` session's lane: the change dir itself, a new
#                                     context's `overview.md`, a capability re-cut (S7). Allowed
#                                     without trust consequence, because the gate freezes
#                                     change.md's hash and criteria.md's legal flips from the
#                                     baseline ONWARD; before it, spec content is the human's.
#   * the tagged commit (HEAD)      — `tests/**` only, exactly as before T09i.
#
# THE ANCHOR — and why it is not the S9 base branch. The range needs a lower bound, and the
# obvious one is the fork point with the base branch. It is NOT used here: resolving a base needs
# `accept.derive_base`, which aborts when two branches are equally close, so every first baseline
# would start depending on a resolvable, unambiguous base branch — trading this latent fail-open
# for a live fail-closed, which is the author's trade to make and not this screen's (T09i).
#
# The anchor is the narrower thing that always resolves without one: the commit that CREATED this
# change's directory (`change.md` / `criteria.md`). In the sanctioned sequence that commit is the
# change branch's first commit — `/adw:spec` creates the branch and commits the change dir, and
# /implement step 0 refuses to start without it — so "since the change dir was born" and "since
# the branch was cut" are the same range, derived from the change instead of from the branch graph.
#
# The honest limit, printed rather than assumed away: a commit made on the branch BEFORE the
# change dir existed is outside this screen. Closing that needs the base branch, i.e. the trade
# above. Every commit the test-author makes is inside it, which is what D3 is about — and the
# report always names the anchor and every path it allowed, so the scope is visible. An anchor
# that cannot be resolved FAILS: HEAD is still screened (never less than the pre-T09i check), the
# refusal says the range is unknown, and no tag is created. A screen that silently narrows is
# worse than one that is known to be narrow.

TESTS_LANE = "tests/** — the test-author's lane"
DEPS_LANE = "the pre-baseline `deps:` commit — pyproject.toml / uv.lock"
SPECS_LANE = "specs/** — the /adw:spec session's lane"

PRE_BASELINE_DEPS = frozenset({"pyproject.toml", "uv.lock"})


def path_lane(rel: str) -> str | None:
    """The pre-baseline lane `rel` belongs to, or None when it belongs to none of them.

    One home for the `tests/**` grammar the tagged-commit rule and the range screen share (C7).
    """
    if rel == "tests" or rel.startswith("tests/"):
        return TESTS_LANE
    if rel in PRE_BASELINE_DEPS:
        return DEPS_LANE
    if rel == "specs" or rel.startswith("specs/"):
        return SPECS_LANE
    return None


def non_tests_paths(paths: list[str]) -> list[str]:
    """The baseline-commit paths that are NOT under tests/ (order preserved)."""
    return [p for p in paths if path_lane(p) != TESTS_LANE]


def _git_checked(tree: Path, args: list[str], what: str) -> str:
    """Run a git command whose answer a screen depends on; a bad rc is a loud refusal.

    The notes/19 direction rule, one level down: an unanswerable git call must never reach a
    check as an empty answer, because "nothing came back" would read as "nothing is wrong".
    """
    proc = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RedCheckError(f"{what}: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


@dataclass(frozen=True)
class RangeCommit:
    """One commit of a screened range: the paths it touches, or the fact that it is a merge."""

    sha: str
    paths: tuple[str, ...] = ()
    merge: bool = False


def commits_in_range(tree: Path, anchor: str, head: str = "HEAD") -> list[RangeCommit]:
    """Every commit in `anchor..head`, newest first, with the paths each one touches.

    Per commit, never as a net tree diff, so an intermediate commit that writes code cannot hide
    behind a later revert. A MERGE commit is reported as one and carries no paths on purpose:
    `git diff-tree -r <merge>` prints no names, which would read as "this commit touches
    nothing" and let an arbitrary tree through — the notes/19 fail-open class (T06h). Callers
    refuse a merge rather than judging it. Every git call is rc-checked (`_git_checked`): an
    unanswerable range is not an empty one.
    """
    revs = _git_checked(tree, ["rev-list", f"{anchor}..{head}"], f"could not list the commits in {anchor}..{head}")
    commits: list[RangeCommit] = []
    for sha in revs.split():
        parents = _git_checked(tree, ["rev-list", "--parents", "-n", "1", sha], f"could not read the parents of {sha}")
        if len(parents.split()) > 2:  # <sha> <parent> [<parent> ...]
            commits.append(RangeCommit(sha, (), merge=True))
            continue
        touched = _git_checked(
            tree,
            ["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha],
            f"could not inspect commit {sha}",
        )
        commits.append(RangeCommit(sha, tuple(rel.strip() for rel in touched.splitlines() if rel.strip())))
    return commits


@dataclass(frozen=True)
class Anchor:
    """The screened range's lower bound: the commit, how it was derived, or why it was not."""

    sha: str = ""
    how: str = ""
    error: str = ""


def change_dir_birth(tree: Path, change_dir: Path, head: str = "HEAD") -> str:
    """The oldest commit reachable from `head` that ADDED this change's change.md / criteria.md.

    Oldest, not newest: if the two files arrived in different commits the earlier one is the
    boundary, so the later spec commit is itself screened (as `specs/**`) instead of skipped.
    """
    rel = change_dir.resolve().relative_to(tree.resolve()).as_posix()
    out = _git_checked(
        tree,
        ["log", "--diff-filter=A", "--format=%H", head, "--", f"{rel}/change.md", f"{rel}/criteria.md"],
        f"could not look up the commit that created {rel}",
    )
    shas = [line.strip() for line in out.splitlines() if line.strip()]
    return shas[-1] if shas else ""


def pre_baseline_anchor(tree: Path, change_dir: Path, head: str) -> Anchor:
    """Resolve the range's lower bound, or say why it could not be (see the section note)."""
    rel = change_dir.resolve().relative_to(tree.resolve()).as_posix()
    birth = change_dir_birth(tree, change_dir, head)
    if not birth:
        return Anchor(
            error=(
                f"no commit in this branch's history adds {rel}/change.md or {rel}/criteria.md, so the commits "
                "that entered the tree before this baseline cannot be enumerated. Commit the change directory "
                "(/adw:spec does) and re-run — the screen is NOT degraded to inspecting HEAD alone, because a "
                "screen that silently narrows is worse than one that is known to be narrow (T09i)."
            )
        )
    if birth == head:
        return Anchor(
            sha=birth,
            error=(
                f"{rel} was created by the very commit being tagged, so there is no pre-baseline range to "
                "screen. The change directory belongs to an earlier /adw:spec commit (/implement §1) and the "
                "baseline commit must touch tests/** only."
            ),
        )
    return Anchor(sha=birth, how=f"since {birth[:8]}, the commit that created {rel}")


@dataclass
class ScreenedCommit:
    """One judged commit: which lane each allowed path fell in, and what was refused."""

    sha: str
    lanes: dict[str, list[str]] = field(default_factory=dict)
    offenders: list[str] = field(default_factory=list)
    merge: bool = False
    tagged: bool = False  # the baseline candidate itself: tests/** only

    @property
    def ok(self) -> bool:
        return not self.merge and not self.offenders


@dataclass
class BaselineScreen:
    anchor: Anchor
    commits: list[ScreenedCommit] = field(default_factory=list)

    @property
    def offenders(self) -> list[str]:
        return [rel for commit in self.commits for rel in commit.offenders]

    @property
    def ok(self) -> bool:
        return not self.anchor.error and all(commit.ok for commit in self.commits)


def judge_commit(commit: RangeCommit, *, tagged: bool) -> ScreenedCommit:
    """Sort one commit's paths into the pre-baseline lanes; the tagged commit gets `tests/**` only."""
    screened = ScreenedCommit(sha=commit.sha, merge=commit.merge, tagged=tagged)
    for rel in commit.paths:
        lane = path_lane(rel)
        if lane is None or (tagged and lane != TESTS_LANE):
            screened.offenders.append(rel)
        else:
            screened.lanes.setdefault(lane, []).append(rel)
    return screened


def screen_pre_baseline(tree: Path, change_dir: Path, *, anchor: Anchor | None = None) -> BaselineScreen:
    """Screen every commit from the range's anchor up to HEAD (see the section note).

    `anchor` overrides the derivation for a baseline MOVE, where the range's lower bound is the
    tag being left behind — a narrower, always-resolvable question ("what entered since the tag
    I am moving from?") that composes with the screen the first tagging already made.
    """
    head = _git_checked(tree, ["rev-parse", "HEAD"], "could not resolve HEAD").strip()
    resolved = anchor if anchor is not None else pre_baseline_anchor(tree, change_dir, head)
    commits = commits_in_range(tree, resolved.sha, head) if resolved.sha and not resolved.error else []
    if all(commit.sha != head for commit in commits):
        # HEAD is screened unconditionally. An unresolvable or degenerate anchor must never mean
        # "nothing to screen": that would fail open in the one place the pre-T09i check did hold.
        commits.insert(0, RangeCommit(head, tuple(baseline_commit_paths(tree))))
    return BaselineScreen(resolved, [judge_commit(c, tagged=c.sha == head) for c in commits])


def format_screen_report(screen: BaselineScreen) -> str:
    lines: list[str] = []
    if screen.anchor.error:
        lines.append("BASELINE SCREEN: FAILED — the pre-baseline range could not be anchored:")
        lines.extend(f"    {ln}" for ln in screen.anchor.error.splitlines())
        lines.append("HEAD is screened on its own below, so this is never less than a HEAD-only check.")
    else:
        lines.append(f"BASELINE SCREEN: {len(screen.commits)} commit(s) {screen.anchor.how}, oldest first:")
    for commit in reversed(screen.commits):  # the order they entered the tree
        label = f"  {commit.sha[:8]}{' (tagged)' if commit.tagged else '         '}"
        if commit.merge:
            lines.append(f"{label}  REFUSED: a merge commit — its tree cannot be judged path by path")
            continue
        for lane, paths in commit.lanes.items():
            lines.append(f"{label}  {len(paths)} path(s) allowed — {lane}")
            lines.extend(f"{' ' * len(label)}      {rel}" for rel in paths)
        for rel in commit.offenders:
            lines.append(f"{label}  REFUSED: {rel}")
    if screen.ok:
        lines.append("BASELINE SCREEN: clean — only tests/**, the declared deps and specs/** entered pre-baseline")
    else:
        lines.append(
            "BASELINE SCREEN: REFUSED — a commit before the baseline writes outside the pre-baseline lanes "
            "(anti-collusion, §4/D3).\nThe tagged commit may touch tests/** only; the commits before it may "
            "also touch pyproject.toml / uv.lock (the `deps:` commit) and specs/**. Nothing else: code that "
            "enters the tree before the baseline is code nobody reviewed and neither script can see afterwards "
            "(src/** is not a gate-protected tree — it is the implementer's lane AFTER the baseline)."
        )
    return "\n".join(lines)


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


# ---------------------------------------------------------------------------------------
# The `hardening` class — a baseline proved by MUTATION, because it has no red phase (T09g)
# ---------------------------------------------------------------------------------------
#
# The cycle's baseline property is redness: a test that fails before the code exists proves it
# asserts the behaviour, and that the behaviour was absent. One legitimate change shape cannot
# have it — a change that only makes the TESTS stronger while behaviour stays identical (the
# adversarial pass of an earlier change found a mutation its suite did not kill). Those tests
# pass on arrival, so red_check would refuse them, and the adversarial pass — the one step whose
# job is measuring test strength — would produce findings the workflow cannot act on.
#
# `Class: hardening` is that lane. Redness is not dropped, it is REPLACED by a strictly stronger
# pair, and nothing about D3/D4 changes (the mutation is spec content, authored by the human at
# /adw:spec from the earlier verdict's adversarial table; it is applied only in a throwaway
# worktree; nobody writes `src/**`):
#
#   * GREEN-on-clean — every ac-marked test of THIS change's ACs passes at the candidate commit.
#     ("this change's ACs", not every marked test in the tree: a hardening change is brownfield
#     by nature, and the greenness of tests belonging to older changes is the gate's business.)
#   * RED-on-mutation — for each mutation declared in change.md's `## Mutations`, applying that
#     patch in a throwaway worktree of the candidate commit makes at least one ac-marked test of
#     every AC id the mutation names go RED. A mutation nothing kills is exactly the finding an
#     adversarial pass reports, so a hardening baseline that cannot kill its own mutation is
#     refused: it would ship the weakness it claims to close.
#
# Why this is stronger than redness: "this test fails when the code is wrong in THIS specific
# way" is a sharper claim than "this test fails when the code is absent". What it costs is the
# declaration — hence the refusals that are pure declaration hygiene, all checked before a single
# test runs: a hardening change with no mutations at all, an AC no mutation names (it would have
# no proof of strength at all — neither redness nor a kill), a mutation naming an AC that is not
# in criteria.md, a mutation patching anything but `src/**` (a "mutation" that deletes an
# assertion makes any test fail and proves nothing), and a patch that does not apply.


@dataclass
class GreenResult:
    """GREEN-on-clean: the AC coverage + pass state of this change's ac-marked tests."""

    ac_ids: list[str]
    ac_to_tests: dict[str, list[str]]
    missing_acs: list[str] = field(default_factory=list)
    passed_tests: list[str] = field(default_factory=list)
    not_green: list[tuple[str, str]] = field(default_factory=list)  # (node-id, outcome)

    @property
    def ok(self) -> bool:
        return not self.missing_acs and not self.not_green


def analyze_green(ac_ids: list[str], inventory: dict) -> GreenResult:
    """Coverage as in `analyze`, but the expected outcome of a marked test is PASSED."""
    outcomes: dict[str, str] = inventory.get("outcomes", {})
    ac_to_tests = map_ac_to_tests(ac_ids, inventory.get("markers", {}))
    result = GreenResult(ac_ids=ac_ids, ac_to_tests=ac_to_tests)
    result.missing_acs = [ac for ac in ac_ids if not ac_to_tests.get(ac)]
    for nodeid in sorted({n for ac in ac_ids for n in ac_to_tests.get(ac, [])}):
        outcome = outcomes.get(nodeid, "missing")
        if outcome == "passed":
            result.passed_tests.append(nodeid)
        else:  # failed / error / skipped / xfail / uncollected — not a green witness
            result.not_green.append((nodeid, outcome))
    return result


@dataclass
class MutationOutcome:
    """What one mutation did to the suite: which ACs it killed, and which survived it."""

    mutation: Mutation
    error: str | None = None  # the patch could not be applied, or the mutated tree not tested
    killed: dict[str, list[str]] = field(default_factory=dict)  # AC -> the node-ids that went RED
    survived: list[str] = field(default_factory=list)  # AC ids no marked test caught it for

    @property
    def ok(self) -> bool:
        return not self.error and not self.survived


@dataclass
class HardeningResult:
    ac_ids: list[str]
    mutations: list[Mutation]
    declaration_defects: list[str] = field(default_factory=list)
    clean: GreenResult | None = None  # None when the declaration was already refused
    lint_failures: list[str] | None = None
    outcomes: list[MutationOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.declaration_defects
            and self.clean is not None
            and self.clean.ok
            and not self.lint_failures
            and bool(self.outcomes)
            and all(outcome.ok for outcome in self.outcomes)
        )


def mutation_declaration_defects(ac_ids: list[str], mutations: list[Mutation]) -> list[str]:
    """Everything wrong with the DECLARATION, decided without running a test."""
    defects: list[str] = []
    if not mutations:
        return [
            "a `hardening` change must declare at least one mutation in change.md's `## Mutations` "
            "section — the mutation IS this class's baseline proof, and without one the change has "
            "neither a red phase nor a kill to show for its new tests (spec §3.1)"
        ]
    for mutation in mutations:
        if "@@" not in mutation.diff:
            defects.append(
                f"{mutation.mid}: not a unified diff (no `@@` hunk header) — red_check applies it with git apply"
            )
        if not mutation.ac_ids:
            defects.append(f"{mutation.mid}: names no AC id — a mutation must state which criteria it must kill")
        for ac in mutation.ac_ids:
            if ac not in ac_ids:
                defects.append(f"{mutation.mid}: names {ac}, which is not in criteria.md")
        if not mutation.paths:
            defects.append(f"{mutation.mid}: no file paths in the diff — name them as `--- a/src/… / +++ b/src/…`")
        for path in mutation.paths:
            # `..` is checked, not assumed away: `src/../tests/test_x.py` starts with `src/` and
            # lands in the test tree, which is precisely the one thing this rule exists to stop.
            if not path.startswith("src/") or ".." in Path(path).parts:
                defects.append(
                    f"{mutation.mid}: patches {path} — a mutation may only patch `src/**`; mutating a "
                    "test (or the spec) makes the suite fail for a reason that proves nothing"
                )
    covered = {ac for mutation in mutations for ac in mutation.ac_ids}
    defects += [
        f"{ac} is named by no mutation — every AC of a hardening change needs one (it is the only "
        "proof of strength this class has)"
        for ac in ac_ids
        if ac not in covered
    ]
    return defects


def apply_mutation(worktree: Path, diff: str) -> str | None:
    """`git apply` the diff inside `worktree`; None on success, else git's own complaint."""
    patch = diff if diff.endswith("\n") else diff + "\n"
    proc = subprocess.run(
        ["git", "-C", str(worktree), "apply", "--whitespace=nowarn", "-"],
        input=patch,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return None
    return (proc.stderr or proc.stdout).strip() or f"git apply exited {proc.returncode}"


def judge_mutation(tree: Path, mutation: Mutation, ref: str) -> MutationOutcome:
    """Run the suite with `mutation` applied in a throwaway worktree of `ref`.

    An AC counts as KILLED only by a test that actually ran and went failed/errored. A skipped
    or uncollected test is not a kill: a mutation that merely breaks an import makes everything
    disappear, which says nothing about the strength of any assertion.
    """
    with worktree_at(tree, ref) as wt:
        error = apply_mutation(wt, mutation.diff)
        if error:
            return MutationOutcome(mutation, error=f"the patch does not apply at {ref[:8]}: {error}")
        try:
            inventory = run_tests(wt)
        except RedCheckError as exc:
            return MutationOutcome(mutation, error=f"the mutated tree could not be tested: {exc}")
    outcomes: dict[str, str] = inventory.get("outcomes", {})
    ac_to_tests = map_ac_to_tests(list(mutation.ac_ids), inventory.get("markers", {}))
    result = MutationOutcome(mutation)
    for ac in mutation.ac_ids:
        red = [nodeid for nodeid in ac_to_tests.get(ac, []) if outcomes.get(nodeid) in RED_OUTCOMES]
        if red:
            result.killed[ac] = red
        else:
            result.survived.append(ac)
    return result


def run_hardening_checks(
    tree: Path, ac_ids: list[str], mutations: list[Mutation], ref: str = "HEAD"
) -> HardeningResult:
    """The `hardening` baseline: declaration hygiene, then GREEN-on-clean, then RED-on-mutation.

    Every test run happens in a throwaway worktree of `ref` — the live work tree is never
    patched, and no mutation can leak into another's world or into the repo.
    """
    result = HardeningResult(ac_ids=ac_ids, mutations=mutations)
    result.declaration_defects = mutation_declaration_defects(ac_ids, mutations)
    if result.declaration_defects:
        return result  # nothing to run: the proof is not even declared

    with worktree_at(tree, ref) as wt:
        result.clean = analyze_green(ac_ids, run_tests(wt))
        result.lint_failures = lint_tests(wt) if result.clean.ok else None
    if not result.clean.ok or result.lint_failures:
        return result  # a suite that is not green on clean code cannot prove anything by mutation

    result.outcomes = [judge_mutation(tree, mutation, ref) for mutation in mutations]
    return result


def format_hardening_report(change_id: str, result: HardeningResult) -> str:
    lines = [f"red_check (Class: {HARDENING_CLASS}): {change_id}", ""]
    lines.append(f"criteria: {len(result.ac_ids)} AC ({', '.join(result.ac_ids) or 'none'})")
    by_ac = {ac: [m.mid for m in result.mutations if ac in m.ac_ids] for ac in result.ac_ids}
    for ac in result.ac_ids:
        mutations = ", ".join(by_ac[ac]) or "none"
        if result.clean is None:  # the declaration was refused — no test ever ran, so say so
            lines.append(f"  [ -- ] {ac}: not run, mutations: {mutations}")
            continue
        tests = result.clean.ac_to_tests.get(ac) or []
        mark = "OK  " if tests and by_ac[ac] else "MISS"
        lines.append(f"  [{mark}] {ac}: {len(tests)} marked test(s), mutations: {mutations}")
    if result.declaration_defects:
        lines.append("MUTATION DECLARATION (change.md `## Mutations`) — FAILED:")
        lines.extend(f"    {defect}" for defect in result.declaration_defects)
    if result.clean is not None:
        if result.clean.missing_acs:
            lines.append(f"MISSING MARKER: {', '.join(result.clean.missing_acs)} — every AC needs an ac-marked test")
        if result.clean.not_green:
            lines.append("NOT GREEN ON CLEAN (a hardening change changes no behaviour, so its tests must PASS")
            lines.append("against the unmutated code — a failure here is a real defect, not a red baseline):")
            lines.extend(f"    {nodeid} [{outcome}]" for nodeid, outcome in result.clean.not_green)
        else:
            lines.append(
                f"GREEN ON CLEAN: {len(result.clean.passed_tests)} ac-marked test(s) pass at the candidate commit"
            )
    for outcome in result.outcomes:
        named = ", ".join(outcome.mutation.ac_ids)
        if outcome.error:
            lines.append(f"  [ERROR   ] {outcome.mutation.mid} ({named}): {outcome.error}")
            continue
        for ac, nodeids in outcome.killed.items():
            lines.append(f"  [KILLED  ] {outcome.mutation.mid} {ac}: {', '.join(nodeids)}")
        for ac in outcome.survived:
            lines.append(
                f"  [SURVIVED] {outcome.mutation.mid} {ac}: no ac-marked test went RED under this mutation — "
                "the criterion's tests do not catch the wrong code this patch describes"
            )
    lines.append("")
    lines.append(f"HARDENING-CHECK: {'MUTATION-CONFIRMED' if result.ok else 'FAILED'}")
    if result.lint_failures is not None:
        if result.lint_failures:
            lines.append("")
            lines.append("BASELINE LINT: FAILED — tests/** must be lint-clean before tagging (T09f):")
            for block in result.lint_failures:
                lines.extend(f"    {ln}" for ln in block.splitlines())
        else:
            lines.append("BASELINE LINT: clean (ruff-check + ruff-format over tests/)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------
# The `invisible` class — a baseline whose property is GREEN-AT-BASELINE, not redness (T20)
# ---------------------------------------------------------------------------------------
#
# `invisible` (refactor / dependency upgrade / performance — spec §3.1) is the second class with
# no red phase, and for the opposite reason to `hardening`: its ACs describe behaviour that
# ALREADY holds, because the whole claim is that behaviour does not change. A test written for
# such an AC passes the moment it is written, so redness cannot be its baseline property either —
# and before T20 nothing here read the `Class:` line at all, so an invisible change ran into
# GREEN-BEFORE-IMPLEMENTATION, got no tag, and could not enter /implement. The class existed in
# canon and was unreachable in the tools.
#
# WHAT REPLACES REDNESS (the anti-collusion question, and "nothing" is not an answer). Three
# legs, none of which the implementer can touch:
#
#   1. GREEN-AT-BASELINE — every ac-marked test of THIS change's ACs passes at the candidate
#      commit, i.e. against the code as it stands BEFORE the refactor. That is the sharpest thing
#      an invisible change's own tests can prove: they describe existing behaviour rather than the
#      refactor's, so they cannot be tests OF the new code (the collusion this class could invite).
#   2. THE INHERITED SUITE — the baseline test inventory is frozen here and enforced by the gate
#      (E-05: every baseline test must still be collected and pass; a deleted, deselected, skipped
#      or xfailed one is RED), and the implementer cannot write `tests/**` at all (D4). So the
#      whole existing suite, not just this change's ACs, has to stay green over the refactor.
#   3. THE SURFACE DIFF — `gate.py`'s `invisible.openapi-diff` compares the constructed app's
#      OpenAPI operation set against the baseline commit's and FAILs on any difference. This is
#      the leg that catches what a green suite cannot: an endpoint ADDED or REMOVED, which breaks
#      no existing test.
#
# Legs 2 and 3 are exactly §3.1's declared proof ("полный gate зелёный + diff OpenAPI-схемы
# до/после пуст"); leg 1 is what this script can add at baseline time.
#
# Which is also why the before-surface is screened HERE, before the tag: the gate's diff needs a
# constructible app at the BASELINE commit, and the baseline tree is frozen the moment it is
# tagged. If it cannot be constructed, no `src/**` edit could ever clear that RED — the implementer
# would burn its whole ceiling on something outside its lane (T09f's deadlock, third variant). So
# an unreadable before-surface refuses the baseline, with the reason, at author time.
#
# The honest coverage limit, stated rather than skipped: a tree with no HTTP surface on either
# side (a domain-only refactor, a library) has nothing to diff — that is reported out loud and the
# change rests on legs 1 and 2. And a BREAKING dependency upgrade whose baseline source cannot
# import under the new package versions makes the before-surface UNDETERMINED, so this class
# cannot prove it; that is a refusal with a named cause, never a silent pass.


@dataclass
class InvisibleResult:
    ac_ids: list[str]
    clean: GreenResult | None = None  # GREEN-AT-BASELINE
    lint_failures: list[str] | None = None
    surface: object | None = None  # gate.Surface of the candidate commit — the diff's BEFORE side

    @property
    def surface_ok(self) -> bool:
        return self.surface is not None and not getattr(self.surface, "undetermined", "")

    @property
    def ok(self) -> bool:
        return (
            self.clean is not None
            and self.clean.ok
            and not self.lint_failures
            and self.surface is not None
            and self.surface_ok
        )


def run_invisible_checks(tree: Path, ac_ids: list[str], ref: str = "HEAD") -> InvisibleResult:
    """The `invisible` baseline: GREEN-AT-BASELINE, the lint screen, then a readable before-surface.

    Everything is judged in a throwaway worktree of `ref` (the candidate commit) — the live work
    tree is never touched, and the surface read is of the tree the tag will actually pin.
    """
    result = InvisibleResult(ac_ids=ac_ids)
    with worktree_at(tree, ref) as wt:
        result.clean = analyze_green(ac_ids, run_tests(wt))
        if not result.clean.ok:
            return result  # tests that do not pass on the unchanged code cannot claim "unchanged"
        result.lint_failures = lint_tests(wt)
        if result.lint_failures:
            return result
        result.surface = _gate().route_inventory(wt)
    return result


def format_invisible_report(change_id: str, result: InvisibleResult) -> str:
    lines = [f"red_check (Class: {INVISIBLE_CLASS}): {change_id}", ""]
    lines.append(f"criteria: {len(result.ac_ids)} AC ({', '.join(result.ac_ids) or 'none'})")
    for ac in result.ac_ids:
        tests = (result.clean.ac_to_tests.get(ac) or []) if result.clean else []
        mark = "OK  " if tests else "MISS"
        lines.append(f"  [{mark}] {ac}: {len(tests)} marked test(s)")
    if result.clean is not None:
        if result.clean.missing_acs:
            lines.append(f"MISSING MARKER: {', '.join(result.clean.missing_acs)} — every AC needs an ac-marked test")
        if result.clean.not_green:
            lines.append("NOT GREEN AT BASELINE (an invisible change alters no behaviour, so the tests that pin")
            lines.append("that behaviour must already PASS against the code as it stands — a failure here is a")
            lines.append("real defect or a behavioural AC in the wrong class, never a red baseline):")
            lines.extend(f"    {nodeid} [{outcome}]" for nodeid, outcome in result.clean.not_green)
        else:
            lines.append(
                f"GREEN AT BASELINE: {len(result.clean.passed_tests)} ac-marked test(s) pass at the candidate commit"
            )
    surface = result.surface
    if surface is not None:
        if getattr(surface, "undetermined", ""):
            lines.append("BEFORE-SURFACE: UNDETERMINED — the app does not construct at the candidate commit, so")
            lines.append("gate.py could never compute this class's before/after OpenAPI diff (§3.1); the RED it")
            lines.append("would report is outside the implementer's lane, so the baseline is refused here:")
            lines.extend(f"    {ln}" for ln in str(surface.undetermined).splitlines())
        elif getattr(surface, "absent", ""):
            lines.append(f"BEFORE-SURFACE: none to compare — {surface.absent};")
            lines.append("the proof rests on the tests passing before AND after (gate: E-05 test inventory)")
        else:
            operations = list(surface.operations)
            lines.append(f"BEFORE-SURFACE: {len(operations)} OpenAPI operation(s) at the candidate commit")
            lines.extend(f"    {op}" for op in operations)
    lines.append("")
    lines.append(f"INVISIBLE-CHECK: {'BASELINE-CONFIRMED' if result.ok else 'FAILED'}")
    if result.lint_failures is not None:
        if result.lint_failures:
            lines.append("")
            lines.append("BASELINE LINT: FAILED — tests/** must be lint-clean before tagging (T09f):")
            for block in result.lint_failures:
                lines.extend(f"    {ln}" for ln in block.splitlines())
        else:
            lines.append("BASELINE LINT: clean (ruff-check + ruff-format over tests/)")
    return "\n".join(lines)


def rebaseline(
    tree: Path,
    change_id: str,
    change_dir: Path,
    ac_ids: list[str],
    *,
    change_class: str = "behavioral",  # the register's default (gate.DEFAULT_CHANGE_CLASS); main always passes it
    hardening_mutations: list[Mutation] | None = None,
) -> int:
    """Move `baseline/<ctx>-NNN` onto HEAD after a TESTS-HANDBACK. Return a process exit code.

    `change_class` picks the baseline property step (c) asks for — redness, the `hardening` pair
    (GREEN-on-clean + RED-on-mutation, using `hardening_mutations`), or the `invisible` triple —
    the same route the first baseline takes, so a handback needs no hand `git tag -f` in any class.
    """
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

    # (a) the candidate commit must touch tests/** only, and nothing outside the pre-baseline
    #     lanes may have entered since the tag being moved — anti-collusion (§4/D3). The anchor
    #     here is the OLD baseline, not the change dir's birth: the range before that tag was
    #     screened when it was created, so the two questions compose to full coverage, and the
    #     narrower one is the only one a move can be refused for (T09i).
    screen = screen_pre_baseline(tree, change_dir, anchor=Anchor(sha=old_sha, how=f"since {tag} ({old_sha[:8]})"))
    print(format_screen_report(screen))
    print()
    if not screen.ok:
        failures.append("the re-baseline range writes outside the pre-baseline lanes (see the screen report above)")

    # (b) no ac-marked test may vanish across the move
    dropped = sorted(set(ac_inventory_at(tree, old_sha)) - set(ac_inventory_at(tree, head)))
    if dropped:
        failures.append(
            "ac-marked tests present at the old baseline are gone — a baseline move must not "
            "drop a test (it would blind gate.py's integrity.test-inventory):\n"
            + "\n".join(f"    {nodeid}" for nodeid in dropped)
        )

    # (c) the class's baseline property + AC coverage + lint, judged in a worktree of HEAD:
    #     redness needs `src/` ABSENT there; the hardening pair and the invisible triple need the
    #     committed `src/` and nothing else — either way the live tree (with the implementer's
    #     uncommitted src/) is the wrong world to judge in, and all of them are judged in one.
    if change_class == HARDENING_CLASS:
        hardening = run_hardening_checks(tree, ac_ids, hardening_mutations or [], ref=head)
        print(format_hardening_report(change_id, hardening))
        print()
        lint_failures = hardening.lint_failures
        if not hardening.ok:
            failures.append("the corrected tests are not a valid mutation-proved baseline (see above)")
    elif change_class == INVISIBLE_CLASS:
        invisible = run_invisible_checks(tree, ac_ids, ref=head)
        print(format_invisible_report(change_id, invisible))
        print()
        lint_failures = invisible.lint_failures
        if not invisible.ok:
            failures.append("the corrected tests are not a valid green-at-baseline invisible baseline (see above)")
    else:
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


# ---------------------------------------------------------------------------------------
# Clear an ESCALATE — move the baseline over a committed ESCALATE removal (§5.3/E-08, T06h)
# ---------------------------------------------------------------------------------------
#
# The iteration-ceiling `ESCALATE` is a human-only lock, and since T06h the hook COMMITS it, so
# `gate.py`'s `integrity.escalate-intact` sees its removal and goes RED. That is the point — but
# it also means clearing a lock would leave the gate permanently RED, because the only way to
# re-anchor an integrity check is to move the baseline tag, and `--rebaseline` refuses any commit
# outside `tests/**`. Hence this second, strictly NARROWER baseline move, and hence its home here:
# `red_check` already owns baseline-tag movement, and one home for that is C7.
#
# Three guards, all required:
#   (i)   an ESCALATE was committed on this branch since the baseline and is now gone — this flag
#         does nothing else, and refuses to be a general-purpose tag mover;
#   (ii)  EVERY commit in `<old baseline>..HEAD` touches nothing but `specs/*/changes/*/ESCALATE`.
#         This is what makes the move strictly narrower than `--rebaseline`: the old and the new
#         baseline trees then differ ONLY by the lock, so no criteria flip, `change.md` edit or
#         dropped test can be laundered through it. It requires the lock to be cleared BEFORE
#         anything else is committed — which in a real escalation holds by construction, since the
#         implementer commits `src/**` only on green (T09e) and an escalated change never reached
#         green, so its `src/` is still uncommitted. The error message says so.
#   (iii) no ac-marked test disappeared across the move — the same guard `--rebaseline` makes
#         (a baseline move must never blind `gate.py`'s `integrity.test-inventory`).
#
# What this does NOT do (deliberately, S8): it cannot tell a human from an agent. An agent at its
# ceiling can delete the file, commit, and run this flag itself. The deliverable is that the act is
# RECORDED — a commit plus a tag move, both in git — not that it is prevented.


def is_escalate_path(rel: str) -> bool:
    """True for a change directory's ESCALATE — the only path this step may see moving."""
    return rel.endswith("/ESCALATE") and "/changes/" in rel


def non_escalate_commit_paths(tree: Path, anchor: str) -> list[str]:
    """Guard (ii): what the commits in `anchor..HEAD` touch besides a change dir's ESCALATE.

    Per commit, not as a net tree diff, so an intermediate commit that writes code cannot hide
    behind a later revert. A MERGE commit is refused outright: `diff-tree` prints no names for
    one, which would read as "touches nothing" and let an arbitrary tree in — the notes/19
    fail-open class. The walk itself is `commits_in_range`, shared with the pre-baseline screen
    (C7: one range walk, one merge refusal, one set of rc guards); only the predicate differs."""
    violations: list[str] = []
    for commit in commits_in_range(tree, anchor):
        if commit.merge:
            violations.append(f"{commit.sha[:8]}: a merge commit — its tree cannot be judged path by path")
            continue
        violations.extend(f"{commit.sha[:8]}: {rel}" for rel in commit.paths if not is_escalate_path(rel))
    return violations


def clear_escalate(tree: Path, change_id: str) -> int:
    """Move `baseline/<ctx>-NNN` over a committed ESCALATE removal. Return a process exit code."""
    gate = _gate()
    tag = "baseline/" + change_id.replace("/", "-")
    resolved = subprocess.run(["git", "-C", str(tree), "rev-parse", "--verify", tag], capture_output=True, text=True)
    if resolved.returncode != 0:
        raise RedCheckError(
            f"no existing tag {tag} to move — an ESCALATE can only be cleared on a change that has a red baseline"
        )
    old_sha = resolved.stdout.strip()
    head = _git_checked(tree, ["rev-parse", "HEAD"], "could not resolve HEAD").strip()

    print(f"red_check --clear-escalate: {change_id}")
    print(f"  {tag}: {old_sha[:8]} -> {head[:8]} (HEAD)")
    print()

    since = gate.escalate_state(tree, old_sha)
    if since.error:  # "could not ask" must never read as "nothing to clear"
        raise RedCheckError(since.error)
    at_head = gate.escalate_state(tree, "HEAD")
    if at_head.error:
        raise RedCheckError(at_head.error)

    failures: list[str] = []

    # (i) an ESCALATE entered this branch's history since the baseline, and is now gone for good
    if not since.known:
        failures.append(
            f"no ESCALATE was committed on this branch since {tag} ({old_sha[:8]}) — --clear-escalate moves the "
            "baseline ONLY over the removal of a committed lock (§5.3/E-08), never as a general tag move"
        )
    else:
        standing = [rel for rel in since.known if rel not in since.missing]
        if standing:
            failures.append(
                "the ESCALATE is still in the work tree — delete it and commit THAT deletion, then re-run:\n"
                + "\n".join(f"    {rel}" for rel in standing)
            )
        if at_head.known:
            failures.append(
                "the removal is not COMMITTED — these locks are still tracked at HEAD, so moving the tag would "
                "carry them into the new baseline:\n" + "\n".join(f"    {rel}" for rel in at_head.known)
            )

    # (ii) the range carries nothing but the ESCALATE — what keeps this narrower than --rebaseline
    offenders = non_escalate_commit_paths(tree, old_sha)
    if offenders:
        failures.append(
            "commits since the baseline touch more than the ESCALATE, so the move would re-anchor other "
            "content too (a criteria flip, a change.md edit, a dropped test):\n"
            + "\n".join(f"    {item}" for item in offenders)
            + "\n    Clear the lock FIRST, before committing anything else. In a real escalation that holds by"
            "\n    construction: the implementer commits src/** only on green (T09e), and an escalated change"
            "\n    never reached green — so its src/ is still uncommitted."
        )

    # (iii) no ac-marked test may vanish across the move (the --rebaseline guard, reused)
    dropped = sorted(set(ac_inventory_at(tree, old_sha)) - set(ac_inventory_at(tree, head)))
    if dropped:
        failures.append(
            "ac-marked tests present at the old baseline are gone — a baseline move must not drop a test "
            "(it would blind gate.py's integrity.test-inventory):\n" + "\n".join(f"    {nodeid}" for nodeid in dropped)
        )

    if failures:
        print("CLEAR-ESCALATE: REFUSED")
        for item in failures:
            print(f"  - {item}")
        return 1

    tag_baseline(tree, change_id, force=True)
    print(f"cleared: {', '.join(since.missing)}")
    print(f"CLEAR-ESCALATE: OK — moved {tag} -> {head[:8]}")
    return 0


def finish_tagging(tree: Path, change_id: str, change_dir: Path, *, no_tag: bool, force: bool) -> int:
    """The tail both baseline paths share: the pre-baseline screen, then the tag.

    Class-independent on purpose — whatever proved the baseline (redness, mutation or
    green-at-baseline), the commit being tagged must touch `tests/**` only and nothing outside
    the pre-baseline lanes may have entered the tree before it (anti-collusion, §4/D3)."""
    if no_tag:
        return 0
    screen = screen_pre_baseline(tree, change_dir)
    print(format_screen_report(screen))
    if not screen.ok:
        if screen.offenders:
            print(
                "red_check: FAILED — the tree carries pre-baseline content outside the test-author's lane "
                "— anti-collusion, §4/D3.\nthese paths were refused (see the BASELINE SCREEN report above):",
                file=sys.stderr,
            )
            for path in screen.offenders:
                print(f"    {path}", file=sys.stderr)
        else:
            print(
                "red_check: FAILED — the pre-baseline range could not be screened, so nothing is tagged "
                "(see the BASELINE SCREEN report above).",
                file=sys.stderr,
            )
        return 1
    tag = tag_baseline(tree, change_id, force=force)
    print(f"tagged baseline: {tag} -> HEAD")
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
    parser.add_argument(
        "--clear-escalate",
        dest="clear_escalate",
        action="store_true",
        help="move an existing baseline tag over a COMMITTED ESCALATE removal — the human's "
        "sanctioned way to clear the §5.3 lock without leaving gate.py permanently RED (T06h)",
    )
    args = parser.parse_args(argv)
    if args.rebaseline and args.clear_escalate:
        parser.error("--rebaseline and --clear-escalate are different baseline moves; run one at a time")

    tree = Path(args.tree).resolve()
    try:
        change_id, change_dir = resolve_change(tree, args.change)
        if args.clear_escalate:
            # This step runs no tests and invokes no tool, so neither the criteria parse nor the
            # toolchain preflight applies: it only moves a tag over a committed ESCALATE removal.
            return clear_escalate(tree, change_id)
        criteria_path = change_dir / "criteria.md"
        if not criteria_path.is_file():
            raise RedCheckError(f"no criteria.md at {criteria_path}")
        ac_ids = parse_ac_ids(criteria_path.read_text(encoding="utf-8"))
        if not ac_ids:
            raise RedCheckError(f"no AC-n items found in {criteria_path}")

        # Which baseline property applies is the change's CLASS, read from change.md — the same
        # file gate.py freezes at the baseline, so the declaration is attested (E-12).
        change_md_path = change_dir / "change.md"
        change_md = change_md_path.read_text(encoding="utf-8") if change_md_path.is_file() else ""
        change_class = parse_change_class(change_md)

        preflight_toolchain(tree, rebaseline=args.rebaseline)
        if args.rebaseline:
            return rebaseline(
                tree,
                change_id,
                change_dir,
                ac_ids,
                change_class=change_class,
                hardening_mutations=parse_mutations(change_md) if change_class == HARDENING_CLASS else None,
            )
        if change_class == HARDENING_CLASS:
            # No red phase: GREEN-on-clean + RED-on-mutation, judged in throwaway worktrees of
            # HEAD (the candidate commit), then the same tests-only screen and tag as the red path.
            result = run_hardening_checks(tree, ac_ids, parse_mutations(change_md))
            print(format_hardening_report(change_id, result))
            if not result.ok:
                return 1
            return finish_tagging(tree, change_id, change_dir, no_tag=args.no_tag, force=args.force_tag)
        if change_class == INVISIBLE_CLASS:
            # No red phase either, for the opposite reason: the behaviour these tests pin already
            # holds. GREEN-AT-BASELINE + a readable before-surface, then the same screen and tag.
            invisible = run_invisible_checks(tree, ac_ids)
            print(format_invisible_report(change_id, invisible))
            if not invisible.ok:
                return 1
            return finish_tagging(tree, change_id, change_dir, no_tag=args.no_tag, force=args.force_tag)

        inventory = run_tests(tree)
        inventory = apply_greenfield_fallback(tree, inventory, project_package(tree))

        red = analyze(ac_ids, inventory)

        # The lint screen runs only after redness is confirmed (a not-yet-red baseline already
        # fails); it is reported alongside the RED-CHECK verdict and blocks the tag on any finding.
        lint_failures = lint_tests(tree) if red.ok else None
        print(format_report(change_id, red, lint_failures))

        if not red.ok or lint_failures:
            return 1
        return finish_tagging(tree, change_id, change_dir, no_tag=args.no_tag, force=args.force_tag)
    except RedCheckError as exc:
        print(f"red_check: ERROR — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
