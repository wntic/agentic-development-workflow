---
name: test-repository-contract
description: The house form for one relational repository's integration test — drives the real class against a real Postgres through the `sf` fixture: CRUD round-trip, every unique constraint on insert AND update, cascades, every `get_by_<field>`, the `updated_at` advance, and `context["constraint"]` asserted to pin the `IntegrityError` translator.
when_to_use: Writing or changing the contract test for a repository adapter on a relational store.
paths: tests/**
---

# Test — Repository Contract

Produces one integration-test file per repository. Catches what unit-level coverage cannot: real `UNIQUE` / `FK` violations, real `ON DELETE CASCADE` semantics, the `IntegrityError`-to-domain-exception translator's constraint-name map, and the `onupdate=` clause on `updated_at`.

## When to use vs. neighbours

- A new or modified repository adapter under `infrastructure/postgres/repositories/` (a relational store) → this skill.
- A repository on a client-style store (qdrant/redis/…, `infra-store-repository`) → `test-store-repository-contract` (namespace isolation, not `sf`/rollback).
- Schema-only checks (an index exists, a migration carries data correctly) → separate flat files under `tests/integration/postgres/` (`test_indexes.py`, `test_<NNNN>_migration.py`) that use `db_settings` and `run_alembic`, not `sf`.
- HTTP-layer integration (route, auth, OpenAPI) → `test-restapi-endpoint`.
- The rollback `conftest.py` itself → `test-integration-isolation` (one-shot).
- Pure domain test → `test-domain-entity` / `test-domain-value-object` / `test-domain-enum` / `test-domain-service`.

## Template(s)

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

## Rules

1. **Every test takes `sf: async_sessionmaker[AsyncSession]`.** The rollback fixture from `test-integration-isolation` makes the DB empty at test start and discards everything at teardown. No marker, no other DB fixture.
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

## Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, stdlib `uuid`, `myapp.domain.*`, `myapp.infrastructure.postgres.repositories.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature including `sf: async_sessionmaker[AsyncSession]`.
- Builder `_<aggregate>()` returns the entity type; overrides keyword-only.
- No `from __future__ import annotations`.

## Hard stops

- `tests/integration/conftest.py` missing or `sf` not provided → stop, install `test-integration-isolation` first.
- Spec asks for `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- Spec asks the test to `dispose_engine` / start its own connection / instantiate `async_sessionmaker(bind=engine)` directly → stop, that bypasses rollback; use `sf`.
- Spec asks to assert on `len(items) == N + 1` or use `any(...)` defensively → stop, rollback isolation makes exact equality correct.
- Spec asks to assert on `ConflictError` without checking `context["constraint"]` → stop, the constraint-name map is the load-bearing contract this test exists to pin.
- Spec adds raw INSERT for seed data on the table under test → stop, drive setup through `repo.create`.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asks to run Alembic from this test → stop, that's a migration regression test in a separate flat file.
- Spec uses `uuid4().hex[:8]` suffixes "to avoid duplicate-key flakes" → stop, rollback removes the need; use fixed values for clarity.
