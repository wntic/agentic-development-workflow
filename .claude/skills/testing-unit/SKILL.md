---
name: testing-unit
description: House style for fast, no-IO unit tests and the whole unit tier's constitution: domain entity / value-object / enum / service tests, application handler tests with in-memory fakes, the fake-repository pattern (stores and returns copies with an updated log, honours every param, a missing fake is a stop not an improvisation), the seven assert-strength recipes, the `@pytest.mark.ac("AC-n")` criteria marker, and the grep-firewall architecture rule. Carries the testing pyramid, conftest hierarchy, fixture-vs-builder rule, no-mocks contract and per-layer speed targets.
when_to_use: Writing a unit test for a domain object, an application handler, a fake repository, or a static architecture invariant.
---
# Testing — unit tier

This merged skill covers 7 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from test-application-handler -->

## Test — Application Handler (unit)

Produces one unit-test file per handler module. Runs in milliseconds against in-memory fakes. Coverage targets the happy path plus every domain exception the handler propagates and — for compensating-transaction handlers — the post-failure undo.

### When to use vs. neighbours

- A new or modified handler under `application/<subdomain>/` → this skill.
- A fake the test needs that doesn't exist yet → `test-fake-repository` (write the fake first).
- A test that drives the handler through the HTTP surface → `test-restapi-endpoint` (integration, not unit).
- A test for a domain entity / value object / enum / service → the matching `test-domain-*` skill.
- A real-DB test of the repository the handler calls → `test-repository-contract`.

### File location

```
tests/unit/application/
└── test_<verb>_<noun>_handler.py        # mirrors the handler module's filename
```

One file per handler. Compensating-tx assertions live in the file for the handler that performs the compensation, not in a separate file.

### Template(s)

#### `create` handler

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

#### `update` handler — PATCH `None`-means-don't-touch (the most common bug catch)

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

#### `delete` handler with one-off `InUseError`

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

#### `list` query handler — sort + pagination

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

#### `compensating-tx` handler — upload, then DB fails, assert undo

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

### Rules

1. **Top-level `async def test_*` functions.** No class wrappers. `pytest-asyncio` runs in auto mode — never add `@pytest.mark.asyncio` or `@pytest.mark.integration`.
2. **`_CALLER = uuid.uuid4()` at module scope** so command construction stays terse. The templates show the **authenticated** form: `caller_id=_CALLER` is passed because the command carries `caller_id`. For a command in an app that declares no auth (or dispatched only by anonymous routes), the command has no `caller_id` field — drop the `caller_id=_CALLER` argument and the `_CALLER` constant (mirrors `application-command` DTO rule 2). `_CALLER` is the authenticated-form convention, not a blanket one.
3. **AAA blocks separated by blank lines.** Arrange — construct fake(s) and handler. Act — call `handler.execute(...)`. Assert — read state back through the fake or assert raised exception. The visual separation makes the structure scannable.
4. **The handler is constructed inside each test, not in a fixture.** Handlers are cheap to build; per-test instantiation keeps each test self-contained.
5. **Read state back via fake's domain methods** (`await repo.get_by_id(...)`), not via attribute peeking on `repo._store`.
6. **Drive setup through the handler path that production uses** when possible. An update-handler test calls `CreateFooHandler` first to set up an "existing" foo, rather than `repo.create(...)`. This keeps tests robust to repository-contract changes.
7. **For exception cases, use `pytest.raises(<DomainExceptionType>) as exc`** and assert on `exc.value.context["..."]` when context shape is the contract being pinned (especially `context["constraint"]` for `ConflictError` — that's the test that proves the integrity-error map is wired right at the repo level even though we're using a fake; the fake's exception copies the real repo's constraint name).
8. **Compensation tests assert call-record state**, not implementation details. For a storage capability, `storage.puts` and `storage.deletes` are the observation surface. Assert the right key was undone, in the right order, for the right reason — but never assert that a specific Python call site invoked them.
9. **One-off failure injection uses an inline `_RaiseXxxRepo(FakeFooRepository)` subclass at module scope.** Subclass name starts with `_` (file-private). Override exactly the method under test — never re-stub the whole protocol.
10. **A handler dependency typed as a CONCRETE domain service (not a Protocol) cannot be faked structurally — subclass it.** Repositories/capabilities are injected as `Protocol`s, so a structural fake satisfies them. A domain *service* is often injected as its concrete class (`def __init__(self, quota_policy: QuotaPolicy)`), and mypy rejects a structural `FakeQuotaPolicy` there — a stand-in must be a true subtype. Two sanctioned shapes: (a) **subclass the service** — `class _StubQuotaPolicy(QuotaPolicy)` overriding the method under test and bypassing the real `__init__` (`def __init__(self) -> None: pass`, since the test doesn't need its injected deps); or (b) **inject via a Protocol** — give the service a `domain-capability-protocol`-style interface and type the handler ctor to it, so a structural fake works like any other. Prefer (b) when the service is itself injected widely; (a) is the lighter test-only path. Do NOT reach for `# type: ignore` on the ctor or a `MagicMock` — that is the concrete-stub smell from notes/13. (Same guidance in `test-fake-repository`.)

### Assert strength — pin the contract, not a coincidence (§9)

An assert is **strong** only if a plausibly-wrong body would FAIL it; an assert a wrong body still passes is **weak** and is exactly what the §9 adversarial pass flags. These recipes (distilled from real weak asserts the adversarial pass caught) keep an assert strong at authoring time — apply them, don't wait to be flagged:

1. **Pin PERSISTED state, not the in-memory entity.** Assert the write happened via the fake's `updated` call-record (`assert repo.updated == [id]`) AND read the value back (`(await repo.get_by_id(id)).status == DONE`). The fake returns a COPY and logs updates (`test-fake-repository` Rule 9), so a body that mutates the entity but never calls `update()` **reds**. Asserting on the entity object the handler mutated in place pins nothing (it observes the in-memory mutation, not the persist).
2. **Test a drop / skip / filter with a SURVIVOR present — never an empty result.** "Below-threshold hits are dropped" / "stale hit is skipped" asserted on an empty set passes a body that drops *everything* (or returns empty for the wrong reason). Seed one item that must SURVIVE alongside the one that must be dropped, and assert the survivor is present and the dropped one absent — the empty-set can't isolate the cause.
3. **Exercise a non-boundary case, not only the boundary.** A quota/limit test that only hits FREE (or only the `>=` boundary) leaves PRO/ENTERPRISE limit-selection — and the "is the right limit even chosen?" logic — unpinned. Add a second tier and a value clearly inside the limit.
4. **Distinguish `total` from `len(items)` with page size < match count.** A paged-list test where the page holds every match passes a body that returns `len(items)` as the total. Seed more rows than the page size so a `total = len(page)` bug reds.
5. **Use ≥2 distinct rows where one can't prove scoping or a join.** A tenant-scope / parent-link / join assertion with a single seeded row passes a body that ignores the scope entirely. Seed a second row (another tenant, another parent) that must be EXCLUDED.
6. **For an echoed / derived field, choose an input a constant would not satisfy.** A "returns the caller's role" / "token subject is the user id" assert against a hard-coded-looking value (the default role, a fixed id) passes a body that returns a constant. Pick a non-default value so only the real wiring satisfies it.
7. **On a guard / reject path, assert NO side effect — not just the raised exception.** Over-quota / already-in-final-state / not-found must also assert nothing was persisted or called (`repo.updated == []`, `storage.puts == []`), or a body that raises *after* writing still passes.

### Coverage checklist (one `test_*` per case — don't parametrize, names form the spec)

#### `create` handler

- `test_assigns_uuid_and_stores` — handler returns a `UUID`; `get_by_id` returns the entity with expected fields and that same id.
- `test_duplicate_<unique_field>_raises_conflict` — for every uniqueness constraint enforced by the repo, assert `ConflictError` on the second attempt with `exc.value.context["constraint"] == "<full_constraint_name>"`.
- Field normalization (when applicable): assert the stored entity has the normalized form (`strip`, `upper`, canonicalized URL), not the raw input.

#### `update` handler

- `test_partial_update_leaves_unspecified_fields_untouched` — set one field with a real value and another with `None`; assert the `None` field is **unchanged** and the real field is updated. This is the PATCH contract and the single most common bug-catching test.
- `test_update_unknown_id_raises_not_found`.
- `test_update_duplicate_<unique_field>_raises_conflict` — renaming row B to row A's name raises `ConflictError`.

#### `delete` handler

- `test_delete_removes` — happy path; `get_by_id` after delete raises `NotFoundError`.
- `test_delete_unknown_id_raises_not_found`.
- `test_delete_<resource>_in_use_propagates` — for referenceable resources, use the inline `_RaiseInUseFooRepo` subclass; assert `InUseError` propagates with the correct `context["reference_type"]`.

#### `get` / single-read query handler

- `test_returns_entity_when_present` — load the fake with one entity; the handler returns it intact.
- `test_returns_none_or_raises_when_absent` — match the handler's contract (`Entity | None` returns `None`; `Entity` returns raises `NotFoundError`).

#### `list` query handler

- `test_sorted_by_<order_key>` — load the fake with deliberately unsorted entities (vary both primary and secondary sort keys); assert the order of `result.items` is exactly the expected sequence.
- `test_pagination_offset_limit` — load N > limit entities; call with `limit=L, offset=O`; assert `len(result.items) == L` and `result.total == N`.

#### `compensating-tx` handler

- `test_db_failure_after_upload_deletes_blob` — fake repo's mutation step raises; assert `storage.deletes` contains the keys `storage.puts` recorded immediately before the failure.
- `test_db_failure_after_multi_step_upload_deletes_all_uploaded_so_far` — when the upload step accumulates multiple keys before the DB write, simulate failure mid-loop or after the loop; assert every key that was uploaded got passed to `delete_many_best_effort`.
- `test_successful_upsert_cleans_up_previous_blob` — for upsert handlers that return a `previous_key`, the success-path cleanup deletes the *old* key (not the new one); use the regular happy-path setup and assert `storage.deletes` contains the previous key after the second call.

### Hard prohibitions (across all handler-unit tests)

- **No `mock.patch`, `MagicMock`, `AsyncMock`, `monkeypatch`** for protocol substitution. Use a fake from `tests/unit/fakes/`, or extend it via an inline `_RaiseXxxRepo` subclass.
- **No `@pytest.mark.asyncio` or `@pytest.mark.integration`.** Auto mode + path-based collection.
- **No fixtures from `tests/integration/`.** No DB, no real app, no JWT, no S3.
- **No `print`, no `caplog` assertions, no log inspection.** Handler logging is a side effect of success — assert on the returned state instead.
- **No `time.sleep`, no real network, no real filesystem.** The whole file should run in well under a second.
- **No business-logic re-implementation in the test.** Don't compute the expected slug, normalize the name, or sort items the way the domain entity does — let the handler produce the output and assert against it.

### Inlined typing / import rules

- Stdlib (`uuid`, `datetime`), `pytest`, `myapp.application.*`, `myapp.domain.exceptions`, `myapp.domain.<subdomain>`, `tests.unit.fakes.*` only.
- `X | None`, full annotations on every fixture, builder, and inline subclass `__init__`.
- No `from __future__ import annotations`.

### Hard stops

- Spec asks for `MagicMock` to stub the repo or storage → stop, use a fake or an inline `_RaiseXxxRepo` subclass.
- Spec needs the test to hit a real database or HTTP endpoint → stop, that's `test-repository-contract` or `test-restapi-endpoint`.
- Spec asks for log assertions on the handler's success event → stop, those are side effects; tests assert on returned state.
- Required fake does not exist in `tests/unit/fakes/` → stop, produce it first via `test-fake-repository`.
- Spec asks to add `fail_next_create=True`-style flags to the fake → stop, use the inline subclass at the test module scope instead.
- Spec asks the test to construct the FastAPI app or import `myapp.restapi.*` → stop, this is a unit test; the HTTP surface is `test-restapi-endpoint`.


<!-- merged from test-fake-repository -->

## Test Fake — Repository / Capability

Produces one in-memory stand-in class for a domain protocol. Handler unit tests under `tests/unit/application/` use this fake instead of the real `infrastructure/` adapter. The fake satisfies the protocol **structurally** — no `(IFooRepository)` inheritance, no `@runtime_checkable` registration.

### When to use vs. neighbours

- A handler unit test (`test-application-handler`) needs a fake that does not yet exist → this skill.
- The handler test that consumes the fake → `test-application-handler`.
- The real adapter the fake stands in for → `infra-sqlalchemy-repository`.
- The domain protocol the fake matches → `domain-repository-protocol` or `domain-capability-protocol`.
- A one-off failure injection for a single handler test → don't extend the fake; declare a `_RaiseXxxRepo(FakeFooRepository)` subclass at the handler test module scope (the pattern is owned by `test-application-handler`).
- Integration tests that drive the real adapter → `test-repository-contract` (no fake).

### File location and naming

```
tests/unit/fakes/
└── fake_<aggregate_snake>_repository.py        # class FakeFooRepository
```

For capabilities: `fake_<capability_snake>.py` → `Fake<Capability>` (e.g. `fake_blob_storage.py` → `FakeBlobStorage`).

**No `__all__`, no `__init__.py`.** Handler tests import directly:

```python
from tests.unit.fakes.fake_foo_repository import FakeFooRepository
```

This is deliberate: keeps fakes out of production import graphs.

### Template(s)

#### CRUD repository fake

```python
from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

from myapp.domain.exceptions import ConflictError, NotFoundError
from myapp.domain.foos import Foo, FooListFilter

class FakeFooRepository:
    def __init__(self, items: list[Foo] | None = None) -> None:
        # Store DETACHED copies; never alias the caller's instances (see Rule 9).
        self._store: dict[UUID, Foo] = {f.id: replace(f) for f in (items or [])}
        self.updated: list[UUID] = []  # call record — ids passed to update(), in order

    async def list(self, *, filter: FooListFilter) -> Sequence[Foo]:
        ordered = sorted(
            self._store.values(),
            key=lambda f: (f.sort_order, f.name),
        )
        return [replace(f) for f in ordered[filter.offset : filter.offset + filter.limit]]

    async def count(self, *, filter: FooListFilter) -> int:
        return len(self._store)

    async def get_by_id(self, id: UUID) -> Foo:
        if id not in self._store:
            raise NotFoundError("Foo not found", {"id": str(id)})
        return replace(self._store[id])  # a copy — a caller mutation must not leak into the store

    async def get_by_name(self, name: str) -> Foo | None:
        match = next((f for f in self._store.values() if f.name == name), None)
        return replace(match) if match is not None else None

    async def create(self, foo: Foo) -> None:
        if any(f.name == foo.name for f in self._store.values()):
            raise ConflictError(
                "foo name already exists",
                {"constraint": "uq_foos_name"},
            )
        self._store[foo.id] = replace(foo)

    async def update(self, foo: Foo) -> None:
        if foo.id not in self._store:
            raise NotFoundError("Foo not found", {"id": str(foo.id)})
        if any(f.name == foo.name and f.id != foo.id for f in self._store.values()):
            raise ConflictError(
                "foo name already exists",
                {"constraint": "uq_foos_name"},
            )
        self._store[foo.id] = replace(foo)
        self.updated.append(foo.id)  # so a "mutate-but-never-persist" handler is observably caught

    async def delete(self, id: UUID) -> None:
        if id not in self._store:
            raise NotFoundError("Foo not found", {"id": str(id)})
        del self._store[id]
```

#### Aggregate with cascading sub-collection

```python
class FakeFooRepository:
    def __init__(self, foos: list[Foo] | None = None) -> None:
        self._store: dict[UUID, Foo] = {f.id: f for f in (foos or [])}
        self._attachments: dict[UUID, FooAttachment] = {}

    async def add_attachment(self, foo_id: UUID, attachment: FooAttachment) -> None:
        if foo_id not in self._store:
            raise NotFoundError("Foo not found", {"id": str(foo_id)})
        self._attachments[attachment.id] = attachment

    async def delete(self, id: UUID) -> None:
        if id not in self._store:
            raise NotFoundError("Foo not found", {"id": str(id)})
        # Replay the schema's ON DELETE CASCADE
        cascaded = [a_id for a_id, a in self._attachments.items() if a.foo_id == id]
        for a_id in cascaded:
            del self._attachments[a_id]
        del self._store[id]
```

#### Behavioral capability (`ICanDoX`) — single async method

```python
from myapp.domain.foos import FooExportRow

class FakeExportFoosXlsx:
    def __init__(self, payload: bytes = b"fake-xlsx") -> None:
        self._payload = payload
        self.exported: list[Sequence[FooExportRow]] = []

    async def export(self, rows: Sequence[FooExportRow]) -> bytes:
        self.exported.append(tuple(rows))
        return self._payload
```

Behavioral fakes expose a call-record list (`self.exported`) so handler tests can assert what was invoked. Prefer asserting on resulting domain state when possible; reach for call records only when call shape is the thing under test.

#### Storage gateway with a call-record observation surface

A storage fake records what it was asked to do (puts / deletes) so compensating-transaction tests can assert the `*_best_effort` cleanup ran — no failure-injection flags, just observable call records:

```python
class FakeBlobStorage:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []
        self.deletes: list[str] = []

    async def put(self, key: str, data: bytes) -> None:
        self.puts.append((key, data))

    async def delete_many_best_effort(self, keys: list[str]) -> None:
        # Swallows internal errors; mirrors the real best-effort contract.
        self.deletes.extend(keys)
```

The `puts` and `deletes` lists are the test-side observation surface. **No `fail_next_call=...` flags**: a test that needs the DB write *after* an upload to fail uses an inline `_RaisingFooRepo(FakeFooRepository)` at the test scope, not a flag on the storage fake.

### Rules

1. **No inheritance from the protocol.** Structural matching is verified by the type checker.
2. **One state field per collection** — `self._store: dict[UUID, <Entity>]` keyed by id. No secondary indexes, no shadow caches. Queries scan the dict — the data set is tiny.
3. **Constructor takes `items: list[<Entity>] | None = None`** with `or []` fallback so the empty-fake call site is terse: `FakeFooRepository()`.
4. **Every method is `async def`**, even when there's nothing to await — the protocol says async; the fake matches.
5. **`list(*, filter: <FilterRecord>)` is keyword-only** and applies a deterministic sort matching the real repository's `ORDER BY`. Handler tests assert exact order — sort, don't return insertion order.
   - **A fake method MUST honour every filtering / scoping parameter it declares — never ignore one.** If the method takes a `since` / `workspace_id` / status-set / parent-id, the fake actually filters its `_store` by it (`v for v in self._store.values() if v.created_at >= since and v.workspace_id == workspace_id`). A fake that accepts `count_created_since(since)` but returns the all-time count makes the "monthly vs all-time" contract **uncatchable** — the §9 assert for it can never be strong (the dry-run hit exactly this). The fake's filtering need not be efficient, just correct: a wrong body that ignores the same parameter must produce a different result against the fake.
6. **The exception contract is copied verbatim from the real adapter.** Same class, same message, same `context` keys — exactly what `_map_integrity_error` populates and no more. The relational adapter raises `ConflictError("foo name already exists", {"constraint": "uq_foos_name"})` — context carries **only** `constraint`, so the fake matches it exactly. Adding a key the real adapter never sets (e.g. `"name"`) is the silent drift this rule exists to prevent: a handler test asserting that key passes against the fake and fails against the real adapter.
7. **Cascades match the schema.** When the real schema has `ON DELETE CASCADE`, the fake removes the dependent rows. Skipping the cascade in the fake produces a green unit test that a failing integration test then catches — defeats the point.
8. **Default-happy-path only.** No `fail_next_create=True` flags or `_should_raise` knobs. Tests needing one-off failures declare a private subclass at the **handler test module scope** (the pattern is owned by `test-application-handler`):

   ```python
   class _RaiseInUseFooRepo(FakeFooRepository):
       async def delete(self, id: UUID) -> None:
           raise InUseError("foo is used", {"reference_type": "foo", "id": str(id)})
   ```

   The storage-gateway `puts` / `deletes` call records are the only sanctioned per-call observation surface — and they observe, they do not inject failure. A test that needs an injected failure uses the inline-subclass pattern above, not a flag or a hook on the fake.

9. **Never alias the caller's entity — store and return COPIES, and record `update()` calls.** The real repository round-trips through the DB: a mutation is persisted **only** by an explicit `update()`, and a fresh `get_by_id` reads back the persisted row. A naive fake that does `self._store[id] = foo` and `return self._store[id]` aliases the same object, so a handler that mutates the entity **in place but never calls `update()`** still observes its change through a later `get_by_id` — a "mutate-but-never-persist" bug passes green, and a persistence assert (`(await repo.get_by_id(x)).status == DONE`) is unpinnable (F-018). So: copy on **write** (`self._store[id] = replace(foo)`) and on **read** (`return replace(self._store[id])`), via `dataclasses.replace` (shallow copy; `copy.deepcopy` only if a field is itself mutable and the test mutates through it), and keep an `updated: list[UUID]` call record that `update()` appends to. Handler tests then pin persistence two ways — `assert repo.updated == [id]` (update was called) and `assert (await repo.get_by_id(id)).status == DONE` (the new state was written) — and a body that forgets `update()` reds both.

### What a fake must not do

- **No `unittest.mock`.** A fake is a hand-written class; `MagicMock` defeats the visibility.
- **No production imports beyond `myapp.domain`.** Fakes import domain entities, value objects, enums, and exceptions. Never `myapp.infrastructure`, `myapp.application`, `myapp.restapi`.
- **No IO.** No file reads, no network, no `time.sleep`, no real timezone-aware datetime that varies between runs.
- **No third-party imports** other than what stdlib + `myapp.domain` + `pytest` require.
- **No state retained across instances.** No class variables, no module-level caches. Each `FakeFooRepository()` constructs a fresh `_store`.
- **No `__all__`, no `__init__.py` re-export.** Direct import only.

### Inlined typing / import rules

- Stdlib (`collections.abc`, `uuid`), `myapp.domain.*` only.
- `X | None`, full annotations on `__init__` and every method.
- No `from __future__ import annotations`.

### Hard stops

- Spec asks to fake a handler's **concrete domain-service** dependency (e.g. `QuotaPolicy`, injected as the class, not a Protocol) → stop, a structural fake won't type-check there; **subclass the service** (override the method under test, bypass `__init__`) or have the handler **inject via a Protocol**. This is the handler-test's call — see `test-application-handler` rule 10. Repository/capability fakes (this skill) are structural because their dependencies are Protocols.
- Spec asks to register the fake with `@runtime_checkable` / `isinstance` → stop, type checking is enough.
- Spec asks to add failure-injection flags to a repository fake → stop, use the inline-subclass pattern at the handler test module scope instead.
- Spec asks to model `InUseError` in the default repository fake → stop, that's an inline subclass case at the test site (cross-aggregate references aren't modeled in-memory).
- Real adapter's exception contract cannot be located → stop, the fake's contract is copied, not invented.
- Spec uses `MagicMock` / `AsyncMock` to "implement" the fake → stop, hand-write the class.
- Spec adds `__all__` or an `__init__.py` re-export → stop, the fakes directory is direct-import only by design.


<!-- merged from test-domain-entity -->

## Test — Domain Entity

Produces one unit-test file for one domain entity. Sync `def` tests; entities have no IO. Asserts identity equality and every `__post_init__` invariant. Nothing else.

### When to use vs. neighbours

- A `@dataclass` entity with UUID identity → this skill.
- A frozen `@dataclass(frozen=True)` value object → `test-domain-value-object`.
- A `StrEnum` / `Enum` member set → `test-domain-enum`.
- A domain service (orchestrator with injected protocols, or pure-logic service) → `test-domain-service`.
- A grep-firewall architectural rule → `test-architecture-rule`.

### Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<entity_snake>_entity.py
```

#### Standard template

```python
import uuid

import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import Foo

def _make_foo(**overrides) -> Foo:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        name="Test",
    )
    defaults.update(overrides)
    return Foo(**defaults)

def test_equality_by_id() -> None:
    shared_id = uuid.uuid4()
    a = Foo(id=shared_id, name="alpha")
    b = Foo(id=shared_id, name="beta")
    c = Foo(id=uuid.uuid4(), name="alpha")

    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert hash(a) != hash(c)

def test_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        _make_foo(name="")
    assert exc.value.context["field"] == "name"
```

The builder spreads **only the entity's real declared fields** (`id` + its domain fields). Two things it must NOT carry: `created_at`/`updated_at` (audit timestamps are a DB-managed table convention, never entity fields — these are reserved column names forbidden on an entity, so constructing `Foo(created_at=...)` fails), and any `import datetime` that exists only to feed them. `datetime` enters this file **only** if a specific entity genuinely declares a datetime domain field. If the entity has a computed property/method, add one `test_*` per Rule 7 (an entity without one needs no such test).

#### Few-field entity (skip the builder)

```python
import uuid

import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import Foo

def test_equality_by_id() -> None:
    shared_id = uuid.uuid4()
    assert Foo(id=shared_id, name="a") == Foo(id=shared_id, name="b")

def test_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        Foo(id=uuid.uuid4(), name="")
    assert exc.value.context["field"] == "name"
```

### Rules

1. **The four-line identity-equality block is the contract.** Entity equality is by id only; `hash` agrees with `eq`. Don't paraphrase.
2. **`_make_<entity>(**overrides)` is a module-level `def`** — never a `@pytest.fixture`. Defaults must be valid; no-override construction must succeed.
3. **No conditional logic in the builder.** Dumb spreader. Computations belong in tests.
4. **One `test_*` per `__post_init__` invariant.** Pattern: `with pytest.raises(ValidationError) as exc:` then `assert exc.value.context["field"] == "<field>"`.
5. **Group multiple failure modes of the same invariant in one test.** Several `with pytest.raises(...)` blocks under one `test_*` named after the invariant.
6. **Don't test what `@dataclass` gives for free.** No tests for field equality on frozen dataclasses, hashability, immutability — those are guaranteed by Python's data model. Test only `__post_init__`, computed properties, and methods.
7. **Computed properties / methods get their own `test_*`** named after the rule — but only when the entity actually declares one (e.g. an entity with a computed `is_active` → `test_<entity>_is_active_when_...`). Don't add a lifecycle/archive test to an entity that has no such property; that is a per-aggregate feature, not a default.
8. **Assert against literal expected values.** Never re-implement the entity's logic to compute the expected value — that hides bugs where both sides have the same mistake.

### Inlined typing / import rules

- Stdlib (`uuid`, `datetime`) + `pytest` + `myapp.domain.*` only. No infrastructure, no application, no restapi, no pydantic, no SQLAlchemy.
- Full annotations on `_make_<entity>`; tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

### Hard stops

- Spec asks the test to touch the database / an HTTP endpoint / S3 → stop, use `test-repository-contract` or `test-restapi-endpoint`.
- Spec asks to use `MagicMock` / `AsyncMock` / `monkeypatch` → stop, domain has no IO; mocks have no place here.
- Spec asks for the builder as a `@pytest.fixture` → stop, builders are module-level `def`.
- Spec asks to test `dataclass`-given equality / hash / immutability → stop, Python's data model already guarantees it; assert on `__post_init__` and methods only.
- Spec re-implements the invariant in the test ("compute expected slug from name, then assert") → stop, assert literal values.
- Spec asserts on log output / `caplog` → stop, entities don't log.
- Spec puts `created_at` / `updated_at` in the builder or treats them as entity fields → stop, audit timestamps are a DB-managed table convention, never entity fields; the builder spreads only the entity's real domain fields.


<!-- merged from test-domain-value-object -->

## Test — Domain Value Object

Produces one unit-test file for one domain value object — only when there is something custom to test. Stdlib + `pytest` + `<root>.domain.*` only.

### When to use vs. neighbours

- A frozen value object with `__post_init__` invariants or a canonicalization rule → this skill.
- A frozen value object with neither `__post_init__` nor custom equality → **do not invoke this skill**; Python guarantees the contract for free.
- An entity (UUID identity, mutable) → `test-domain-entity`.
- An enum → `test-domain-enum`.
- A service → `test-domain-service`.
- A grep-firewall rule → `test-architecture-rule`.

### Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<vo_snake>.py
```

(No `_value_object` suffix — `test_foo_key.py`, not `test_foo_key_value_object.py`.)

#### Canonical-form equality + invariant

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import FooKey

def test_canonical_equality() -> None:
    a = FooKey(raw="abc", canonical="ABC")
    b = FooKey(raw="ABC", canonical="ABC")

    assert a == b
    assert hash(a) == hash(b)

def test_rejects_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        FooKey(raw="", canonical="")
    assert exc.value.context["field"] == "canonical"
```

#### Invariant only (no canonicalization)

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.amounts import Money

def test_amount_must_be_non_negative() -> None:
    with pytest.raises(ValidationError) as exc:
        Money(amount=-1, currency="USD")
    assert exc.value.context["field"] == "amount"

def test_currency_must_be_three_letters() -> None:
    with pytest.raises(ValidationError) as exc:
        Money(amount=1, currency="US")
    assert exc.value.context["field"] == "currency"
```

### Rules

1. **Skip the file entirely when the VO has no `__post_init__` and no custom `__eq__`.** Frozen-dataclass equality is given by Python's data model — testing it adds maintenance with no defect-detection value. The skill produces no file in this case.
2. **Canonical-form equality tests pin the rule, not Python's `==`.** Two instances with the same `canonical` field must be equal even when their `raw` fields differ. `hash` must agree.
3. **One `test_*` per `__post_init__` invariant.** Pattern: `with pytest.raises(ValidationError) as exc:` then `assert exc.value.context["field"] == "<field>"`.
4. **No `_make_*` builder.** Value objects are small — pass fields directly. Builders are for many-field entities (`test-domain-entity`).
5. **No `@pytest.fixture`.** Tests construct the VO directly.
6. **Assert literal canonical values.** `canonical="ABC"` — don't compute the expected canonical form in the test, or both sides may agree on a bug.

### Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

### Hard stops

- VO has no `__post_init__` and no custom `__eq__` → stop, no file is produced; the contract is Python's data model.
- Spec asks for the test to touch infrastructure → stop, value objects have no IO.
- Spec asks to mock anything → stop, no IO to stub.
- Spec re-implements the canonicalization rule in the test → stop, assert literal canonical values.
- Spec adds a builder → stop, VOs are constructed inline.


<!-- merged from test-domain-enum -->

## Test — Domain Enum

Produces one unit-test file for one domain enum. Pins each member's value (typically a string the DB / wire format depends on), asserts unknown values are rejected, and covers any pure-logic methods on the enum.

### When to use vs. neighbours

- A `StrEnum` / `Enum` with closed-set members → this skill.
- An entity → `test-domain-entity`.
- A value object → `test-domain-value-object`.
- A service → `test-domain-service`.
- A grep-firewall rule → `test-architecture-rule`.

### Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<enum_snake>_enum.py
```

#### Standard template — values + rejection

```python
import pytest

from myapp.domain.foos import FooStatus

def test_values() -> None:
    assert FooStatus.ALPHA == "ALPHA"
    assert FooStatus.BETA == "BETA"

    with pytest.raises(ValueError):
        FooStatus("GAMMA")
```

#### With a pure-logic method

```python
import pytest

from myapp.domain.auth import Role

def test_values() -> None:
    assert Role.SUPER_ADMIN == "SUPER_ADMIN"
    assert Role.ADMIN == "ADMIN"
    assert Role.COLLABORATOR == "COLLABORATOR"

    with pytest.raises(ValueError):
        Role("ROOT")

def test_satisfies() -> None:
    assert Role.SUPER_ADMIN.satisfies(Role.ADMIN) is True
    assert Role.ADMIN.satisfies(Role.ADMIN) is True
    assert Role.COLLABORATOR.satisfies(Role.ADMIN) is False
    assert Role.COLLABORATOR.satisfies(Role.COLLABORATOR) is True
```

### Rules

1. **Pin every member with an explicit assertion.** `assert FooStatus.ALPHA == "ALPHA"` — one line per member. The DB / wire format depends on these strings; a silent rename must break the test.
2. **Don't loop over members.** `for m in FooStatus: assert m.value == m.name` masks the bug it's supposed to catch — a renamed value still passes. Explicit asserts only.
3. **Always include the unknown-value rejection.** `with pytest.raises(ValueError): FooStatus("<unknown>")` proves the enum is closed.
4. **One `test_*` per pure-logic method on the enum.** Name the test after the method (`test_satisfies`, `test_is_terminal`). Inside, assert every relevant input/output pair with `is True` / `is False` for boolean returns — `==` may accidentally compare `int(1)` to `True`.
5. **No fixtures, no builders.** Enums are constants.
6. **No mocks.** Enums have no IO.

### Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

### Hard stops

- Spec proposes looping over members → stop, write explicit asserts.
- Spec asks the test to touch infrastructure → stop, enums have no IO.
- Spec asks for the test to import from `application` / `infrastructure` / `restapi` → stop, domain layer only.
- Spec asks to use `==` instead of `is` for boolean enum-method returns → stop, `is True` / `is False` prevents truthy-but-not-True bugs.
- The enum has no members listed in the spec → stop, members must be enumerated explicitly.


<!-- merged from test-domain-service -->

## Test — Domain Service

Produces one unit-test file for one domain service. Two flavors: orchestrators (with injected protocols — uniqueness checks, existence guards) and pure-logic services (no dependencies — URL canonicalizers, hash transformers). Stdlib + `pytest` + `<root>.domain.*` only. No fixtures, no mocks, no fakes from `tests/unit/fakes/`, no IO outside the inline protocol stub.

### When to use vs. neighbours

- A domain service class (with or without injected protocols) → this skill.
- An entity → `test-domain-entity`.
- A value object → `test-domain-value-object`.
- An enum → `test-domain-enum`.
- The infrastructure adapter that implements the protocol the service depends on → not a domain test; `test-repository-contract`.
- The application handler that *uses* the service → end-to-end through the API; `test-restapi-endpoint`.

### Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<service_snake>_service.py        # orchestrator
└── test_<service_snake>.py                # pure-logic (no `_service` suffix)
```

#### Orchestrator — minimal inline-class stub

```python
import pytest

from myapp.domain.exceptions import FooConflictError
from myapp.domain.foos import FooUniquenessService

def _service(existing_keys: list[str] | None = None) -> FooUniquenessService:
    class _MinimalRepo:
        def __init__(self, keys: list[str]) -> None:
            self._keys = set(keys)

        async def exists_by_canonical_key(self, canonical_key: str) -> bool:
            return canonical_key in self._keys

    return FooUniquenessService(repo=_MinimalRepo(existing_keys or []))

async def test_assert_available_raises_when_present() -> None:
    service = _service(["abc"])
    with pytest.raises(FooConflictError):
        await service.assert_available("abc")

async def test_assert_available_passes_when_absent() -> None:
    service = _service([])
    await service.assert_available("abc")  # does not raise
```

#### Pure-logic service

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import UrlCanonicalizer

c = UrlCanonicalizer()

def test_strips_trailing_slash() -> None:
    assert c.canonicalize("https://example.com/path/") == "https://example.com/path"

def test_drops_default_port() -> None:
    assert c.canonicalize("https://example.com:443/path") == "https://example.com/path"

def test_idempotent() -> None:
    samples = ["https://example.com/", "https://example.com/path/?b=2&a=1"]
    for s in samples:
        assert c.canonicalize(c.canonicalize(s)) == c.canonicalize(s)

def test_rejects_non_http() -> None:
    with pytest.raises(ValidationError):
        c.canonicalize("ftp://example.com")
```

### Rules

1. **Orchestrators use a minimal inline class, not a fake from `tests/unit/fakes/`.** The class implements only the protocol methods the service actually calls. This makes the service's true dependency surface visible — a service that "needs the whole repo" is probably an entity method in disguise.
2. **The `_service(...)` factory returns the constructed service.** Hides the inline-class plumbing from the body of each test.
3. **One `test_*` per behavior of each service method.** Naming follows the rule: `test_assert_available_raises_when_present`, `test_assert_available_passes_when_absent`. The test name **is** the spec line.
4. **Async tests are `async def test_*`** when the service method is async; `pytest-asyncio` runs in auto mode — never add `@pytest.mark.asyncio`.
5. **Pure-logic services construct one instance at module scope.** The service is stateless; per-test construction is wasted ceremony.
6. **Canonicalizers always include `test_idempotent`.** Loop a few representative inputs and assert `f(f(x)) == f(x)`. Idempotence is part of the canonicalization contract; forgetting it is the most common bug class.
7. **Pair every happy-path test with a rejection test.** `with pytest.raises(ValidationError):` for the negative case. Single-direction tests are incomplete.
8. **No mocks.** The inline class is a hand-written stub, not a `MagicMock`. Using mocks defeats the purpose of making the dependency surface visible.
9. **No `@pytest.fixture`.** The `_service(...)` factory is a module-level `def`.
10. **Assert literal expected values.** Don't re-implement the canonicalization in the test.

### Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Full annotations on the `_service(...)` factory and on the inline `_MinimalRepo`.
- Tests are `def test_*() -> None` (sync) or `async def test_*() -> None` (async).
- No `from __future__ import annotations`.

### Hard stops

- Spec asks to import a fake from `tests/unit/fakes/` → stop, that directory is gone; use a minimal inline class scoped to the `_service(...)` factory.
- Spec uses `MagicMock` / `AsyncMock` for the protocol stub → stop, hand-write the inline class so the dependency surface stays visible.
- Spec adds methods to the inline class that the service does not call → stop, the inline class implements exactly the called surface, no more.
- Spec adds `@pytest.mark.asyncio` → stop, auto mode handles async.
- Spec asks the test to touch a real database / HTTP endpoint → stop, that's `test-repository-contract` / `test-restapi-endpoint`.
- Pure-logic service test omits `test_idempotent` for a canonicalizer → stop, idempotence is part of the contract.
- Spec re-implements the rule in the test to compute the expected value → stop, assert literal values.


<!-- merged from test-architecture-rule -->

## Test — Architectural Firewall Rule

`tests/unit/test_architecture.py` is a static grep firewall. Each function greps the source tree for a forbidden pattern and asserts the result is empty. Adding a rule here is cheaper than catching the same mistake repeatedly in code review.

### When to use vs. neighbours

- A static, absolute "do not import X in layer Y" invariant the codebase needs enforced → this skill.
- A runtime unit/integration test for entity / VO / enum / service / repository / endpoint behavior → the matching `test-*` skill. Greps enforce static structure; runtime tests enforce dynamic behavior.
- A type-correctness rule → `mypy` / `pyright` enforce it; do not duplicate as a grep test.
- A style / formatting rule → `ruff` enforces it; do not duplicate.
- A "should usually" rule with material exceptions → not a firewall candidate; document in a layer skill instead. Firewalls are absolutes that accumulate exceptions and stop paying for themselves.
- An intent-based rule ("don't use `Any` *unless* at a true external boundary") → not a firewall candidate; greps either hit or don't, with no intent inspection.

### Template(s)

Only `tests/unit/test_architecture.py` is touched. `_grep(...)` and the `_ROOT` / `_SRC` / `_TESTS` / `_DOMAIN` / `_APP` constants already exist at the top of the file.

#### Standard rule (no allow-list)

```python
def test_no_<rule_name>() -> None:
    hits = _grep("<pattern>", <paths>)
    assert hits == [], "<message>:\n" + "\n".join(hits)
```

Concrete:

```python
def test_domain_has_no_sqlalchemy() -> None:
    hits = _grep(r"import sqlalchemy\|from sqlalchemy", _DOMAIN)
    assert hits == [], "sqlalchemy import in domain:\n" + "\n".join(hits)
```

#### Rule with in-test allow-list

```python
def test_no_print_calls_outside_allowed() -> None:
    _main_py = str(_ROOT / "src" / "myapp" / "restapi" / "main.py")
    _cli = str(_ROOT / "src" / "myapp" / "cli")
    all_hits = _grep("print(", _SRC)
    forbidden = [h for h in all_hits if not h.startswith(_main_py) and not h.startswith(_cli)]
    assert forbidden == [], "print() calls found outside allowed locations:\n" + "\n".join(forbidden)
```

The pattern stays simple ("no `print(`"); exceptions are explicit and visible to a future maintainer.

#### Adding a new path constant (when a new scope is needed)

Append at the top of the file, next to the existing constants:

```python
_RESTAPI = str(_ROOT / "src" / "myapp" / "restapi")
_INFRA   = str(_ROOT / "src" / "myapp" / "infrastructure")
```

### Rules

1. **One `def test_*` per rule.** No fixtures, no parametrization, no async. The test name **is** the rule, and the names form the file's spec.
2. **Naming convention.** Layer-scoped → `test_<layer>_has_no_<thing>` (e.g. `test_domain_has_no_pydantic`). Repo-wide → `test_no_<thing>` (e.g. `test_no_future_annotations_anywhere`). Don't pluralize; don't add qualifiers.
3. **The `assert hits == []` form is deliberate.** When the test fails, pytest prints `[]` alongside the actual list, and the message lists every offending location — a clean diff.
4. **Use the path constants; don't inline literal paths.** `_SRC`, `_TESTS`, `_DOMAIN`, `_APP` exist at the top of the file. Add a new constant alongside them for a new scope (e.g. `_RESTAPI`). Inlined paths drift if the tree moves.
5. **Pattern syntax.** Plain string for unique tokens (`"Optional["`, `"time.sleep"`); alternation with escaped `\|` for equivalent forms (`r"import sqlalchemy\|from sqlalchemy"`); `\b` to avoid substring false matches (`r"Mapped\b"`). Use raw strings (`r"..."`) whenever the pattern contains a backslash.
6. **Test the pattern locally before committing.** Run `grep -rn --include='*.py' --exclude=test_architecture.py 'your pattern' src/ tests/` and confirm zero unexpected hits. Never ship a test that's already red — fix the hits or narrow the pattern first.
7. **Allow-list lives inside the test, not in the pattern.** Filter the `_grep` result with `startswith(...)` checks against the named exception paths. Cap the allow-list at **three entries**. Beyond three, the rule has too many exceptions to be a firewall; demote it to a layer skill's prose or split it into a more specific rule.
8. **`_grep` excludes `test_architecture.py` itself.** The `--exclude=test_architecture.py` argument inside `_grep` prevents the file from finding its own pattern strings.

### Inlined typing / import rules

- `subprocess` and `pathlib.Path` only at the file level (already present).
- Never import from `myapp` — importing what you're trying to forbid defeats the firewall.
- Tests are sync `def test_*() -> None`.

### Hard stops

- Pattern produces unintended hits in the current tree → stop, fix them first or narrow the pattern.
- Rule depends on intent or runtime state → stop, this isn't a grep-firewall rule.
- Allow-list would need more than three entries → stop, the rule is too leaky; restructure or demote it.
- Spec adds a fixture, parametrization, or async to the test → stop, one `def test_*` per rule; "no X in domain" across multiple `X` values means one test per `X`.
- Spec adds `try/except` around `_grep` or conditional skips → stop, that breaks the unconditional property of the firewall.
- Spec imports anything from `myapp` → stop, importing the thing you forbid defeats the firewall.
- Spec inlines a literal path inside a test → stop, use the `_<NAME>` constants at module top; add a new constant if a new scope is needed.


## The unit testing constitution (shared)

These rules govern the whole unit tier and were the catalog-level testing constitution; they live here now (they moved out of `test-principles`, which is reduced to the paid-fixes guard). The integration-specific half — the conftest hierarchy, fixture scope, and reliability rules — lives in `testing-integration`.

## The testing pyramid

| Layer | Skill | Touches IO? | Target speed (per test) | What it catches |
|-------|-------|-------------|-------------------------|-----------------|
| Domain unit | `test-domain-entity`, `test-domain-value-object`, `test-domain-enum`, `test-domain-service` | No | < 10 ms | Identity equality, `__post_init__` invariants, enum values, pure-logic services, single-rule policies |
| Application handler unit | `test-application-handler` (+ `test-fake-repository`) | No (in-memory fakes) | < 50 ms | Handler orchestration, PATCH semantics, normalization, domain-exception propagation, compensating-tx undo |
| App construct smoke | `test-discovery-invariants` | No (constructs the app, no DB) | < 100 ms | Construct-time wiring + framework deps the type/lint/unit layers miss (e.g. `python-multipart`), OpenAPI schema build |
| Repository contract | `test-repository-contract` | Real Postgres via testcontainers, transaction-rollback isolation | < 500 ms | `IntegrityError` translation, constraint-name map, cascades, `onupdate=`, `get_by_*` semantics |
| REST endpoint | `test-restapi-endpoint` | Real app + real Postgres via ASGI | < 1 s | Routing, DI wiring, auth (when declared), request/response validation, tenancy/authorization scoping (when the app declares multi-tenancy) |
| Discovery invariants | `test-discovery-invariants` | Real app, no DB calls | < 500 ms | Global properties (every protected route 401s; every code in OpenAPI matches `error_responses(...)`; CORS; 413) |
| Architecture | `test-architecture-rule` | None (greps the source tree) | < 100 ms | Static "no X in layer Y" invariants |

The shape is the goal: **fast layers run on every save; slow layers run on every commit; the slowest layers run in CI.** If a domain unit test starts touching IO or a repository test starts depending on the FastAPI app, the layer is leaking and the speed budget is gone.

## Fixture vs. builder

| | Builder (module-level `def`) | Fixture (`@pytest.fixture`) |
|--|------------------------------|------------------------------|
| Use for | Constructing one domain object with sensible defaults | Shared infrastructure or mutable factories that touch real state |
| Lives in | The same test module that uses it, or a per-resource conftest | A conftest at the appropriate level of the hierarchy |
| Examples | `_make_foo(**overrides) -> Foo`, `_foo(name="alpha") -> Foo`, `_policy(existing_keys=...)` | `sf`, `real_app`, `authed_client`, `make_foo` (per-resource factory that hits the real DB) |
| Why | Builders are pure-Python; calling them in a fixture adds ceremony without value. Fixtures live in conftests; importing a builder across files duplicates plumbing. | Fixtures handle setup/teardown lifecycle (sessions, transactions, ASGI transports) — that's what they're for. |

**Rule:** if the thing you're constructing has no setup or teardown beyond its `__init__`, write a module-level `def`, not a fixture. The producer skills (`test-domain-entity`, `test-application-handler`) require this — see their rule lists.

## Naming conventions

- **Test file**: mirror the source file with a `test_` prefix. `application/foos/create_foo_handler.py` → `tests/unit/application/test_create_foo_handler.py`.
- **Test function**: `test_<rule_being_pinned>` in snake_case. `test_assigns_uuid_and_stores`, `test_duplicate_name_raises_conflict`, `test_partial_update_leaves_unspecified_fields_untouched`. The name **is** the spec line — reading the file's `def test_*` list reads as a list of behaviors.
- **Builders**: `_make_<entity>(**overrides)` or `_<entity>(name="alpha")` for the short form. Underscore prefix marks them as file-private.
- **Inline failure-injection subclasses**: `_Raise<X>Repo(FakeFooRepository)` at module scope, underscore-prefixed, overriding exactly the method that should fail.

## When to parametrize — and when not to

**Use `@pytest.mark.parametrize`** when:

- The parameter set is **discovered from the running system** — every protected route in `app.routes`, every operation in `app.openapi()`. `test-discovery-invariants` is the canonical example.
- The test is **input-domain coverage**: a single behavior verified against many inputs (10 invalid emails, 20 valid date formats). The behavior is one thing; the inputs vary.
- Adding a new parameter would extend, not duplicate, an existing test set.

**Do not parametrize** when:

- Each case is a distinct rule whose **name forms part of the spec**. `test_assigns_uuid_and_stores` and `test_duplicate_name_raises_conflict` are different behaviors; collapsing them into `@pytest.mark.parametrize("scenario, expected", [...])` hides the spec lines in tuples.
- The case differs in setup or assertions, not just input values.
- The test is in `tests/unit/domain/` covering `__post_init__` invariants — those are individual rules.

The rule of thumb: if you can read the parametrize ids out loud and they sound like a list of behaviors, parametrize is fine. If you can't (because the ids would be `0`, `1`, `2`), the cases are different rules and want different `def test_*` names.

## AAA structure (Arrange / Act / Assert)

Every test follows three visually-separated blocks:

```python
async def test_assigns_uuid_and_stores() -> None:
    # Arrange
    repo = FakeFooRepository()
    handler = CreateFooHandler(repo=repo)

    # Act
    foo_id = await handler.execute(CreateFooCommand(caller_id=_CALLER, name="alpha"))

    # Assert
    stored = await repo.get_by_id(foo_id)
    assert stored.name == "alpha"
```

Rules:

1. **Blank lines separate the three blocks.** Comments (`# Arrange`, `# Act`, `# Assert`) are optional once the pattern is established, but the blank lines are not.
2. **One Act per test.** If a test has two `handler.execute(...)` calls, the second one is part of Arrange (setup) for an assertion about the first. When in doubt, split into two tests.
3. **One assertion subject per test.** Multiple `assert` statements that all check the same returned object are fine (`assert stored.name == "alpha"; assert stored.created_at >= ...`). Multiple assertions across different objects often means two tests in one.
4. **Arrange constructs valid state.** Don't write defensive `try/except` in Arrange — if the setup fails, the test fails, and that's the right outcome.

## No-mocks rule

| Tool | Forbidden? | Notes |
|------|-----------|-------|
| `unittest.mock.MagicMock` | yes | always |
| `unittest.mock.AsyncMock` | yes | always |
| `unittest.mock.patch` | yes | always |
| `pytest.MonkeyPatch.setattr` (`monkeypatch.setattr`) | yes | never patch handler dependencies |
| `monkeypatch.setenv` | conditional | only inside env-parsing tests (`tests/unit/infrastructure/test_*_settings.py`); never used to drive handler tests |
| Hand-written fakes (`FakeFooRepository`) | preferred | the canonical substitution mechanism |
| Inline `_RaiseXxxRepo(FakeFooRepository)` subclass | preferred | one-off failure injection at the test module scope |

The rationale: mocks describe *what was called*; fakes describe *what state would result*. The state-based assertion catches whole classes of bug the call-based assertion can't. Mocks also encode interface details that drift independently of the protocol — a refactor that adds a parameter to `repo.create(...)` silently breaks no `MagicMock` test, but a hand-written fake fails compile-time.

The single sanctioned exception is `monkeypatch.setenv` inside settings-parsing tests (which exercise the env-reading code itself). Everywhere else, the answer is a fake.

## Testing hard stops (tier-wide)

- A test imports from `myapp.infrastructure.*` from `tests/unit/` → stop, unit tests use fakes; reach for `tests/integration/` if the real adapter is what's under test.
- A test imports `myapp.restapi.*` from `tests/unit/` → stop, the HTTP surface is integration-only.
- A test uses `MagicMock` / `AsyncMock` / `patch` → stop, use a fake or an inline subclass.
- A test adds `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- A test reads `os.environ` to fork behavior → stop, the isolation fixture handles environment differences once.
- A test asserts `len(items) == N + 1` "to account for the test's own row plus seed rows" → stop, rollback isolation drops everything; exact equality is correct.
- A test uses `uuid4().hex[:4]` or `[:5]` natural-key suffixes "to avoid collisions" → stop, rollback isolation makes the DB empty; fixed values like `"alpha"` are fine.
- A "convenience" autouse fixture is proposed → stop, the autouse list is closed (DB guard, migration, bucket cleanup, optional singleton reset). New autouse fixtures cause spooky-action-at-a-distance.
- A producer skill says something this skill forbids → stop, the producer skill is wrong; fix it. This skill is the source of truth.


## The `@pytest.mark.ac` criteria marker

Every acceptance criterion in a change's `criteria.md` is pinned by at least one test carrying its marker: `@pytest.mark.ac("AC-2")` on the test function. This is the convention the change cycle cross-checks — a `[x]` criterion must have a **passed** `ac`-marked test in the run's junit report (spec §3.3). Put the marker on the test that most directly exercises the criterion's observable behaviour; one criterion may have several marked tests. A criterion no test can physically pin is a candidate for the manual `[m]` state, flagged explicitly rather than left silently unmarked.

## A missing fake is a stop, not an improvisation

When a handler test needs a fake repository or fake capability that does not yet exist, **stop and author the fake first** (following the fake-repository rules above — copy the real adapter's exception contract, store and return copies with an updated log, honour every constructor param). Never improvise a half-fake inline, and never reach for the production adapter body to stand in. (Harvested from notes/16 C4.)
