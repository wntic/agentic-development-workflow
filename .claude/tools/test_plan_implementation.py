"""Tests for the implementation planner (.claude/tools/plan_implementation.py).

Lives next to the tool (outside the default `tests/` path). Run it explicitly:

    uv run pytest .claude/tools/test_plan_implementation.py

Focus: the registry/DAG derivation that does NOT touch the file tree — the polyglot repo-file
stem (F-009/F-014: two repos backing one aggregate must not collide) and the synthetic repo→table
DAG edge (F-025: a relational repo's body selects its table's columns, so the table fills first).
The `--app` union (F-010) is exercised end-to-end against a scaffolded tree, not here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plan_implementation as pi

# A minimal polyglot manifest: ONE aggregate (Meeting) backed by TWO repositories — a relational
# IMeetingRepository on Postgres `main` and a client-style IMeetingSearchIndex on Qdrant `vectors`.
_POLYGLOT: dict = {
    "domain": {
        "entities": [{"name": "Meeting", "subdomain": "meetings"}],
        "repository_protocols": [
            {
                "name": "IMeetingRepository",
                "aggregate": "Meeting",
                "methods": [{"signature": "async def add(self, meeting: Meeting) -> None"}],
            },
            {
                "name": "IMeetingSearchIndex",
                "aggregate": "Meeting",
                "methods": [{"signature": "async def index(self, meeting_id: int) -> None"}],
            },
        ],
    },
    "infrastructure": {
        "datastores": [
            {"name": "main", "kind": "postgres"},
            {"name": "vectors", "kind": "qdrant"},
        ],
        "repositories": [
            {"implements": "IMeetingRepository", "backs": "Meeting", "store": "main"},
            {"implements": "IMeetingSearchIndex", "backs": "Meeting", "store": "vectors"},
        ],
    },
}


# ── repo_file_stem: backs-derived (relational) vs protocol-derived (client) ─────


def test_relational_repo_stem_is_backs_derived() -> None:
    repo = {"backs": "Meeting", "implements": "IMeetingRepository"}
    assert pi.repo_file_stem(repo, "postgres") == "meeting_repository"


def test_implicit_postgres_repo_stem_is_backs_derived() -> None:
    # store_kind is None ⇒ the implicit single postgres store (relational).
    repo = {"backs": "Meeting", "implements": "IMeetingRepository"}
    assert pi.repo_file_stem(repo, None) == "meeting_repository"


def test_client_repo_stem_is_protocol_derived() -> None:
    # F-009 root cause: a client-store repo backing the same aggregate must NOT key off `backs`.
    repo = {"backs": "Meeting", "implements": "IMeetingSearchIndex"}
    assert pi.repo_file_stem(repo, "qdrant") == "meeting_search_index"


# ── build_registry: polyglot two-repos-one-aggregate does not collide (F-009/F-014) ──


def test_polyglot_repos_get_distinct_keys_and_correct_skills() -> None:
    reg = pi.build_registry(_POLYGLOT)
    relational = reg["meeting_repository|repositories"]
    client = reg["meeting_search_index|repositories"]
    # distinct entries — the relational repo is NOT clobbered by the vector repo
    assert relational["skill"] == "infra-sqlalchemy-repository"
    assert client["skill"] == "infra-store-repository"
    assert relational["label"] == "IMeetingRepository impl"
    assert client["label"] == "IMeetingSearchIndex impl"


def test_only_the_relational_repo_gets_a_table() -> None:
    reg = pi.build_registry(_POLYGLOT)
    # the relational store backs a write-once Table scaffold; the client store has none
    assert "meetings|tables" in reg
    assert reg["meetings|tables"]["label"] == "Meeting table"
    assert not any(k.endswith("|tables") and reg[k]["label"] == "Meeting table" and "search" in k for k in reg)


# ── DAG: a relational repo depends on its table; a client repo does not (F-025) ──


def test_relational_table_ranks_below_its_repo() -> None:
    reg = pi.build_registry(_POLYGLOT)
    levels = pi._dag_level(reg)
    assert levels["meetings|tables"] < levels["meeting_repository|repositories"]


def test_client_repo_has_no_table_edge() -> None:
    reg = pi.build_registry(_POLYGLOT)
    # the qdrant repo has no SQLAlchemy table, so it carries no synthetic table dep → level 0
    assert pi._dag_level(reg)["meeting_search_index|repositories"] == 0
