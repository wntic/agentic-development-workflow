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
import shutil
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

# The same fixture project CLAIMING to be installable. Nothing ever installs a fixture tree
# into an environment (that is what keeps this suite cheap), so this is the shape of a project
# whose `[build-system]` promise is not kept — the FAIL branch of the import smoke (T12b).
PYPROJECT_INSTALLABLE = (
    PYPROJECT + '\n[build-system]\nrequires = ["uv_build>=0.11.6,<0.12.0"]\nbuild-backend = "uv_build"\n'
)

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

# The removal vocabulary is spec §3.1's, pinned by T03c: the `REMOVED` marker plus the
# `## Removed` section the change.md template ships. The gate reads node-ids out of the raw
# change.md text (any mention counts as the legal-removal allowance), but the fixture writes them
# where the author is instructed to — one spelling everywhere, so a reader of this fixture learns
# the real shape.
CHANGE_MD_REMOVAL = """\
# demo/001 — fixture removal change

Class: behavioral, REMOVED

## Task
Remove the `add` behaviour.

## Removed
- `add` — the operation goes from the app surface.
- `tests/test_core.py::test_add` — obsolete with it.

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


ESCALATE_FILE = """\
# ESCALATE (hook-authored, spec §5.3 / E-08)

gate.py stayed RED after 3 implementer passes.
Failed checks: toolchain.pytest

accept.py denies while this file exists; only a human removes it.
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


def make_repo(
    root: Path,
    *,
    change_md: str = CHANGE_MD,
    tag: bool = True,
    escalate: bool = False,
    pyproject: str = PYPROJECT,
) -> FixtureRepo:
    repo = FixtureRepo(root)
    repo.write("pyproject.toml", pyproject)
    repo.write(".gitignore", GITIGNORE)
    repo.write("src/app/__init__.py", SRC_INIT)
    repo.write("src/app/core.py", SRC_CORE)
    repo.write("src/app/main.py", SRC_MAIN)
    repo.write("tests/test_core.py", TESTS_CORE)
    repo.write("specs/demo/core.md", CAPABILITY_MD)
    repo.write("specs/demo/changes/001-thing/change.md", change_md)
    repo.write("specs/demo/changes/001-thing/criteria.md", CRITERIA_MD)
    if escalate:
        repo.write("specs/demo/changes/001-thing/ESCALATE", ESCALATE_FILE)
    for name in TOOL_FILES:
        repo.write(f".claude/tools/{name}", (TOOLS_DIR / name).read_text(encoding="utf-8"))
    repo.git("init", "-q")
    # A real repo has an identity; the fixture needs a LOCAL one because tooling that commits by
    # itself (subagent_stop's ESCALATE commit, T06h) runs git without the `-c user.*` this helper
    # passes — and must not depend on the machine's global config.
    repo.git("config", "user.name", "gate")
    repo.git("config", "user.email", "gate@test")
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
        "integrity.escalate-intact",
        "integrity.test-inventory",
        "integrity.self-hash",
    ):
        assert statuses[check_id] == "PASS", (check_id, statuses)
    assert statuses["smoke.table-metadata"] == "SKIP"
    assert statuses["docker.alembic"] == "SKIP"
    # the fixture tree is never installed into any environment, so the import smoke's SKIP is
    # the honest report — and it is LOUD, naming the reason (T12b).
    assert statuses["smoke.package-import"] == "SKIP"
    assert "PACKAGE IMPORT SKIPPED" in proc.stdout
    assert "no [build-system]" in proc.stdout


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
    src_unsorted = (
        '"""Fixture domain module."""\n\nimport sys\nimport os\n\n'
        '__all__ = ["add", "os", "sys"]\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
    )
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
        "integrity.escalate-intact",
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


# ---------------------------------------------------------------------------------------
# `Class: invisible` — the before/after OpenAPI operation diff (spec §3.1, T20)
# ---------------------------------------------------------------------------------------
#
# The class declares a deterministic proof — a green gate plus an empty before/after OpenAPI diff —
# and until T20 the second half existed in no script. These cases hold both directions: a genuine
# refactor (identical operation set) is GREEN, and the same refactor plus/minus one operation is RED
# naming it. A check that cannot fail is the defect class notes/19 is about.

CHANGE_MD_INVISIBLE = """\
# demo/001 — extract the summing helper

Class: invisible

## Task
Move the addition behind a private helper. No behaviour changes, no surface changes.

## Acceptance criteria
- AC-1: `app.core.add` returns `3` for input `1, 2`.
- AC-2: `create_app()` exposes a non-empty OpenAPI schema.
"""

# The fixture factory WITH an OpenAPI `paths` mapping — the surface the diff reads. No web
# framework: the route inventory is a property of `app.openapi()`, not of FastAPI.
SRC_MAIN_ROUTES = '''\
"""Fixture app factory exposing an OpenAPI `paths` mapping (the surface diff's input)."""

PATHS: dict[str, dict[str, dict[str, str]]] = {
    "/health": {"get": {}},
    "/users": {"get": {}, "post": {}},
}


class App:
    """Minimal stand-in exposing the openapi() surface the smoke and the surface diff call."""

    def openapi(self) -> dict[str, object]:
        return {"openapi": "3.1.0", "paths": PATHS}


def create_app() -> App:
    return App()
'''

# The implementer's refactor: identical behaviour, identical surface — an honest invisible change.
SRC_CORE_REFACTORED = '''\
"""Fixture domain module, refactored behind a private helper."""


def _sum(a: int, b: int) -> int:
    return a + b


def add(a: int, b: int) -> int:
    return _sum(a, b)
'''


def _invisible_repo(root: Path, *, tag: bool = True, baseline_main: str = SRC_MAIN_ROUTES) -> FixtureRepo:
    """A `Class: invisible` change whose baseline commit carries a route-serving app."""
    repo = make_repo(root, change_md=CHANGE_MD_INVISIBLE, tag=False)
    repo.write("src/app/main.py", baseline_main)
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")  # keep the baseline a single commit
    if tag:
        repo.git("tag", "baseline/demo-001")
    return repo


def test_an_invisible_change_with_an_unchanged_surface_is_green(tmp_path: Path) -> None:
    repo = _invisible_repo(tmp_path / "app")
    repo.write("src/app/core.py", SRC_CORE_REFACTORED)  # the refactor, behaviour untouched
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["invisible.openapi-diff"] == "PASS"
    assert "all 3 OpenAPI operation(s) identical to the baseline" in proc.stdout


def test_an_invisible_change_that_adds_an_operation_is_red_naming_it(tmp_path: Path) -> None:
    # The route nothing else can catch: an ADDED endpoint breaks no existing test, so the suite
    # stays green and only the surface diff sees it.
    repo = _invisible_repo(tmp_path / "app")
    repo.write("src/app/core.py", SRC_CORE_REFACTORED)
    repo.write("src/app/main.py", SRC_MAIN_ROUTES.replace('    "/users"', '    "/metrics": {"get": {}},\n    "/users"'))
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["invisible.openapi-diff"] == "FAIL"
    assert "+ GET /metrics (served now, absent at baseline)" in proc.stdout
    assert repo.statuses()["toolchain.pytest"] == "PASS"  # the suite is green: only the diff fails


def test_an_invisible_change_that_removes_an_operation_is_red_naming_it(tmp_path: Path) -> None:
    repo = _invisible_repo(tmp_path / "app")
    repo.write("src/app/main.py", SRC_MAIN_ROUTES.replace('{"get": {}, "post": {}}', '{"get": {}}'))
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["invisible.openapi-diff"] == "FAIL"
    assert "- POST /users (served at baseline, gone now)" in proc.stdout


def test_a_behavioral_change_skips_the_surface_diff_loudly(tmp_path: Path) -> None:
    # Class-keyed, and never silent: the report names the class it read, so a reader can tell the
    # difference between "this check does not apply" and "this check was forgotten".
    repo = make_repo(tmp_path / "app")
    proc = repo.gate("--change", "demo/001")
    assert repo.statuses()["invisible.openapi-diff"] == "SKIP"
    assert "Class: behavioral — the before/after OpenAPI diff is the `invisible` class's proof" in proc.stdout


def test_an_invisible_change_without_a_baseline_is_red(tmp_path: Path) -> None:
    # Every other integrity check SKIPs loudly without a baseline; this one cannot, because the
    # baseline IS the before side of the only proof this class has.
    repo = _invisible_repo(tmp_path / "app", tag=False)
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["invisible.openapi-diff"] == "FAIL"
    assert "without a BEFORE side it has no proof at all" in proc.stdout


def test_an_invisible_change_whose_baseline_does_not_construct_is_red(tmp_path: Path) -> None:
    # Undetermined is not "unchanged" (notes/19): with the baseline app unconstructible the diff
    # cannot run, and passing it would hand the class a proof nobody computed.
    repo = _invisible_repo(tmp_path / "app", baseline_main=SRC_MAIN_BROKEN)
    repo.write("src/app/main.py", SRC_MAIN_ROUTES)  # HEAD constructs; the baseline does not
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1
    assert repo.statuses()["invisible.openapi-diff"] == "FAIL"
    assert "the baseline's OpenAPI surface could not be determined" in proc.stdout
    assert "undetermined is not 'unchanged'" in proc.stdout


def test_an_invisible_change_with_no_http_surface_skips_loudly(tmp_path: Path) -> None:
    # A domain-only refactor (or a library) has no surface to diff. Reported as applicability, not
    # as cleanliness — and the class still has the green gate + the baseline test inventory.
    repo = make_repo(tmp_path / "app", change_md=CHANGE_MD_INVISIBLE, tag=False)
    (repo.root / "src/app/main.py").unlink()
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "baseline/demo-001")
    repo.write("src/app/core.py", SRC_CORE_REFACTORED)
    proc = repo.gate("--change", "demo/001")
    assert repo.statuses()["invisible.openapi-diff"] == "SKIP", proc.stdout
    assert "no constructible HTTP surface on either side" in proc.stdout
    assert "rests on the green gate plus the baseline test inventory alone" in proc.stdout


def test_the_class_parse_ignores_the_template_comment(tmp_path: Path) -> None:
    # The change.md template enumerates every class name inside its own comment; a change that
    # keeps the comment declares the DEFAULT. One parse, shared with red_check (C7).
    template = (TOOLS_DIR.parent / "templates" / "change.md").read_text(encoding="utf-8")
    assert "invisible" in template  # the trap is really in the template
    assert gate.parse_change_class(template) == "behavioral"
    assert gate.parse_change_class("Class: Invisible   <!-- x -->\n") == "invisible"
    assert gate.parse_change_class("# demo/001\n\n## Task\nx\n") == "behavioral"


def test_route_inventory_reports_absent_and_undetermined_apart(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert gate.route_inventory(empty).absent
    repo = _invisible_repo(tmp_path / "app")
    surface = gate.route_inventory(repo.root)
    assert surface.operations == ["GET /health", "GET /users", "POST /users"]
    assert not surface.undetermined and not surface.absent
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)
    broken = gate.route_inventory(repo.root)
    assert broken.undetermined and not broken.routes  # never an empty surface read as "no routes"


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
# Toolchain preflight (T12b) — a missing tool is a sentence, not a traceback
# ---------------------------------------------------------------------------------------


def test_required_toolchain_tracks_what_the_run_will_invoke(tmp_path: Path) -> None:
    # The preflight's scope is exactly the checks that will run: a tree whose checks SKIP must
    # never abort over a tool it was never going to invoke.
    bare = tmp_path / "bare"
    bare.mkdir()
    assert gate.required_toolchain(bare, docker_available=False) == []

    src_only = tmp_path / "src-only"
    (src_only / "src").mkdir(parents=True)
    assert gate.required_toolchain(src_only, docker_available=False) == ["mypy", "ruff"]

    app = tmp_path / "app"
    (app / "src").mkdir(parents=True)
    (app / "tests").mkdir(parents=True)
    assert gate.required_toolchain(app, docker_available=False) == ["mypy", "ruff", "pytest"]

    (app / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    # the alembic tier only runs when the daemon is there, so neither does its requirement
    assert gate.required_toolchain(app, docker_available=False) == ["mypy", "ruff", "pytest"]
    assert gate.required_toolchain(app, docker_available=True) == ["mypy", "ruff", "pytest", "alembic"]


def test_missing_toolchain_probe_that_cannot_run_is_loud(tmp_path: Path) -> None:
    # "could not ask" must never read as "nothing missing" (T10f's rule, applied here).
    with pytest.raises(gate.GateError):
        gate.missing_toolchain(["mypy"], {}, tmp_path / "does-not-exist")


def test_missing_toolchain_aborts_with_the_fix_not_a_traceback(tmp_path: Path) -> None:
    # A consumer project whose environment lacks the toolchain used to get a raw
    # `No module named mypy` out of three separate subprocesses. The gate now refuses to run
    # and says what to install — and leaves NO verdict.json, so nothing downstream can read
    # the aborted run as an answer.
    repo = make_repo(tmp_path / "app")
    bare = tmp_path / "bare-venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], check=True, capture_output=True)
    python = bare / "bin" / "python"
    if not python.exists():  # pragma: no cover — Windows layout
        python = bare / "Scripts" / "python.exe"

    env = os.environ.copy()
    env["GATE_DOCKER"] = "0"
    proc = subprocess.run(
        [str(python), str(repo.root / ".claude/tools/gate.py"), str(repo.root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=repo.root,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 2, output  # 2 = could not run, distinct from RED's 1
    assert "toolchain missing from this project's environment" in output
    for tool in ("mypy", "ruff", "pytest"):
        assert tool in output
    assert "[dependency-groups]" in output and "uv sync" in output
    assert "Traceback" not in output
    assert not (repo.root / ".gate/verdict.json").exists()


# ---------------------------------------------------------------------------------------
# Package-import smoke (T12b) — the A4 question asked with the gate's injection stripped
# ---------------------------------------------------------------------------------------


def test_plan_package_import_unit(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    assert gate.plan_package_import(bare).kind == "skip"

    not_installable = tmp_path / "not-installable"
    not_installable.mkdir()
    (not_installable / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    plan = gate.plan_package_import(not_installable)
    assert plan.kind == "skip" and "[build-system]" in plan.reason

    installable = tmp_path / "installable"
    installable.mkdir()
    (installable / "pyproject.toml").write_text(PYPROJECT_INSTALLABLE, encoding="utf-8")
    plan = gate.plan_package_import(installable)
    assert plan.kind == "import" and plan.package == "fixture_app"  # `-` -> `_`

    nameless = tmp_path / "nameless"
    nameless.mkdir()
    (nameless / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n', encoding="utf-8"
    )
    assert gate.plan_package_import(nameless).kind == "fail"  # undetermined input, never a pass

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pyproject.toml").write_text("[project\nname = oops\n", encoding="utf-8")
    assert gate.plan_package_import(broken).kind == "fail"


def test_import_probe_ignores_a_pythonpath_injection(tmp_path: Path) -> None:
    # The whole point of the smoke: a package reachable ONLY through PYTHONPATH (which is what
    # gate.py hands every other subprocess) must NOT count as importable here.
    (tmp_path / "src" / "ghostpkg").mkdir(parents=True)
    (tmp_path / "src" / "ghostpkg" / "__init__.py").write_text("", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(tmp_path / "src"))
    rc, _ = gate.import_without_injection("ghostpkg", env, tmp_path)
    assert rc != 0
    # the same probe still finds what the interpreter's own environment really provides
    rc, _ = gate.import_without_injection("json", env, tmp_path)
    assert rc == 0


def test_installable_project_that_cannot_be_imported_is_red(tmp_path: Path) -> None:
    # The A4 finding itself: every other check is GREEN (they all run under the gate's
    # PYTHONPATH=src injection) while `uvicorn` / a plain import would die.
    repo = make_repo(tmp_path / "app", pyproject=PYPROJECT_INSTALLABLE)
    proc = repo.gate()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    statuses = repo.statuses()
    assert statuses["smoke.package-import"] == "FAIL"
    assert statuses["toolchain.pytest"] == "PASS"
    assert statuses["smoke.construct"] == "PASS"  # constructs fine — under the injection
    assert repo.verdict()["failed"] == ["smoke.package-import"]
    assert "unstartable outside gate.py" in proc.stdout
    assert "fixture_app" in proc.stdout


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


def test_escalate_deleted_since_baseline_is_red(tmp_path: Path) -> None:
    # §5.3/E-08 bypass: the agent that hit its iteration ceiling unlocks itself by deleting the
    # hook-written ESCALATE (accept.py only checks whether the file exists NOW). The change dir
    # is not in PROTECTED_PATHS by design, so the disappearance needs its own baseline check.
    repo = make_repo(tmp_path / "app", escalate=True)
    (repo.root / "specs/demo/changes/001-thing/ESCALATE").unlink()
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "FAIL"
    assert "specs/demo/changes/001-thing/ESCALATE" in proc.stdout
    assert "only a human may clear it" in proc.stdout


def test_escalate_still_present_is_not_a_gate_failure(tmp_path: Path) -> None:
    # The gate reports on the file's DISAPPEARANCE, not its existence: while the ESCALATE
    # stands, accept.py is the script that denies (§5.4 gate 2) — the gate must stay usable
    # so the human can see whether the tree is otherwise green.
    repo = make_repo(tmp_path / "app", escalate=True)
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "PASS"


def test_change_without_an_escalate_is_unaffected(repo: FixtureRepo) -> None:
    # The overwhelmingly common case: no ESCALATE was ever written for this change.
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    statuses = repo.statuses()
    assert statuses["integrity.escalate-intact"] == "PASS"
    assert "no ESCALATE file at the baseline commit" in proc.stdout


ESCALATE_REL = "specs/demo/changes/001-thing/ESCALATE"


def _commit_escalate(repo: FixtureRepo) -> None:
    """The shipped sequence T06h makes real: the hook writes AND commits the lock, path-scoped,
    on top of the already-tagged red baseline (its ceiling fires after baselining, so an ESCALATE
    can never sit in the baseline tree — the reason a baseline-vs-HEAD diff could not see it)."""
    repo.write(ESCALATE_REL, ESCALATE_FILE)
    repo.git("add", "--", ESCALATE_REL)
    repo.git("commit", "-q", "-m", "hook: escalate", "--", ESCALATE_REL)


def test_escalate_committed_after_the_baseline_then_deleted_is_red(tmp_path: Path) -> None:
    # THE bypass, in the shape the shipped flow actually produces: the hook commits the lock after
    # the baseline is tagged, then the agent at its ceiling deletes it and commits over it. Before
    # T06h this passed silently — the baseline tree had no ESCALATE, so there was nothing to miss.
    repo = make_repo(tmp_path / "app")
    _commit_escalate(repo)
    repo.git("rm", "-q", "--", ESCALATE_REL)
    repo.git("commit", "-q", "-m", "unlock myself", "--", ESCALATE_REL)
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "FAIL"
    assert ESCALATE_REL in proc.stdout
    assert "only a human may clear it" in proc.stdout
    assert "--clear-escalate" in proc.stdout  # the denial names the sanctioned way out


def test_escalate_committed_then_deleted_in_the_work_tree_is_red(tmp_path: Path) -> None:
    # The same bypass without the cover-up commit: git knows the file, the work tree does not.
    repo = make_repo(tmp_path / "app")
    _commit_escalate(repo)
    (repo.root / ESCALATE_REL).unlink()
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "FAIL"


def test_escalate_committed_and_standing_is_not_a_gate_failure(tmp_path: Path) -> None:
    # The asymmetry §5.3 requires: a live lock is accept.py's business, not the gate's. Making it
    # RED would leave every escalated change un-gateable — the human could not even see whether
    # the tree is otherwise green.
    repo = make_repo(tmp_path / "app")
    _commit_escalate(repo)
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "PASS"


def test_escalate_cleared_through_red_check_passes(tmp_path: Path) -> None:
    # The sanctioned clearing path end to end (T06h part 3): the human removes the lock, commits
    # that removal ALONE, and `red_check --clear-escalate` moves the baseline over it. Without this
    # step the gate would stay RED forever, since --rebaseline refuses a non-tests/ commit.
    repo = make_repo(tmp_path / "app")
    _commit_escalate(repo)
    repo.git("rm", "-q", "--", ESCALATE_REL)
    repo.git("commit", "-q", "-m", "human clears the ESCALATE", "--", ESCALATE_REL)
    clear = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "red_check.py"), str(repo.root), "--change", "demo/001", "--clear-escalate"],
        capture_output=True,
        text=True,
    )
    assert clear.returncode == 0, clear.stdout + clear.stderr
    assert "CLEAR-ESCALATE: OK" in clear.stdout
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "PASS"


def test_escalate_state_fails_closed_on_an_unanswerable_git_call(repo: FixtureRepo) -> None:
    # T04e's rc-guard, kept and extended to the log call: a git result that could not be obtained
    # must never read as "no ESCALATE" (notes/19's fail-open class).
    state = gate.escalate_state(repo.root, "refs/tags/no-such-baseline")
    assert state.error and state.known == () and state.missing == ()


# --- The other baseline helper: git could not answer ≠ the baseline carries no paths (T04f) ---
#
# `_baseline_paths()` used to return `[]` on a non-zero rc, so its callers could not tell an
# unreadable baseline from a baseline that touched no files. They failed closed only by luck —
# the per-file `_baseline_blob()` failed too and produced "created after the baseline commit",
# blaming the work tree for a git failure. The messages below are the load-bearing assertions.


def _unreadable_baseline_ctx(repo: FixtureRepo) -> gate.GateContext:
    """A resolved context whose baseline ref git cannot answer for.

    `resolve_context()` verifies an explicit `--baseline` up front, so a context can only reach
    this state the way reality does: the ref resolved once and the object store cannot serve it
    now. Overriding the field is the hermetic model of that; the end-to-end case below produces
    it for real by deleting the baseline tree object.
    """
    ctx = gate.resolve_context(repo.root, "demo/001", None)
    ctx.baseline = "refs/tags/no-such-baseline"
    return ctx


def test_baseline_paths_raises_instead_of_returning_an_empty_list(repo: FixtureRepo) -> None:
    with pytest.raises(gate.GateError) as exc:
        gate._baseline_paths(_unreadable_baseline_ctx(repo), "specs")
    assert "ls-tree" in str(exc.value)


def test_criteria_flips_fails_naming_git_when_the_baseline_is_unreadable(repo: FixtureRepo) -> None:
    check = gate.check_criteria_flips(_unreadable_baseline_ctx(repo))
    assert check.status == "FAIL"
    assert "git ls-tree" in check.detail
    assert "created after the baseline commit" not in check.detail  # the pre-fix misattribution


def test_change_frozen_fails_naming_git_when_the_baseline_is_unreadable(repo: FixtureRepo) -> None:
    check = gate.check_change_frozen(_unreadable_baseline_ctx(repo))
    assert check.status == "FAIL"
    assert "git ls-tree" in check.detail
    assert "created after the baseline commit" not in check.detail  # the pre-fix misattribution


def test_test_inventory_fails_naming_git_when_the_baseline_is_unreadable(repo: FixtureRepo) -> None:
    # The third caller (the legal-removal allowance is read out of the baseline change.md). Its
    # git-naming comes from `collect_baseline_inventory`'s own guard, which runs first; the point
    # of the case is that the check never PASSes and never silently loses the allowance.
    check, exempt = gate.check_test_inventory(
        _unreadable_baseline_ctx(repo),
        gate.Check("toolchain.pytest", "PASS", "fixture"),
        docker_available=False,
    )
    assert check.status == "FAIL"
    assert "git archive" in check.detail
    assert exempt == []


def test_unreadable_baseline_tree_is_red_and_blames_git(tmp_path: Path) -> None:
    # End to end, with the corruption git itself would report: the baseline commit object is
    # there (so the ref resolves and every integrity check runs) but its tree object is gone —
    # a partial/damaged object store. Every affected check must FAIL naming git.
    repo = make_repo(tmp_path / "app")
    tree_oid = repo.git("rev-parse", "baseline/demo-001^{tree}").strip()
    (repo.root / ".git/objects" / tree_oid[:2] / tree_oid[2:]).unlink()

    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    statuses = repo.statuses()
    for check_id in ("integrity.criteria-flips", "integrity.change-frozen", "integrity.test-inventory"):
        assert statuses[check_id] == "FAIL", (check_id, statuses)
    assert "git ls-tree baseline/demo-001" in proc.stdout
    assert "created after the baseline commit" not in proc.stdout


def test_human_removal_followed_by_a_rebaseline_is_not_punished(tmp_path: Path) -> None:
    # The legal path: the human clears the lock, the removal is committed, and the baseline
    # moves onto that commit (red_check.py --rebaseline). The new baseline carries no
    # ESCALATE, so the check goes quiet — the clearing is recorded in git, not undetectable.
    repo = make_repo(tmp_path / "app", escalate=True)
    (repo.root / "specs/demo/changes/001-thing/ESCALATE").unlink()
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "human clears the ESCALATE")
    repo.git("tag", "-f", "baseline/demo-001")
    proc = repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert repo.statuses()["integrity.escalate-intact"] == "PASS"


def test_gate_edited_on_work_tree_is_red(repo: FixtureRepo) -> None:
    # E-02 bypass: soften the gate itself, then run it.
    repo.append(".claude/tools/gate.py", "\n# tampered after baseline\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.self-hash"] == "FAIL"
    assert "E-02" in proc.stdout


# ---------------------------------------------------------------------------------------
# The anchor set: what a consumer's trust rests on (E-02 widened by T18)
# ---------------------------------------------------------------------------------------
#
# In a consumer the plugin lives outside the project's repository, so `bash_guard` allows
# writes to it (T06e, by design) and `integrity.protected-trees` diffs paths that do not
# exist in the consumer tree (vacuous PASS, notes/20 F-02). Self-hash is the only check
# left, so every file a verdict depends on has to be inside it.


def test_anchor_globs_pick_the_deciders_and_leave_the_rest(tmp_path: Path) -> None:
    anchors = gate.self_integrity_anchors(
        [
            "tools/gate.py",
            "tools/criteria_lint.py",
            "tools/accept.py",
            "tools/red_check.py",
            "hooks/bash_guard.py",
            "hooks/criteria_guard.py",
            "hooks/subagent_stop.py",
            "hooks/session_stop.py",
            "hooks/hooks.json",
            "bin/adw.py",
            ".claude-plugin/plugin.json",
            "settings.json",
            # NOT anchored, each for its own reason (see SELF_INTEGRITY_GLOBS):
            "tools/test_gate.py",  # ships, but no decision reads it
            "tools/fixtures/users-002-change-spec.md",  # nested: `tools/*.py` is one level
            "skills/conventions/SKILL.md",  # knowledge, not a decider
            "agents/implementer.md",
            "commands/spec.md",
            "templates/change.md",
        ]
    )
    assert anchors == [
        ".claude-plugin/plugin.json",
        "bin/adw.py",
        "hooks/bash_guard.py",
        "hooks/criteria_guard.py",
        "hooks/hooks.json",
        "hooks/session_stop.py",
        "hooks/subagent_stop.py",
        "settings.json",
        "tools/accept.py",
        "tools/criteria_lint.py",
        "tools/gate.py",
        "tools/red_check.py",
    ]


def test_this_repos_own_plugin_tree_anchors_every_decider() -> None:
    """The live set, so that adding a tool/hook without anchoring it cannot pass unnoticed.

    It fired as designed when `tools/drift.py` landed (T17): the glob anchored the new tool by
    construction and this list had to be told about it, which is the review moment the set exists
    to force. Keep the count out of the test NAME — it drifts, the list does not.
    """
    root = gate.plugin_root()
    assert root == TOOLS_DIR.parent
    anchors = set(gate.self_integrity_anchors(gate._worktree_anchor_candidates(root)))
    assert {
        "tools/gate.py",
        "tools/criteria_lint.py",
        "tools/accept.py",
        "tools/red_check.py",
        "tools/drift.py",
        "hooks/bash_guard.py",
        "hooks/criteria_guard.py",
        "hooks/subagent_stop.py",
        "hooks/session_stop.py",
        "hooks/hooks.json",
        "bin/adw.py",
        ".claude-plugin/plugin.json",
        "settings.json",
    } == anchors, anchors


# The plugin layout as it ships (notes/21 §1), relative to the plugin root.
PLUGIN_FILES = (
    "tools/accept.py",
    "tools/red_check.py",
    "hooks/bash_guard.py",
    "hooks/criteria_guard.py",
    "hooks/subagent_stop.py",
    "hooks/session_stop.py",
    "hooks/hooks.json",
    "bin/adw.py",
    ".claude-plugin/plugin.json",
    "settings.json",
)


def install_plugin_files(repo: FixtureRepo) -> None:
    """Give the fixture the WHOLE plugin (not just gate.py + criteria_lint.py) at its baseline.

    Amends the baseline commit rather than adding one, so `integrity.protected-trees` still
    sees `.claude/**` identical to the baseline and this isolates the self-hash question.
    """
    for rel in PLUGIN_FILES:
        repo.write(f".claude/{rel}", (TOOLS_DIR.parent / rel).read_text(encoding="utf-8"))
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "-f", "baseline/demo-001")


@pytest.fixture()
def plugin_repo(tmp_path: Path) -> FixtureRepo:
    repo = make_repo(tmp_path / "app")
    install_plugin_files(repo)
    return repo


def test_a_full_plugin_tree_is_green(plugin_repo: FixtureRepo) -> None:
    proc = plugin_repo.gate("--change", "demo/001")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert plugin_repo.statuses()["integrity.self-hash"] == "PASS"
    assert "12 enforcement anchor(s) match git HEAD" in proc.stdout


@pytest.mark.parametrize("rel", PLUGIN_FILES)
def test_every_anchor_fails_the_gate_when_tampered(plugin_repo: FixtureRepo, rel: str) -> None:
    # The case the task exists for: accept.py, red_check.py, the four hooks, hooks.json,
    # the invocation shim and plugin.json itself were all unprotected in a consumer.
    plugin_repo.append(f".claude/{rel}", "\n" if rel.endswith(".json") else "\n# tampered\n")
    proc = plugin_repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert plugin_repo.statuses()["integrity.self-hash"] == "FAIL"
    assert rel in proc.stdout  # the message NAMES the file
    assert "the enforcement layer was modified" in proc.stdout


def test_a_deleted_anchor_fails_the_gate(plugin_repo: FixtureRepo) -> None:
    # Deletion is the other tamper direction: unhook by removal rather than by edit.
    (plugin_repo.root / ".claude/hooks/bash_guard.py").unlink()
    proc = plugin_repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert plugin_repo.statuses()["integrity.self-hash"] == "FAIL"
    assert "hooks/bash_guard.py: committed at HEAD but missing from the work tree" in proc.stdout


def test_an_uncommitted_new_tool_fails_the_gate(plugin_repo: FixtureRepo) -> None:
    # The anchor set is the union of HEAD and the work tree, so a tool DROPPED IN next to the
    # gate cannot hide from it by never being committed.
    plugin_repo.write(".claude/tools/helper.py", "# dropped in after the baseline\n")
    proc = plugin_repo.gate("--change", "demo/001")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert plugin_repo.statuses()["integrity.self-hash"] == "FAIL"
    assert "tools/helper.py: not committed at HEAD" in proc.stdout


def test_a_plugin_outside_git_fails_loudly_with_the_remedy(plugin_repo: FixtureRepo, tmp_path: Path) -> None:
    # Decision (2): no provenance means no verdict. A `git-subdir` marketplace source is a
    # content copy with no `.git` (notes/21 §5) — the gate must FAIL, not degrade quietly.
    detached = tmp_path / "plugin-cache"
    shutil.copytree(plugin_repo.root / ".claude", detached)
    assert not (detached / ".git").exists()
    env = os.environ.copy()
    env["GATE_DOCKER"] = "0"
    proc = subprocess.run(
        [sys.executable, str(detached / "tools/gate.py"), "--change", "demo/001", str(plugin_repo.root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=plugin_repo.root,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert plugin_repo.statuses()["integrity.self-hash"] == "FAIL"
    assert "are not inside a git repository" in proc.stdout
    assert "never `git-subdir`" in proc.stdout


def test_the_self_hash_floor_holds_when_the_globs_see_nothing(plugin_repo: FixtureRepo) -> None:
    # Fail-closed floor: gate.py + criteria_lint.py are anchored even in a layout whose plugin
    # root holds no `tools/`, `hooks/` or manifest at all (a vendored copy), so E-02's original
    # coverage can never shrink to zero because a file moved out of a glob's reach.
    elsewhere = plugin_repo.root / "vendor" / "toolz"
    elsewhere.mkdir(parents=True)
    for name in TOOL_FILES:
        shutil.copy(plugin_repo.root / ".claude/tools" / name, elsewhere / name)
    plugin_repo.git("add", "-A")
    plugin_repo.git("commit", "-q", "--amend", "--no-edit")
    plugin_repo.git("tag", "-f", "baseline/demo-001")
    env = os.environ.copy()
    env["GATE_DOCKER"] = "0"

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(elsewhere / "gate.py"), "--change", "demo/001", str(plugin_repo.root)],
            capture_output=True,
            text=True,
            env=env,
            cwd=plugin_repo.root,
        )

    proc = run()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 enforcement anchor(s) match git HEAD" in proc.stdout
    (elsewhere / "gate.py").write_text(
        (elsewhere / "gate.py").read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8"
    )
    proc = run()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "toolz/gate.py: work-tree content differs from HEAD" in proc.stdout


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


# The shape accept.py's capability birth produces: an instructional HTML comment that spells
# out the provenance form, above the real invariants (T10j).
CAPABILITY_WITH_COMMENT_MD = (
    "# demo — core capability\n"
    "\n"
    "## Invariants\n"
    "<!-- EVERY invariant carries its provenance mark:\n"
    "       - <invariant> (verified by: <test-id>)\n"
    "       - <invariant> (MANUAL) -->\n"
) + CAPABILITY_MD.split("\n", 2)[2]


def test_provenance_inside_an_html_comment_is_not_a_reference(repo: FixtureRepo) -> None:
    """T10j — matching raw text read the template's own `<test-id>` example as a real
    provenance reference, so a successful `accept.py --execute` of a capability-birthing
    change left the BASE branch RED: the acceptance script breaking S9."""
    repo.write("specs/demo/core.md", CAPABILITY_WITH_COMMENT_MD)
    proc = repo.gate()
    assert proc.returncode == 0, proc.stdout
    assert repo.statuses()["spec.invariant-tests"] == "PASS"
    assert "<test-id>" not in proc.stdout


def test_a_rotted_reference_still_fails_beside_a_comment(repo: FixtureRepo) -> None:
    """The strip must not become a hiding place: the same commented file, real rot below it,
    is still RED — L-06 is what keeps provenance honest."""
    repo.write(
        "specs/demo/core.md",
        CAPABILITY_WITH_COMMENT_MD.replace("tests/test_core.py::test_add", "tests/test_core.py::test_vanished"),
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["spec.invariant-tests"] == "FAIL"
    assert "test_vanished" in proc.stdout


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
