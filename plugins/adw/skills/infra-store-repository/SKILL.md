---
name: infra-store-repository
description: The house form for a repository adapter on a client-style store — a vector, cache or document backend (qdrant, redis, chroma, pinecone, mongo). One class wrapping the store's injected SDK client, mapping entities to its record shape and translating SDK errors into domain exceptions at the boundary. One skill serves every such vendor.
when_to_use: Producing or editing a repository adapter for an aggregate whose store is not relational.
paths: src/**/infrastructure/**
---

# Infrastructure Store Repository

Produces one repository class that adapts a domain repository protocol to a client-style datastore — any store reached through an injected SDK client rather than the shared SQLAlchemy bootstrap. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract. The skill is **vendor-agnostic** the same way `infra-capability-adapter` is: the pattern (client injection, record↔entity mapping, boundary error translation) is fixed here; the vendor rides in via the injected client type, the store's settings, and the spec's notes.

## When to use vs. neighbours

- The aggregate's store is the relational bootstrap store (SQLAlchemy/Postgres) → `infra-persistence`.
- The protocol file (`i_foo_repository.py`) → `domain-ports`.
- A single-action `ICan<Verb>` port (not an aggregate's collection) → `infra-capability-adapter`.
- The settings class the store's connection factory consumes → `infra-wiring`.
- The DI provider that constructs this repository → `infra-wiring`.
- An in-memory test stand-in for handler unit tests → `test-fake-repository`.
- The integration contract test that drives this adapter against the real store → `testing-contract`.

## File layout

```
src/<root>/infrastructure/<store-kind>/   # qdrant/, redis/, <vendor>/ — infra groups by tech
├── __init__.py
├── connection.py          # create_<store>_client(settings) — the datastore's factory, not this skill
├── settings.py            # infra-settings
└── repositories/
    ├── __init__.py        # update to re-export the new module
    └── foo_repository.py  # this skill writes this file
```

## Template — key-value / document form

```python
import json
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from myapp.domain.exceptions import NotFoundError, UpstreamError
# Never import IFooRepository — the adapter does NOT inherit the protocol (structural
# subtyping at the DI site is the contract, Rule 2). Importing it leaves a dead F401.
from myapp.domain.foos import Foo

from ..settings import FoosStoreSettings

__all__ = ["FooRepository"]


class FooRepository:
    def __init__(self, client: Redis, settings: FoosStoreSettings) -> None:
        self._client = client
        self._prefix = settings.key_prefix   # the store's container token (Rule 5)

    def _key(self, foo_id: UUID) -> str:
        return f"{self._prefix}:{foo_id}"

    def _record_to_entity(self, record: dict[str, object]) -> Foo:
        return Foo(id=UUID(str(record["id"])), name=str(record["name"]))

    async def add(self, foo: Foo) -> None:
        record = {"id": str(foo.id), "name": foo.name}
        try:
            await self._client.set(self._key(foo.id), json.dumps(record))
        except RedisError as exc:
            raise UpstreamError(
                "store write failed",
                {"key": self._key(foo.id), "reason": exc.__class__.__name__},
            ) from exc

    async def get_by_id(self, foo_id: UUID) -> Foo:
        try:
            raw = await self._client.get(self._key(foo_id))
        except RedisError as exc:
            raise UpstreamError(
                "store read failed",
                {"key": self._key(foo_id), "reason": exc.__class__.__name__},
            ) from exc
        if raw is None:
            raise NotFoundError("Foo not found", {"id": str(foo_id)})
        return self._record_to_entity(json.loads(raw))

    async def delete(self, foo_id: UUID) -> None:
        try:
            removed = await self._client.delete(self._key(foo_id))
        except RedisError as exc:
            raise UpstreamError(
                "store delete failed",
                {"key": self._key(foo_id), "reason": exc.__class__.__name__},
            ) from exc
        if removed == 0:
            raise NotFoundError("Foo not found", {"id": str(foo_id)})
```

## Template — vector-collection form

```python
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from myapp.domain.exceptions import UpstreamError
from myapp.domain.foos import Foo

from ..settings import FoosVectorSettings

__all__ = ["FooRepository"]


class FooRepository:
    def __init__(self, client: AsyncQdrantClient, settings: FoosVectorSettings) -> None:
        self._client = client
        self._collection = settings.collection

    async def add_many(self, foos: tuple[Foo, ...]) -> None:
        points = [
            PointStruct(
                id=str(foo.id),
                vector=foo.vector,
                payload={"bar_id": str(foo.bar_id), "text": foo.text},
            )
            for foo in foos
        ]
        try:
            await self._client.upsert(collection_name=self._collection, points=points)
        # qdrant's SDK has no single exception root — the boundary broad-catch is
        # sanctioned HERE because every path translates before re-raising (Rule 9).
        except Exception as exc:
            raise UpstreamError(
                "vector upsert failed",
                {"collection": self._collection, "reason": exc.__class__.__name__},
            ) from exc

    async def search(
        self, query_vector: list[float], k: int
    ) -> tuple[tuple[Foo, float], ...]:
        try:
            response = await self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                limit=k,
                with_payload=True,
                with_vectors=True,  # each entity carries its OWN vector, never the query's
            )
        except Exception as exc:
            raise UpstreamError(
                "vector search failed",
                {"collection": self._collection, "reason": exc.__class__.__name__},
            ) from exc
        # The store computed a similarity score per hit — return it alongside the entity
        # (the protocol's pair shape exists precisely so the score is not discarded).
        return tuple(
            (self._point_to_entity(point), point.score) for point in response.points
        )

    async def delete_by_bar(self, bar_id: UUID) -> None:
        selector = FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="bar_id", match=MatchValue(value=str(bar_id)))]
            )
        )
        try:
            await self._client.delete(
                collection_name=self._collection, points_selector=selector
            )
        except Exception as exc:
            raise UpstreamError(
                "vector delete failed",
                {
                    "collection": self._collection,
                    "bar_id": str(bar_id),
                    "reason": exc.__class__.__name__,
                },
            ) from exc

    def _point_to_entity(self, point: object) -> Foo:
        payload = point.payload or {}  # type: ignore[attr-defined]
        return Foo(
            id=UUID(str(point.id)),  # type: ignore[attr-defined]
            bar_id=UUID(str(payload["bar_id"])),
            text=str(payload["text"]),
            vector=list(point.vector or []),  # type: ignore[attr-defined]
        )
```

## Rules

### Form

1. **One class per module.** Filename: `<aggregate_snake>_repository.py`. Class: `<Aggregate>Repository` — **no vendor in the class name** (the directory carries the tech; an aggregate has exactly one home store, unlike a capability port that several vendors may implement).
2. **No explicit `(IFooRepository)` inheritance.** Structural subtyping.
3. **Method signatures match the protocol exactly**, including async mode, keyword-only markers, and compound return shapes (a `tuple[tuple[Foo, float], ...]` of scored hits is returned as pairs — never flattened to bare entities with the score discarded).

### Client & settings

4. **Inject the SDK client and the settings class.** Both come from `containers.py`; the client is built once by the datastore's `create_<store>_client(settings)` factory and injected as a `Singleton`. Never construct a client inline in a method, and never swap the injected client type for a different flavor of the SDK.
5. **Stash only what the methods need** — typically the store's *container token* (collection / key-prefix / index / bucket name) read from settings in `__init__`.

### Records ↔ entities

6. **Private, pure mapping helpers** (`_record_to_entity` / `_point_to_entity` / `_entity_to_record`): no IO, no logging. IDs serialize as strings unless the SDK is UUID-native.
7. **The record shape is a design decision, not a transcription.** What becomes the key, what goes into the payload, what the store indexes — the client-store analogue of "column types are judgment" in `infra-persistence`. The spec's notes guide it.
8. **An entity is reconstructed from its own stored data.** Never substitute query-side values for stored ones (e.g. a search result's vector is the point's own, not the query's); when the read path doesn't consume a stored field, omit it explicitly rather than faking it.

### Exception translation

9. **Catch the SDK's exception family at the boundary and raise a domain exception** with `raise <DomainException>(...) from exc`. When the SDK has no single exception root (qdrant), a broad `except Exception` immediately around the client call is sanctioned — every path must translate. The SDK's exception types never escape the repository.
10. **Mandatory fallback:** `UpstreamError` for network / unknown store failures. An absent record on `get_by_id` is **not** an SDK error — detect it (a `None`, an empty result, a zero count) and raise `NotFoundError`.
11. **Populate `context`** with the container token (`collection` / `key` / `index`), the identifying inputs, and the upstream code or exception class name.

### Vendor & semantics

12. **Vendor semantics come from the SDK, not from this skill.** Query API, filter DSL, batching, consistency options — read them from the SDK's own documentation. A **new vendor is a store-profile row plus its package — never a fork of this skill** (the same way `infra-capability-adapter` serves boto3, httpx, PyJWT, and openai with one skill).
13. **No provisioning.** The repository never creates collections, indexes, buckets, or schemas — provisioning is a deployment/bootstrap concern.
14. **Ordering is explicit.** A `list`/`search` that promises an order must produce it deliberately (the store's score order, an explicit sort key) — never rely on insertion accident.
15. **No logging, no retries, no caching, no domain reasoning.** Same thinness contract as every adapter (see `infra-capability-adapter`'s adapters-are-thin rules).

## Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.foos import Foo`); the sibling settings module relative (`from ..settings import FoosStoreSettings`). **Never import the protocol the adapter satisfies** — structural subtyping needs no import (Rule 2); importing it is a dead F401.
- SDK types stay inside the adapter; method signatures use domain types or primitives only.
- Raw SDK payloads may be `dict[str, Any]` / `object` at the immediate boundary — convert to the domain type in the mapping helper, never return them.
- No `from __future__ import annotations`. Full annotations on every method.

## Package wiring

The `repositories/__init__.py` must re-export the new module via `from .foo_repository import *`. Follow `architecture`.

## Hard stops

- The aggregate's store is relational (the `postgres` profile) → stop, use `infra-persistence`.
- Spec asks for SQL, SQLAlchemy, or a `Table` for this aggregate → stop, that is the relational path (`infra-persistence`).
- Spec asks the repository to create or migrate the collection/index/bucket → stop, provisioning is not the repository's concern.
- Spec asks for atomicity across this store and another (two stores in one transaction) → stop, there is no cross-store transaction; compensation lives in the handler (`patterns`).
- Spec asks the repository to log → stop, repositories never log.
- The port is a single-action capability (`ICan<Verb>`), not an aggregate's collection → stop, use `infra-capability-adapter`.
