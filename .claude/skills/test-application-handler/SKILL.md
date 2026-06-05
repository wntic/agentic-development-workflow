---
name: test-application-handler
description: Apply when adding or modifying a unit test for an application command or query handler. Produces one self-contained test file under `tests/unit/application/test_<verb>_<noun>_handler.py` using AAA structure, an in-memory fake from `tests/unit/fakes/`, the `_CALLER` module-level UUID, and optional inline `_RaiseXxxRepo` subclasses for one-off failure injection (including the compensating-transaction "DB-fails-after-upload" path). No mocks, no fixtures, no real DB, no HTTP. Each test runs in milliseconds. Pairs with `application-command`, `application-query`, and `application-compensating-tx`. Defers fake creation to `test-fake-repository`; end-to-end coverage to `test-restapi-endpoint`.
---

# Test — Application Handler (unit)

Produces one unit-test file per handler module. Runs in milliseconds against in-memory fakes. Coverage targets the happy path plus every domain exception the handler propagates and — for compensating-transaction handlers — the post-failure undo.

## When to use vs. neighbours

- A new or modified handler under `application/<subdomain>/` → this skill.
- A fake the test needs that doesn't exist yet → `test-fake-repository` (write the fake first).
- A test that drives the handler through the HTTP surface → `test-restapi-endpoint` (integration, not unit).
- A test for a domain entity / value object / enum / service → the matching `test-domain-*` skill.
- A real-DB test of the repository the handler calls → `test-repository-contract`.

## File location

```
tests/unit/application/
└── test_<verb>_<noun>_handler.py        # mirrors the handler module's filename
```

One file per handler. Compensating-tx assertions live in the file for the handler that performs the compensation, not in a separate file.

## Template(s)

### `create` handler

```python
import uuid

import pytest

from myapp.application.foos import CreateFooCommand, CreateFooHandler
from myapp.domain.exceptions import ConflictError
from tests.unit.fakes.fake_foo_repository import FakeFooRepository

_CALLER = uuid.uuid4()

async def test_assigns_uuid_and_stores() -> None:
    # Arrange
    repo = FakeFooRepository()
    handler = CreateFooHandler(repo=repo)

    # Act
    foo_id = await handler.execute(CreateFooCommand(caller_id=_CALLER, name="alpha"))

    # Assert
    assert foo_id is not None
    stored = await repo.get_by_id(foo_id)
    assert stored.name == "alpha"
    assert stored.id == foo_id

async def test_duplicate_name_raises_conflict() -> None:
    repo = FakeFooRepository()
    handler = CreateFooHandler(repo=repo)
    await handler.execute(CreateFooCommand(caller_id=_CALLER, name="alpha"))

    with pytest.raises(ConflictError) as exc:
        await handler.execute(CreateFooCommand(caller_id=_CALLER, name="alpha"))

    assert exc.value.context["constraint"] == "uq_foos_name"

async def test_name_is_stripped_on_create() -> None:
    repo = FakeFooRepository()
    handler = CreateFooHandler(repo=repo)

    foo_id = await handler.execute(CreateFooCommand(caller_id=_CALLER, name="  alpha  "))

    stored = await repo.get_by_id(foo_id)
    assert stored.name == "alpha"
```

### `update` handler — PATCH `None`-means-don't-touch (the most common bug catch)

```python
async def test_partial_update_leaves_unspecified_fields_untouched() -> None:
    repo = FakeFooRepository()
    create_handler = CreateFooHandler(repo=repo)
    update_handler = UpdateFooHandler(repo=repo)
    foo_id = await create_handler.execute(
        CreateFooCommand(caller_id=_CALLER, name="alpha", sort_order=5),
    )

    await update_handler.execute(
        UpdateFooCommand(caller_id=_CALLER, id=foo_id, name="beta", sort_order=None),
    )

    stored = await repo.get_by_id(foo_id)
    assert stored.name == "beta"
    assert stored.sort_order == 5  # None on the command means "don't touch"

async def test_update_unknown_id_raises_not_found() -> None:
    handler = UpdateFooHandler(repo=FakeFooRepository())

    with pytest.raises(NotFoundError):
        await handler.execute(
            UpdateFooCommand(caller_id=_CALLER, id=uuid.uuid4(), name="x"),
        )
```

### `delete` handler with one-off `InUseError`

```python
class _RaiseInUseFooRepo(FakeFooRepository):
    async def delete(self, id: uuid.UUID) -> None:
        raise InUseError(
            "foo is used by one or more bars",
            {"reference_type": "foo", "id": str(id)},
        )

async def test_delete_propagates_in_use_error() -> None:
    target_id = uuid.uuid4()
    handler = DeleteFooHandler(repo=_RaiseInUseFooRepo(items=[
        Foo(id=target_id, name="alpha"),
    ]))

    with pytest.raises(InUseError) as exc:
        await handler.execute(DeleteFooCommand(caller_id=_CALLER, id=target_id))

    assert exc.value.context["reference_type"] == "foo"
    assert exc.value.context["id"] == str(target_id)
```

### `list` query handler — sort + pagination

```python
async def test_sorted_by_sort_order_then_name() -> None:
    repo = FakeFooRepository(items=[
        Foo(id=uuid.uuid4(), name="b", sort_order=1),
        Foo(id=uuid.uuid4(), name="a", sort_order=1),
        Foo(id=uuid.uuid4(), name="c", sort_order=0),
    ])
    handler = ListFoosHandler(repo=repo)

    result = await handler.execute(ListFoosQuery(filter=FooListFilter(limit=10)))

    assert [f.name for f in result.items] == ["c", "a", "b"]
    assert result.total == 3
```

### `compensating-tx` handler — upload, then DB fails, assert undo

```python
class _RaiseAfterUploadRepo(FakeFooRepository):
    async def create(self, foo: Foo) -> None:
        raise RuntimeError("simulated DB failure after blob upload")

async def test_db_failure_after_upload_deletes_blob() -> None:
    repo = _RaiseAfterUploadRepo()
    storage = FakeBlobStorage()
    handler = UpsertFooHandler(repo=repo, storage=storage)

    with pytest.raises(RuntimeError):
        await handler.execute(
            UpsertFooCommand(caller_id=_CALLER, data=b"payload", ...),
        )

    # Compensation contract: the blob written before the failed DB step
    # must have been deleted via the best-effort cleanup capability.
    assert len(storage.puts) == 1
    assert storage.deletes == [storage.puts[0][0]]  # exactly the uploaded key
```

The simulated exception type is incidental — `RuntimeError` here, or any uncaught exception. The contract is: **the put landed, then something failed, then the same key was deleted.** That's the compensation assertion.

## Rules

1. **Top-level `async def test_*` functions.** No class wrappers. `pytest-asyncio` runs in auto mode — never add `@pytest.mark.asyncio` or `@pytest.mark.integration`.
2. **`_CALLER = uuid.uuid4()` at module scope** so command construction stays terse.
3. **AAA blocks separated by blank lines.** Arrange — construct fake(s) and handler. Act — call `handler.execute(...)`. Assert — read state back through the fake or assert raised exception. The visual separation makes the structure scannable.
4. **The handler is constructed inside each test, not in a fixture.** Handlers are cheap to build; per-test instantiation keeps each test self-contained.
5. **Read state back via fake's domain methods** (`await repo.get_by_id(...)`), not via attribute peeking on `repo._store`.
6. **Drive setup through the handler path that production uses** when possible. An update-handler test calls `CreateFooHandler` first to set up an "existing" foo, rather than `repo.create(...)`. This keeps tests robust to repository-contract changes.
7. **For exception cases, use `pytest.raises(<DomainExceptionType>) as exc`** and assert on `exc.value.context["..."]` when context shape is the contract being pinned (especially `context["constraint"]` for `ConflictError` — that's the test that proves the integrity-error map is wired right at the repo level even though we're using a fake; the fake's exception copies the real repo's constraint name).
8. **Compensation tests assert call-record state**, not implementation details. For a storage capability, `storage.puts` and `storage.deletes` are the observation surface. Assert the right key was undone, in the right order, for the right reason — but never assert that a specific Python call site invoked them.
9. **One-off failure injection uses an inline `_RaiseXxxRepo(FakeFooRepository)` subclass at module scope.** Subclass name starts with `_` (file-private). Override exactly the method under test — never re-stub the whole protocol.

## Coverage checklist (one `test_*` per case — don't parametrize, names form the spec)

### `create` handler

- `test_assigns_uuid_and_stores` — handler returns a `UUID`; `get_by_id` returns the entity with expected fields and that same id.
- `test_duplicate_<unique_field>_raises_conflict` — for every uniqueness constraint enforced by the repo, assert `ConflictError` on the second attempt with `exc.value.context["constraint"] == "<full_constraint_name>"`.
- Field normalization (when applicable): assert the stored entity has the normalized form (`strip`, `upper`, canonicalized URL), not the raw input.

### `update` handler

- `test_partial_update_leaves_unspecified_fields_untouched` — set one field with a real value and another with `None`; assert the `None` field is **unchanged** and the real field is updated. This is the PATCH contract and the single most common bug-catching test.
- `test_update_unknown_id_raises_not_found`.
- `test_update_duplicate_<unique_field>_raises_conflict` — renaming row B to row A's name raises `ConflictError`.

### `delete` handler

- `test_delete_removes` — happy path; `get_by_id` after delete raises `NotFoundError`.
- `test_delete_unknown_id_raises_not_found`.
- `test_delete_<resource>_in_use_propagates` — for referenceable resources, use the inline `_RaiseInUseFooRepo` subclass; assert `InUseError` propagates with the correct `context["reference_type"]`.

### `get` / single-read query handler

- `test_returns_entity_when_present` — load the fake with one entity; the handler returns it intact.
- `test_returns_none_or_raises_when_absent` — match the handler's contract (`Entity | None` returns `None`; `Entity` returns raises `NotFoundError`).

### `list` query handler

- `test_sorted_by_<order_key>` — load the fake with deliberately unsorted entities (vary both primary and secondary sort keys); assert the order of `result.items` is exactly the expected sequence.
- `test_pagination_offset_limit` — load N > limit entities; call with `limit=L, offset=O`; assert `len(result.items) == L` and `result.total == N`.

### `compensating-tx` handler

- `test_db_failure_after_upload_deletes_blob` — fake repo's mutation step raises; assert `storage.deletes` contains the keys `storage.puts` recorded immediately before the failure.
- `test_db_failure_after_multi_step_upload_deletes_all_uploaded_so_far` — when the upload step accumulates multiple keys before the DB write, simulate failure mid-loop or after the loop; assert every key that was uploaded got passed to `delete_many_best_effort`.
- `test_successful_upsert_cleans_up_previous_blob` — for upsert handlers that return a `previous_key`, the success-path cleanup deletes the *old* key (not the new one); use the regular happy-path setup and assert `storage.deletes` contains the previous key after the second call.

## Hard prohibitions (across all handler-unit tests)

- **No `mock.patch`, `MagicMock`, `AsyncMock`, `monkeypatch`** for protocol substitution. Use a fake from `tests/unit/fakes/`, or extend it via an inline `_RaiseXxxRepo` subclass.
- **No `@pytest.mark.asyncio` or `@pytest.mark.integration`.** Auto mode + path-based collection.
- **No fixtures from `tests/integration/`.** No DB, no real app, no JWT, no S3.
- **No `print`, no `caplog` assertions, no log inspection.** Handler logging is a side effect of success — assert on the returned state instead.
- **No `time.sleep`, no real network, no real filesystem.** The whole file should run in well under a second.
- **No business-logic re-implementation in the test.** Don't compute the expected slug, normalize the name, or sort items the way the domain entity does — let the handler produce the output and assert against it.

## Inlined typing / import rules

- Stdlib (`uuid`, `datetime`), `pytest`, `myapp.application.*`, `myapp.domain.exceptions`, `myapp.domain.<subdomain>`, `tests.unit.fakes.*` only.
- `X | None`, full annotations on every fixture, builder, and inline subclass `__init__`.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks for `MagicMock` to stub the repo or storage → stop, use a fake or an inline `_RaiseXxxRepo` subclass.
- Spec needs the test to hit a real database or HTTP endpoint → stop, that's `test-repository-contract` or `test-restapi-endpoint`.
- Spec asks for log assertions on the handler's success event → stop, those are side effects; tests assert on returned state.
- Required fake does not exist in `tests/unit/fakes/` → stop, produce it first via `test-fake-repository`.
- Spec asks to add `fail_next_create=True`-style flags to the fake → stop, use the inline subclass at the test module scope instead.
- Spec asks the test to construct the FastAPI app or import `myapp.restapi.*` → stop, this is a unit test; the HTTP surface is `test-restapi-endpoint`.
