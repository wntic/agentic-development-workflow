"""Test suite for red_check.py (workflow v3, T09).

Pure-function tests for the parse/analyze layer, plus end-to-end fixture repos that build a
git tree with red (and deliberately non-red) ac-marked tests and run red_check as a whole:
the red baseline is confirmed and tagged; green-before-implementation and missing coverage
are caught and leave no baseline tag behind."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", TOOLS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


red_check = _load("red_check")


# --- pure: parse_ac_ids ----------------------------------------------------------------

CRITERIA_MD = """\
# Criteria — demo/001-health

<!-- template comment with a decoy: - [ ] AC-9: should be ignored -->

- [ ] AC-1: `GET /health` returns `200` with body field `status`
- [ ] AC-2: `GET /health` body `status` equals `ok`
"""


def test_parse_ac_ids_skips_comments_and_dedupes() -> None:
    assert red_check.parse_ac_ids(CRITERIA_MD) == ["AC-1", "AC-2"]


# --- pure: analyze ---------------------------------------------------------------------


def test_analyze_all_red_is_ok() -> None:
    inv = {
        "outcomes": {"tests/t.py::test_a": "failed", "tests/t.py::test_b": "error"},
        "markers": {"tests/t.py::test_a": ["AC-1"], "tests/t.py::test_b": ["AC-2"]},
    }
    result = red_check.analyze(["AC-1", "AC-2"], inv)
    assert result.ok
    assert set(result.red_tests) == {"tests/t.py::test_a", "tests/t.py::test_b"}


def test_analyze_missing_marker_fails() -> None:
    inv = {"outcomes": {"tests/t.py::test_a": "failed"}, "markers": {"tests/t.py::test_a": ["AC-1"]}}
    result = red_check.analyze(["AC-1", "AC-2"], inv)
    assert not result.ok
    assert result.missing_acs == ["AC-2"]


def test_analyze_green_before_implementation_fails() -> None:
    inv = {"outcomes": {"tests/t.py::test_a": "passed"}, "markers": {"tests/t.py::test_a": ["AC-1"]}}
    result = red_check.analyze(["AC-1"], inv)
    assert not result.ok
    assert result.green_before_impl == ["tests/t.py::test_a"]


def test_analyze_skipped_cannot_prove_redness() -> None:
    inv = {"outcomes": {"tests/t.py::test_a": "skipped"}, "markers": {"tests/t.py::test_a": ["AC-1"]}}
    result = red_check.analyze(["AC-1"], inv)
    assert not result.ok
    assert result.not_red_other == ["tests/t.py::test_a"]


# --- pure: non_tests_paths (tests-only baseline filter) --------------------------------


def test_non_tests_paths_accepts_only_tests() -> None:
    assert red_check.non_tests_paths(["tests/a.py", "tests/sub/b.py", "tests"]) == []


def test_non_tests_paths_flags_src_and_change_dir() -> None:
    paths = ["tests/a.py", "src/app/main.py", ".gitignore", "specs/demo/x.md"]
    assert red_check.non_tests_paths(paths) == ["src/app/main.py", ".gitignore", "specs/demo/x.md"]


# --- pure: greenfield fallback (static AST marker scan) --------------------------------


def test_scan_ac_markers_finds_top_level_and_class_methods() -> None:
    source = (
        "import pytest\n\n\n"
        '@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    pass\n\n\n'
        "class TestGroup:\n"
        '    @pytest.mark.ac("AC-2")\n    def test_b(self) -> None:\n        pass\n\n\n'
        "def test_unmarked() -> None:\n    pass\n"
    )
    found = red_check.scan_ac_markers(source, "tests/test_x.py")
    assert found == {
        "tests/test_x.py::test_a": ["AC-1"],
        "tests/test_x.py::TestGroup::test_b": ["AC-2"],
    }


def test_missing_module_of_extracts_name() -> None:
    assert red_check.missing_module_of("E   ModuleNotFoundError: No module named 'app'") == "app"
    assert red_check.missing_module_of("cannot import name 'x' from 'app.main'") is None


def test_project_package_reads_and_normalizes_name(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\nversion = "0.1.0"\n')
    assert red_check.project_package(tmp_path) == "my_app"
    assert red_check.project_package(tmp_path / "nope") is None


def test_greenfield_fallback_only_when_package_absent(tmp_path: Path) -> None:
    inv = {
        "outcomes": {},
        "markers": {},
        "collect_errors": [{"nodeid": "tests/test_h.py", "longrepr": "ModuleNotFoundError: No module named 'app'"}],
    }
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_h.py").write_text(
        'import pytest\n\n\n@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n'
        "    from app.main import create_app\n\n    assert create_app()\n"
    )
    # package absent → fallback restores the marker as RED
    out = red_check.apply_greenfield_fallback(tmp_path, dict(inv, markers={}, outcomes={}), "app")
    assert out["markers"] == {"tests/test_h.py::test_a": ["AC-1"]}
    assert out["outcomes"]["tests/test_h.py::test_a"] == "error"

    # brownfield: src/app exists → a collection error is NOT masked (fallback is a no-op)
    (tmp_path / "src" / "app").mkdir(parents=True)
    out2 = red_check.apply_greenfield_fallback(tmp_path, dict(inv, markers={}, outcomes={}), "app")
    assert out2["markers"] == {}


def test_greenfield_fallback_ignores_third_party_missing_module(tmp_path: Path) -> None:
    # a forgotten third-party dep (not the project's own package) must NOT be masked
    inv = {
        "markers": {},
        "outcomes": {},
        "collect_errors": [{"nodeid": "tests/test_h.py", "longrepr": "ModuleNotFoundError: No module named 'httpx'"}],
    }
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_h.py").write_text(
        'import pytest\n\n\n@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    pass\n'
    )
    out = red_check.apply_greenfield_fallback(tmp_path, inv, "app")
    assert out["markers"] == {}


# --- end-to-end fixture repos ----------------------------------------------------------


class FixtureRepo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=rc", "-c", "user.email=rc@test", *args],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"git {args} failed: {proc.stdout}{proc.stderr}"
        return proc.stdout

    def tags(self) -> list[str]:
        return [t for t in self.git("tag").splitlines() if t]


def _base_repo(tmp_path: Path) -> FixtureRepo:
    """A repo whose FIRST commit is the /spec commit (change-dir + .gitignore).

    /implement sequences the commits so the change-dir files land before the test-author
    runs (step 0 confirms change.md + criteria.md already exist); the red-tests commit that
    red_check tags is therefore a *separate*, later, tests-only commit. The fixtures mirror
    that: _base_repo lays the spec commit, each e2e test adds the baseline commit on top.
    """
    repo = FixtureRepo(tmp_path)
    repo.write(".gitignore", ".gate/\n__pycache__/\n.pytest_cache/\n")
    repo.write("specs/demo/changes/001-health/criteria.md", CRITERIA_MD)
    repo.git("init", "-q")
    repo.git("add", "-A")
    repo.git("commit", "-qm", "spec: demo/001")
    return repo


def _run(repo: FixtureRepo, *extra: str) -> int:
    return red_check.main([str(repo.root), "--change", "demo/001", *extra])


RED_TESTS = """\
import pytest


@pytest.mark.ac("AC-1")
def test_health_status_field() -> None:
    from app.main import health  # does not exist yet — red

    assert "status" in health()


@pytest.mark.ac("AC-2")
def test_health_status_ok() -> None:
    from app.main import health

    assert health()["status"] == "ok"
"""


def test_e2e_red_baseline_confirmed_and_tagged(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")

    assert _run(repo) == 0
    assert "baseline/demo-001" in repo.tags()


def test_e2e_baseline_touching_src_refused_with_path_named(tmp_path: Path, capsys) -> None:
    # A partial src seed: tests stay RED (red_check's coverage + redness both pass), but the
    # baseline commit smuggles in src/ code — the anti-collusion (§4/D3, S8) case T09b closes.
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.write("src/app/main.py", "def health():\n    return {}\n")  # partial: no 'status' key
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests + sneaked-in src")

    assert _run(repo) == 1
    combined = capsys.readouterr()
    assert "src/app/main.py" in (combined.out + combined.err)
    assert "baseline/demo-001" not in repo.tags()


def test_e2e_green_before_implementation_fails_no_tag(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    # both marked tests pass without any code — the green-before-implementation smell
    repo.write(
        "tests/test_health.py",
        "import pytest\n\n\n"
        '@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    assert True\n\n\n'
        '@pytest.mark.ac("AC-2")\ndef test_b() -> None:\n    assert True\n',
    )
    repo.git("add", "-A")
    repo.git("commit", "-qm", "green tests")

    assert _run(repo) == 1
    assert "baseline/demo-001" not in repo.tags()


def test_e2e_missing_ac_coverage_fails_no_tag(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    # only AC-1 has a (red) test; AC-2 is uncovered
    repo.write(
        "tests/test_health.py",
        'import pytest\n\n\n@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    assert False\n',
    )
    repo.git("add", "-A")
    repo.git("commit", "-qm", "partial")

    assert _run(repo) == 1
    assert "baseline/demo-001" not in repo.tags()


def test_e2e_no_tag_flag_skips_tagging(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")

    assert _run(repo, "--no-tag") == 0
    assert "baseline/demo-001" not in repo.tags()


# --- greenfield / brownfield collection-error e2e --------------------------------------

# NB the blank line: `app` is the project's OWN package, so ruff (with known-first-party pinned
# by gate.ruff_common) sorts it into a separate first-party group even though src/ does not exist
# yet — the baseline screen now judges own-package imports exactly as the gate later will (notes/18).
GREENFIELD_TESTS = """\
# the whole package is absent yet — the module import below is a greenfield collection error
import pytest

from app.restapi.main import create_app


@pytest.mark.ac("AC-1")
def test_health_status_field() -> None:
    app = create_app()
    assert app is not None


@pytest.mark.ac("AC-2")
def test_health_status_ok() -> None:
    app = create_app()
    assert app is not None
"""


def test_e2e_greenfield_collection_error_is_red_with_all_acs(tmp_path: Path) -> None:
    # First-ever change: deps land in a pre-baseline commit (pyproject), the tests-only
    # baseline commit imports the not-yet-written package → collection error. The fallback
    # must count it RED and recover both markers so every AC is covered.
    repo = _base_repo(tmp_path)
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.git("add", "-A")
    repo.git("commit", "-qm", "deps: pre-baseline")
    repo.write("tests/test_health.py", GREENFIELD_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")

    assert _run(repo) == 0
    assert "baseline/demo-001" in repo.tags()


def test_e2e_greenfield_own_package_import_ungrouped_refused_at_baseline(tmp_path: Path, capsys) -> None:
    # notes/18 regression: the own-package import grouped with third-party (clean while src/ is
    # absent under naive isort, I001 once src/ exists) is the drift that ESCALATEd users/001. With
    # known-first-party pinned, the baseline lint screen judges it as the gate will and REFUSES the
    # tag — so the test-author fixes it at author time, not the implementer at an unwinnable gate.
    ungrouped = GREENFIELD_TESTS.replace("import pytest\n\nfrom app", "import pytest\nfrom app")
    repo = _base_repo(tmp_path)
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.git("add", "-A")
    repo.git("commit", "-qm", "deps: pre-baseline")
    repo.write("tests/test_health.py", ungrouped)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests, own-package import ungrouped")

    assert _run(repo) == 1
    assert "I001" in "".join(capsys.readouterr())
    assert "baseline/demo-001" not in repo.tags()


def test_e2e_brownfield_broken_import_still_fails_no_tag(tmp_path: Path) -> None:
    # Brownfield: the package EXISTS but a test mis-imports a submodule (typo) → a real broken
    # test. The greenfield fallback must NOT mask it: red_check fails on the missing markers.
    repo = _base_repo(tmp_path)
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.write("src/app/__init__.py", "")
    repo.write("src/app/restapi/__init__.py", "")
    repo.write("src/app/restapi/main.py", "def create_app() -> object:\n    return object()\n")
    repo.git("add", "-A")
    repo.git("commit", "-qm", "deps + existing package")
    repo.write(
        "tests/test_health.py",
        "from app.restapi.mian import create_app  # typo: mian\n\nimport pytest\n\n\n"
        '@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    assert create_app() is not None\n\n\n'
        '@pytest.mark.ac("AC-2")\ndef test_b() -> None:\n    assert True\n',
    )
    repo.git("add", "-A")
    repo.git("commit", "-qm", "broken test")

    assert _run(repo) == 1
    assert "baseline/demo-001" not in repo.tags()


# --- re-baseline after a TESTS-HANDBACK (notes/18) -------------------------------------
#
# The handback fixes tests/** while the implementer's src/ is UNCOMMITTED, then the baseline tag
# must move onto the corrected tests commit. --rebaseline must do that without stashing: redness
# judged in a worktree of the candidate commit (src/ absent there), mypy judged in the live tree
# (src/ present). These tests pin both worlds and the two integrity refusals.

SRC_SHELL = {
    "src/app/__init__.py": "",
    "src/app/restapi/__init__.py": "",
    "src/app/restapi/main.py": "def create_app() -> object:\n    return object()\n",
}


def _handback_repo(tmp_path: Path) -> FixtureRepo:
    """A repo at the handback moment: baseline tagged on the red tests, src/ uncommitted."""
    repo = _base_repo(tmp_path)
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.git("add", "-A")
    repo.git("commit", "-qm", "deps: pre-baseline")
    repo.write("tests/test_health.py", GREENFIELD_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")
    assert _run(repo) == 0  # tags baseline/demo-001 on the red-tests commit
    return repo


def test_rebaseline_moves_the_tag_without_stashing_uncommitted_src(tmp_path: Path) -> None:
    # The money test: the implementer's src/ is present and UNCOMMITTED in the live tree, so an
    # in-place redness re-run would see the package and prove nothing (that is why the manual
    # recovery had to stash). --rebaseline judges redness in a worktree of the candidate commit,
    # where src/ is absent by construction — no stash, and the live src/ is left untouched.
    repo = _handback_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()

    repo.write("tests/test_health.py", GREENFIELD_TESTS.replace("# the whole", "# corrected; the whole"))
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: corrected tests (handback)")
    for rel, content in SRC_SHELL.items():  # the implementer's work — deliberately NOT committed
        repo.write(rel, content)

    assert _run(repo, "--rebaseline") == 0
    head = repo.git("rev-parse", "HEAD").strip()
    assert repo.git("rev-parse", "baseline/demo-001").strip() == head
    assert head != old
    for rel in SRC_SHELL:  # the live work tree survived the move
        assert (repo.root / rel).exists()


def test_rebaseline_refuses_a_commit_that_writes_outside_tests(tmp_path: Path) -> None:
    # A baseline move is still the test-author's lane: src/ in the re-baseline commit is the
    # anti-collusion case (§4/D3), refused exactly as at the first tagging.
    repo = _handback_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    repo.write("tests/test_health.py", GREENFIELD_TESTS.replace("# the whole", "# corrected; the whole"))
    for rel, content in SRC_SHELL.items():
        repo.write(rel, content)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: corrected + smuggled src")

    assert _run(repo, "--rebaseline") == 1
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old  # tag did NOT move


def test_rebaseline_refuses_when_an_ac_marked_test_disappeared(tmp_path: Path, capsys) -> None:
    # Moving the tag re-anchors gate.py's integrity.test-inventory, so a test dropped in the
    # handback would become invisible to it. Refuse the move and name the lost node-id.
    repo = _handback_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    dropped = GREENFIELD_TESTS.split('@pytest.mark.ac("AC-2")')[0].rstrip() + "\n"
    repo.write("tests/test_health.py", dropped)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: corrected but AC-2 test dropped")

    assert _run(repo, "--rebaseline") == 1
    assert "tests/test_health.py::test_health_status_ok" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


# The users/001 root-cause regression: tests that are RED and ruff-clean but do NOT type-check
# against the existing src/. This is precisely what the old baseline screen could not see (it
# skips mypy, undecidable while src/ is absent) and what left the implementer at an unwinnable
# gate. At re-baseline time src/ EXISTS, so the check is finally decidable — and must refuse.
MYPY_DIRTY_TESTS = """\
# red in a worktree (package absent), ruff-clean, but mypy-dirty against a present src/
import pytest

from app.restapi.main import create_app


def _built() -> object:
    return create_app()


@pytest.mark.ac("AC-1")
def test_health_status_field() -> None:
    assert _built().status is None


@pytest.mark.ac("AC-2")
def test_health_status_ok() -> None:
    assert _built() is not None
"""


def test_rebaseline_refuses_tests_that_do_not_typecheck_against_the_present_src(tmp_path: Path, capsys) -> None:
    repo = _handback_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    repo.write("tests/test_health.py", MYPY_DIRTY_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: corrected imports but still mypy-dirty")
    for rel, content in SRC_SHELL.items():
        repo.write(rel, content)

    assert _run(repo, "--rebaseline") == 1
    out = "".join(capsys.readouterr())
    assert "BASELINE MYPY: FAILED" in out
    assert "attr-defined" in out
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old  # tag did NOT move


def test_rebaseline_without_an_existing_tag_is_an_error(tmp_path: Path) -> None:
    # --rebaseline *moves* a tag; a first baseline must go through the normal red_check path.
    repo = _base_repo(tmp_path)
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.write("tests/test_health.py", GREENFIELD_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests, never tagged")

    assert _run(repo, "--rebaseline") == 2
    assert "baseline/demo-001" not in repo.tags()


# --- baseline lint screen (T09f) -------------------------------------------------------
#
# A lint defect in the RED baseline's tests/** deadlocks the implementer (tool-blocked from
# tests/**, ruff is per-file), so red_check must refuse to tag a lint-dirty baseline.

# The health/001 shape: two third-party imports split into two blocks by a blank line (I001).
I001_CONFTEST = """\
import pytest

import httpx


@pytest.fixture
def client() -> object:
    return httpx.Client()
"""


def test_lint_tests_flags_i001_split_imports(tmp_path: Path) -> None:
    (tmp_path / "tests" / "integration").mkdir(parents=True)
    (tmp_path / "tests" / "integration" / "conftest.py").write_text(I001_CONFTEST)
    failures = red_check.lint_tests(tmp_path)
    assert failures, "an I001 split-import block must be caught"
    assert "conftest.py" in "\n".join(failures)


def test_lint_tests_clean_tree_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        'import pytest\n\n\n@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    assert True\n'
    )
    assert red_check.lint_tests(tmp_path) == []


def test_lint_tests_catches_format_only_violation(tmp_path: Path) -> None:
    # Lint-passing but badly formatted (extra spaces around the operator) — the format arm
    # must catch what ruff-check alone would let through.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fmt.py").write_text("x = 1+2\n")
    failures = red_check.lint_tests(tmp_path)
    assert any("format" in f for f in failures), f"format arm should fire: {failures}"


def _conftest_with_split_imports(repo: FixtureRepo) -> None:
    repo.write("tests/integration/conftest.py", I001_CONFTEST)


def test_e2e_lint_dirty_baseline_refused_no_tag(tmp_path: Path, capsys) -> None:
    # RED baseline whose conftest.py has the health/001 I001 defect: coverage + redness pass,
    # but the lint screen refuses to tag (else the implementer would deadlock).
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    _conftest_with_split_imports(repo)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests + lint-dirty conftest")

    assert _run(repo) == 1
    combined = capsys.readouterr()
    assert "conftest.py" in (combined.out + combined.err)
    assert "baseline/demo-001" not in repo.tags()

    # After ruff --fix on the offending file, the same command is RED-CONFIRMED and tags.
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--fix", "--select", "I", str(repo.root / "tests")],
        check=True,
        capture_output=True,
    )
    repo.git("add", "-A")
    repo.git("commit", "-qm", "ruff --fix conftest")
    assert _run(repo) == 0
    assert "baseline/demo-001" in repo.tags()


def test_e2e_lint_clean_baseline_still_tagged(tmp_path: Path) -> None:
    # No regression: a lint-clean RED baseline is still RED-CONFIRMED and tagged as before.
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")

    assert _run(repo) == 0
    assert "baseline/demo-001" in repo.tags()


def test_resolve_change_autodetects_single_change_dir(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    change_id, change_dir = red_check.resolve_change(repo.root, None)
    assert change_id == "demo/001"
    assert change_dir.name == "001-health"


def test_resolve_change_rejects_bad_id(tmp_path: Path) -> None:
    with pytest.raises(red_check.RedCheckError):
        red_check.resolve_change(tmp_path, "not-a-change-id")


# --- toolchain preflight (T06j) --------------------------------------------------------


def test_required_toolchain_is_what_red_check_invokes_not_the_gate_set(tmp_path: Path) -> None:
    # Deliberately NOT the gate's set: mypy is absent at baseline time (T09f — a greenfield
    # first change imports a not-yet-written package, which is the intended redness), and only
    # --rebaseline runs it, only where mypy_tests() would (a live tree with src/).
    bare = tmp_path / "bare"
    bare.mkdir()
    assert red_check.required_toolchain(bare) == []

    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    assert red_check.required_toolchain(app) == ["pytest", "ruff"]
    assert red_check.required_toolchain(app, rebaseline=True) == ["pytest", "ruff"]  # no src/ → no mypy

    (app / "src").mkdir()
    assert red_check.required_toolchain(app) == ["pytest", "ruff"]  # a normal run never runs mypy
    assert red_check.required_toolchain(app, rebaseline=True) == ["pytest", "ruff", "mypy"]


def test_preflight_is_silent_when_the_toolchain_is_present(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    red_check.preflight_toolchain(tmp_path)  # this interpreter has pytest + ruff — no raise


def test_e2e_missing_toolchain_is_a_sentence_not_a_traceback(tmp_path: Path) -> None:
    # A consumer's very first change: red_check is the first script the workflow runs, in an
    # environment that has no ruff/pytest yet. Before T06j that surfaced as a raw
    # `No module named ruff` (or a misattributed "pytest produced no inventory"); now the same
    # sentence gate.py would give — naming the tools and how to install them — comes out first.
    repo = _base_repo(tmp_path / "app")
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")

    bare = tmp_path / "bare-venv"
    made = subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], capture_output=True)
    if made.returncode != 0:  # pragma: no cover — environment without ensurepip/venv
        pytest.skip("python -m venv unavailable")
    python = bare / "bin" / "python"
    if not python.exists():  # pragma: no cover — Windows layout
        python = bare / "Scripts" / "python.exe"

    proc = subprocess.run(
        [str(python), str(TOOLS_DIR / "red_check.py"), str(repo.root), "--change", "demo/001"],
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 2, output  # 2 = could not run, distinct from a failed check's 1
    assert "toolchain missing from this project's environment" in output
    assert "pytest" in output and "ruff" in output
    assert "mypy" not in output  # red_check does not run mypy at baseline time (T09f)
    assert "[dependency-groups]" in output and "uv sync" in output
    assert "Traceback" not in output
    assert "baseline/demo-001" not in repo.tags()  # nothing tagged off an unrunnable check


# --- --clear-escalate: the sanctioned way to clear a §5.3 lock (T06h) ------------------
#
# Since T06h the SubagentStop hook COMMITS the ESCALATE, so gate.py sees its removal and goes
# RED — which means clearing a lock needs a baseline move, and --rebaseline cannot serve: it
# refuses any commit outside tests/**. --clear-escalate is that move, and only that move: three
# guards keep it strictly narrower than --rebaseline, so the old and new baseline trees differ
# by nothing but the lock.

ESCALATE_REL = "specs/demo/changes/001-health/ESCALATE"


def _escalated_repo(tmp_path: Path) -> FixtureRepo:
    """A repo at the escalation moment: red baseline tagged, the lock committed on top of it."""
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")
    assert _run(repo) == 0  # tags baseline/demo-001 on the red-tests commit
    repo.write(ESCALATE_REL, "# ESCALATE (hook-authored)\n\ngate.py stayed RED after 3 passes.\n")
    repo.git("add", "--", ESCALATE_REL)
    repo.git("commit", "-qm", "hook: escalate", "--", ESCALATE_REL)
    return repo


def _remove_escalate(repo: FixtureRepo) -> None:
    repo.git("rm", "-q", "--", ESCALATE_REL)
    repo.git("commit", "-qm", "human clears the ESCALATE", "--", ESCALATE_REL)


def test_clear_escalate_moves_the_baseline_over_the_removal(tmp_path: Path, capsys) -> None:
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    _remove_escalate(repo)

    assert _run(repo, "--clear-escalate") == 0
    head = repo.git("rev-parse", "HEAD").strip()
    assert repo.git("rev-parse", "baseline/demo-001").strip() == head
    assert head != old
    out = "".join(capsys.readouterr())
    assert "CLEAR-ESCALATE: OK" in out
    assert ESCALATE_REL in out  # the report names what was cleared


def test_clear_escalate_refuses_when_nothing_was_escalated(tmp_path: Path, capsys) -> None:
    # Guard (i): this flag is not a general-purpose tag mover.
    repo = _base_repo(tmp_path)
    repo.write("tests/test_health.py", RED_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "red tests")
    assert _run(repo) == 0
    old = repo.git("rev-parse", "baseline/demo-001").strip()

    assert _run(repo, "--clear-escalate") == 1
    assert "no ESCALATE was committed on this branch" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_refuses_while_the_lock_still_stands(tmp_path: Path, capsys) -> None:
    # Guard (i): the tag may only move over a lock that is actually GONE.
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()

    assert _run(repo, "--clear-escalate") == 1
    assert "still in the work tree" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_refuses_an_uncommitted_removal(tmp_path: Path, capsys) -> None:
    # Guard (i): a work-tree deletion is not a record. Moving the tag onto HEAD would carry the
    # lock into the new baseline, leaving the gate RED for a reason nobody could see.
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    (repo.root / ESCALATE_REL).unlink()

    assert _run(repo, "--clear-escalate") == 1
    assert "not COMMITTED" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_refuses_a_range_that_carries_anything_else(tmp_path: Path, capsys) -> None:
    # Guard (ii) — the guard that makes this narrower than --rebaseline: a criteria flip riding
    # along in the range would be re-anchored by the move, laundering it past every integrity
    # check gate.py makes against the baseline.
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    _remove_escalate(repo)
    repo.write("specs/demo/changes/001-health/criteria.md", CRITERIA_MD.replace("- [ ] AC-1", "- [x] AC-1"))
    repo.git("add", "-A")
    repo.git("commit", "-qm", "flip AC-1 while nobody is looking")

    assert _run(repo, "--clear-escalate") == 1
    out = "".join(capsys.readouterr())
    assert "specs/demo/changes/001-health/criteria.md" in out
    assert "Clear the lock FIRST" in out  # the ordering rule is stated, not left to be guessed
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_refuses_a_dropped_ac_marked_test(tmp_path: Path, capsys) -> None:
    # Guard (iii), the --rebaseline guard reused: a baseline move must never drop a test. Guard
    # (ii) fires on the same commit (tests/** is not an ESCALATE), and BOTH reasons are reported —
    # the move is refused for the narrow reason and for the inventory reason.
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    _remove_escalate(repo)
    repo.write("tests/test_health.py", RED_TESTS.split('@pytest.mark.ac("AC-2")')[0].rstrip() + "\n")
    repo.git("add", "-A")
    repo.git("commit", "-qm", "drop the AC-2 test")

    assert _run(repo, "--clear-escalate") == 1
    out = "".join(capsys.readouterr())
    assert "tests/test_health.py::test_health_status_ok" in out  # guard (iii): the lost node-id
    assert "must not drop a test" in out  # guard (iii)'s reason
    assert "Clear the lock FIRST" in out  # guard (ii) fires on the same commit
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_refuses_a_merge_commit_in_the_range(tmp_path: Path, capsys) -> None:
    # `diff-tree` prints no names for a merge, which would read as "this commit touches nothing"
    # and let an arbitrary tree into the new baseline — notes/19's fail-open class.
    repo = _escalated_repo(tmp_path)
    old = repo.git("rev-parse", "baseline/demo-001").strip()
    _remove_escalate(repo)
    repo.git("checkout", "-q", "-b", "side", old)
    repo.write("tests/test_side.py", "def test_side() -> None:\n    assert True\n")
    repo.git("add", "-A")
    repo.git("commit", "-qm", "side work")
    repo.git("checkout", "-q", "-")
    repo.git("merge", "-q", "--no-ff", "-m", "merge side", "side")

    assert _run(repo, "--clear-escalate") == 1
    assert "a merge commit" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-001").strip() == old


def test_clear_escalate_without_an_existing_tag_is_an_error(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    assert _run(repo, "--clear-escalate") == 2


def test_clear_escalate_and_rebaseline_are_not_combinable(tmp_path: Path) -> None:
    # Two different baseline moves with two different guard sets: running both at once would make
    # it unclear which one licensed the move.
    with pytest.raises(SystemExit) as exc:
        red_check.main([str(tmp_path), "--change", "demo/001", "--rebaseline", "--clear-escalate"])
    assert exc.value.code == 2


# =======================================================================================
# `Class: hardening` — the baseline proved by MUTATION, because it has no red phase (T09g)
# =======================================================================================
#
# The change shape the cycle had no lane for: the tests get stronger while behaviour stays
# identical (a prior adversarial pass found a mutation the suite did not kill). Such tests are
# green on arrival, so redness cannot be their baseline property; this class replaces it with
# GREEN-on-clean + RED-on-mutation. The fixtures below are the users/002 **F1** shape verbatim,
# reduced to one function: a `save` that filters by key, a weak suite that a filter-dropping
# mutation walks straight through, and the strengthened suite that kills it.

CHANGE_TEMPLATE = (TOOLS_DIR.parent / "templates" / "change.md").read_text(encoding="utf-8")


# --- pure: the change.md parse ---------------------------------------------------------


def test_parse_change_class_defaults_to_behavioral() -> None:
    assert red_check.parse_change_class("") == "behavioral"
    assert red_check.parse_change_class("# demo/001 — x\n\n## Task\nwhatever\n") == "behavioral"


def test_parse_change_class_reads_the_declared_class() -> None:
    assert red_check.parse_change_class("Class: hardening\n") == "hardening"
    assert red_check.parse_change_class("Class: Hardening    <!-- comment -->\n") == "hardening"
    assert red_check.parse_change_class("Class: invisible\n") == "invisible"


def test_parse_change_class_ignores_the_template_comment() -> None:
    # The template's own comment enumerates every class name, `hardening` included. A change that
    # kept the comment declares `behavioral` — the same trap accept.classify_removal disarms.
    assert "hardening" in CHANGE_TEMPLATE  # the trap is really in the template
    assert red_check.parse_change_class(CHANGE_TEMPLATE) == "behavioral"


def test_parse_mutations_reads_the_fenced_diffs_and_their_ac_ids() -> None:
    change_md = (
        "Class: hardening\n\n## Acceptance criteria\n- AC-9 something\n\n"
        "## Mutations\n\n"
        "### M-1 — must kill AC-1, AC-2\n\n"
        "```diff\n--- a/src/app/store.py\n+++ b/src/app/store.py\n@@ -1 +1 @@\n-old\n+new\n```\n\n"
        "The second one must kill AC-2 only:\n\n"
        "```diff\n--- a/src/app/other.py\n+++ b/src/app/other.py\n@@ -1 +1 @@\n-a\n+b\n```\n\n"
        "## Verification\n- AC-3 is not a mutation id\n"
    )
    mutations = red_check.parse_mutations(change_md)
    assert [(m.mid, m.ac_ids) for m in mutations] == [("M-1", ("AC-1", "AC-2")), ("M-2", ("AC-2",))]
    assert mutations[0].paths == ("src/app/store.py",)
    # the section ends at the next same-or-shallower heading: AC-3 (Verification) leaked nowhere
    assert all("AC-3" not in m.ac_ids for m in mutations)


def test_parse_mutations_is_empty_without_the_section_and_for_the_template() -> None:
    assert red_check.parse_mutations("Class: hardening\n\n## Task\nx\n") == []
    # the template's EXAMPLE diff lives inside the section's HTML comment, so a change that kept
    # the comment declares no mutation (it must not read as a satisfied obligation)
    assert "## Mutations" in CHANGE_TEMPLATE
    assert red_check.parse_mutations(CHANGE_TEMPLATE) == []


def test_section_body_survives_a_subheading_and_matches_any_depth() -> None:
    text = "## Mutations\nbody\n### M-1\nmore\n## Verification\nout\n"
    assert red_check.section_body(text, "Mutations") == "\nbody\n### M-1\nmore\n"
    assert red_check.section_body("### Mutations\nb\n## Next\n", "Mutations") == "\nb\n"
    assert red_check.section_body(text, "Nope") is None


def test_mutation_paths_drop_the_dev_null_side() -> None:
    mutation = red_check.Mutation("M-1", ("AC-1",), "--- /dev/null\n+++ b/src/app/new.py\n@@ -0,0 +1 @@\n+x\n")
    assert mutation.paths == ("src/app/new.py",)


# --- pure: analyze_green + the declaration screen ---------------------------------------


def test_analyze_green_wants_marked_tests_to_pass() -> None:
    inv = {
        "outcomes": {"tests/t.py::a": "passed", "tests/t.py::b": "failed"},
        "markers": {"tests/t.py::a": ["AC-1"], "tests/t.py::b": ["AC-2"]},
    }
    result = red_check.analyze_green(["AC-1", "AC-2"], inv)
    assert not result.ok
    assert result.passed_tests == ["tests/t.py::a"]
    assert result.not_green == [("tests/t.py::b", "failed")]

    ok = red_check.analyze_green(["AC-1"], inv)
    assert ok.ok and ok.missing_acs == []


def test_analyze_green_reports_an_uncovered_ac() -> None:
    inv = {"outcomes": {"tests/t.py::a": "passed"}, "markers": {"tests/t.py::a": ["AC-1"]}}
    result = red_check.analyze_green(["AC-1", "AC-2"], inv)
    assert not result.ok and result.missing_acs == ["AC-2"]


def test_analyze_green_ignores_tests_of_other_changes_acs() -> None:
    # A hardening change is brownfield: older changes' tests carry their own ac markers. Their
    # state is the gate's business, not this baseline's — judging them here would make an
    # unrelated failure anywhere in the suite refuse a correct hardening baseline.
    inv = {
        "outcomes": {"tests/new.py::a": "passed", "tests/old.py::z": "failed"},
        "markers": {"tests/new.py::a": ["AC-1"], "tests/old.py::z": ["AC-7"]},
    }
    assert red_check.analyze_green(["AC-1"], inv).ok


def _mutation(diff: str, *, mid: str = "M-1", acs: tuple[str, ...] = ("AC-1",)):  # noqa: ANN202
    return red_check.Mutation(mid, acs, diff)


HUNK = "--- a/src/app/store.py\n+++ b/src/app/store.py\n@@ -1 +1 @@\n-old\n+new\n"


def test_declaration_defects_refuse_a_hardening_change_with_no_mutations() -> None:
    defects = red_check.mutation_declaration_defects(["AC-1"], [])
    assert len(defects) == 1
    assert "## Mutations" in defects[0]


def test_declaration_defects_refuse_a_mutation_outside_src() -> None:
    diff = HUNK.replace("src/app/store.py", "tests/test_store.py")
    defects = red_check.mutation_declaration_defects(["AC-1"], [_mutation(diff)])
    assert any("may only patch `src/**`" in d for d in defects), defects


def test_declaration_defects_refuse_a_traversal_back_into_tests() -> None:
    # `src/../tests/x.py` starts with `src/` and lands in the test tree — the one thing the
    # src-only rule exists to stop, so the prefix check alone is not the check.
    diff = HUNK.replace("src/app/store.py", "src/../tests/test_store.py")
    defects = red_check.mutation_declaration_defects(["AC-1"], [_mutation(diff)])
    assert any("may only patch `src/**`" in d for d in defects), defects


def test_declaration_defects_refuse_an_ac_no_mutation_names() -> None:
    defects = red_check.mutation_declaration_defects(["AC-1", "AC-2"], [_mutation(HUNK)])
    assert any(d.startswith("AC-2 is named by no mutation") for d in defects), defects


def test_declaration_defects_refuse_an_unknown_ac_and_a_non_diff() -> None:
    defects = red_check.mutation_declaration_defects(["AC-1"], [_mutation("prose, not a patch", acs=("AC-1", "AC-9"))])
    assert any("not a unified diff" in d for d in defects), defects
    assert any("AC-9, which is not in criteria.md" in d for d in defects), defects


def test_declaration_defects_refuse_a_mutation_naming_no_ac() -> None:
    defects = red_check.mutation_declaration_defects(["AC-1"], [_mutation(HUNK, acs=())])
    assert any("names no AC id" in d for d in defects), defects


# --- end-to-end: the F1 shape ----------------------------------------------------------

STORE_SRC = '''\
def save(rows: dict[str, str], key: str, value: str) -> dict[str, str]:
    """Return `rows` with the single row `key` updated to `value`."""
    return {k: (value if k == key else v) for k, v in rows.items()}
'''

# users/002's F1 verbatim, one function down: the row filter is gone, so a "single-row update"
# rewrites EVERY row. The shipped code is correct; this is the wrong code the tests must catch.
STORE_SRC_MUTATED = '''\
def save(rows: dict[str, str], key: str, value: str) -> dict[str, str]:
    """Return `rows` with the single row `key` updated to `value`."""
    return {k: value for k in rows}
'''

# The strengthened suite: each test has a BYSTANDER row, which is exactly what F1 said was
# missing ("AC-8 and AC-9 each create exactly one user").
STRONG_TESTS = """\
import pytest

from app.store import save


@pytest.mark.ac("AC-1")
def test_save_updates_only_the_named_row() -> None:
    assert save({"a": "1", "b": "1"}, "a", "2") == {"a": "2", "b": "1"}


@pytest.mark.ac("AC-2")
def test_save_leaves_a_bystander_row_untouched() -> None:
    assert save({"a": "1", "b": "1"}, "a", "2")["b"] == "1"
"""

# The suite as it was BEFORE the hardening change: green, and blind to F1 — one row only, so
# dropping the filter changes nothing it looks at. This is the "advisory theatre" state.
WEAK_TESTS = """\
import pytest

from app.store import save


@pytest.mark.ac("AC-1")
def test_save_updates_only_the_named_row() -> None:
    assert save({"a": "1"}, "a", "2") == {"a": "2"}


@pytest.mark.ac("AC-2")
def test_save_leaves_a_bystander_row_untouched() -> None:
    assert save({"a": "1"}, "a", "2")["a"] == "2"
"""

HARDENING_CRITERIA = """\
# Criteria — demo/002-harden-save

- [ ] AC-1: updating one row returns the other rows with their previous values
- [ ] AC-2: after updating row `a`, reading row `b` returns `b`'s old value
"""

CHANGE_DIR = "specs/demo/changes/002-harden-save"

# The mutation as a human writes it into change.md: a unified diff of STORE_SRC -> STORE_SRC_MUTATED.
F1_DIFF = '''\
--- a/src/app/store.py
+++ b/src/app/store.py
@@ -1,3 +1,3 @@
 def save(rows: dict[str, str], key: str, value: str) -> dict[str, str]:
     """Return `rows` with the single row `key` updated to `value`."""
-    return {k: (value if k == key else v) for k, v in rows.items()}
+    return {k: value for k in rows}
'''


def _change_md(mutations: str | None) -> str:
    body = (
        "# demo/002 — strengthen the save() criteria\n\n"
        "Class: hardening\n\n"
        "## Task\nAC-1/AC-2 pass against a save() that rewrites every row. Strengthen them.\n\n"
        "## Acceptance criteria\n- AC-1: only the named row changes\n- AC-2: a bystander keeps its value\n"
    )
    return body if mutations is None else f"{body}\n## Mutations\n\n{mutations}"


def _mutation_block(diff: str, *, mid: str = "M-1", acs: str = "AC-1, AC-2") -> str:
    return f"### {mid} — must kill {acs}\n\n```diff\n{diff}```\n"


_DEFAULT_MUTATIONS = _mutation_block(F1_DIFF)


def _hardening_repo(
    tmp_path: Path,
    *,
    tests: str = STRONG_TESTS,
    mutations: str | None = _DEFAULT_MUTATIONS,
    also_in_baseline: dict[str, str] | None = None,
) -> FixtureRepo:
    """A brownfield repo with correct, committed src/, then the /spec commit, then the tests commit.

    By default the `## Mutations` section declares the F1 mutation over both ACs; pass another
    block, or None to leave the section out entirely.
    """
    repo = FixtureRepo(tmp_path)
    repo.write(".gitignore", ".gate/\n__pycache__/\n.pytest_cache/\n")
    repo.write("pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    repo.write("src/app/__init__.py", "")
    repo.write("src/app/store.py", STORE_SRC)
    repo.git("init", "-q")
    repo.git("add", "-A")
    repo.git("commit", "-qm", "the shipped, correct app")

    repo.write(f"{CHANGE_DIR}/criteria.md", HARDENING_CRITERIA)
    repo.write(f"{CHANGE_DIR}/change.md", _change_md(mutations))
    repo.git("add", "-A")
    repo.git("commit", "-qm", "spec: demo/002 (hardening)")

    repo.write("tests/test_store.py", tests)
    for rel, content in (also_in_baseline or {}).items():
        repo.write(rel, content)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: strengthen AC-1/AC-2")
    return repo


def _run_hardening(repo: FixtureRepo, *extra: str) -> int:
    return red_check.main([str(repo.root), "--change", "demo/002", *extra])


def test_e2e_hardening_baseline_is_confirmed_by_mutation_and_tagged(tmp_path: Path, capsys) -> None:
    # The money test: no red phase anywhere, and the baseline is still earned — the tests pass
    # against the shipped code AND both ACs go RED under the declared mutation.
    repo = _hardening_repo(tmp_path)

    assert _run_hardening(repo) == 0
    out = "".join(capsys.readouterr())
    assert "HARDENING-CHECK: MUTATION-CONFIRMED" in out
    assert "GREEN ON CLEAN: 2 ac-marked test(s) pass" in out
    assert "[KILLED  ] M-1 AC-1: tests/test_store.py::test_save_updates_only_the_named_row" in out
    assert "[KILLED  ] M-1 AC-2:" in out
    assert "baseline/demo-002" in repo.tags()


def test_e2e_hardening_refuses_the_weak_suite_the_mutation_survives(tmp_path: Path, capsys) -> None:
    # The pre-hardening suite: green on clean code, blind to F1. This is the state the adversarial
    # pass reported, and a baseline must not be earned by it — the change would ship no strength.
    repo = _hardening_repo(tmp_path, tests=WEAK_TESTS)

    assert _run_hardening(repo) == 1
    out = "".join(capsys.readouterr())
    assert "[SURVIVED] M-1 AC-1:" in out
    assert "[SURVIVED] M-1 AC-2:" in out
    assert "HARDENING-CHECK: FAILED" in out
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_refuses_tests_that_fail_against_the_shipped_code(tmp_path: Path, capsys) -> None:
    # Behaviour is identical in a hardening change, so a marked test that FAILS on the unmutated
    # code is a real defect (a wrong assertion, or a behaviour change smuggled into the class) —
    # never a red baseline to be tagged.
    broken = STRONG_TESTS.replace('== {"a": "2", "b": "1"}', '== {"a": "2", "b": "2"}')
    repo = _hardening_repo(tmp_path, tests=broken)

    assert _run_hardening(repo) == 1
    out = "".join(capsys.readouterr())
    assert "NOT GREEN ON CLEAN" in out
    assert "tests/test_store.py::test_save_updates_only_the_named_row [failed]" in out
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_refuses_a_change_with_no_mutations_section(tmp_path: Path, capsys) -> None:
    # Without a mutation the class has NO baseline property at all: not redness (the tests pass),
    # not a kill (none is declared). Refused before a single test runs.
    repo = _hardening_repo(tmp_path, mutations=None)

    assert _run_hardening(repo) == 1
    out = "".join(capsys.readouterr())
    assert "MUTATION DECLARATION" in out
    assert "## Mutations" in out
    assert "GREEN ON CLEAN" not in out  # the declaration is screened first — nothing was run
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_refuses_a_mutation_that_patches_a_test(tmp_path: Path, capsys) -> None:
    # A "mutation" that deletes an assertion makes the suite fail for a reason that proves
    # nothing — the cheapest way to fake this class's proof. src/** only.
    fake = "--- a/tests/test_store.py\n+++ b/tests/test_store.py\n@@ -1 +1 @@\n-import pytest\n+raise SystemExit\n"
    repo = _hardening_repo(tmp_path, mutations=_mutation_block(fake))

    assert _run_hardening(repo) == 1
    assert "may only patch `src/**`" in "".join(capsys.readouterr())
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_refuses_an_ac_that_no_mutation_names(tmp_path: Path, capsys) -> None:
    # AC-2 would then have no proof of strength at all — neither redness (it passes) nor a kill.
    repo = _hardening_repo(tmp_path, mutations=_mutation_block(F1_DIFF, acs="AC-1"))

    assert _run_hardening(repo) == 1
    assert "AC-2 is named by no mutation" in "".join(capsys.readouterr())
    assert "baseline/demo-002" not in repo.tags()


STALE_DIFF = """\
--- a/src/app/store.py
+++ b/src/app/store.py
@@ -1,2 +1,2 @@
-def gone(rows: dict[str, str]) -> None:
-    return None
+def gone(rows: dict[str, str]) -> int:
+    return 0
"""


def test_e2e_hardening_refuses_a_patch_that_does_not_apply(tmp_path: Path, capsys) -> None:
    # A mutation lifted from an older verdict may no longer describe the code. Silence here would
    # mean "no ac test went red" — i.e. an unappliable patch would read as a survived mutation and
    # blame the tests; the report must name the real cause.
    repo = _hardening_repo(tmp_path, mutations=_mutation_block(STALE_DIFF))

    assert _run_hardening(repo) == 1
    out = "".join(capsys.readouterr())
    assert "[ERROR   ] M-1" in out
    assert "does not apply" in out
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_baseline_commit_must_still_be_tests_only(tmp_path: Path, capsys) -> None:
    # The anti-collusion screen is class-independent: whatever proved the baseline, the commit
    # being tagged touches tests/** only. A hardening change that edits src/ is a different change.
    repo = _hardening_repo(tmp_path, also_in_baseline={"src/app/store.py": STORE_SRC + "\n\nEXTRA = 1\n"})

    assert _run_hardening(repo) == 1
    combined = capsys.readouterr()
    assert "src/app/store.py" in (combined.out + combined.err)
    assert "baseline/demo-002" not in repo.tags()


def test_e2e_hardening_no_tag_flag_still_skips_tagging(tmp_path: Path) -> None:
    repo = _hardening_repo(tmp_path)
    assert _run_hardening(repo, "--no-tag") == 0
    assert "baseline/demo-002" not in repo.tags()


def test_rebaseline_routes_a_hardening_change_through_the_mutation_path(tmp_path: Path, capsys) -> None:
    # A TESTS-HANDBACK can happen here too (a lint/type defect in the new tests, which no src/**
    # edit could fix — this class has no implementer at all). The tag must move over the corrected
    # tests without a hand `git tag -f`, asking the hardening question, not for redness.
    repo = _hardening_repo(tmp_path, tests=WEAK_TESTS)
    repo.git("tag", "baseline/demo-002")  # the baseline as it stood when the handback happened
    old = repo.git("rev-parse", "baseline/demo-002").strip()

    repo.write("tests/test_store.py", STRONG_TESTS)
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: strengthen after the handback")

    assert _run_hardening(repo, "--rebaseline") == 0
    out = "".join(capsys.readouterr())
    assert "HARDENING-CHECK: MUTATION-CONFIRMED" in out
    assert "RED-CHECK" not in out  # the class's question was asked, not redness
    head = repo.git("rev-parse", "HEAD").strip()
    assert repo.git("rev-parse", "baseline/demo-002").strip() == head != old


def test_rebaseline_of_a_hardening_change_refuses_a_suite_that_lost_its_bite(tmp_path: Path, capsys) -> None:
    repo = _hardening_repo(tmp_path)
    assert _run_hardening(repo) == 0  # a real, mutation-confirmed baseline first
    old = repo.git("rev-parse", "baseline/demo-002").strip()

    repo.write("tests/test_store.py", WEAK_TESTS)  # a "correction" that drops the bystander
    repo.git("add", "-A")
    repo.git("commit", "-qm", "test: weaken back")

    assert _run_hardening(repo, "--rebaseline") == 1
    assert "[SURVIVED] M-1" in "".join(capsys.readouterr())
    assert repo.git("rev-parse", "baseline/demo-002").strip() == old  # tag did NOT move


def test_a_behavioral_change_keeps_the_red_requirement_even_with_a_mutations_section(tmp_path: Path, capsys) -> None:
    # No existing class loses its proof obligation: the mutation path is keyed on `Class:`, so a
    # behavioral change is still judged by redness — a `## Mutations` section does not license
    # green tests, and green-before-implementation still refuses the tag.
    repo = _base_repo(tmp_path)
    change_md = (
        "# demo/001 — health\n\nClass: behavioral\n\n## Mutations\n\n"
        "```diff\n--- a/src/app/main.py\n+++ b/src/app/main.py\n@@ -1 +1 @@\n-a\n+b\n```\n"
    )
    repo.write("specs/demo/changes/001-health/change.md", change_md)
    repo.write(
        "tests/test_health.py",
        "import pytest\n\n\n"
        '@pytest.mark.ac("AC-1")\ndef test_a() -> None:\n    assert True\n\n\n'
        '@pytest.mark.ac("AC-2")\ndef test_b() -> None:\n    assert True\n',
    )
    repo.git("add", "-A")
    repo.git("commit", "-qm", "green tests + a mutations section")

    assert _run(repo) == 1
    out = "".join(capsys.readouterr())
    assert "GREEN BEFORE IMPLEMENTATION" in out
    assert "HARDENING-CHECK" not in out
    assert "baseline/demo-001" not in repo.tags()
