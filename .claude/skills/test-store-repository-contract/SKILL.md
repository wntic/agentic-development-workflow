---
name: test-store-repository-contract
description: Apply when adding or modifying an integration test for a client-style store repository — the `infra-store-repository` adapter for a vector / cache / document store (qdrant, redis, chroma, …). Produces one test file under `tests/integration/<store-kind>/test_<aggregate>_repository.py` that drives the real repository against a real store via testcontainers, isolated by a per-test namespace (a fresh collection / key-prefix) instead of transaction rollback, exercising the CRUD round-trip, the store's non-CRUD verbs (search, delete-by-filter, …), the entity↔record mapping, and the SDK-error → domain-exception (`UpstreamError` / `NotFoundError`) translation. Does not own the relational contract test (use `test-repository-contract`), the repository itself (use `infra-store-repository`), the protocol (use `domain-repository-protocol`), or any HTTP-layer test (use `test-restapi-endpoint`).
---

# Test — Store Repository Contract

Produces one integration-test file per client-style store repository. This is the non-relational sibling of `test-repository-contract`: same goal (prove the real adapter against the real backend), different mechanics. A client store has **no SQL transaction to roll back** and **no `IntegrityError` constraint map** — so isolation is by a per-test namespace, and the load-bearing contract is the entity↔record mapping plus the SDK-error → domain-exception translation the adapter performs at its boundary.

## When to use vs. neighbours

- A repository adapter under `infrastructure/<store-kind>/repositories/` (qdrant/redis/…) → this skill.
- A repository on the relational (`uses_bootstrap`) store → `test-repository-contract` (it uses `sf` + transaction rollback).
- The repository being tested → `infra-store-repository`.
- An in-memory fake of the same protocol for handler unit tests → `test-fake-repository`.
- HTTP-layer integration (route, auth, OpenAPI) → `test-restapi-endpoint`.

## Isolation — namespace, not rollback

A client store has no nested transaction, so the `sf`-rollback model does not apply (see `test-integration-isolation`, which is relational-only). Isolate exactly as the `s3_prefix` pattern does: **each test owns a fresh namespace** — a unique collection name (qdrant/chroma), key-prefix (redis), or database/bucket — created in a fixture and dropped at teardown. Bring the real store up once per session via testcontainers; create/destroy the per-test namespace per test. This skill's fixtures live in the sibling `tests/integration/<store-kind>/conftest.py` (not in `test-integration-isolation`, which owns only the relational + blob fixtures).

## Template(s)

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

    with QdrantContainer("qdrant/qdrant:latest") as q:
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

1. **Each test runs against the real store via testcontainers** — never a fake, never a mock. The fake (`test-fake-repository`) is for handler unit tests; this layer exists to prove the adapter against the actual backend, which is the only place the SDK call shape and error mapping are exercised.
2. **Isolate by a per-test namespace, not rollback.** A fresh collection / key-prefix / database per test, created in the `store` (or equivalently-named) fixture and dropped at teardown. There is no transaction to roll back; do not reach for `sf`.
3. **The container is session-scoped; the namespace is function-scoped.** One store per run (expensive to start); one namespace per test (cheap, gives each test sole ownership). CI reads a provided endpoint from env (the `os.getenv("CI")` branch) instead of starting a container.
4. **Exercise the full protocol**, CRUD verbs and non-CRUD alike — `add_many`/`get`/`delete` AND the store's own verbs (`search`, `delete_by_<field>`, range/scan). A `search` test asserts ordering (nearest-first / score-ordered), not just membership.
5. **Assert the entity↔record mapping round-trips.** What was written comes back as the same entity (ids, payload fields, and — when the read path hydrates it — the vector). A returned scored pair asserts both the entity and that the score is a real `float`, not a placeholder.
6. **Assert the SDK-error → domain-exception translation end-to-end.** This is the load-bearing contract (the client-store analogue of the relational `context["constraint"]` assertion): point the repository at an unreachable/closed client, or trigger a store rejection, and assert the boundary raises the domain exception the adapter promises — `UpstreamError` for a network / store failure, `NotFoundError` for an absent record — never the raw SDK exception. These are the manifest-declared domain exceptions `infra-store-repository` translates into at its boundary (shown here as placeholders); assert whichever ones that adapter actually raises, not a frozen literal. Assert the `context` keys the adapter promises.
7. **Fixed test values are fine.** Namespace isolation gives each test an empty store at start; no unique-suffix natural keys needed (same as the relational contract's rollback guarantee).
8. **Small test vectors.** Use a tiny dimension (e.g. 3) created on the per-test collection; the production embedding dimension is a settings concern, not the contract's.
9. **No FastAPI, no `httpx`, no DI container.** Import the repository class, construct it with the real client + a settings object scoped to the per-test namespace, call methods, assert. The HTTP surface is `test-restapi-endpoint`.
10. **No assertions on global store contents.** Assert only within this test's namespace — exactly the `s3_prefix` discipline, because cleanup is namespace-scoped, not transactional.

## Inlined typing / import rules

- `pytest`, the store SDK (`qdrant_client` / `redis` / …), stdlib `uuid` / `os`, `myapp.domain.*`, `myapp.infrastructure.<store-kind>.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature and fixture, including the `store` fixture's `tuple[<Client>, str]` shape. Yielding fixtures use `AsyncIterator[T]` / `Iterator[T]`.
- No `from __future__ import annotations`.

## Hard stops

- The repository is on the relational (`uses_bootstrap`) store → stop, use `test-repository-contract` (`sf` + rollback), not this skill.
- Spec asks to use `sf` / transaction rollback for a client store → stop, there is no nested transaction; isolate by per-test namespace + teardown.
- Spec asks to mock the store SDK or assert against a fake → stop, this layer drives the real backend; the fake belongs to `test-fake-repository` at the handler-unit layer.
- Spec asserts on `ConflictError` + `context["constraint"]` → stop, that is the relational `IntegrityError` contract; a client store asserts the domain exceptions its adapter translates SDK errors into (`UpstreamError` / `NotFoundError`) instead.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asserts on store contents outside the test's own namespace → stop, assert only within the per-test collection/prefix.
