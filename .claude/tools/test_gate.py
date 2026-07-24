"""Test suite for gate.py (workflow v3, T04).

One fixture mini-tree per check class, red and green case each; the integrity cases
simulate real bypasses (spec §10 WP3: negative tests MUST include bypasses): criteria
reworded under the same checkboxes, baseline tests deleted / silenced via conftest /
skipped, gate.py edited on the work tree.

Every integration test copies gate.py + criteria_lint.py from this directory into an
isolated git fixture repo, commits them, tags the baseline, and runs THAT copy — so the
self-hash check judges the fixture repo's HEAD, not this repo's."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
TOOL_FILES = ("gate.py", "criteria_lint.py")

# --- fixture tree content (clean under gate.py's pinned mypy/ruff config) --------------

PYPROJECT = """\
[project]
name = "fixture-app"
version = "0.1.0"
requires-python = ">=3.12"
"""

GITIGNORE = """\
.gate/
__pycache__/
.pytest_cache/
"""

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

SRC_MAIN_BROKEN = '''\
"""Fixture app factory that raises at construction time (the A4 failure mode)."""


class App:
    """Minimal stand-in exposing the openapi() surface the smoke calls."""

    def openapi(self) -> dict[str, str]:
        return {"openapi": "3.1.0"}


def create_app() -> App:
    raise RuntimeError("missing framework dependency at construct time")
'''

TESTS_CORE = '''\
"""Fixture tests."""

import pytest

from app.core import add


@pytest.mark.ac("AC-1")
def test_add() -> None:
    assert add(1, 2) == 3


def test_add_zero() -> None:
    assert add(0, 0) == 0
'''

# An integration test that skips exactly when the gate's Docker probe is off. gate() sets
# GATE_DOCKER=0 in the subprocess env (never stripped), so this deterministically skips on
# every machine while --collect-only still records the node-id into the baseline inventory.
TESTS_INTEGRATION = '''\
"""Fixture integration test — needs a container; skips when the daemon is absent."""

import os

import pytest


@pytest.mark.skipif(os.environ.get("GATE_DOCKER") == "0", reason="needs docker daemon")
def test_needs_container() -> None:
    assert True
'''

# A unit test whose skip-reason STRING pretends docker is unavailable — it lives OUTSIDE
# tests/integration/, so the carve-out (directory-keyed) must not exempt it: RED.
TESTS_FAKE_DOCKER_SKIP = '''\
"""Fixture unit test that lies about docker in its skip reason (T04b: the string is not the key)."""

import pytest


@pytest.mark.skip(reason="docker unavailable")
def test_pretends_to_need_docker() -> None:
    assert True
'''

CHANGE_MD = """\
# demo/001 — fixture change

Class: behavioral

## Task
Provide `add` and the app factory for the gate fixture.

## Acceptance criteria
- AC-1: `app.core.add` returns `3` for input `1, 2`.
- AC-2: `create_app()` exposes a non-empty OpenAPI schema.
"""

CHANGE_MD_REMOVAL = """\
# demo/001 — fixture removal change

Class: behavioral

## Task
Remove the `add` behaviour (removal flavour).

Removed tests (obsolete with the removed behaviour):
- tests/test_core.py::test_add

## Acceptance criteria
- AC-1: `add` operation is gone from the app surface.
"""

CRITERIA_MD = """\
# Criteria — demo/001-thing

- [ ] AC-1: `app.core.add` returns the sum `3` for input `1, 2`
- [ ] AC-2: `create_app()` returns a non-empty `openapi` schema
"""

CAPABILITY_MD = """\
# demo — core capability

- The `add` operation returns the arithmetic sum (verified by: tests/test_core.py::test_add)
"""

VERDICT_MD_MANUAL = """\
# Verdict — demo/001

Gate: GREEN · SHA: fixture · junit: .gate/last-run.xml

## Per-criterion verdicts

- AC-2: MANUAL-candidate
  - state: [m]
  - proof: manual: accepted by the human — checked the schema by eye in the fixture
"""


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("gate_under_test", TOOLS_DIR / "gate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


gate = _load_gate_module()


class FixtureRepo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def append(self, rel: str, content: str) -> None:
        with (self.root / rel).open("a", encoding="utf-8") as fh:
            fh.write(content)

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=gate", "-c", "user.email=gate@test", *args],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"git {args} failed: {proc.stdout}{proc.stderr}"
        return proc.stdout

    def flip(self, ac_id: str, state: str) -> None:
        """Flip one criteria checkbox state in the work tree (the evaluator's move)."""
        rel = "specs/demo/changes/001-thing/criteria.md"
        text = (self.root / rel).read_text(encoding="utf-8")
        old = f"- [ ] {ac_id}:"
        assert old in text
        self.write(rel, text.replace(old, f"- [{state}] {ac_id}:"))

    def gate(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GATE_DOCKER"] = "0"  # deterministic across machines; the skip must be LOUD
        return subprocess.run(
            [sys.executable, str(self.root / ".claude/tools/gate.py"), *args, str(self.root)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.root,
        )

    def verdict(self) -> dict:
        return json.loads((self.root / ".gate/verdict.json").read_text(encoding="utf-8"))

    def statuses(self) -> dict[str, str]:
        return {c["id"]: c["status"] for c in self.verdict()["checks"]}


def make_repo(root: Path, *, change_md: str = CHANGE_MD, tag: bool = True) -> FixtureRepo:
    repo = FixtureRepo(root)
    repo.write("pyproject.toml", PYPROJECT)
    repo.write(".gitignore", GITIGNORE)
    repo.write("src/app/__init__.py", SRC_INIT)
    repo.write("src/app/core.py", SRC_CORE)
    repo.write("src/app/main.py", SRC_MAIN)
    repo.write("tests/test_core.py", TESTS_CORE)
    repo.write("specs/demo/core.md", CAPABILITY_MD)
    repo.write("specs/demo/changes/001-thing/change.md", change_md)
    repo.write("specs/demo/changes/001-thing/criteria.md", CRITERIA_MD)
    for name in TOOL_FILES:
        repo.write(f".claude/tools/{name}", (TOOLS_DIR / name).read_text(encoding="utf-8"))
    repo.git("init", "-q")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "red tests baseline (fixture)")
    if tag:
        repo.git("tag", "baseline/demo-001")
    return repo


@pytest.fixture()
def repo(tmp_path: Path) -> FixtureRepo:
    return make_repo(tmp_path / "app")


# ---------------------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------------------


def test_help_works() -> None:
    proc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "gate.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    for flag in ("--criteria", "--baseline", "--change"):
        assert flag in proc.stdout


def test_green_tree_is_green(repo: FixtureRepo) -> None:
    repo.flip("AC-1", "x")  # legal evaluator flip, junit-backed by the ac-marked test
    proc = repo.gate("--criteria", "--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GATE: GREEN" in proc.stdout
    assert "DOCKER SKIPPED" in proc.stdout  # loud, never silent
    verdict = repo.verdict()
    assert verdict["result"] == "GREEN"
    assert verdict["sha"] == repo.git("rev-parse", "HEAD").strip()
    assert verdict["baseline"] == "baseline/demo-001"
    assert (repo.root / ".gate/last-run.xml").exists()
    statuses = repo.statuses()
    for check_id in (
        "toolchain.mypy",
        "toolchain.ruff-check",
        "toolchain.ruff-format",
        "toolchain.pytest",
        "grep.not-implemented",
        "grep.no-orm",
        "grep.no-mocks",
        "smoke.construct",
        "criteria.junit-backing",
        "criteria.manual-verdict",
        "spec.invariant-tests",
        "integrity.protected-trees",
        "integrity.criteria-flips",
        "integrity.change-frozen",
        "integrity.test-inventory",
        "integrity.self-hash",
    ):
        assert statuses[check_id] == "PASS", (check_id, statuses)
    assert statuses["smoke.table-metadata"] == "SKIP"
    assert statuses["docker.alembic"] == "SKIP"


def test_red_localized_to_tests_when_only_tests_static_toolchain_red(tmp_path: Path) -> None:
    # notes/18: a RED whose ONLY failure is the static toolchain over tests/** cannot be cleared
    # by the implementer (src/** is its lane, D4). gate.py flags it so /implement hands back to
    # the test-author instead of looping to a spurious ESCALATE. Bake the tests-side defect
    # (own-package import ungrouped → I001) INTO the baseline so integrity passes and the
    # localization is isolated; src/ stays clean and the tests still run green.
    repo = make_repo(tmp_path / "app")
    repo.write(
        "tests/test_core.py", TESTS_CORE.replace("import pytest\n\nfrom app.core", "import pytest\nfrom app.core")
    )
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "-f", "baseline/demo-001")

    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    verdict = repo.verdict()
    assert verdict["result"] == "RED"
    assert verdict["failed"] == ["toolchain.ruff-check"], verdict["failed"]
    assert verdict["red_localized_to"] == "tests"
    assert "red localized to: tests/**" in proc.stdout


def test_red_localized_to_none_when_src_is_static_toolchain_red(tmp_path: Path) -> None:
    # The mirror case: the static-toolchain RED is in src/ (the implementer's OWN lane), so it is
    # NOT a handback — the localization signal must stay None even though the failing check id is
    # in the handback set. The src-alone re-run is what distinguishes the two.
    src_unsorted = '"""Fixture domain module."""\n\nimport sys\nimport os\n\n__all__ = ["add", "os", "sys"]\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
    repo = make_repo(tmp_path / "app")
    repo.write("src/app/core.py", src_unsorted)
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "-f", "baseline/demo-001")

    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    verdict = repo.verdict()
    assert verdict["result"] == "RED"
    assert "toolchain.ruff-check" in verdict["failed"]
    assert verdict["red_localized_to"] is None
    assert "red localized to: tests/**" not in proc.stdout


def test_no_baseline_skips_integrity_loudly(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "app", tag=False)
    proc = repo.gate()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "INTEGRITY SKIPPED" in proc.stdout
    assert "baseline/demo-001 not found" in proc.stdout
    statuses = repo.statuses()
    for check_id in (
        "integrity.protected-trees",
        "integrity.criteria-flips",
        "integrity.change-frozen",
        "integrity.test-inventory",
    ):
        assert statuses[check_id] == "SKIP"
    assert statuses["integrity.self-hash"] == "PASS"  # runs even without a baseline


# ---------------------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------------------


def test_failing_test_is_red_but_inventory_intact(repo: FixtureRepo) -> None:
    repo.write("tests/test_core.py", TESTS_CORE.replace("add(1, 2) == 3", "add(1, 2) == 4"))
    proc = repo.gate()
    assert proc.returncode == 1
    assert "GATE: RED" in proc.stdout
    statuses = repo.statuses()
    assert statuses["toolchain.pytest"] == "FAIL"
    # a FAILING baseline test is a pytest failure, not an inventory violation
    assert statuses["integrity.test-inventory"] == "PASS"


def test_mypy_and_ruff_red(repo: FixtureRepo) -> None:
    repo.write(
        "src/app/bad.py",
        '"""Broken module."""\n\nimport os\n\n\ndef wrong() -> int:\n    return "x"\n',
    )
    proc = repo.gate()
    assert proc.returncode == 1
    statuses = repo.statuses()
    assert statuses["toolchain.mypy"] == "FAIL"
    assert statuses["toolchain.ruff-check"] == "FAIL"  # F401: unused import os


# ---------------------------------------------------------------------------------------
# Grep gates
# ---------------------------------------------------------------------------------------


def test_grep_patterns_unit() -> None:
    samples = {
        "grep.type-ignore": "x = f()  # type: ignore[arg-type]",
        "grep.future-annotations": "from __future__ import annotations",
        "grep.noqa-f401": "import os  # noqa: F401,E501",
        "grep.not-implemented": "    raise NotImplementedError",
        "grep.no-orm": "    users = relationship(User)",
    }
    clean = "def add(a: int, b: int) -> int:  # a normal content line"
    for check_id, pattern, _ref in gate.GREP_GATES:
        assert pattern.search(samples[check_id]), check_id
        assert not pattern.search(clean), check_id


def test_no_orm_patterns_unit() -> None:
    # Every SQLAlchemy ORM signature the house style bans must trip the one no-orm gate.
    (_id, pattern, _ref) = next(g for g in gate.GREP_GATES if g[0] == "grep.no-orm")
    for orm in (
        "Base = declarative_base()",
        "class Base(DeclarativeBase):",
        "    name: Mapped[str]",
        "    id = mapped_column(Integer, primary_key=True)",
        "    items = relationship('Item')",
    ):
        assert pattern.search(orm), orm
    for core in (
        "users = Table('users', metadata, Column('id', Integer))",
        "stmt = select(users).where(users.c.id == 1)",
        "def relationship_note() -> str:  # not a call",
    ):
        assert not pattern.search(core), core


def test_no_mocks_patterns_unit() -> None:
    (_id, pattern, _ref) = gate.TEST_GREP_GATES[0]
    assert _id == "grep.no-mocks"
    for mock in (
        "from unittest.mock import MagicMock",
        "    repo = MagicMock()",
        "    client = AsyncMock()",
        "@patch('app.core.add')",
        "    with mock.patch('app.core.add'):",
        "    result = mocker.patch('x')",
    ):
        assert pattern.search(mock), mock
    for fake in (
        "class FakeUserRepository(IUserRepository):",
        "    repo = FakeUserRepository()",
        "def test_add() -> None:",
        "    response = client.patch('/users/1')",  # a REST .patch(), not @patch
        # monkeypatch is house-sanctioned (T04d): setenv in settings tests, setattr for
        # non-dependencies. Misuse (patching a handler dependency) stays ADVICE — no clean
        # grep signature, so the gate must never fire on the family.
        "    monkeypatch.setenv('APP_DB_DSN', 'postgres://x')",
        "    monkeypatch.setattr(os, 'environ', {})",
    ):
        assert not pattern.search(fake), fake


def test_not_implemented_stub_is_red(repo: FixtureRepo) -> None:
    repo.append("src/app/core.py", "\n\ndef todo() -> None:\n    raise NotImplementedError\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["grep.not-implemented"] == "FAIL"
    assert "V-04" in proc.stdout


def test_orm_use_in_src_is_red(repo: FixtureRepo) -> None:
    # SQLAlchemy ORM in src/** — Core is the house style (T04c). mypy/ruff stay green.
    repo.write(
        "src/app/models.py",
        '"""ORM model that should never pass the gate."""\n\n'
        "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\n\n\n"
        "class Base(DeclarativeBase):\n    pass\n\n\n"
        "class User(Base):\n"
        '    __tablename__ = "users"\n'
        "    id: Mapped[int] = mapped_column(primary_key=True)\n",
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["grep.no-orm"] == "FAIL"


def test_core_only_src_keeps_no_orm_green(repo: FixtureRepo) -> None:
    # SQLAlchemy Core is allowed — the no-orm gate must not fire on it.
    repo.write(
        "src/app/tables.py",
        '"""Core table — the house style, no ORM."""\n\n'
        "from sqlalchemy import Column, Integer, MetaData, Table\n\n"
        "metadata = MetaData()\n"
        'users = Table("users", metadata, Column("id", Integer, primary_key=True))\n',
    )
    proc = repo.gate()
    assert repo.statuses()["grep.no-orm"] == "PASS", proc.stdout


def test_mock_use_in_tests_is_red(repo: FixtureRepo) -> None:
    # A mock in the target app's tests/** — the no-mocks contract (T04c).
    repo.write(
        "tests/test_mocked.py",
        '"""Test that reaches for a mock — banned."""\n\n'
        "from unittest.mock import MagicMock\n\n\n"
        "def test_with_mock() -> None:\n"
        "    repo = MagicMock()\n"
        "    assert repo is not None\n",
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["grep.no-mocks"] == "FAIL"


def test_fakes_only_tests_keep_no_mocks_green(repo: FixtureRepo) -> None:
    # The green fixture tree uses fakes / plain asserts — the no-mocks gate stays green.
    proc = repo.gate()
    assert repo.statuses()["grep.no-mocks"] == "PASS", proc.stdout


def test_monkeypatch_setenv_in_settings_test_keeps_no_mocks_green(repo: FixtureRepo) -> None:
    # House-sanctioned (T04d): monkeypatch.setenv exercises the env-reading code in a
    # settings-parsing test. The no-mocks gate must NOT fire on the monkeypatch family.
    repo.write(
        "tests/unit/infrastructure/test_app_settings.py",
        '"""Settings-parsing test — monkeypatch.setenv is house-sanctioned."""\n\n'
        "import os\n\n\n"
        "def test_env_read(monkeypatch) -> None:\n"
        "    monkeypatch.setenv('APP_X', '1')\n"
        "    assert os.environ['APP_X'] == '1'\n",
    )
    proc = repo.gate()
    assert repo.statuses()["grep.no-mocks"] == "PASS", proc.stdout


def test_monkeypatch_setattr_keeps_no_mocks_green(repo: FixtureRepo) -> None:
    # monkeypatch.setattr for a non-dependency is available house style (T04d); misuse
    # (patching a handler dependency) is semantic and stays ADVICE, not a gate.
    repo.write(
        "tests/unit/test_clock.py",
        '"""monkeypatch.setattr for a non-dependency — house-sanctioned."""\n\n'
        "import time\n\n\n"
        "def test_frozen(monkeypatch) -> None:\n"
        "    monkeypatch.setattr(time, 'time', lambda: 42.0)\n"
        "    assert time.time() == 42.0\n",
    )
    proc = repo.gate()
    assert repo.statuses()["grep.no-mocks"] == "PASS", proc.stdout


# ---------------------------------------------------------------------------------------
# Construct + table smokes
# ---------------------------------------------------------------------------------------


def test_construct_smoke_red_when_create_app_raises(repo: FixtureRepo) -> None:
    # A4: mypy, ruff and the unit tests all stay green — only the smoke catches this.
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)
    proc = repo.gate()
    assert proc.returncode == 1
    statuses = repo.statuses()
    assert statuses["smoke.construct"] == "FAIL"
    assert statuses["toolchain.pytest"] == "PASS"
    assert statuses["toolchain.mypy"] == "PASS"


def test_table_smoke_red_when_table_module_import_fails(repo: FixtureRepo) -> None:
    repo.write(
        "src/app/tables.py",
        '"""Registers sqlalchemy-style tables (fixture)."""\n\n\n'
        "def table_factory(name: str) -> None:\n"
        '    raise RuntimeError("Table(" + name + ") registration failed at import")\n\n\n'
        'table_factory("users")\n',
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["smoke.table-metadata"] == "FAIL"
    assert "F-012" in proc.stdout


# ---------------------------------------------------------------------------------------
# --criteria: junit backing + [m] verdict entries
# ---------------------------------------------------------------------------------------


def test_unbacked_flip_is_red(repo: FixtureRepo) -> None:
    repo.flip("AC-1", "x")
    repo.flip("AC-2", "x")  # no @pytest.mark.ac("AC-2") test exists
    proc = repo.gate("--criteria", "--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["criteria.junit-backing"] == "FAIL"
    assert "AC-2" in proc.stdout
    # the legal flip stays legal on the integrity side
    assert repo.statuses()["integrity.criteria-flips"] == "PASS"


def test_manual_state_requires_verdict_entry(repo: FixtureRepo) -> None:
    repo.flip("AC-2", "m")
    proc = repo.gate("--criteria", "--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["criteria.manual-verdict"] == "FAIL"

    repo.write("specs/demo/changes/001-thing/verdict.md", VERDICT_MD_MANUAL)
    proc = repo.gate("--criteria", "--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["criteria.manual-verdict"] == "PASS"


# ---------------------------------------------------------------------------------------
# Integrity vs baseline — the bypass simulations
# ---------------------------------------------------------------------------------------


def test_criteria_reworded_under_same_checkboxes_is_red(repo: FixtureRepo) -> None:
    # E-03 bypass: keep the checkbox, bend the wording to fit the implementation.
    rel = "specs/demo/changes/001-thing/criteria.md"
    text = (repo.root / rel).read_text(encoding="utf-8")
    repo.write(rel, text.replace("returns the sum `3`", "returns any value"))
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.criteria-flips"] == "FAIL"
    assert "beyond a state flip" in proc.stdout


def test_change_md_edit_is_red(repo: FixtureRepo) -> None:
    repo.append("specs/demo/changes/001-thing/change.md", "\n- AC-3: quietly widened scope.\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.change-frozen"] == "FAIL"


def test_protected_tree_edits_are_red(repo: FixtureRepo) -> None:
    # E-01/E-02 bypass: mutate enforcement inputs via plain file writes (no hook fires).
    repo.append("pyproject.toml", '\n[tool.pytest.ini_options]\naddopts = "-k nothing"\n')
    repo.write(".claude/hooks/evil.py", "# injected after baseline\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.protected-trees"] == "FAIL"
    assert "pyproject.toml" in proc.stdout
    assert ".claude/hooks/evil.py" in proc.stdout


def test_deleted_baseline_test_is_red(repo: FixtureRepo) -> None:
    repo.write("tests/test_core.py", TESTS_CORE.replace('@pytest.mark.ac("AC-1")\ndef test_add', "def _gone", 1))
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.test-inventory"] == "FAIL"
    assert "tests/test_core.py::test_add" in proc.stdout


def test_conftest_suppression_is_red(repo: FixtureRepo) -> None:
    # E-05 bypass: silence one test from OUTSIDE tests/** — no test file changes. (A root
    # `collect_ignore = ["tests"]` is already neutralized by the gate's pinned explicit-arg
    # invocation; the deselect hook works regardless, and only the inventory catches it.)
    repo.write(
        "conftest.py",
        "def pytest_collection_modifyitems(config, items):\n"
        '    items[:] = [i for i in items if "test_add_zero" not in i.nodeid]\n',
    )
    proc = repo.gate()
    assert proc.returncode == 1
    statuses = repo.statuses()
    assert statuses["integrity.test-inventory"] == "FAIL"
    assert statuses["toolchain.pytest"] == "PASS"  # the surviving tests are green — only the inventory catches it
    assert "test_add_zero" in proc.stdout


def test_skipped_baseline_test_is_red(repo: FixtureRepo) -> None:
    repo.write(
        "tests/test_core.py",
        TESTS_CORE.replace('@pytest.mark.ac("AC-1")', '@pytest.mark.ac("AC-1")\n@pytest.mark.skip(reason="hush")'),
    )
    proc = repo.gate()
    assert proc.returncode == 1
    statuses = repo.statuses()
    assert statuses["integrity.test-inventory"] == "FAIL"
    assert statuses["toolchain.pytest"] == "PASS"  # a skip is green for pytest — only the inventory catches it


def test_docker_absent_integration_skip_is_green_and_listed(tmp_path: Path) -> None:
    # T04b: a skipped integration baseline test is GREEN when the gate's own probe (here
    # forced off via GATE_DOCKER=0) found no daemon — and its node-id is listed loudly in
    # the DOCKER SKIPPED block, never silently swallowed.
    repo = make_repo(tmp_path / "app")
    repo.write("tests/integration/test_container.py", TESTS_INTEGRATION)
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")  # fold into the red baseline commit
    repo.git("tag", "-f", "baseline/demo-001")
    proc = repo.gate()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GATE: GREEN" in proc.stdout
    statuses = repo.statuses()
    assert statuses["integrity.test-inventory"] == "PASS"
    node = "tests/integration/test_container.py::test_needs_container"
    assert "DOCKER SKIPPED" in proc.stdout
    assert node in proc.stdout  # listed in the loud DOCKER SKIPPED block
    assert repo.verdict()["docker_exempt"] == [node]


def test_docker_absent_non_integration_skip_is_red(tmp_path: Path) -> None:
    # T04b: the carve-out is directory-keyed. A skipped NON-integration baseline test is RED
    # even with the daemon absent (GATE_DOCKER=0).
    repo = make_repo(tmp_path / "app")
    repo.write("tests/unit/test_skip.py", TESTS_FAKE_DOCKER_SKIP)
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "-f", "baseline/demo-001")
    proc = repo.gate()
    assert proc.returncode == 1
    statuses = repo.statuses()
    assert statuses["integrity.test-inventory"] == "FAIL"
    assert "tests/unit/test_skip.py::test_pretends_to_need_docker" in proc.stdout
    assert repo.verdict()["docker_exempt"] == []


def test_removal_listed_in_change_md_is_legal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "app", change_md=CHANGE_MD_REMOVAL)
    # the capability invariant of the removed behaviour goes too (worktree spec edit is
    # the /spec session's territory, not gate-frozen) — otherwise L-06 fires, correctly
    repo.write("specs/demo/core.md", "# demo — core capability\n\n- The `add` operation is being removed.\n")
    repo.write(
        "tests/test_core.py",
        '"""Fixture tests after removal."""\n\nfrom app.core import add\n\n\n'
        "def test_add_zero() -> None:\n    assert add(0, 0) == 0\n",
    )
    proc = repo.gate()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.test-inventory"] == "PASS"


def test_gate_edited_on_work_tree_is_red(repo: FixtureRepo) -> None:
    # E-02 bypass: soften the gate itself, then run it.
    repo.append(".claude/tools/gate.py", "\n# tampered after baseline\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.self-hash"] == "FAIL"
    assert "E-02" in proc.stdout


# ---------------------------------------------------------------------------------------
# Spec invariants (L-06)
# ---------------------------------------------------------------------------------------


def test_rotted_invariant_reference_is_red(repo: FixtureRepo) -> None:
    repo.write(
        "specs/demo/core.md",
        CAPABILITY_MD.replace("tests/test_core.py::test_add", "tests/test_core.py::test_vanished"),
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["spec.invariant-tests"] == "FAIL"
    assert "L-06" in proc.stdout


# ---------------------------------------------------------------------------------------
# Pure-function units
# ---------------------------------------------------------------------------------------


def test_criteria_flip_violations_unit() -> None:
    base = ["# Criteria — demo/001", "- [ ] AC-1: `add` returns `3`", "- [ ] AC-2: schema is non-empty `dict`"]
    legal = ["# Criteria — demo/001", "- [x] AC-1: `add` returns `3`", "- [m] AC-2: schema is non-empty `dict`"]
    assert gate.criteria_flip_violations(base, legal) == []
    reworded = ["# Criteria — demo/001", "- [x] AC-1: `add` returns anything", "- [ ] AC-2: schema is non-empty `dict`"]
    assert gate.criteria_flip_violations(base, reworded)
    renumbered = ["# Criteria — demo/001", "- [ ] AC-9: `add` returns `3`", "- [ ] AC-2: schema is non-empty `dict`"]
    assert gate.criteria_flip_violations(base, renumbered)
    shrunk = ["# Criteria — demo/001", "- [x] AC-1: `add` returns `3`"]
    assert gate.criteria_flip_violations(base, shrunk)


def test_inventory_violations_unit() -> None:
    baseline = {"tests/t.py::test_a", "tests/t.py::test_b"}
    ok, exempt = gate.inventory_violations(
        baseline, baseline, {"tests/t.py::test_a": "passed", "tests/t.py::test_b": "failed"}, "", docker_available=False
    )
    assert ok == [] and exempt == []
    missing, _ = gate.inventory_violations(
        baseline, {"tests/t.py::test_a"}, {"tests/t.py::test_a": "passed"}, "", docker_available=False
    )
    assert any("test_b" in v for v in missing)
    allowed, _ = gate.inventory_violations(
        baseline,
        {"tests/t.py::test_a"},
        {"tests/t.py::test_a": "passed"},
        "Removed tests: tests/t.py::test_b",
        docker_available=False,
    )
    assert allowed == []
    for silenced in ("skipped", "xfail", None):
        outcomes = {"tests/t.py::test_a": "passed"}
        if silenced:
            outcomes["tests/t.py::test_b"] = silenced
        # test_b is a NON-integration node, so even with docker absent it is RED (the
        # carve-out is directory-keyed, not skip-reason-keyed).
        violations, _ = gate.inventory_violations(baseline, baseline, outcomes, "", docker_available=False)
        assert any("test_b" in v for v in violations), silenced


def test_docker_carveout_unit() -> None:
    # T04b: the sole inventory carve-out — a collected, skipped integration baseline test is
    # exempt only when the gate's own probe found the daemon absent. Directory + probe are
    # the key; the skip-reason string is never consulted here.
    unit = "tests/unit/test_x.py::test_a"
    integ = "tests/integration/postgres/test_repo.py::test_round_trip"
    baseline = {unit, integ}
    passed_unit = {unit: "passed"}

    # integration skipped + daemon absent -> exempt (listed, not a violation)
    violations, exempt = gate.inventory_violations(
        baseline, baseline, {**passed_unit, integ: "skipped"}, "", docker_available=False
    )
    assert violations == [] and exempt == [integ]

    # SAME tree + daemon present -> no exemption, RED
    violations, exempt = gate.inventory_violations(
        baseline, baseline, {**passed_unit, integ: "skipped"}, "", docker_available=True
    )
    assert any(integ in v for v in violations) and exempt == []

    # NON-integration skipped + daemon absent -> RED (carve-out is directory-keyed)
    violations, exempt = gate.inventory_violations(
        baseline, baseline, {unit: "skipped", integ: "passed"}, "", docker_available=False
    )
    assert any(unit in v for v in violations) and exempt == []

    # a DESELECTED/deleted integration test (not collected) is still RED — the carve-out
    # must not reopen the deselect bypass (finding 4).
    violations, exempt = gate.inventory_violations(baseline, {integ}, {integ: "passed"}, "", docker_available=False)
    assert any(unit in v for v in violations) and exempt == []

    # only `skipped` is exempt: an xfailed integration test still fails even with docker off.
    violations, exempt = gate.inventory_violations(
        baseline, baseline, {**passed_unit, integ: "xfail"}, "", docker_available=False
    )
    assert any(integ in v for v in violations) and exempt == []


def test_manual_violations_unit() -> None:
    assert gate.manual_violations([], None) == []
    assert gate.manual_violations(["AC-2"], None)
    assert gate.manual_violations(["AC-2"], "- AC-2: PASS\n  - proof: ac-test: tests/t.py::test_b\n")
    good = "- AC-2: MANUAL-candidate\n  - proof: manual: human accepted, reason recorded\n"
    assert gate.manual_violations(["AC-2"], good) == []
