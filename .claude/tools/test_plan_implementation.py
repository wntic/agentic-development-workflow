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


# ── signature canonicalizer: formatting noise is NOT drift, a real change IS ──


def _sig(s: str) -> tuple[tuple[str, ...], str]:
    mo = pi.re.search(r"\bdef\s+(\w+)\s*\(", s)
    assert mo
    return pi._canonical_sig(s, mo.end() - 1)


def test_canonical_sig_ignores_self_defaults_and_whitespace() -> None:
    # self dropped, default value dropped, internal whitespace + bracket spacing collapsed
    a = _sig("async def list(self, status: TicketStatus | None = None) -> tuple[tuple[Ticket, ...], int]")
    b = _sig("async def list(self,status:TicketStatus|None)->tuple[tuple[Ticket,...],int]:")
    assert a == b == (("status:TicketStatus|None",), "tuple[tuple[Ticket,...],int]")


def test_canonical_sig_ignores_forward_ref_quotes() -> None:
    assert _sig('def satisfies(self, required: "Role") -> bool') == _sig("def satisfies(self, required: Role) -> bool")


def test_canonical_sig_keeps_keyword_only_marker() -> None:
    assert _sig("def f(self, *, x: int) -> None") != _sig("def f(self, x: int) -> None")


def test_canonical_sig_added_param_and_changed_return_differ() -> None:
    base = _sig("async def get_by_id(self, id: UUID) -> Foo")
    assert base != _sig("async def get_by_id(self, id: UUID, org_id: UUID) -> Foo")  # added param
    assert base != _sig("async def get_by_id(self, id: UUID) -> Foo | None")  # changed return
    assert base != _sig("async def get_by_id(self, ident: UUID) -> Foo")  # renamed param


# ── drifted_files: missing method (presence) AND drifted signature (the §4 gap) ──

_DRIFT_MANIFEST: dict = {
    "domain": {
        "repository_protocols": [
            {
                "name": "IFooRepository",
                "aggregate": "Foo",
                "methods": [
                    "async def add(self, foo: Foo) -> None",
                    "async def get_by_id(self, id: UUID, org_id: UUID) -> Foo",  # grew org_id
                    "async def purge(self, id: UUID) -> None",  # added method (missing in body)
                ],
            },
        ],
    },
    "infrastructure": {
        "datastores": [{"name": "main", "kind": "postgres"}],
        "repositories": [{"implements": "IFooRepository", "backs": "Foo", "store": "main"}],
    },
}


def _write_repo(tmp_path: Path, body: str) -> Path:
    pkg_src = tmp_path / "src" / "app"
    repo_dir = pkg_src / "infrastructure" / "postgres" / "repositories"
    repo_dir.mkdir(parents=True)
    (repo_dir / "foo_repository.py").write_text(body)
    return pkg_src


def test_no_drift_when_body_matches_protocol(tmp_path: Path) -> None:
    pkg_src = _write_repo(
        tmp_path,
        "class FooRepository:\n"
        "    async def add(self, foo: Foo) -> None: ...\n"
        "    async def get_by_id(self, id: UUID, org_id: UUID) -> Foo: ...\n"
        "    async def purge(self, id: UUID) -> None: ...\n",
    )
    assert pi.drifted_files(_DRIFT_MANIFEST, pkg_src, set()) == {}


def test_signature_drift_and_missing_method_both_caught(tmp_path: Path) -> None:
    # body is the PRE-delta shape: get_by_id has no org_id, and purge was never added.
    pkg_src = _write_repo(
        tmp_path,
        "class FooRepository:\n"
        "    async def add(self, foo: Foo) -> None: ...\n"
        "    async def get_by_id(self, id: UUID) -> Foo: ...\n",
    )
    drift = pi.drifted_files(_DRIFT_MANIFEST, pkg_src, set())
    (info,) = drift.values()
    assert info == {"missing": ["purge"], "changed": ["get_by_id"]}


def test_drift_skips_files_already_pending(tmp_path: Path) -> None:
    pkg_src = _write_repo(tmp_path, "class FooRepository:\n    async def add(self, foo: Foo) -> None: ...\n")
    repo_file = pkg_src / "infrastructure" / "postgres" / "repositories" / "foo_repository.py"
    # a NIE/column-less file is already on the worklist as a scaffold trigger → not double-reported
    assert pi.drifted_files(_DRIFT_MANIFEST, pkg_src, {repo_file}) == {}


def test_whitespace_noise_alone_is_not_drift(tmp_path: Path) -> None:
    # the body matches but is formatted differently (no spaces) — must NOT flag drift (F-014 lesson)
    pkg_src = _write_repo(
        tmp_path,
        "class FooRepository:\n"
        "    async def add(self,foo:Foo)->None: ...\n"
        "    async def get_by_id(self,id:UUID,org_id:UUID)->Foo: ...\n"
        "    async def purge(self,id:UUID)->None: ...\n",
    )
    assert pi.drifted_files(_DRIFT_MANIFEST, pkg_src, set()) == {}
