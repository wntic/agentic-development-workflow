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


def test_resolve_change_autodetects_single_change_dir(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    change_id, change_dir = red_check.resolve_change(repo.root, None)
    assert change_id == "demo/001"
    assert change_dir.name == "001-health"


def test_resolve_change_rejects_bad_id(tmp_path: Path) -> None:
    with pytest.raises(red_check.RedCheckError):
        red_check.resolve_change(tmp_path, "not-a-change-id")
