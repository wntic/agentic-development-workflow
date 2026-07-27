<!-- merged from test-fake-repository -->

# Test Fake — Repository / Capability

Produces one in-memory stand-in class for a domain protocol. Handler unit tests under `tests/unit/application/` use this fake instead of the real `infrastructure/` adapter. The fake satisfies the protocol **structurally** — no `(IFooRepository)` inheritance, no `@runtime_checkable` registration.

## When to use vs. neighbours

- A handler unit test (`handler.md`) needs a fake that does not yet exist → this skill.
- The handler test that consumes the fake → `handler.md`.
- The real adapter the fake stands in for → `infra-sqlalchemy-repository`.
- The domain protocol the fake matches → `domain-repository-protocol` or `domain-capability-protocol`.
- A one-off failure injection for a single handler test → don't extend the fake; declare a `_RaiseXxxRepo(FakeFooRepository)` subclass at the handler test module scope (the pattern is owned by `handler.md`).
- Integration tests that drive the real adapter → `test-repository-contract` (no fake).

## File location and naming

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

## Template(s)

### CRUD repository fake

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

### Aggregate with cascading sub-collection

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

### Behavioral capability (`ICanDoX`) — single async method

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

### Storage gateway with a call-record observation surface

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

## Rules

1. **No inheritance from the protocol.** Structural matching is verified by the type checker.
2. **One state field per collection** — `self._store: dict[UUID, <Entity>]` keyed by id. No secondary indexes, no shadow caches. Queries scan the dict — the data set is tiny.
3. **Constructor takes `items: list[<Entity>] | None = None`** with `or []` fallback so the empty-fake call site is terse: `FakeFooRepository()`.
4. **Every method is `async def`**, even when there's nothing to await — the protocol says async; the fake matches.
5. **`list(*, filter: <FilterRecord>)` is keyword-only** and applies a deterministic sort matching the real repository's `ORDER BY`. Handler tests assert exact order — sort, don't return insertion order.
   - **A fake method MUST honour every filtering / scoping parameter it declares — never ignore one.** If the method takes a `since` / `workspace_id` / status-set / parent-id, the fake actually filters its `_store` by it (`v for v in self._store.values() if v.created_at >= since and v.workspace_id == workspace_id`). A fake that accepts `count_created_since(since)` but returns the all-time count makes the "monthly vs all-time" contract **uncatchable** — the §9 assert for it can never be strong (the dry-run hit exactly this). The fake's filtering need not be efficient, just correct: a wrong body that ignores the same parameter must produce a different result against the fake.
6. **The exception contract is copied verbatim from the real adapter.** Same class, same message, same `context` keys — exactly what `_map_integrity_error` populates and no more. The relational adapter raises `ConflictError("foo name already exists", {"constraint": "uq_foos_name"})` — context carries **only** `constraint`, so the fake matches it exactly. Adding a key the real adapter never sets (e.g. `"name"`) is the silent drift this rule exists to prevent: a handler test asserting that key passes against the fake and fails against the real adapter.
7. **Cascades match the schema.** When the real schema has `ON DELETE CASCADE`, the fake removes the dependent rows. Skipping the cascade in the fake produces a green unit test that a failing integration test then catches — defeats the point.
8. **Default-happy-path only.** No `fail_next_create=True` flags or `_should_raise` knobs. Tests needing one-off failures declare a private subclass at the **handler test module scope** (the pattern is owned by `handler.md`):

   ```python
   class _RaiseInUseFooRepo(FakeFooRepository):
       async def delete(self, id: UUID) -> None:
           raise InUseError("foo is used", {"reference_type": "foo", "id": str(id)})
   ```

   The storage-gateway `puts` / `deletes` call records are the only sanctioned per-call observation surface — and they observe, they do not inject failure. A test that needs an injected failure uses the inline-subclass pattern above, not a flag or a hook on the fake.

9. **Never alias the caller's entity — store and return COPIES, and record `update()` calls.** The real repository round-trips through the DB: a mutation is persisted **only** by an explicit `update()`, and a fresh `get_by_id` reads back the persisted row. A naive fake that does `self._store[id] = foo` and `return self._store[id]` aliases the same object, so a handler that mutates the entity **in place but never calls `update()`** still observes its change through a later `get_by_id` — a "mutate-but-never-persist" bug passes green, and a persistence assert (`(await repo.get_by_id(x)).status == DONE`) is unpinnable (F-018). So: copy on **write** (`self._store[id] = replace(foo)`) and on **read** (`return replace(self._store[id])`), via `dataclasses.replace` (shallow copy; `copy.deepcopy` only if a field is itself mutable and the test mutates through it), and keep an `updated: list[UUID]` call record that `update()` appends to. Handler tests then pin persistence two ways — `assert repo.updated == [id]` (update was called) and `assert (await repo.get_by_id(id)).status == DONE` (the new state was written) — and a body that forgets `update()` reds both.

## What a fake must not do

- **No `unittest.mock`.** A fake is a hand-written class; `MagicMock` defeats the visibility.
- **No production imports beyond `myapp.domain`.** Fakes import domain entities, value objects, enums, and exceptions. Never `myapp.infrastructure`, `myapp.application`, `myapp.restapi`.
- **No IO.** No file reads, no network, no `time.sleep`, no real timezone-aware datetime that varies between runs.
- **No third-party imports** other than what stdlib + `myapp.domain` + `pytest` require.
- **No state retained across instances.** No class variables, no module-level caches. Each `FakeFooRepository()` constructs a fresh `_store`.
- **No `__all__`, no `__init__.py` re-export.** Direct import only.

## Inlined typing / import rules

- Stdlib (`collections.abc`, `uuid`), `myapp.domain.*` only.
- `X | None`, full annotations on `__init__` and every method.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks to fake a handler's **concrete domain-service** dependency (e.g. `QuotaPolicy`, injected as the class, not a Protocol) → stop, a structural fake won't type-check there; **subclass the service** (override the method under test, bypass `__init__`) or have the handler **inject via a Protocol**. This is the handler-test's call — see `handler.md` rule 10. Repository/capability fakes (this skill) are structural because their dependencies are Protocols.
- Spec asks to register the fake with `@runtime_checkable` / `isinstance` → stop, type checking is enough.
- Spec asks to add failure-injection flags to a repository fake → stop, use the inline-subclass pattern at the handler test module scope instead.
- Spec asks to model `InUseError` in the default repository fake → stop, that's an inline subclass case at the test site (cross-aggregate references aren't modeled in-memory).
- Real adapter's exception contract cannot be located → stop, the fake's contract is copied, not invented.
- Spec uses `MagicMock` / `AsyncMock` to "implement" the fake → stop, hand-write the class.
- Spec adds `__all__` or an `__init__.py` re-export → stop, the fakes directory is direct-import only by design.
