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
# Verbatim snapshots of real change documents used as regression fixtures (T10e).
FIXTURES_DIR = TOOLS_DIR / "fixtures"


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

# A second, pre-existing capability file for the multi-target `Affects` cases.
EXTRA_CAPABILITY_MD = """\
# demo / extra

## Behaviour
The app-construction surface of the demo context.

## Invariants
"""

OVERVIEW_MULTI = OVERVIEW_MD.replace(
    "- `core.md` — arithmetic core",
    "- `core.md` — arithmetic core\n- `extra.md` — app construction",
)

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

# A multi-target variant: `Affects` names two pre-existing capability files, so invariant
# distribution needs a placement map from /accept-change (spec §5.4, T10b).
MULTI_CHANGE_MD = CHANGE_MD.replace("Affects: core.md", "Affects: core.md extra.md")

# An M-depth variant: a filled Interface sketch is the structural signal of M/L depth, which
# makes the adversarial pass mandatory (spec §6 step 4).
M_CHANGE_MD = CHANGE_MD.replace(
    "## Acceptance criteria",
    "## Interface sketch\n`app.core.add(a, b)`; `create_app()` factory.\n\n## Acceptance criteria",
)

# The same verdict, but with the adversarial section actually filled by a run.
VERDICT_ADVERSARIAL = VERDICT_MD.replace(
    "## Adversarial review\nN/A (S)",
    "## Adversarial review\nRan the assert-strength recipes over the test diff — asserts pin\nexact values; no tautologies found.",
)

# The exact platform/001 pre-fix shape (T10c): the Gate-line SHA wrapped in backticks and the
# adversarial section under the `## Adversarial pass` heading the /implement prose misled the
# evaluator into. accept.py must read both without a cosmetic deny.
VERDICT_BACKTICKED_SHA_PASS_HEADING = VERDICT_ADVERSARIAL.replace("· SHA: {sha} ·", "· SHA: `{sha}` ·").replace(
    "## Adversarial review", "## Adversarial pass"
)

# A verdict whose Gate-line pins no hex at all (only the placeholder text) — the per-criterion
# `- sha:` lines are lowercase, so the capital `SHA:` parse finds no hex and freshness must FAIL.
VERDICT_NO_SHA = VERDICT_MD.replace("· SHA: {sha} ·", "· SHA: (pending) ·")

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


def make_repo(
    root: Path,
    *,
    change_md: str = CHANGE_MD,
    verdict_md: str = VERDICT_MD,
    overview_md: str = OVERVIEW_MD,
    extra_caps: dict[str, str] | None = None,
) -> FixtureRepo:
    root.mkdir(parents=True, exist_ok=True)
    repo = FixtureRepo(root)
    repo.git("-c", "init.defaultBranch=main", "init", "-q")
    # M0 — green main: tools + the existing capability spec, no change dir, no app yet.
    repo.write("pyproject.toml", PYPROJECT)
    repo.write(".gitignore", GITIGNORE)
    repo.write("specs/demo/overview.md", overview_md)
    repo.write("specs/demo/core.md", CAPABILITY_MD)
    for name, content in (extra_caps or {}).items():
        repo.write(f"specs/demo/{name}", content)
    for name in TOOL_FILES:
        repo.write(f".claude/tools/{name}", (TOOLS_DIR / name).read_text(encoding="utf-8"))
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "main baseline")

    repo.git("checkout", "-q", "-b", "change/demo-001")
    # commit A — red baseline: change dir + src + tests.
    repo.write(f"{CHANGE_DIR}/change.md", change_md)
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
    repo.write(f"{CHANGE_DIR}/verdict.md", verdict_md.format(sha=sha_b))
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


def test_build_invariant_lines_are_keyed_by_ac_id() -> None:
    criteria = [_crit("x", "AC-1", "add returns the sum"), _crit("m", "AC-2", "throttle seen live")]
    pairs = accept.build_invariant_lines(criteria, {"AC-1": "tests/t.py::test_add"})
    assert pairs == [
        ("AC-1", "- add returns the sum (verified by: tests/t.py::test_add)"),
        ("AC-2", "- throttle seen live (MANUAL)"),
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


def test_rebase_freshness_state_transitions() -> None:
    # the pin was rebased away AND its commit object is gone -> the attested tree is unknowable,
    # so FAIL rather than a silent pass (T10d fixes the pre-T10d empty-diff false accept).
    gone = accept.rebase_freshness_state("dead", "head", False, set(), set())
    assert gone[0] == accept.FAIL and "pruned" in gone[1]
    # rebased away but resolvable, and a change file differs -> attested tree changed -> FAIL.
    changed = accept.rebase_freshness_state("old", "head", True, {"src/app/core.py"}, {"src/app/core.py"})
    assert changed[0] == accept.FAIL and "src/app/core.py" in changed[1]
    # rebased away, resolvable, only base / .claude drift (no change file differs) -> tree
    # identity of the attested state preserved -> PASS (the re-pin cascade is unnecessary).
    ok = accept.rebase_freshness_state("old", "head", True, {"README.md"}, {"src/app/core.py"})
    assert ok[0] == accept.PASS and "tree-identity" in ok[1]


def test_parse_verdict_sha_tolerates_markdown_around_the_hex() -> None:
    # the canonical bare line.
    assert accept.parse_verdict_sha("Gate: GREEN · SHA: 246f84a · junit: x") == "246f84a"
    # the platform/001 pre-fix shape: backticks around the hex must not break the parse (T10c).
    assert accept.parse_verdict_sha("· SHA: `246f84abcdef` ·") == "246f84abcdef"
    # bold / emphasis punctuation around the token is tolerated too.
    assert accept.parse_verdict_sha("SHA: **deadbeef1234**") == "deadbeef1234"
    # no hex anywhere -> None (freshness then FAILs — no false accept).
    assert accept.parse_verdict_sha("Gate: GREEN · SHA: (pending) · junit: x") is None
    assert accept.parse_verdict_sha("no sha line here at all") is None


def test_orphan_violations() -> None:
    assert accept.orphan_violations(["gone"], "clean spec", "clean src") == []
    hit = accept.orphan_violations(["ghost"], "the ghost lingers", "")
    assert hit and "ghost" in hit[0]


# ---------------------------------------------------------------------------------------
# removal-flavour classification (T10e) — structural, never grepped out of prose
# ---------------------------------------------------------------------------------------

USERS_002_CHANGE_MD = (FIXTURES_DIR / "users-002-change-spec.md").read_text(encoding="utf-8")

REMOVAL_CHANGE_MD = """\
# demo/007 — drop the legacy export

Class: behavioral, removal flavour
Affects: export.md

## Interface sketch

- `ExportHandler.handle(cmd) -> bool` — `True` when a row was removed, `False` when no row
  held that id; the removed id is echoed in the log line.

## Removed

- `LegacyExportHandler` — the whole handler goes, with its route.
- `tests/test_export.py::test_legacy_export` — obsolete, deleted by this change's test-author.

## Acceptance criteria

- AC-1: `GET /export/legacy` returns 404.
"""


def test_classify_removal_does_not_fire_on_users_002() -> None:
    """Regression (T10e): the verbatim users/002 change.md — `Class: behavioral`, no `Removed`
    heading, but two prose spots saying "removed" — must NOT read as a removal-flavour change.
    The pre-T10e classifier fired on the wrapped sketch line and then harvested 19 generic
    identifiers (`id`, `save`, `None`, …), denying acceptance of a change that removes nothing."""
    flavour = accept.classify_removal(USERS_002_CHANGE_MD)
    assert flavour.fires is False
    assert flavour.by_class is False
    assert flavour.sections == ()
    assert flavour.terms == ()
    # the fixture is the real document, not a sanitised one: both triggering spots are present.
    assert "removed id, or `None` when no user held it." in USERS_002_CHANGE_MD
    assert "`True` when a row was removed" in USERS_002_CHANGE_MD


def test_classify_removal_fires_on_a_real_heading_and_captures_only_its_terms() -> None:
    flavour = accept.classify_removal(REMOVAL_CHANGE_MD)
    assert flavour.fires is True
    assert flavour.by_class is True  # the `Class:` line declares the flavour
    # the capture is anchored to the heading, so the sketch's own "removed" prose and its
    # backticked `True` / `False` / `ExportHandler` never enter the term list.
    assert set(flavour.terms) == {"LegacyExportHandler", "test_legacy_export"}


def test_classify_removal_ignores_prose_without_a_heading() -> None:
    prose = (
        "# demo/008 — patch a user\n\nClass: behavioral\n\n## Task\n"
        "  removed id, or `None` when no user held it.\n"
        "removed the `Widget` from the response? no — this line is prose, not a heading.\n"
    )
    flavour = accept.classify_removal(prose)
    assert flavour.fires is False and flavour.terms == ()


def test_classify_removal_ignores_the_template_comment_vocabulary() -> None:
    """The change.md template's own HTML comment on the `Class:` line explains the removal
    flavour ("behavioral, removal flavour: list the removed behaviour explicitly"). A change
    that kept the comment must not classify as a removal."""
    template = (TOOLS_DIR.parent / "templates" / "change.md").read_text(encoding="utf-8")
    assert "removal flavour" in template  # the trap is really in the template
    assert accept.classify_removal(template).fires is False


def _sweep_context(tmp_path: Path, change_md: str, *, spec_text: str = "", src_text: str = "") -> object:
    (tmp_path / "specs" / "demo" / "changes" / "007-x").mkdir(parents=True, exist_ok=True)
    (tmp_path / "specs" / "demo" / "export.md").write_text(spec_text, encoding="utf-8")
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "core.py").write_text(src_text, encoding="utf-8")
    return accept.AcceptContext(
        tree=tmp_path,
        change_id="demo/007",
        ctx="demo",
        nnn="007",
        change_dir=tmp_path / "specs" / "demo" / "changes" / "007-x",
        base="main",
        branch="change/demo-007",
        head="0" * 40,
        change_md=change_md,
        criteria_text="",
        verdict_text=None,
    )


def test_orphan_sweep_skips_a_non_removal_change(tmp_path: Path) -> None:
    result = accept._orphan_sweep(_sweep_context(tmp_path, USERS_002_CHANGE_MD))
    assert result.status == accept.SKIP
    assert "not a removal-flavour change" in result.detail


def test_orphan_sweep_skips_when_class_declares_removal_but_no_heading_lists_it(tmp_path: Path) -> None:
    change_md = "# demo/007 — drop it\n\nClass: behavioral, removal flavour\n\n## Task\n\nDrop `LegacyExportHandler`.\n"
    result = accept._orphan_sweep(_sweep_context(tmp_path, change_md, src_text="class LegacyExportHandler: ...\n"))
    # no heading -> nothing structural to sweep; the sweep never falls back to free prose.
    assert result.status == accept.SKIP
    assert "no `Removed` heading" in result.detail


def test_orphan_sweep_still_fails_on_a_symbol_that_survived(tmp_path: Path) -> None:
    ctx = _sweep_context(
        tmp_path,
        REMOVAL_CHANGE_MD,
        spec_text="- the legacy export is served by `LegacyExportHandler` (verified by: x)\n",
        src_text="class LegacyExportHandler:\n    pass\n",
    )
    result = accept._orphan_sweep(ctx)
    assert result.status == accept.FAIL
    assert "LegacyExportHandler" in result.detail
    assert "spec text" in result.detail and "src symbols" in result.detail


def test_orphan_sweep_passes_when_the_removed_symbols_are_gone(tmp_path: Path) -> None:
    ctx = _sweep_context(tmp_path, REMOVAL_CHANGE_MD, spec_text="- export is gone\n", src_text="x = 1\n")
    result = accept._orphan_sweep(ctx)
    assert result.status == accept.PASS
    assert "2 removed symbol(s)" in result.detail


def test_adversarial_required_by_depth_and_novelty() -> None:
    s_change = "## Task\ndo a thing\n\n## Acceptance criteria\n- AC-1: x returns y\n"
    # S depth on an existing capability -> opt-in, not required.
    assert accept.adversarial_required(s_change, creates_new_capability=False)[0] is False
    # first change of a capability -> required even at S depth (spec §6 step 4).
    assert accept.adversarial_required(s_change, creates_new_capability=True)[0] is True
    # a filled Interface sketch marks M/L depth -> required.
    m_change = "## Context\nbecause.\n\n" + s_change + "\n## Interface sketch\n`Foo(dep: Bar)`\n"
    assert accept.adversarial_required(m_change, creates_new_capability=False)[0] is True


def test_adversarial_section_filled() -> None:
    assert accept.adversarial_section_filled(None) is False
    # the template comment / an empty section is not a run.
    assert accept.adversarial_section_filled("## Adversarial review\n<!-- slot -->\n") is False
    # a bare N/A marker legitimises only the not-required case, never a required one.
    assert accept.adversarial_section_filled("## Adversarial review\nN/A (S)\n") is False
    assert accept.adversarial_section_filled("## Adversarial review\nRan recipes; asserts strong.\n") is True
    # the `## Adversarial pass` heading the /implement prose misled authors into is accepted too (T10c).
    assert accept.adversarial_section_filled("## Adversarial pass\nRan recipes; asserts strong.\n") is True
    assert accept.adversarial_section_filled("## Adversarial pass\n<!-- slot -->\n") is False


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
# integration — multi-target placement map (T10b)
# ---------------------------------------------------------------------------------------


def _multi_repo(root: Path) -> FixtureRepo:
    return make_repo(
        root,
        change_md=MULTI_CHANGE_MD,
        overview_md=OVERVIEW_MULTI,
        extra_caps={"extra.md": EXTRA_CAPABILITY_MD},
    )


def test_multi_target_check_mode_flags_need_for_placement_map(tmp_path: Path) -> None:
    # check mode (the command's step 1): multi-target Affects surfaces a merge.placement FLAG
    # — not a deny — so the command knows to propose a map before --execute.
    repo = _multi_repo(tmp_path / "app")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[FLAG] merge.placement" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout
    # nothing placed without an approved map.
    assert "verified by" not in repo.show("main", "specs/demo/core.md")
    assert "verified by" not in repo.show("main", "specs/demo/extra.md")


def test_multi_target_execute_without_map_is_refused(tmp_path: Path) -> None:
    repo = _multi_repo(tmp_path / "app")
    proc = repo.accept("demo/001", "--base", "main", "--execute")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "refusing to --execute" in proc.stdout
    assert "placement map" in proc.stdout
    # main untouched — no dumping into the first Affects file.
    assert "verified by" not in repo.show("main", "specs/demo/core.md")
    assert "verified by" not in repo.show("main", "specs/demo/extra.md")


def test_multi_target_valid_map_distributes_each_invariant(tmp_path: Path) -> None:
    repo = _multi_repo(tmp_path / "app")
    proc = repo.accept(
        "demo/001",
        "--base",
        "main",
        "--execute",
        "--placement",
        '{"AC-1": "core.md", "AC-2": "extra.md"}',
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] merge.placement" in proc.stdout
    assert "EXECUTED" in proc.stdout
    core = repo.show("main", "specs/demo/core.md")
    extra = repo.show("main", "specs/demo/extra.md")
    # each invariant landed in exactly its mapped file.
    assert "verified by: tests/test_core.py::test_add" in core
    assert "test_add" not in extra
    assert "verified by: tests/test_core.py::test_create_app" in extra
    assert "test_create_app" not in core


def test_multi_target_map_naming_file_outside_affects_is_refused(tmp_path: Path) -> None:
    repo = _multi_repo(tmp_path / "app")
    proc = repo.accept(
        "demo/001",
        "--base",
        "main",
        "--execute",
        "--placement",
        '{"AC-1": "core.md", "AC-2": "ghost.md"}',
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] merge.placement" in proc.stdout
    assert "ghost.md" in proc.stdout
    assert "verdict: DENIED" in proc.stdout
    # nothing written.
    assert "verified by" not in repo.show("main", "specs/demo/core.md")


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


def _rebase_onto_updated_main(repo: FixtureRepo) -> None:
    """Land a commit on main (a base/tooling fix — NOT one of the change's files) and rebase the
    change branch onto it, so every SHA on the branch is rewritten and the verdict's pinned SHA is
    orphaned. Re-tag the baseline to the rebased red-tests commit as the real workflow does — but
    DO NOT re-pin the verdict SHA: that re-pin is exactly what T10d makes unnecessary."""
    repo.git("checkout", "-q", "main")
    repo.write("README.md", "canon fix landed on main mid-flight\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "main canon fix")
    repo.git("checkout", "-q", "change/demo-001")
    repo.git("rebase", "-q", "main")
    # branch shape is baseline -> flip -> verdict, so the red-tests baseline is HEAD~2.
    repo.git("tag", "-f", "baseline/demo-001", "HEAD~2")


def test_freshness_survives_a_tree_preserving_rebase(repo: FixtureRepo) -> None:
    # the platform/001 re-pin cascade, minus the re-pin: rebasing onto a canon fix rewrites every
    # SHA and orphans the pinned verdict SHA, but the change's attested files (src + criteria) are
    # byte-identical -> freshness PASSES with no re-pin (T10d).
    _rebase_onto_updated_main(repo)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] verdict.freshness" in proc.stdout
    assert "tree-identity" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_rebase_then_amended_code_fails_freshness(repo: FixtureRepo) -> None:
    # a rebase orphans the pin, then a post-rebase commit changes the code (a change file) -> the
    # attested tree changed, so freshness FAILS even though the pin is unreachable (T10d).
    _rebase_onto_updated_main(repo)
    repo.write("src/app/core.py", SRC_CORE + "\n\n# post-rebase code edit\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "amend code after the rebase")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] verdict.freshness" in proc.stdout
    assert "src/app/core.py" in proc.stdout


def test_rebase_then_changed_criteria_fails_freshness(repo: FixtureRepo) -> None:
    # a rebase orphans the pin, then criteria.md changes after it -> attested tree changed -> FAIL.
    _rebase_onto_updated_main(repo)
    repo.write(f"{CHANGE_DIR}/criteria.md", CRITERIA_FLIPPED + "\n<!-- post-rebase criteria drift -->\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "touch criteria after the rebase")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] verdict.freshness" in proc.stdout
    assert "criteria.md" in proc.stdout


def test_unbacked_flip_denies(repo: FixtureRepo) -> None:
    # a criterion flipped [x] with no ac-marked test backing it -> gate.py goes RED on
    # criteria.junit-backing, which accept surfaces as a deny.
    flipped = CRITERIA_FLIPPED + "- [x] AC-3: the `missing_code` field is returned in the body\n"
    repo.write(f"{CHANGE_DIR}/criteria.md", flipped)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1
    assert "[FAIL] criteria.junit-backing" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_m_change_missing_adversarial_section_denies(tmp_path: Path) -> None:
    # M-depth change (filled Interface sketch), verdict.md's adversarial section left as "N/A" —
    # the pass never ran for a class that requires it, so accept must deny (spec §6 step 4).
    repo = make_repo(tmp_path / "app", change_md=M_CHANGE_MD, verdict_md=VERDICT_MD)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] adversarial.presence" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_m_change_with_adversarial_section_is_acceptable(tmp_path: Path) -> None:
    # same M-depth change, but the adversarial section is filled by a real run -> acceptable.
    repo = make_repo(tmp_path / "app", change_md=M_CHANGE_MD, verdict_md=VERDICT_ADVERSARIAL)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] adversarial.presence" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_platform001_prefix_verdict_backticked_sha_and_pass_heading_is_acceptable(tmp_path: Path) -> None:
    # the exact shape that DENIED platform/001 twice on cosmetics (T10c): the Gate-line SHA is
    # wrapped in backticks and the adversarial section sits under `## Adversarial pass`. Both the
    # freshness parse and the adversarial-presence check must now PASS on an M-depth change.
    repo = make_repo(tmp_path / "app", change_md=M_CHANGE_MD, verdict_md=VERDICT_BACKTICKED_SHA_PASS_HEADING)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] verdict.freshness" in proc.stdout
    assert "[PASS] adversarial.presence" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_verdict_with_no_sha_hex_still_denies_on_freshness(tmp_path: Path) -> None:
    # tolerance widens the parse, not the semantics: a Gate line pinning no hex is still a deny.
    repo = make_repo(tmp_path / "app", verdict_md=VERDICT_NO_SHA)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] verdict.freshness" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_s_change_does_not_require_adversarial(repo: FixtureRepo) -> None:
    # the default fixture is S depth on an existing capability -> the pass is opt-in, not gated.
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0
    assert "[PASS] adversarial.presence" in proc.stdout
    assert "not required" in proc.stdout


def test_help_lists_flags() -> None:
    proc = subprocess.run([sys.executable, str(TOOLS_DIR / "accept.py"), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for flag in ("--execute", "--base", "--tree", "--placement"):
        assert flag in proc.stdout
