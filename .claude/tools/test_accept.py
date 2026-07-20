"""Test suite for accept.py (workflow v3, T05).

Two layers:
  - pure-function units (merge-fidelity, freshness, invariant building, orphan sweep) run
    without git or the gate — fast, and they carry the deny-case coverage the Verification
    section names for merge-fidelity;
  - integration fixtures build a two-branch git repo (a green `main`, a `change/demo-001`
    branch carrying the red baseline + implementation + flipped criteria + verdict) and run
    the fixture's OWN copy of accept.py, so the gate's self-hash / protected-tree checks
    judge the fixture repo's HEAD, not this repo's. accept.py runs the real gate.py in-process.

Every accept subprocess sets GATE_DOCKER=0 so the Docker tier deterministically SKIPs.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
TOOL_FILES = ("gate.py", "criteria_lint.py", "accept.py")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


accept = _load("accept_under_test", "accept.py")
criteria_lint = _load("criteria_lint_for_accept", "criteria_lint.py")


# ---------------------------------------------------------------------------------------
# fixture tree content
# ---------------------------------------------------------------------------------------

PYPROJECT = """\
[project]
name = "fixture-app"
version = "0.1.0"
requires-python = ">=3.12"
"""

GITIGNORE = ".gate/\n__pycache__/\n.pytest_cache/\n"

SRC_INIT = '"""Fixture app package."""\n'

SRC_CORE = '''\
"""Fixture domain module."""


def add(a: int, b: int) -> int:
    return a + b
'''

SRC_MAIN = '''\
"""Fixture app factory (construct-smoke target)."""


class App:
    """Minimal stand-in exposing the openapi() surface the smoke calls."""

    def openapi(self) -> dict[str, str]:
        return {"openapi": "3.1.0"}


def create_app() -> App:
    return App()
'''

TESTS_CORE = '''\
"""Fixture tests."""

import pytest

from app.core import add
from app.main import create_app


@pytest.mark.ac("AC-1")
def test_add() -> None:
    assert add(1, 2) == 3


@pytest.mark.ac("AC-2")
def test_create_app() -> None:
    assert create_app().openapi()


def test_add_zero() -> None:
    assert add(0, 0) == 0
'''

OVERVIEW_MD = """\
# demo — overview

## Purpose
The demo bounded context — arithmetic and app construction.

## Capabilities
- `core.md` — arithmetic core

## Cross-cutting invariants and domain terms

## Integrations
"""

CAPABILITY_MD = """\
# demo / core

## Behaviour
The core arithmetic operations of the demo context.

## Invariants
"""

CHANGE_MD = """\
# demo/001 — provide the arithmetic core

Class: behavioral
Affects: core.md

## Task
Provide `add` and the app factory.

## Acceptance criteria
- AC-1: `app.core.add` returns the sum `3` for input `1, 2`
- AC-2: `create_app()` returns a non-empty `openapi` schema

## Verification
Run the gate; AC-1 and AC-2 are backed by ac-marked unit tests.
"""

CRITERIA_OPEN = """\
# Criteria — demo/001-thing

- [ ] AC-1: `app.core.add` returns the sum `3` for input `1, 2`
- [ ] AC-2: `create_app()` returns a non-empty `openapi` schema
"""

CRITERIA_FLIPPED = CRITERIA_OPEN.replace("- [ ]", "- [x]")

VERDICT_MD = """\
# Verdict — demo/001-thing

Gate: GREEN · SHA: {sha} · junit: .gate/last-run.xml

## Per-criterion verdicts

- AC-1: PASS
  - state: [x]
  - proof: ac-test: tests/test_core.py::test_add
  - sha: {sha}
- AC-2: PASS
  - state: [x]
  - proof: ac-test: tests/test_core.py::test_create_app
  - sha: {sha}

## Out-of-scope diff
None

## Adversarial review
N/A (S)
"""

CHANGE_DIR = "specs/demo/changes/001-thing"


class FixtureRepo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=acc", "-c", "user.email=acc@test", *args],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"git {args} failed: {proc.stdout}{proc.stderr}"
        return proc.stdout

    def accept(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GATE_DOCKER"] = "0"
        return subprocess.run(
            [sys.executable, str(self.root / ".claude/tools/accept.py"), *args, "--tree", str(self.root)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.root,
        )

    def show(self, ref: str, rel: str) -> str:
        proc = subprocess.run(["git", "-C", str(self.root), "show", f"{ref}:{rel}"], capture_output=True, text=True)
        return proc.stdout if proc.returncode == 0 else ""


def make_repo(root: Path) -> FixtureRepo:
    root.mkdir(parents=True, exist_ok=True)
    repo = FixtureRepo(root)
    repo.git("-c", "init.defaultBranch=main", "init", "-q")
    # M0 — green main: tools + the existing capability spec, no change dir, no app yet.
    repo.write("pyproject.toml", PYPROJECT)
    repo.write(".gitignore", GITIGNORE)
    repo.write("specs/demo/overview.md", OVERVIEW_MD)
    repo.write("specs/demo/core.md", CAPABILITY_MD)
    for name in TOOL_FILES:
        repo.write(f".claude/tools/{name}", (TOOLS_DIR / name).read_text(encoding="utf-8"))
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "main baseline")

    repo.git("checkout", "-q", "-b", "change/demo-001")
    # commit A — red baseline: change dir + src + tests.
    repo.write(f"{CHANGE_DIR}/change.md", CHANGE_MD)
    repo.write(f"{CHANGE_DIR}/criteria.md", CRITERIA_OPEN)
    repo.write("src/app/__init__.py", SRC_INIT)
    repo.write("src/app/core.py", SRC_CORE)
    repo.write("src/app/main.py", SRC_MAIN)
    repo.write("tests/test_core.py", TESTS_CORE)
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "red tests baseline")
    repo.git("tag", "baseline/demo-001")
    # commit B — evaluator flips the criteria.
    repo.write(f"{CHANGE_DIR}/criteria.md", CRITERIA_FLIPPED)
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "flip criteria to [x]")
    sha_b = repo.git("rev-parse", "HEAD").strip()
    # commit C — evaluator's verdict, pinned to sha_b.
    repo.write(f"{CHANGE_DIR}/verdict.md", VERDICT_MD.format(sha=sha_b))
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "evaluator verdict")
    return repo


@pytest.fixture()
def repo(tmp_path: Path) -> FixtureRepo:
    return make_repo(tmp_path / "app")


# ---------------------------------------------------------------------------------------
# pure-function units
# ---------------------------------------------------------------------------------------


def _crit(state: str, ac_id: str, text: str):
    return criteria_lint.Criterion(1, state, ac_id, text)


def test_merge_fidelity_pass_and_deny() -> None:
    merged = "- POST /meetings returns 201 with the meeting id (verified by: tests/t.py::test_x)"
    acs = [("AC-1", "POST /meetings returns 201 with the meeting id")]
    assert accept.merge_fidelity_violations(acs, merged) == []
    # an AC whose behaviour never landed in the merge is a deny (L-11).
    absent = [("AC-2", "monthly quota overflow returns 402 quota_exceeded")]
    violations = accept.merge_fidelity_violations(absent, merged)
    assert violations and "AC-2" in violations[0]


def test_build_invariants_carry_provenance() -> None:
    criteria = [_crit("x", "AC-1", "add returns the sum"), _crit("m", "AC-2", "throttle can only be seen live")]
    lines = accept.build_invariants(criteria, {"AC-1": "tests/test_core.py::test_add"})
    assert lines == [
        "- add returns the sum (verified by: tests/test_core.py::test_add)",
        "- throttle can only be seen live (MANUAL)",
    ]


def test_freshness_state_transitions() -> None:
    assert accept.freshness_state("abc", "abc", set(), set())[0] == accept.PASS
    # stale + the diff intersects the change's files -> recompute demanded (L-04).
    stale = accept.freshness_state("old", "head", {"src/app/core.py"}, {"src/app/core.py"})
    assert stale[0] == accept.FAIL and "L-04" in stale[1]
    # stale but only the verdict moved -> still fresh.
    assert accept.freshness_state("old", "head", set(), {"src/app/core.py"})[0] == accept.PASS
    # stale, non-empty diff, no intersection -> a non-blocking flag.
    assert accept.freshness_state("old", "head", {"README.md"}, {"src/app/core.py"})[0] == accept.FLAG
    assert accept.freshness_state(None, "head", set(), set())[0] == accept.FAIL


def test_orphan_violations() -> None:
    assert accept.orphan_violations(["gone"], "clean spec", "clean src") == []
    hit = accept.orphan_violations(["ghost"], "the ghost lingers", "")
    assert hit and "ghost" in hit[0]


def test_instantiate_and_append() -> None:
    text = accept.instantiate_capability("demo", "search.md")
    assert text.startswith("# demo / search")
    merged = accept.append_invariants("# x\n\n## Invariants\n", ["- inv (MANUAL)"])
    assert merged.endswith("- inv (MANUAL)\n")


# ---------------------------------------------------------------------------------------
# integration — check mode / execute (run the gate)
# ---------------------------------------------------------------------------------------


def test_check_mode_green_prints_diff_without_touching_main(repo: FixtureRepo) -> None:
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verdict: ACCEPTABLE" in proc.stdout
    assert "PREPARED MERGE DIFF" in proc.stdout
    assert "verified by: tests/test_core.py::test_add" in proc.stdout
    # main is untouched: still no invariants merged, still on the change branch.
    assert "verified by" not in repo.show("main", "specs/demo/core.md")
    assert repo.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "change/demo-001"


def test_execute_merges_criteria_and_tags(repo: FixtureRepo) -> None:
    proc = repo.accept("demo/001", "--base", "main", "--execute")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "EXECUTED" in proc.stdout
    core = repo.show("main", "specs/demo/core.md")
    assert "verified by: tests/test_core.py::test_add" in core
    assert "verified by: tests/test_core.py::test_create_app" in core
    # the change dir is gone from main, the tag exists, the app merged in.
    assert repo.show("main", f"{CHANGE_DIR}/criteria.md") == ""
    assert "change/demo-001" in repo.git("tag", "--list", "change/demo-001")
    assert "def add" in repo.show("main", "src/app/core.py")
    assert "drift-check on main" in proc.stdout


# ---------------------------------------------------------------------------------------
# integration — deny cases
# ---------------------------------------------------------------------------------------


def test_escalate_file_denies(repo: FixtureRepo) -> None:
    repo.write(f"{CHANGE_DIR}/ESCALATE", "3-pass ceiling reached\n")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] escalate" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_open_criteria_denies(repo: FixtureRepo) -> None:
    repo.write(f"{CHANGE_DIR}/criteria.md", CRITERIA_OPEN)  # revert one flip to [ ]
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] criteria.complete" in proc.stdout
    assert "AC-1" in proc.stdout


def test_missing_companion_denies(repo: FixtureRepo) -> None:
    change = (repo.root / f"{CHANGE_DIR}/change.md").read_text(encoding="utf-8")
    repo.write(f"{CHANGE_DIR}/change.md", change.replace("Affects: core.md", "Affects: core.md\nCompanion: other/001"))
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] companion" in proc.stdout
    assert "other/001" in proc.stdout


def test_stale_verdict_with_intersecting_diff_denies(repo: FixtureRepo) -> None:
    # a new commit touches a change file AFTER the verdict SHA -> recompute demanded (L-04).
    repo.write("src/app/core.py", SRC_CORE + "\n\n# late edit after the verdict\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "post-verdict src edit")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] verdict.freshness" in proc.stdout
    assert "src/app/core.py" in proc.stdout


def test_unbacked_flip_denies(repo: FixtureRepo) -> None:
    # a criterion flipped [x] with no ac-marked test backing it -> gate.py goes RED on
    # criteria.junit-backing, which accept surfaces as a deny.
    flipped = CRITERIA_FLIPPED + "- [x] AC-3: the `missing_code` field is returned in the body\n"
    repo.write(f"{CHANGE_DIR}/criteria.md", flipped)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] criteria.junit-backing" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_help_lists_flags() -> None:
    proc = subprocess.run([sys.executable, str(TOOLS_DIR / "accept.py"), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for flag in ("--execute", "--base", "--tree"):
        assert flag in proc.stdout
