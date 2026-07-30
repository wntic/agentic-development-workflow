---
name: testing-contract
description: The house forms for a repository adapter's integration test, driven against the real backend — relational through the `sf` rollback fixture (CRUD, every unique constraint on insert AND update, cascades, the `updated_at` advance, `context["constraint"]` pinned), and client-style stores through per-test namespace isolation (CRUD plus the store's own verbs, the entity-record mapping, the SDK-error translation).
when_to_use: Writing or changing the contract test for a repository adapter, on either a relational store or a vector, cache or document store.
paths: tests/**
---

# Testing — Repository Contract

One integration-test file per repository adapter, driven against the **real** backend. This layer catches
what unit coverage cannot, and what it catches differs by store kind:

- **Relational** — real `UNIQUE` and `FK` violations, real `ON DELETE CASCADE` semantics, the
  `IntegrityError`-to-domain-exception translator's constraint-name map, and the `onupdate=` clause on
  `updated_at`.
- **Client-style** (vector, cache, document) — the entity-record mapping round-trip and the
  SDK-error-to-domain-exception translation the adapter performs at its boundary. There is no SQL
  transaction and no constraint map here, so both the isolation mechanism and the load-bearing assertion
  are different.

The two halves share their purpose and their shape; they differ in isolation, and that difference is the
first thing to get right.

## When to use vs. neighbours

- A repository adapter on a relational store, under `infrastructure/postgres/repositories/` → the
  **relational** half.
- A repository adapter on a client-style store, under `infrastructure/<store-kind>/repositories/` → the
  **client-style** half.
- Schema-only checks (an index exists, a migration carries data correctly) → separate flat files under `tests/integration/postgres/` (`test_indexes.py`, `test_<NNNN>_migration.py`) that use `db_settings` and `run_alembic`, not `sf`.
- HTTP-layer integration (route, auth, OpenAPI) → `test-restapi-endpoint`.
- The rollback `conftest.py` and the session containers themselves → `testing-integration-setup`.
- A pure domain test → `testing-unit-domain`.
- The repository being tested → `infra-persistence` (relational) or `infra-store-repository`.
- An in-memory fake of the same protocol, for handler unit tests → `test-fake-repository`.

## Isolation — the one thing that differs

**Relational: transaction rollback.** Every test takes `sf: async_sessionmaker[AsyncSession]`, the fixture from
`testing-integration-setup`. The database is empty at test start and everything the test wrote is
discarded at teardown. No marker, no other DB fixture.

**Client-style: a fresh namespace.** A client store has no nested transaction, so the `sf`-rollback model does not apply (the rollback fixture is relational-only). Isolate exactly as the `s3_prefix` pattern does: **each test owns a fresh namespace** — a unique collection name (qdrant/chroma), key-prefix (redis), or database/bucket — created in a fixture and dropped at teardown. Bring the real store up once per session via testcontainers; create/destroy the per-test namespace per test. This skill's fixtures live in the sibling `tests/integration/<store-kind>/conftest.py` (not in `testing-integration-setup`, which owns the relational and blob fixtures).

## Template(s)

### Relational

```
tests/integration/postgres/
└── test_<aggregate_snake>_repository.py
```

Large surfaces may concern-split (`test_<aggregate>_repository_create.py`, `test_<aggregate>_repository_update.py`) — but only when the single file exceeds ~300 lines. Default is one file per repository.

### Standard CRUD test file

```python
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myapp.domain.exceptions import ConflictError, NotFoundError
from myapp.domain.foos import Foo, FooListFilter
from myapp.infrastructure.postgres.repositories.foo_repository import FooRepository

def _foo(name: str = "alpha") -> Foo:
    return Foo(id=uuid.uuid7(), name=name)

async def test_crud_roundtrip(sf: async_sessionmaker[AsyncSession]) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()

    await repo.create(foo)
    loaded = await repo.get_by_id(foo.id)
    assert loaded == foo

    foo.name = "beta"
    await repo.update(foo)
    assert (await repo.get_by_id(foo.id)).name == "beta"

    await repo.delete(foo.id)
    with pytest.raises(NotFoundError):
        await repo.get_by_id(foo.id)

async def test_duplicate_name_on_insert_raises_conflict(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))

    with pytest.raises(ConflictError) as exc:
        await repo.create(_foo("alpha"))

    assert exc.value.context["constraint"] == "uq_foos_name"

async def test_duplicate_name_on_update_raises_conflict(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))
    second = _foo("beta")
    await repo.create(second)

    second.name = "alpha"
    with pytest.raises(ConflictError) as exc:
        await repo.update(second)

    assert exc.value.context["constraint"] == "uq_foos_name"

async def test_updated_at_advances_on_update(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    before = (await repo.get_by_id(foo.id)).updated_at

    foo.name = "beta"
    await repo.update(foo)
    after = (await repo.get_by_id(foo.id)).updated_at

    assert after >= before

async def test_get_by_name_returns_match(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))

    loaded = await repo.get_by_name("alpha")
    assert loaded is not None
    assert loaded.name == "alpha"

async def test_get_by_name_returns_none_when_absent(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)

    assert await repo.get_by_name("alpha") is None

async def test_list_respects_pagination_and_sort(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    for name in ("c", "a", "b"):
        await repo.create(_foo(name))

    page = await repo.list(filter=FooListFilter(limit=2, offset=0))
    assert [f.name for f in page] == ["a", "b"]
```

### Cascade — parent + sub-collection

```python
async def test_cascade_delete_removes_attachments(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    await repo.add_attachment(foo.id, _attachment(foo.id))

    await repo.delete(foo.id)

    assert await repo.count_attachments(foo.id) == 0

async def test_attachment_with_wrong_parent_raises_not_found(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    att = _attachment(foo.id)
    await repo.add_attachment(foo.id, att)

    with pytest.raises(NotFoundError):
        await repo.get_attachment(uuid.uuid4(), att.id)
```

### Client-style store

```
tests/integration/<store-kind>/
├── conftest.py                         # session container + per-test namespace fixture
└── test_<aggregate_snake>_repository.py
```

### `conftest.py` — real store + per-test namespace (qdrant example)

```python
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

_DIM = 3  # the test vectors' dimension — small; production dimension lives in settings

@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    if os.getenv("CI"):
        yield os.environ["MYAPP_QDRANT_URL"]
        return
    from testcontainers.qdrant import QdrantContainer

    # Pin the image tag — never float on :latest (mirrors test-integration-isolation's
    # postgres/MinIO pins; :latest makes the suite non-reproducible). The specific pin
    # is a per-deployment choice, bumped deliberately, not a frozen constant.
    with QdrantContainer("qdrant/qdrant:v1.12.4") as q:
        yield f"http://{q.get_container_host_ip()}:{q.get_exposed_port(6333)}"

@pytest.fixture
async def store(qdrant_url: str) -> AsyncIterator[tuple[AsyncQdrantClient, str]]:
    """A fresh collection per test = namespace isolation (no transaction rollback
    for a client store). Create it, hand out (client, collection), drop at teardown."""
    client = AsyncQdrantClient(url=qdrant_url)
    collection = f"test_{uuid.uuid4().hex}"
    await client.create_collection(
        collection, vectors_config=VectorParams(size=_DIM, distance=Distance.COSINE)
    )
    try:
        yield client, collection
    finally:
        await client.delete_collection(collection)
        await client.close()
```

### `test_<aggregate_snake>_repository.py`

```python
import uuid

import pytest
from qdrant_client import AsyncQdrantClient

from myapp.domain.exceptions import UpstreamError
from myapp.domain.foos import Foo
from myapp.infrastructure.qdrant.repositories.foo_repository import FooRepository
from myapp.infrastructure.qdrant.settings import FoosVectorSettings

def _foo(text: str = "alpha", *, vector: list[float] | None = None, bar_id: uuid.UUID | None = None) -> Foo:
    return Foo(
        id=uuid.uuid4(),
        bar_id=bar_id or uuid.uuid4(),
        text=text,
        vector=vector or [0.1, 0.2, 0.3],
    )

def _repo(store: tuple[AsyncQdrantClient, str]) -> FooRepository:
    client, collection = store
    return FooRepository(client=client, settings=FoosVectorSettings(collection=collection))

async def test_add_many_then_search_roundtrip(store: tuple[AsyncQdrantClient, str]) -> None:
    repo = _repo(store)
    foo = _foo()
    await repo.add_many((foo,))

    hits = await repo.search(query_vector=foo.vector, k=1)
    assert len(hits) == 1
    found, score = hits[0]
    assert found.id == foo.id
    assert found.text == "alpha"
    assert isinstance(score, float)

async def test_search_returns_nearest_first(store: tuple[AsyncQdrantClient, str]) -> None:
    repo = _repo(store)
    near = _foo("near", vector=[0.1, 0.0, 0.0])
    far = _foo("far", vector=[0.9, 0.9, 0.9])
    await repo.add_many((near, far))

    hits = await repo.search(query_vector=[0.1, 0.0, 0.0], k=2)
    assert [f.text for f, _ in hits] == ["near", "far"]

async def test_delete_by_bar_removes_only_that_bars_points(
    store: tuple[AsyncQdrantClient, str],
) -> None:
    repo = _repo(store)
    keep, drop = uuid.uuid4(), uuid.uuid4()
    await repo.add_many((
        _foo("keep", vector=[0.1, 0.0, 0.0], bar_id=keep),
        _foo("drop", vector=[0.0, 0.1, 0.0], bar_id=drop),
    ))

    await repo.delete_by_bar(drop)

    remaining = await repo.search(query_vector=[0.1, 0.1, 0.1], k=10)
    assert {f.bar_id for f, _ in remaining} == {keep}

async def test_search_against_unreachable_store_raises_upstream_error() -> None:
    dead = AsyncQdrantClient(url="http://127.0.0.1:1")  # nothing listening
    repo = FooRepository(client=dead, settings=FoosVectorSettings(collection="x"))

    with pytest.raises(UpstreamError):
        await repo.search(query_vector=[0.0, 0.0, 0.0], k=1)
```

## Rules

### Relational

1. **Every test takes `sf: async_sessionmaker[AsyncSession]`.** The rollback fixture from `testing-integration-setup` makes the DB empty at test start and discards everything at teardown. No marker, no other DB fixture.
2. **`_<aggregate>()` builder is a module-level `def`, not a `@pytest.fixture`.** Defaults must be valid; no-override construction succeeds.
3. **No unique-suffix natural keys.** Rollback isolation guarantees an empty DB; `name="alpha"` is safe across tests. The old `uuid4().hex[:8]` floor is obsolete here.
4. **`assert exc.value.context["constraint"] == "<constraint_name>"` on every `ConflictError`.** This is the only place the `IntegrityError`-to-domain-exception translator's name map is exercised end-to-end — the fake-based unit-test path can't verify it.
5. **Insert AND update paths for every unique field.** The bug class "translator handles INSERT but not UPDATE" only surfaces when both are tested. Skipping the update test is the most common gap in repository contracts.
6. **`updated_at` advance is asserted as `>=`, not `>`.** Postgres `now()` may return identical timestamps within a transaction; `>=` pins the `onupdate=` clause without flaking.
7. **Every cascade gets its own test.** Naming: `test_cascade_delete_removes_<child>`. Test the count after parent-delete is zero — only this proves the schema's `ON DELETE CASCADE` works.
8. **Every `get_by_<field>` gets both a found and a not-found test.** For case-sensitivity-sensitive fields, add a mixed-case test that asserts the documented behavior.
9. **`assert list_result == expected_list`** — exact equality, not `any(...)`. Empty DB makes this correct.
10. **No raw INSERTs for seed data on the table under test.** Drive setup through the repository's own `create`. Cross-aggregate seed rows (a referenced `Bar` for a `Foo` test) may use raw INSERT when no `BarRepository.create` is in scope — or inject the bar's repo and use it.
11. **No FastAPI, no `httpx`, no DI container.** This test imports the repository class, takes `sf`, calls methods, asserts. The HTTP surface is `test-restapi-endpoint`.
12. **Migration regression tests are separate.** They live flat at `tests/integration/postgres/test_<NNNN>_migration.py`, take `db_settings`, invoke `run_alembic`, and may `downgrade` / `upgrade`. Ordinary repository tests cannot — they assume `head` is applied.

### Client-style store

13. **Each test runs against the real store via testcontainers** — never a fake, never a mock. The fake (`test-fake-repository`) is for handler unit tests; this layer exists to prove the adapter against the actual backend, which is the only place the SDK call shape and error mapping are exercised.
14. **Isolate by a per-test namespace, not rollback.** A fresh collection / key-prefix / database per test, created in the `store` (or equivalently-named) fixture and dropped at teardown. There is no transaction to roll back; do not reach for `sf`.
15. **The container is session-scoped; the namespace is function-scoped.** One store per run (expensive to start); one namespace per test (cheap, gives each test sole ownership). CI reads a provided endpoint from env (the `os.getenv("CI")` branch) instead of starting a container.
16. **Exercise the full protocol**, CRUD verbs and non-CRUD alike — `add_many`/`get`/`delete` AND the store's own verbs (`search`, `delete_by_<field>`, range/scan). A `search` test asserts ordering (nearest-first / score-ordered), not just membership.
17. **Assert the entity↔record mapping round-trips.** What was written comes back as the same entity (ids, payload fields, and — when the read path hydrates it — the vector). A returned scored pair asserts both the entity and that the score is a real `float`, not a placeholder.
18. **Assert the SDK-error → domain-exception translation end-to-end.** This is the load-bearing contract (the client-store analogue of the relational `context["constraint"]` assertion): point the repository at an unreachable/closed client, or trigger a store rejection, and assert the boundary raises the domain exception the adapter promises — `UpstreamError` for a network / store failure, `NotFoundError` for an absent record — never the raw SDK exception. These are the domain exceptions `infra-store-repository` translates into at its boundary (shown here as placeholders); assert whichever ones that adapter actually raises, not a frozen literal. Assert the `context` keys the adapter promises.
19. **Fixed test values are fine.** Namespace isolation gives each test an empty store at start; no unique-suffix natural keys needed (same as the relational contract's rollback guarantee).
20. **Small test vectors.** Use a tiny dimension (e.g. 3) created on the per-test collection; the production embedding dimension is a settings concern, not the contract's.
21. **No FastAPI, no `httpx`, no DI container.** Import the repository class, construct it with the real client + a settings object scoped to the per-test namespace, call methods, assert. The HTTP surface is `test-restapi-endpoint`.
22. **No assertions on global store contents.** Assert only within this test's namespace — exactly the `s3_prefix` discipline, because cleanup is namespace-scoped, not transactional.

## Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, stdlib `uuid`, `myapp.domain.*`, `myapp.infrastructure.postgres.repositories.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature including `sf: async_sessionmaker[AsyncSession]`.
- Builder `_<aggregate>()` returns the entity type; overrides keyword-only.
- No `from __future__ import annotations`.

For a client-style store, the SDK (`qdrant_client` / `redis` / …) and `myapp.infrastructure.<store-kind>.*`
replace the SQLAlchemy and Postgres imports; the `store` fixture is annotated with its
`tuple[<Client>, str]` shape, and a yielding fixture uses `AsyncIterator[T]` / `Iterator[T]`.

## Hard stops

- `tests/integration/conftest.py` missing or `sf` not provided → stop, install `testing-integration-setup` first.
- Spec asks for `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- Spec asks the test to `dispose_engine` / start its own connection / instantiate `async_sessionmaker(bind=engine)` directly → stop, that bypasses rollback; use `sf`.
- Spec asks to assert on `len(items) == N + 1` or use `any(...)` defensively → stop, rollback isolation makes exact equality correct.
- Spec asks to assert on `ConflictError` without checking `context["constraint"]` → stop, the constraint-name map is the load-bearing contract this test exists to pin.
- Spec adds raw INSERT for seed data on the table under test → stop, drive setup through `repo.create`.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asks to run Alembic from this test → stop, that's a migration regression test in a separate flat file.
- Spec uses `uuid4().hex[:8]` suffixes "to avoid duplicate-key flakes" → stop, rollback removes the need; use fixed values for clarity.
- Spec asks to use `sf` / transaction rollback for a client store → stop, there is no nested transaction; isolate by per-test namespace + teardown.
- Spec asks to mock the store SDK or assert against a fake → stop, this layer drives the real backend; the fake belongs to `test-fake-repository` at the handler-unit layer.
- Spec asserts on `ConflictError` + `context["constraint"]` → stop, that is the relational `IntegrityError` contract; a client store asserts the domain exceptions its adapter translates SDK errors into (`UpstreamError` / `NotFoundError`) instead.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asserts on store contents outside the test's own namespace → stop, assert only within the per-test collection/prefix.
