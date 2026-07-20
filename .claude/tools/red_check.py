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

Usage:
    red_check.py [--change <context>/NNN] [--no-tag] [--force-tag] [tree]

  tree         root of the change work tree (default: cwd); must be a git work tree to tag.
  --change     change id <context>/NNN; else a single specs/*/changes/*/ dir is auto-detected.
  --no-tag     run the checks only, do not create the baseline tag (used by callers/tests).
  --force-tag  move an existing baseline tag (legal only during the red phase, before code).

Exit code 0 only when coverage + redness both hold (and the tag step, if any, succeeded).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
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


def pytest_configure(config):
    config.addinivalue_line("markers", "ac(criterion_id): links a test to an acceptance criterion (AC-n)")


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
            json.dump({"collected": _collected, "outcomes": _outcomes, "markers": _markers}, fh, indent=2)
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


def format_report(change_id: str, result: RedCheckResult) -> str:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confirm the red baseline and tag it.")
    parser.add_argument("tree", nargs="?", default=".")
    parser.add_argument("--change", dest="change", default=None)
    parser.add_argument("--no-tag", action="store_true")
    parser.add_argument("--force-tag", action="store_true")
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
        inventory = run_tests(tree)
    except RedCheckError as exc:
        print(f"red_check: ERROR — {exc}", file=sys.stderr)
        return 2

    result = analyze(ac_ids, inventory)
    print(format_report(change_id, result))

    if not result.ok:
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
