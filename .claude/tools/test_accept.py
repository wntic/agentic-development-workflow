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
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
TOOL_FILES = ("gate.py", "criteria_lint.py", "accept.py")
# Verbatim snapshots of real change documents used as regression fixtures (T10e).
FIXTURES_DIR = TOOLS_DIR / "fixtures"
CAPABILITY_TEMPLATE = (TOOLS_DIR.parent / "templates" / "capability.md").read_text(encoding="utf-8")
CHANGE_TEMPLATE = (TOOLS_DIR.parent / "templates" / "change.md").read_text(encoding="utf-8")


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

# The same M-depth change with the sketch nested one level deeper (T10h). `_section` used to match
# `## ` only, so this read as NO Interface sketch -> S depth -> the mandatory adversarial pass was
# skipped. Depth is not the question the gate asks; "did the author write one" is.
M_CHANGE_MD_NESTED_SKETCH = M_CHANGE_MD.replace("## Interface sketch", "### Interface sketch")

# The same verdict, but with the adversarial section actually filled by a run.
VERDICT_ADVERSARIAL = VERDICT_MD.replace(
    "## Adversarial review\nN/A (S)",
    "## Adversarial review\nRan the assert-strength recipes over the test diff — asserts pin\n"
    "exact values; no tautologies found.",
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

# The GREENFIELD shape (T10f F-02): the first change of a context — no `Affects:` line, no
# capability file on disk, an overview whose Capabilities list is still empty. Its acceptance
# BIRTHS `thing.md` (derived from the change-dir slug), which is exactly the case spec §6 step 4
# makes the adversarial pass mandatory for.
BIRTH_CHANGE_MD = CHANGE_MD.replace("Affects: core.md\n", "")
OVERVIEW_NO_CAPABILITIES = OVERVIEW_MD.replace("- `core.md` — arithmetic core\n", "")
# The users/002 shape: the overview DOES name the capability this acceptance births — once in
# the Capabilities list and once in prose (F-03c/F-10).
OVERVIEW_BIRTH_LISTED = OVERVIEW_MD.replace(
    "- `core.md` — arithmetic core",
    "- `thing.md` — the arithmetic core",
).replace(
    "## Cross-cutting invariants and domain terms\n",
    "## Cross-cutting invariants and domain terms\nNone yet — every invariant lives in `thing.md`.\n",
)

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

    def gate(self, *args: str) -> subprocess.CompletedProcess[str]:
        """The gate as the NEXT change would meet it — run on a checked-out branch, not
        through accept.py. This is the only way an acceptance's own output gets judged (T10j)."""
        env = os.environ.copy()
        env["GATE_DOCKER"] = "0"
        return subprocess.run(
            [sys.executable, str(self.root / ".claude/tools/gate.py"), *args, str(self.root)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.root,
        )


def make_repo(
    root: Path,
    *,
    change_md: str = CHANGE_MD,
    verdict_md: str = VERDICT_MD,
    overview_md: str = OVERVIEW_MD,
    capability_md: str | None = CAPABILITY_MD,
    extra_caps: dict[str, str] | None = None,
) -> FixtureRepo:
    root.mkdir(parents=True, exist_ok=True)
    repo = FixtureRepo(root)
    repo.git("-c", "init.defaultBranch=main", "init", "-q")
    # M0 — green main: tools + the existing capability spec, no change dir, no app yet.
    repo.write("pyproject.toml", PYPROJECT)
    repo.write(".gitignore", GITIGNORE)
    repo.write("specs/demo/overview.md", overview_md)
    # capability_md=None is the GREENFIELD shape: the context has no capability file yet, so
    # this change's acceptance BIRTHS one from the template (T10f F-02/F-11).
    if capability_md is not None:
        repo.write("specs/demo/core.md", capability_md)
    for name, content in (extra_caps or {}).items():
        repo.write(f"specs/demo/{name}", content)
    for name in TOOL_FILES:
        repo.write(f".claude/tools/{name}", (TOOLS_DIR / name).read_text(encoding="utf-8"))
    # the capability template accept.py instantiates a born capability from — a real repo has
    # it; no fixture used to, which is why the birth path had no integration coverage (F-11).
    repo.write(".claude/templates/capability.md", CAPABILITY_TEMPLATE)
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
# removal-flavour classification (T10e) — structural, never grepped out of prose;
# ONE pinned spelling (T03c) — spec §3.1's `REMOVED` marker + the template's `## Removed`
# ---------------------------------------------------------------------------------------

USERS_002_CHANGE_MD = (FIXTURES_DIR / "users-002-change-spec.md").read_text(encoding="utf-8")

REMOVAL_CHANGE_MD = """\
# demo/007 — drop the legacy export

Class: behavioral, REMOVED
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

# The same change written with the pre-T03c wording every downstream document used to teach.
UNPINNED_REMOVAL_CHANGE_MD = REMOVAL_CHANGE_MD.replace(
    "Class: behavioral, REMOVED", "Class: behavioral, removal flavour"
)


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
    assert flavour.by_class is True  # the `Class:` line carries the pinned `REMOVED` marker
    assert flavour.unpinned == ""
    # the capture is anchored to the heading, so the sketch's own "removed" prose and its
    # backticked `True` / `False` / `ExportHandler` never enter the term list.
    assert set(flavour.terms) == {"LegacyExportHandler", "test_legacy_export"}


def test_classify_removal_reads_only_the_pinned_spelling_but_never_ignores_another(tmp_path: Path) -> None:
    """T03c: `REMOVED` (spec §3.1) is the one marker; an older wording is VISIBLE, not accepted.

    T10e's classifier tolerated "removal flavour" / "removes" / "removed" on the `Class:` line —
    a holding pattern, because nothing told an author which to write. Now the template teaches
    the marker, so the classifier reads only it; the previously-tolerated wordings must not turn
    into silence, which would be the same fail-open the sweep already had (notes/19).
    """
    flavour = accept.classify_removal(UNPINNED_REMOVAL_CHANGE_MD)
    assert flavour.by_class is False  # the unpinned wording no longer classifies
    assert flavour.unpinned == "removal"  # but it is captured for the report
    # this document still has a filled `## Removed` section, so V-02 runs on the symbols anyway.
    assert flavour.fires is True
    assert set(flavour.terms) == {"LegacyExportHandler", "test_legacy_export"}
    # with nothing else to go on, the wording alone produces a FLAG naming the pinned spelling.
    wording_only = "# demo/007 — drop it\n\nClass: behavioral, removal flavour\n\n## Task\n\nDrop it.\n"
    result = accept._orphan_sweep(_sweep_context(tmp_path, wording_only))
    assert result.status == accept.FLAG
    assert result.status not in (accept.SKIP, accept.PASS)
    assert "`Class: behavioral, REMOVED`" in result.detail and "did NOT run" in result.detail


def test_classify_removal_is_case_sensitive_on_the_marker() -> None:
    """The marker is a tag, not prose: `removed` in lowercase is drift to report, not a dialect."""
    lower = REMOVAL_CHANGE_MD.replace("Class: behavioral, REMOVED", "Class: behavioral, removed")
    flavour = accept.classify_removal(lower)
    assert flavour.by_class is False and flavour.unpinned == "removed"


def test_classify_removal_terminates_the_section_at_same_or_shallower_only() -> None:
    """T10h finding 3: the naive `#+` terminator truncated a nested `## Removed`.

    `_ANY_HEADING` ended the section at ANY heading depth, so a `### ` sub-entry — the shape a
    long removal list naturally takes, and the one this task's own template skeleton invites —
    cut the harvest short and the sweep under-swept in silence. Same rule as `_section` and
    `red_check.section_body` now: match any depth, terminate at same-or-shallower.
    """
    nested = """\
# demo/009 — drop the whole export subsystem

Class: behavioral, REMOVED

## Removed

### The handler
- `LegacyExportHandler` — gone with its route.

### Its tests
- `tests/test_export.py::test_legacy_export` — obsolete.

## Acceptance criteria
- AC-1: `GET /export/legacy` returns 404.
"""
    flavour = accept.classify_removal(nested)
    assert flavour.fires is True
    assert set(flavour.terms) == {"LegacyExportHandler", "test_legacy_export"}
    # and the terminator still stops at the sibling `## ` heading — the AC section is not harvested.
    assert "Acceptance criteria" not in "".join(flavour.sections)
    # a `### Removed` nested under another section is found too (matched at any depth) — and
    # terminated by its own siblings, `### ` included, which is what same-or-shallower means.
    deeper = "## Out of scope\n\n### Removed\n- `Ghost` — gone.\n\n### Kept\n- `Keeper` — stays.\n"
    assert accept.classify_removal(deeper).terms == ("Ghost",)


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
    flavour, quoting the wordings that are NOT the marker. A change that kept the comment — and
    an un-deleted `## Removed` skeleton whose body is still only that instruction comment — must
    not classify as a removal."""
    assert "removal flavour" in CHANGE_TEMPLATE  # the trap is really in the template
    assert re.search(r"(?m)^## Removed$", CHANGE_TEMPLATE)  # ...and so is the empty section
    assert accept.classify_removal(CHANGE_TEMPLATE).fires is False


def test_the_template_teaches_exactly_the_spelling_the_classifier_reads() -> None:
    """T03c's whole point: the author's instructions and the script's grammar are one rule (C7).

    Before this, four documents said four different things and the sweep keyed on a heading
    nobody was told to write — so V-02's coverage on a genuine removal rested on luck. This test
    fails if either side drifts from the other.
    """
    assert "Class: behavioral, REMOVED" in CHANGE_TEMPLATE  # the marker, verbatim
    # a change filled in exactly as the template instructs classifies, and the sweep gets terms.
    filled = CHANGE_TEMPLATE.replace("Class: behavioral ", "Class: behavioral, REMOVED ", 1).replace(
        "## Removed\n",
        "## Removed\n\n- `LegacyExportHandler` — gone with its `/export/legacy` route.\n"
        "- `tests/test_export.py::test_legacy_export` — obsolete.\n",
        1,
    )
    flavour = accept.classify_removal(filled)
    assert flavour.by_class is True and flavour.unpinned == ""
    assert set(flavour.terms) == {"LegacyExportHandler", "test_legacy_export"}


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


CLASS_DECLARED_NO_HEADING = (
    "# demo/007 — drop it\n\nClass: behavioral, REMOVED\n\n## Task\n\nDrop `LegacyExportHandler`.\n"
)


def test_orphan_sweep_flags_when_class_declares_removal_but_no_heading_lists_it(tmp_path: Path) -> None:
    """T06f part B: a DECLARED removal with nothing structural to sweep is FLAG, not SKIP.

    The sweep never falls back to free prose (T10e) — so SKIP here let a genuine removal reach
    acceptance with V-02 never running and nothing said about it. A gate that can silently
    not-run does not exist (S4); FLAG is surfaced-but-non-blocking, so the human sees the absent
    sweep without a deadlock. Since T03c the template ships the section, so the FLAG's remedy is
    a sentence the author can act on rather than an instruction that existed nowhere."""
    result = accept._orphan_sweep(
        _sweep_context(tmp_path, CLASS_DECLARED_NO_HEADING, src_text="class LegacyExportHandler: ...\n")
    )
    assert result.status == accept.FLAG
    assert result.status not in (accept.SKIP, accept.PASS)
    assert "## Removed" in result.detail and "did NOT run" in result.detail


def test_orphan_sweep_flags_an_undeleted_template_skeleton_as_unfilled(tmp_path: Path) -> None:
    """A `## Removed` heading whose body is still only the template's instruction comment is not
    a list. It must read as "the declared removal lists nothing" (FLAG) for a change that carries
    the marker — and, for a change that does not, as no declaration at all (SKIP), so an author
    who forgot to delete the skeleton is not accused of a removal they did not make."""
    skeleton = "## Removed\n<!-- `Class: behavioral, REMOVED` ONLY — delete this section otherwise. -->\n"
    declared = accept._orphan_sweep(_sweep_context(tmp_path, CLASS_DECLARED_NO_HEADING + "\n" + skeleton))
    assert declared.status == accept.FLAG
    assert "no filled `## Removed` section" in declared.detail
    not_a_removal = "# demo/008 — add a thing\n\nClass: behavioral\n\n## Task\n\nAdd it.\n\n" + skeleton
    result = accept._orphan_sweep(_sweep_context(tmp_path, not_a_removal))
    assert result.status == accept.SKIP


def test_orphan_sweep_flags_when_the_heading_lists_no_sweepable_symbol(tmp_path: Path) -> None:
    """T10f F-05 — the heading's PRESENCE is not the sweep running.

    Supersedes the T06f-era pin that asserted PASS here on the reasoning "once the heading is
    there the sweep ran". It isn't: a prose-only `## Removed` ("the legacy export endpoint,
    entirely") harvests no term, so V-02 checks nothing while the PASS string reads as "the
    sweep ran and found nothing" — with `LegacyExportHandler` still in src/. Same direction as
    the missing-heading case.

    T03c closed F-05 by making the FLAG actionable (the template now teaches the grammar), NOT by
    promoting it to FAIL: a removal whose behaviour has no symbol to name — a route string, a
    feature flag — is legitimate, and denying it would train exactly the routing-around T10e's
    inversion warns against (the task's own out-of-scope line)."""
    change_md = CLASS_DECLARED_NO_HEADING + "\n## Removed\n\nThe legacy export endpoint, entirely.\n"
    result = accept._orphan_sweep(_sweep_context(tmp_path, change_md, src_text="class LegacyExportHandler: ...\n"))
    assert result.status == accept.FLAG
    assert result.status != accept.PASS
    assert "did NOT run" in result.detail and "names no symbol" in result.detail


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


def test_section_matches_any_heading_depth_and_survives_a_subheading() -> None:
    """T10h: `_section` matched `## ` only, so a differently-nested heading was found as NOTHING.

    DECISION pinned here: a `### Interface sketch` under a `## Something` DOES count as the
    Interface sketch. The question every call site asks is "did the author write this section",
    not "at what depth" — the templates emit `## `, so any other depth is hand-written or nested
    prose, and reading it as an absent section fails OPEN (see the test below). Termination stays
    same-or-shallower: a naive `#+` terminator would let a `### ` subheading truncate its parent.
    """
    nested_heading = "# Title\n\n## Wrapper\n\n### Interface sketch\n`Foo(dep: Bar)`\n\n## Next\nafter\n"
    assert accept._section(nested_heading, "Interface sketch").strip() == "`Foo(dep: Bar)`"
    # a DEEPER heading is body, not a terminator (the users/002 verdict's `## Adversarial review`
    # carries `### F1 …` findings — truncating there would drop the whole recorded pass).
    nested_body = "## Section\nlead\n\n### Sub\ndeep\n\n#### Deeper\ndeepest\n\n## Other\nout\n"
    body = accept._section(nested_body, "Section")
    assert "lead" in body and "### Sub" in body and "deep" in body and "deepest" in body
    assert "out" not in body
    # a SHALLOWER heading still terminates, so a nested section never swallows the rest of the file.
    assert "out" not in accept._section("## Wrap\n\n### Section\nin\n\n## Other\nout\n", "Section")
    # unchanged on the shape the templates emit: full heading text, first match, absent -> "".
    assert accept._section("## A\nfirst\n\n## B\nsecond\n", "A").strip() == "first"
    assert accept._section("## A\nfirst\n", "Missing") == ""
    assert accept._section("## Acceptance criteria extra\n- AC-1: x\n", "Acceptance criteria") == ""


def test_adversarial_required_reads_an_m_l_signal_at_any_heading_depth() -> None:
    """The T10h fail-open at the unit level: the existing-capability half of T10f's F-02. A nested
    Interface sketch matched nothing -> empty section -> S depth -> `adversarial.presence` PASSed
    with "adversarial pass not required" for a change that is actually M/L."""
    sketch = "## Task\ndo a thing\n\n### Interface sketch\n`Foo(dep: Bar)`\n\n## Acceptance criteria\n- AC-1: x\n"
    required, reason = accept.adversarial_required(sketch, creates_new_capability=False)
    assert required is True
    assert "Interface sketch" in reason
    # same for the other M/L signal, a filled Context section.
    context = "## Task\ndo a thing\n\n### Context\nbecause.\n\n## Acceptance criteria\n- AC-1: x\n"
    assert accept.adversarial_required(context, creates_new_capability=False)[0] is True


def test_adversarial_section_filled_reads_a_nested_adversarial_heading() -> None:
    """The fail-CLOSED twin of the same parse bug: a `### Adversarial review` (e.g. nested under a
    `## Review` wrapper) was invisible, so a pass that DID run denied acceptance."""
    verdict = "# Verdict\n\n## Review\n\n### Adversarial review\nRan the recipes; asserts pin exact values.\n"
    assert accept.adversarial_section_filled(verdict) is True
    # a nested heading whose body is only the template comment is still not a run.
    assert accept.adversarial_section_filled("## Review\n\n### Adversarial review\n<!-- slot -->\n") is False


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
    # single-target: the verdict carries NO pending-input qualifier — `--execute` may run as is
    # (the counterpart of test_multi_target_check_mode_flags_need_for_placement_map, T10i).
    assert "pending" not in proc.stdout.rsplit("verdict:", 1)[-1]
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
    # — not a deny — so the command knows to propose a map before --execute. merge.placement
    # stays REVIEW-class for exactly this reason (T10i item 1): a TRUST deny here would block
    # the run whose step 4 produces the map, deadlocking every multi-target acceptance.
    repo = _multi_repo(tmp_path / "app")
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[FLAG] merge.placement" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout
    # ...and the verdict line itself says the map is still owed, so "ACCEPTABLE" is never read
    # as "ready for --execute" on a change --execute refuses (T10i item 1).
    assert "verdict: ACCEPTABLE — pending the placement map --execute requires" in proc.stdout
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


def _commit_escalate(repo: FixtureRepo) -> str:
    """The hook's move since T06h: write the lock and commit it, path-scoped (E-08)."""
    rel = f"{CHANGE_DIR}/ESCALATE"
    repo.write(rel, "3-pass ceiling reached\n")
    repo.git("add", "--", rel)
    repo.git("commit", "-q", "-m", "hook: escalate", "--", rel)
    return rel


def test_committed_escalate_denies_through_a_detached_worktree(repo: FixtureRepo, tmp_path: Path) -> None:
    # THE case that would have caught this: every acceptance run of the 2026-07-25/26 session, and
    # notes/19's own users/002 baseline, was produced in a fresh `git worktree` — which never
    # carries untracked files. So the `escalate.exists()` gate had never once been exercised
    # against a real lock. With the hook committing the file (T06h part 1) the worktree carries it
    # and the denial is real.
    _commit_escalate(repo)
    wt = tmp_path / "wt"
    repo.git("worktree", "add", "--detach", "--quiet", str(wt), "HEAD")
    proc = subprocess.run(
        [sys.executable, str(wt / ".claude/tools/accept.py"), "demo/001", "--base", "main", "--tree", str(wt)],
        capture_output=True,
        text=True,
        env={**os.environ, "GATE_DOCKER": "0"},
        cwd=wt,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] escalate" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


def test_committed_then_deleted_escalate_denies_with_the_lock_named(repo: FixtureRepo) -> None:
    # The bypass: the agent at its ceiling deletes the lock and commits over it. accept.py asks the
    # same branch-history question gate.py asks, so the denial NAMES the lock and the sanctioned
    # way out instead of arriving as an opaque RED-gate line (the gate would deny too).
    rel = _commit_escalate(repo)
    repo.git("rm", "-q", "--", rel)
    repo.git("commit", "-q", "-m", "unlock myself", "--", rel)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] escalate" in proc.stdout
    assert rel in proc.stdout
    assert "--clear-escalate" in proc.stdout


def test_escalate_cleared_by_a_baseline_move_stops_denying(repo: FixtureRepo) -> None:
    # The sanctioned clearing path must actually UNBLOCK acceptance, or the lock is a deadlock. The
    # anchor is the baseline TAG for exactly this reason: `red_check --clear-escalate` re-anchors it
    # onto the removal commit, so the history question then asks about an empty range. (The clearing
    # step itself, with its three guards, is driven end to end in test_red_check.py and
    # test_gate.py; here the tag move is applied directly, because this fixture's flip/verdict
    # commits sit between the baseline and the lock — an ordering guard (ii) refuses, and one a real
    # escalation cannot produce: the implementer commits src/** only on green, so nothing else is
    # committed while the lock stands.)
    rel = _commit_escalate(repo)
    repo.git("rm", "-q", "--", rel)
    repo.git("commit", "-q", "-m", "human clears the ESCALATE", "--", rel)
    repo.git("tag", "-f", "baseline/demo-001")  # what --clear-escalate does, and only it may
    proc = repo.accept("demo/001", "--base", "main")
    assert "[PASS] escalate" in proc.stdout, proc.stdout


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


def test_nested_interface_sketch_still_requires_the_adversarial_pass(tmp_path: Path) -> None:
    # T10h end-to-end: the same M-depth change with a `### Interface sketch`. Pre-fix this printed
    # `[PASS] adversarial.presence` ("S depth on an existing capability") and `verdict: ACCEPTABLE`
    # for a change whose adversarial pass never ran — a fail-open on the §6 step 4 obligation.
    repo = make_repo(tmp_path / "app", change_md=M_CHANGE_MD_NESTED_SKETCH, verdict_md=VERDICT_MD)
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] adversarial.presence" in proc.stdout
    assert "verdict: DENIED" in proc.stdout


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


# ---------------------------------------------------------------------------------------
# T10f — the undetermined-input rule and the seven fail-open paths (notes/19_accept_gate_audit)
#
#   A gate whose input could not be DETERMINED returns FAIL if it guards trust, FLAG if it is
#   a review aid. Never PASS, never absent from the report.
#
# Every test below reproduces a path that PASSED (or silently vanished) before T10f.
# ---------------------------------------------------------------------------------------


def test_unresolvable_base_aborts_instead_of_reading_as_no_intersection(repo: FixtureRepo) -> None:
    """F-01 — the T05-era fail-open: `--base ghost` produced an EMPTY `base...HEAD` diff, so
    every post-verdict edit looked non-intersecting and an L-04 deny became ACCEPTABLE. Same
    repo, same commits, one CLI typo apart."""
    # the exact scenario test_stale_verdict_with_intersecting_diff_denies pins as a deny.
    repo.write("src/app/core.py", SRC_CORE + "\n\n# late edit after the verdict\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "post-verdict src edit")
    proc = repo.accept("demo/001", "--base", "ghost-branch")
    assert "verdict: ACCEPTABLE" not in proc.stdout
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "does not resolve" in proc.stderr and "ghost-branch" in proc.stderr


def test_capability_birth_without_affects_requires_the_adversarial_pass(tmp_path: Path) -> None:
    """F-02 — the first change of a context (no `Affects`, no capability file) read as "S depth
    on an existing capability" and skipped the mandatory adversarial pass, because prechecks
    resolved its target WITHOUT the birth slug compute_merge passes. The verdict below carries
    the bare `N/A (S)` marker, so the pass demonstrably never ran."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=OVERVIEW_NO_CAPABILITIES,
        capability_md=None,
        verdict_md=VERDICT_MD,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert "[PASS] adversarial.presence" not in proc.stdout
    assert "[FAIL] adversarial.presence" in proc.stdout
    assert "first change of a capability" in proc.stdout
    assert "verdict: DENIED" in proc.stdout, proc.stdout
    assert proc.returncode == 1


def test_capability_birth_with_the_pass_is_acceptable_and_births_the_file(tmp_path: Path) -> None:
    """F-02/F-11 — the same greenfield change WITH the adversarial pass recorded runs all the way
    to a prepared birth diff. No fixture had ever driven a capability birth through the CLI, which
    is why F-02 hid; the birth also used to crash bare on the absent capability template."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=OVERVIEW_NO_CAPABILITIES,
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] adversarial.presence" in proc.stdout
    assert "(new) specs/demo/thing.md" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout
    # the birth target is derived the SAME way everywhere (C7), so the greenfield path draws no
    # "Affects undeterminable" noise from the intersection gate.
    assert "[PASS] affects.intersection" in proc.stdout
    # F-03c: the born capability IS checked against the overview map — it is unlisted here.
    assert "capability thing.md is missing from overview.md's map" in proc.stdout


def test_a_born_capability_named_in_the_overview_is_not_a_dangling_ref(tmp_path: Path) -> None:
    """F-03c/F-10 — the users/002 shape in miniature: overview.md names the capability this very
    acceptance births, twice. spec-lint read the PRE-merge tree, so it reported a missing spec
    file — once per occurrence, since findings were not deduped."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=OVERVIEW_BIRTH_LISTED,
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "references missing spec file" not in proc.stdout
    assert "[PASS] spec.lint" in proc.stdout


def test_executed_capability_birth_leaves_the_base_branch_green(tmp_path: Path) -> None:
    """T10j — the sequence nobody had ever run: `--execute` a capability-birthing change and
    then run `gate.py` on the BASE. It was RED, on the acceptance script's own output — the
    born file carries the template's comment, and L-06 read its `<test-id>` example as a rotted
    provenance reference. S9 says main is always green; this asserts it of the one script that
    is allowed to write main."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=OVERVIEW_BIRTH_LISTED,
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    proc = repo.accept("demo/001", "--base", "main", "--execute")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "EXECUTED" in proc.stdout
    born = repo.show("main", "specs/demo/thing.md")
    assert "verified by: tests/test_core.py::test_add" in born

    repo.git("checkout", "-q", "main")
    gate = repo.gate()
    assert "GATE: GREEN" in gate.stdout, gate.stdout + gate.stderr
    assert gate.returncode == 0
    # …and the second lock: the template ships no data-shaped specimen to be read as one.
    assert "<test-id>" not in born


def test_capability_birth_without_the_template_fails_loudly(tmp_path: Path) -> None:
    """F-11 — the bare `FileNotFoundError` traceback out of main() becomes a named AcceptError."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=OVERVIEW_NO_CAPABILITIES,
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    (repo.root / ".claude/templates/capability.md").unlink()
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert "capability template" in proc.stderr and "not found" in proc.stderr


def test_merge_fidelity_is_not_vacuous_on_empty_or_tokenless_criteria() -> None:
    """F-04 — `_significant_tokens` keeps only ≥3-char words, so a token-less AC had an empty
    token set and therefore no missing tokens: PASS against ANY merge. And zero criteria read as
    "all 0 acceptance criteria are present"."""
    merged = "- POST /meetings returns 201 with the meeting id (verified by: tests/t.py::test_x)"
    # a criterion whose whole text is short tokens is unverifiable, not "found".
    vacuous = accept.merge_fidelity_violations([("AC-9", "`id` is up")], merged)
    assert vacuous and "AC-9" in vacuous[0] and "unverifiable" in vacuous[0]
    # no criterion at all proves nothing about the merge.
    empty = accept.merge_fidelity_violations([], merged)
    assert empty and "unverifiable" in empty[0]


def test_resolve_targets_reports_unknown_apart_from_a_resolved_list(tmp_path: Path) -> None:
    """F-02/F-07 — an empty target list is missing KNOWLEDGE, never "targets nothing"."""
    (tmp_path / "specs" / "demo").mkdir(parents=True)
    (tmp_path / "specs" / "demo" / "core.md").write_text(CAPABILITY_MD, encoding="utf-8")
    (tmp_path / "specs" / "demo" / "extra.md").write_text(EXTRA_CAPABILITY_MD, encoding="utf-8")
    explicit = accept.resolve_targets(tmp_path, "demo", "Affects: core.md\n")
    assert explicit.known is True and explicit.files == ("core.md",)
    # an Affects line the /spec session left as a placeholder, with two capability files to
    # choose between: nothing can be derived.
    unknown = accept.resolve_targets(tmp_path, "demo", "Affects: <!-- TODO: pick one -->\n")
    assert unknown.known is False and unknown.files == ()


def test_provenance_correlates_on_the_junit_classname(tmp_path: Path) -> None:
    """F-06 — correlation was by function name alone, so two same-named tests in different files
    attributed the invariant to whichever node-id sorted first: the WRONG file. `test_create` in
    both tests/unit and tests/integration is not an exotic shape."""
    import json

    gate_dir = tmp_path / ".gate"
    gate_dir.mkdir()
    (gate_dir / "last-run.xml").write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
        '<testcase classname="tests.integration.test_b" name="test_create">'
        '<properties><property name="ac" value="AC-1"/></properties></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (gate_dir / "inventory.json").write_text(
        json.dumps(
            {
                "collected": ["tests/unit/test_a.py::test_create", "tests/integration/test_b.py::test_create"],
                "outcomes": {
                    "tests/unit/test_a.py::test_create": "passed",
                    "tests/integration/test_b.py::test_create": "passed",
                },
            }
        ),
        encoding="utf-8",
    )
    prov = accept.junit_ac_test_ids(gate_dir)
    assert prov.evidence is True
    assert prov.node_ids == {"AC-1": "tests/integration/test_b.py::test_create"}
    assert prov.uncorrelated == ()


def test_provenance_reports_absent_evidence_instead_of_an_empty_map(tmp_path: Path) -> None:
    """F-06 — with no junit report the old helper returned `{}`, which `build_invariant_lines`
    rendered as `(verified by: ?)`. gate.py's L-06 check cannot resolve that mark, so the
    acceptance would push spec content that turns the BASE branch's own gate RED (S9)."""
    prov = accept.junit_ac_test_ids(tmp_path / ".gate")
    assert prov.node_ids == {} and prov.evidence is False
    # the rendering is unchanged — it is the new gate, not the renderer, that stops the merge.
    lines = accept.build_invariants([_crit("x", "AC-1", "add returns the sum")], prov.node_ids)
    assert lines == ["- add returns the sum (verified by: ?)"]


def test_unresolved_target_still_reports_the_remaining_gates(tmp_path: Path) -> None:
    """F-09 — an unresolvable target made gate_dependent_checks return early, so spec.lint and
    orphan.sweep vanished from the human's output with no trace (fail-closed overall, but the
    reporting half of the same disease)."""
    repo = make_repo(
        tmp_path / "app",
        change_md=CHANGE_MD.replace("Affects: core.md", "Affects: <!-- TODO -->"),
        verdict_md=VERDICT_ADVERSARIAL,
        extra_caps={"extra.md": EXTRA_CAPABILITY_MD},
        overview_md=OVERVIEW_MULTI,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL] merge.fidelity" in proc.stdout and "cannot determine target" in proc.stdout
    for gate_id in ("spec.lint", "orphan.sweep", "merge.placement", "affects.intersection"):
        assert f"] {gate_id} —" in proc.stdout, f"{gate_id} vanished from the report"


def test_every_reported_gate_id_is_registered(tmp_path: Path) -> None:
    """The registry is the parametrised rule's index: a gate missing from it is a gate the
    undetermined-input test cannot walk."""
    source = (TOOLS_DIR / "accept.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'Result\(\s*"([a-z][a-z.\-]+)"', source))
    assert emitted, "the Result-id scan found nothing — the regex drifted from the source"
    assert emitted <= set(accept.GATES), f"unregistered gate id(s): {sorted(emitted - set(accept.GATES))}"
    for gate_id in accept.GATES:
        assert f'"{gate_id}"' in source, f"{gate_id} is registered but never reported"


# --- one undetermined-input scenario per registered gate ---------------------------------

MINI_VERDICT_CHECKS = [
    {"id": "docker.alembic", "status": "SKIP", "detail": "DOCKER SKIPPED (forced off via GATE_DOCKER=0)"},
    {"id": "criteria.junit-backing", "status": "PASS", "detail": "2 [x] criteria junit-backed"},
    {"id": "criteria.manual-verdict", "status": "PASS", "detail": "0 [m] criteria have verdict.md entries"},
]


def _mini_tree(
    tmp_path: Path,
    *,
    change_md: str = CHANGE_MD,
    criteria: str = CRITERIA_FLIPPED,
    overview: str | None = OVERVIEW_MD,
    caps: dict[str, str] | None = None,
    others: dict[str, str] | None = None,
) -> Path:
    """A spec tree with no git and no gate — enough to call a gate function directly."""
    root = tmp_path / "tree"
    (root / CHANGE_DIR).mkdir(parents=True, exist_ok=True)
    (root / CHANGE_DIR / "change.md").write_text(change_md, encoding="utf-8")
    (root / CHANGE_DIR / "criteria.md").write_text(criteria, encoding="utf-8")
    if overview is not None:
        (root / "specs" / "demo" / "overview.md").write_text(overview, encoding="utf-8")
    for name, text in ({"core.md": CAPABILITY_MD} if caps is None else caps).items():
        (root / "specs" / "demo" / name).write_text(text, encoding="utf-8")
    for rel, text in (others or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _mini_ctx(root: Path, *, verdict: str | None = None):
    return accept.AcceptContext(
        tree=root,
        change_id="demo/001",
        ctx="demo",
        nnn="001",
        change_dir=root / CHANGE_DIR,
        base="main",
        branch="change/demo-001",
        head="0" * 40,
        change_md=(root / CHANGE_DIR / "change.md").read_text(encoding="utf-8"),
        criteria_text=(root / CHANGE_DIR / "criteria.md").read_text(encoding="utf-8"),
        verdict_text=verdict,
    )


def _gate_checks(tmp_path: Path, *, verdict: dict | None = None, **tree_kwargs) -> list:
    root = _mini_tree(tmp_path, **tree_kwargs)
    (root / ".claude" / "templates").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "templates" / "capability.md").write_text(CAPABILITY_TEMPLATE, encoding="utf-8")
    payload = {"result": "GREEN", "sha": "0" * 40, "checks": MINI_VERDICT_CHECKS} if verdict is None else verdict
    results, _ = accept.gate_dependent_checks(_mini_ctx(root), payload)
    return results


# Each scenario feeds ONE gate an input that cannot be determined and returns the reported
# results — or None when the whole run aborts loudly before any gate can speak (legal only for
# a TRUST gate: nothing merges). Adding a gate to accept.GATES without adding a scenario here
# fails test_no_gate_passes_on_undetermined_input, so a future gate is covered by construction.
UNDETERMINED_SCENARIOS = {
    # the change directory itself cannot be found — nothing about ESCALATE is knowable.
    "escalate": lambda tmp: _abort(lambda: accept.resolve(_mini_tree(tmp, caps={}), "demo/002", "main")),
    # criteria.md carries no criterion at all.
    "criteria.complete": lambda tmp: accept.prechecks(
        _mini_ctx(_mini_tree(tmp, criteria="# Criteria — demo/001\n<!-- none written yet -->\n"))
    ),
    # the base branch does not resolve, so the change's own file set is unknowable (F-01).
    "verdict.freshness": lambda tmp: _abort(lambda: accept.resolve(make_repo(tmp / "app").root, "demo/001", "ghost")),
    # a companion is declared but its acceptance state cannot be established (no tag).
    "companion": lambda tmp: accept.prechecks(
        _mini_ctx(_mini_tree(tmp, change_md=CHANGE_MD.replace("Affects:", "Companion: other/001\nAffects:")))
    ),
    # the target capability cannot be determined -> assume a birth -> the pass is required (F-02).
    "adversarial.presence": lambda tmp: accept.prechecks(
        _mini_ctx(
            _mini_tree(
                tmp,
                change_md=CHANGE_MD.replace("Affects: core.md", "Affects: <!-- TODO -->"),
                caps={"core.md": CAPABILITY_MD, "extra.md": EXTRA_CAPABILITY_MD},
                overview=OVERVIEW_MULTI,
            )
        )
    ),
    # a gate verdict that carries no result at all.
    "gate.green": lambda tmp: _gate_checks(tmp, verdict={}),
    # no docker.alembic check in the verdict: whether the tier ran is unknown (F-07).
    "docker.tier": lambda tmp: _gate_checks(tmp, verdict={"result": "GREEN", "sha": "0" * 40, "checks": []}),
    "criteria.junit-backing": lambda tmp: _gate_checks(tmp, verdict={"result": "GREEN", "sha": "", "checks": []}),
    "criteria.manual-verdict": lambda tmp: _gate_checks(tmp, verdict={"result": "GREEN", "sha": "", "checks": []}),
    # no junit report in .gate/ -> no criterion resolves to a test node-id (F-06).
    "invariant.provenance": lambda tmp: _gate_checks(tmp),
    # another in-flight change whose own Affects cannot be resolved (F-07).
    "affects.intersection": lambda tmp: _gate_checks(
        tmp,
        caps={"core.md": CAPABILITY_MD, "extra.md": EXTRA_CAPABILITY_MD},
        overview=OVERVIEW_MULTI,
        others={"specs/demo/changes/002-other/change.md": "Class: behavioral\nAffects: <!-- TODO -->\n"},
    ),
    # no acceptance criterion can be read from either source (F-04).
    "merge.fidelity": lambda tmp: _gate_checks(
        tmp,
        change_md="# demo/001\n\nClass: behavioral\nAffects: core.md\n\n## Task\nDo it.\n",
        criteria="# Criteria — demo/001\n<!-- none written yet -->\n",
    ),
    # multi-target Affects with no approved placement map: distribution is undecided (and
    # --execute refuses it outright — test_multi_target_execute_without_map_is_refused).
    "merge.placement": lambda tmp: _gate_checks(
        tmp,
        change_md=MULTI_CHANGE_MD,
        caps={"core.md": CAPABILITY_MD, "extra.md": EXTRA_CAPABILITY_MD},
        overview=OVERVIEW_MULTI,
    ),
    # no overview.md: the context map cannot be checked (F-03).
    "spec.lint": lambda tmp: _gate_checks(tmp, overview=None),
    # a `## Removed` heading whose body names no sweepable symbol (F-05).
    "orphan.sweep": lambda tmp: _gate_checks(
        tmp,
        change_md=CHANGE_MD + "\n## Removed\n\nThe legacy export endpoint, entirely.\n",
    ),
}


def _abort(call) -> None:
    """Run a call that must refuse to produce any verdict at all; returns None (= aborted)."""
    with pytest.raises(accept.AcceptError):
        call()
    return None


@pytest.mark.parametrize("gate_id", sorted(accept.GATES))
def test_no_gate_passes_on_undetermined_input(gate_id: str, tmp_path: Path) -> None:
    """THE rule T10f pins (notes/19_accept_gate_audit.md):

        a gate whose input could not be determined returns FAIL if it guards trust, FLAG if it
        is a review aid — never PASS, never absent from the report.

    Seven gates broke it, all the same way: a helper that could not determine its input returned
    an empty value and the gate read "empty" as "nothing wrong" instead of "nothing known". This
    test walks the gate registry, so the eighth gate is covered by construction."""
    assert gate_id in UNDETERMINED_SCENARIOS, (
        f"{gate_id} is registered in accept.GATES with no undetermined-input scenario — add one: "
        "a gate nobody feeds unknown input to is a gate nobody knows the direction of"
    )
    results = UNDETERMINED_SCENARIOS[gate_id](tmp_path)
    if results is None:
        # the whole run aborted (AcceptError): nothing can merge, so only a TRUST gate may.
        assert accept.GATES[gate_id] == accept.TRUST
        return
    reported = [r for r in results if r.id == gate_id]
    assert reported, f"{gate_id} is absent from the report on undetermined input"
    status = reported[0].status
    assert status != accept.PASS, f"{gate_id} PASSed on input it could not determine: {reported[0].detail}"
    expected = accept.FAIL if accept.GATES[gate_id] == accept.TRUST else accept.FLAG
    assert status == expected, f"{gate_id} returned {status}, expected {expected}: {reported[0].detail}"


def test_execute_refuses_when_git_cannot_report_the_work_tree_state(tmp_path: Path) -> None:
    """T04g — the same rule, applied to `execute()`'s cleanliness precondition.

    `execute()` did `rc, status = _git(tree, "status", "--porcelain")` and discarded `rc`. `_git`
    returns stdout only, so a `git status` that could not run yields `""` and `status.strip()`
    reads it as "the tree is clean" — after which the destructive sequence starts and the change
    directory is deleted before the first `check=True` call notices anything. Undetermined input
    on the one gate that mutates the base branch, found by ruff's RUF059 on the unused `rc` (the
    linter's own report of a discarded git return code — notes/19's family, unaided).
    """
    root = _mini_tree(tmp_path)  # a spec tree with NO git repository
    actx = _mini_ctx(root)
    plan = accept.MergePlan(infos=[], diff_text="", invariants=[], error="")
    with pytest.raises(accept.AcceptError, match="git status --porcelain"):
        accept.execute(actx, plan)
    # ...and it refused BEFORE touching anything: pre-fix this call deleted the change dir.
    assert actx.change_dir.is_dir(), "execute() destroyed the change dir on an undetermined work-tree state"


def test_spec_lint_sees_the_inputs_it_used_to_be_blind_to(tmp_path: Path) -> None:
    """F-03 a+b — a missing overview.md DISABLED the coverage check by its own `if overview_text`
    guard and reported "clean"; and the duplicate check compared filesystem names, which are
    unique by construction, so it was dead code — the duplicate a human can create is a repeated
    entry in overview.md's Capabilities list."""
    no_overview = _spec_lint_result(_mini_tree(tmp_path / "a", overview=None))
    assert no_overview.status == accept.FLAG
    assert "overview.md is absent" in no_overview.detail
    duplicated = OVERVIEW_MD.replace(
        "- `core.md` — arithmetic core",
        "- `core.md` — arithmetic core\n- `core.md` — arithmetic core (listed twice by hand)",
    )
    dupes = _spec_lint_result(_mini_tree(tmp_path / "b", overview=duplicated))
    assert dupes.status == accept.FLAG
    assert "names `core.md` more than once" in dupes.detail


def _spec_lint_result(root: Path):
    return accept._spec_lint(_mini_ctx(root))


# ---------------------------------------------------------------------------------------
# T10i items 3+4 — spec-lint reads content, once
#
# A comment is not content: the same mistake T10j fixed in gate.py's L-06 check was still live
# in _spec_lint, which ran both its dangling-ref scan and its >300-line S7 count over the raw
# text. Every born capability file ships the template's comment block, so every one of them
# carried lines the S7 count should not see. And a finding must be printed once — a repeat is
# noise in the human's review output that reads as two problems.
# ---------------------------------------------------------------------------------------


def test_a_comment_naming_a_missing_md_is_not_a_dangling_reference(tmp_path: Path) -> None:
    """The false-positive half: a comment may legitimately mention a file that does not exist
    (the capability template's own comment block is the live shape) — while a real reference in
    the body must still FLAG, so the strip cannot be a blanket "stop checking"."""
    commented = (
        "# demo / core\n\n<!-- neighbours: `nonexistent-neighbour.md` documents the split -->\n\n## Invariants\n"
    )
    clean = _spec_lint_result(_mini_tree(tmp_path / "a", caps={"core.md": commented}))
    assert clean.status == accept.PASS, clean.detail

    in_body = commented.replace("## Invariants\n", "## Invariants\n- see `nonexistent-neighbour.md` (MANUAL)\n")
    flagged = _spec_lint_result(_mini_tree(tmp_path / "b", caps={"core.md": in_body}))
    assert flagged.status == accept.FLAG
    assert "references missing spec file `nonexistent-neighbour.md`" in flagged.detail


def test_the_born_capability_template_lints_clean(tmp_path: Path) -> None:
    """The live shape, end to end: accept.py births capability files from this very template, so
    the template's comment block must not produce a finding against the file the script wrote."""
    born = CAPABILITY_TEMPLATE.replace("<context>", "demo").replace("<capability>", "core")
    result = _spec_lint_result(_mini_tree(tmp_path, caps={"core.md": born}))
    assert result.status == accept.PASS, result.detail


def test_comment_lines_do_not_count_toward_the_s7_cut_threshold(tmp_path: Path) -> None:
    """The S7 half: 300 lines of invariants plus a 20-line comment block is not a file S7 asks
    the human to cut. Content past the threshold still is."""
    comment = "<!--\n" + "     documentation line\n" * 18 + "-->\n"
    body = "".join(f"- invariant {i} (MANUAL)\n" for i in range(295))
    under = _spec_lint_result(_mini_tree(tmp_path / "a", caps={"core.md": f"# demo / core\n\n{comment}\n{body}"}))
    assert under.status == accept.PASS, under.detail

    over_body = "".join(f"- invariant {i} (MANUAL)\n" for i in range(320))
    over = _spec_lint_result(_mini_tree(tmp_path / "b", caps={"core.md": f"# demo / core\n\n{comment}\n{over_body}"}))
    assert over.status == accept.FLAG
    assert "exceeds 300 lines" in over.detail


def test_a_repeated_reference_is_one_finding(tmp_path: Path) -> None:
    """Item 3 — a reference appearing twice in one file produced two identical lines.

    Honest scope: T10f already deduped this one case per (file, ref) while fixing F-03, so this
    test passes on its code too. It is here because the property was never pinned, and because
    the dedupe now covers the whole findings list rather than that single scan."""
    twice = "# demo / core\n\n## Behaviour\nSee `gone.md`.\n\n## Invariants\n- as `gone.md` says (MANUAL)\n"
    result = _spec_lint_result(_mini_tree(tmp_path, caps={"core.md": twice}))
    assert result.status == accept.FLAG
    lines = [line for line in result.detail.splitlines() if "references missing spec file `gone.md`" in line]
    assert lines == ["specs/demo/core.md references missing spec file `gone.md`"], result.detail


# ---------------------------------------------------------------------------------------
# T10k — the LAST reader on raw text: overview.md's Capabilities list
#
# Same rule as T10j (gate.py's L-06) and T10i (_spec_lint): a comment is not content. This one
# matters beyond lint noise, because the token list feeds resolve_targets' capability-BIRTH path
# — a comment naming a backticked `*.md` could name the file an acceptance CREATES, or fake a
# "names X more than once" finding. Latent, not firing: the shipped overview template's own
# `<capability>.md` placeholder does NOT match the token regex (`<`/`>` are outside its character
# class), so nothing in the templates triggers it today.
#
# The contract that must survive the strip: the tokens stay IN ORDER and WITH REPEATS (T10f F-03).
# ---------------------------------------------------------------------------------------


def _with_capabilities_comment(overview: str, comment: str) -> str:
    return overview.replace("## Capabilities\n", f"## Capabilities\n{comment}\n", 1)


def test_a_comment_in_the_capabilities_list_is_not_a_capability(tmp_path: Path) -> None:
    """The measured pre-fix behaviour: `['ghost.md', 'core.md']` — the comment first, so it also
    won every "the context declares exactly one capability" comparison downstream."""
    overview = _with_capabilities_comment(OVERVIEW_MD, "<!-- see `ghost.md` for the shape of an entry -->")
    root = _mini_tree(tmp_path, overview=overview)
    assert accept._overview_capability_tokens(root, "demo") == ["core.md"]
    assert accept._overview_capabilities(root, "demo") == ["core.md"]


def test_the_capability_token_list_keeps_order_and_repeats(tmp_path: Path) -> None:
    """T10f F-03's contract: the raw list is what lets spec-lint see a capability listed twice.
    Blanking a comment span must not renumber, reorder or de-duplicate anything around it."""
    overview = OVERVIEW_MD.replace(
        "- `core.md` — arithmetic core",
        "- `extra.md` — app construction\n"
        "<!-- `ghost.md` — a comment, never an entry -->\n"
        "- `core.md` — arithmetic core\n"
        "- `extra.md` — listed twice by hand",
    )
    root = _mini_tree(tmp_path, overview=overview, caps={"core.md": CAPABILITY_MD, "extra.md": EXTRA_CAPABILITY_MD})
    assert accept._overview_capability_tokens(root, "demo") == ["extra.md", "core.md", "extra.md"]
    result = _spec_lint_result(root)
    assert result.status == accept.FLAG
    assert "names `extra.md` more than once" in result.detail
    assert "ghost.md" not in result.detail


def test_a_comment_repeating_a_listed_capability_is_not_a_duplicate(tmp_path: Path) -> None:
    """The false-positive half of the same finding: documentation that mentions the capability it
    documents is not a human listing it twice."""
    overview = OVERVIEW_MD.replace(
        "- `core.md` — arithmetic core",
        "- `core.md` — arithmetic core\n<!-- `core.md` is the only capability for now -->",
    )
    result = _spec_lint_result(_mini_tree(tmp_path, overview=overview))
    assert result.status == accept.PASS, result.detail


def test_a_comment_cannot_hijack_the_capability_birth_target(tmp_path: Path) -> None:
    """The reason this is not a lint nit. The greenfield shape: no `Affects`, no capability file,
    an EMPTY Capabilities list carrying an instruction comment. Pre-fix, the comment's `ghost.md`
    read as "the context declares exactly one capability" and the acceptance would have BORN
    `specs/demo/ghost.md` instead of the slug-derived `thing.md`."""
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=_with_capabilities_comment(
            OVERVIEW_NO_CAPABILITIES, "<!-- one line per capability file, e.g. `ghost.md` — what it does -->"
        ),
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "(new) specs/demo/thing.md" in proc.stdout
    assert "ghost.md" not in proc.stdout


def test_the_birth_target_still_comes_from_the_real_capabilities_list(tmp_path: Path) -> None:
    """The regression that would hurt (the users/002 path): the birth capability is derived from
    overview.md's list, so the human's chosen name wins over the change-dir slug. Discriminating
    on purpose — the listed name differs from the slug — and the comment alongside it changes
    nothing."""
    overview = _with_capabilities_comment(
        OVERVIEW_MD.replace("- `core.md` — arithmetic core", "- `renamed.md` — the arithmetic core"),
        "<!-- see `ghost.md` for the shape of an entry -->",
    )
    repo = make_repo(
        tmp_path / "app",
        change_md=BIRTH_CHANGE_MD,
        overview_md=overview,
        capability_md=None,
        verdict_md=VERDICT_ADVERSARIAL,
    )
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "(new) specs/demo/renamed.md" in proc.stdout
    assert "specs/demo/thing.md" not in proc.stdout
    assert "[PASS] spec.lint" in proc.stdout


def test_the_drift_fallback_reads_the_resolved_context_not_the_raw_arguments(
    repo: FixtureRepo, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """T17 finding 2 — `run()`'s `--execute` tail called `drift_report(tree, base)` with the RAW
    arguments: `base` is Optional since T10g derives it, so the no-plan branch handed `git log`
    a `None` ref and died inside subprocess. Unreachable by luck today (`plan is None` implies a
    FAIL implies the deny above), which is why the branch is driven here directly: the next
    refactor that makes it reachable must find a clean report, not a traceback."""
    monkeypatch.setattr(accept, "run_gate", lambda actx: {"result": "GREEN", "sha": "0" * 40, "checks": []})
    monkeypatch.setattr(accept, "gate_dependent_checks", lambda actx, verdict, placement=None: ([], None))
    rc = accept.run(repo.root, "demo/001", None, True)  # base=None: derived, as /accept-change runs it
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "drift-check on main (spec §5.5)" in out
    assert "every src commit is attached to a change/* tag" in out


# ---------------------------------------------------------------------------------------
# T10g — the S9 base is DERIVED, never a hardcoded name
#
# `/accept-change` runs the script with no --base, and the old default `main` is wrong for
# this very repo (S9 base `markdown-specs`) and for any project on `master`/`trunk`. A wrong
# base silently re-answers every `base...HEAD` gate — and a wrong base that does not resolve
# is exactly F-01's path. So: derive it, or say loudly that it could not be derived.
# ---------------------------------------------------------------------------------------


def test_base_is_derived_when_the_flag_is_absent(repo: FixtureRepo) -> None:
    """The command's documented invocation — no --base — must reach the same verdict as
    `--base main` did, and say which base it derived."""
    proc = repo.accept("demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "base main (derived)" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_derivation_follows_the_graph_not_the_name_main(repo: FixtureRepo) -> None:
    """The load-bearing case: a project whose integration branch is not called `main`. Nothing
    in the derivation may know that name (C6) — the fork point decides."""
    repo.git("branch", "-m", "main", "trunk")
    proc = repo.accept("demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "base trunk (derived)" in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_derivation_prefers_the_nearest_fork_over_an_older_base(repo: FixtureRepo) -> None:
    """This repo's own shape: `main` is behind the live integration branch, which carries the
    fork the change was actually cut from. Both share history with HEAD; the nearer one wins."""
    repo.git("checkout", "-q", "main")
    repo.write("notes.md", "the integration branch moved on after main\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "integration branch commit")
    repo.git("branch", "integration")
    repo.git("reset", "-q", "--hard", "HEAD~1")  # main stays behind; `integration` keeps the tip
    repo.git("checkout", "-q", "change/demo-001")
    repo.git("rebase", "-q", "integration")
    assert accept.derive_base(repo.root) == "integration"


def test_derivation_ignores_change_branches_including_the_detached_one(repo: FixtureRepo) -> None:
    """The acceptance run usually stands on (or is detached at) a `change/*` branch — whose fork
    point with HEAD is HEAD itself, so it would win every comparison. S9's own branch name is the
    one thing the derivation is allowed to know."""
    repo.git("branch", "change/demo-002")
    repo.git("checkout", "-q", "--detach")
    assert accept.derive_base(repo.root) == "main"


def test_ambiguous_base_is_an_error_not_a_guess(repo: FixtureRepo) -> None:
    """Two branches equally close to HEAD: the base is undetermined, and an undetermined input
    that feeds every gate may not be guessed (the T10f rule, one level up)."""
    repo.git("branch", "release", "main")
    proc = repo.accept("demo/001")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "could not be derived" in proc.stderr
    assert "main" in proc.stderr and "release" in proc.stderr
    assert "--base" in proc.stderr
    assert "verdict:" not in proc.stdout


def test_no_candidate_branch_is_an_error(repo: FixtureRepo) -> None:
    """Nothing but the change branch itself: there is no base to accept into, and the run says
    so instead of judging the change against a branch it invented."""
    repo.git("branch", "-D", "main")
    with pytest.raises(accept.AcceptError) as excinfo:
        accept.derive_base(repo.root)
    assert "no local branch outside 'change/*' shares history" in str(excinfo.value)


def test_explicit_base_still_wins(repo: FixtureRepo) -> None:
    """--base is not deprecated: it is the remedy the derivation's error messages point at."""
    repo.git("branch", "release", "main")  # derivation alone would be ambiguous here
    proc = repo.accept("demo/001", "--base", "main")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "base main," in proc.stdout and "(derived)" not in proc.stdout
    assert "verdict: ACCEPTABLE" in proc.stdout


def test_help_lists_flags() -> None:
    proc = subprocess.run([sys.executable, str(TOOLS_DIR / "accept.py"), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for flag in ("--execute", "--base", "--tree", "--placement"):
        assert flag in proc.stdout
