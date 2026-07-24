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
