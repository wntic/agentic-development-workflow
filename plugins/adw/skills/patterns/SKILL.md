---
name: patterns
description: The two cross-layer patterns a command handler may need — the compensating transaction (catch → undo → re-raise, the only sanctioned `try/except` in `application/`) and the unit of work (one atomic commit across two or more repositories, as an `IUnitOfWork` protocol plus its SQLAlchemy implementation). They nest — compensation outside, unit of work inside.
when_to_use: A command must undo an external side effect when a later step fails, or must persist changes across two or more repositories atomically.
---

# Patterns

Two patterns that span layers rather than owning one layer's artifact, which is why neither belongs to
`application` or `infra-persistence` alone.

- **Compensating transaction** — produces no new file. It shapes a command handler's `execute` body when
  the handler has already done something the outside world can see before a later step can still fail.
- **Unit of work** — produces three artifacts: a domain protocol, an infrastructure implementation, and
  the handler form that consumes it.

They compose in one direction only: **compensation wraps the unit of work.** try → `async with uow` →
commit → except → undo → raise.

## When to use vs. neighbours

Compensating transaction:

- The handler creates an external side effect — blob upload, third-party POST, file write — **before** a
  DB write that can still fail, and the side effect must be undone on failure → **compensation**.
- The side effect is harmless if left behind (a cache warm-up), is the *last* step with nothing after it
  to fail, or can simply be reordered after the DB write → neither pattern; drop the `try/except`.

Unit of work:

- The handler writes to **two or more repositories in one transaction** — a write plus an audit append,
  an aggregate plus an outbox row → **unit of work**.
- Only one repository participates → neither pattern; the `session_factory` style in
  `infra-persistence` is simpler.
- The only motivation is read performance → neither; `expire_on_commit=False` already covers it.
- The atomic group spans two backends (Postgres plus S3, or Postgres plus Redis) → **compensation**, not
  a unit of work, and if it spans two *unrelated* backends both ways it is a saga and out of scope here.

Elsewhere:

- The handler itself, and its default no-`try/except` shape → `application`.
- The `*_best_effort` cleanup method a compensation calls → `domain-ports`.
- The repository that joins a unit of work → `infra-persistence`.
- The container declarations both patterns need → `infra-wiring`.

## Template(s)

### Compensation — a single side effect

```python
async def execute(self, cmd: UpsertFooCommand) -> uuid.UUID:
    # validation that doesn't depend on the side effect goes BEFORE the upload
    ...

    storage_key = await self._storage.put(cmd.data, ...)

    try:
        await self._repo.create(Foo(..., storage_key=storage_key))
    except Exception:
        await self._storage.delete_many_best_effort([storage_key])
        raise

    # caller_id is logged only when the command carries it (the authenticated form);
    # an auth-less command has no caller_id field — drop it. See `application`.
    logger.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))
    return foo.id
```

### Compensation — multi-step side effects

Accumulate the work-to-undo in a list so partial progress is cleaned too:

```python
uploaded_keys: list[str] = []
try:
    items = await self._upload_items(uploads, foo_id, uploaded_keys)
    foo = _build_foo(cmd, items)
    await self._repo.create(foo)
except Exception:
    await self._storage.delete_many_best_effort(uploaded_keys)
    raise
```

The helper appends to `uploaded_keys` after each successful upload, so a failure mid-loop still rolls
back what already landed.

### Successful-path cleanup is **not** compensation

When an upsert *replaces* a previous resource, the old one is cleaned **after** the DB commit:

```python
previous_key = await self._repo.upsert_foo(...)
# ... the try/except wraps only the upsert above ...

if previous_key is not None:
    await self._storage.delete_many_best_effort([previous_key])
```

That trailing call is ordinary cleanup: it runs only on success and disposes of the *old* resource. Do
not conflate the two.

### Unit of work — the protocol

```python
# src/<root>/domain/i_unit_of_work.py
from typing import Protocol

from .foos import IFooRepository
from .audit import IAuditRepository

__all__ = ["IUnitOfWork"]

class IUnitOfWork(Protocol):
    foos: IFooRepository
    audit: IAuditRepository

    async def __aenter__(self) -> "IUnitOfWork": ...
    async def __aexit__(self, *args: object) -> None: ...
    async def commit(self) -> None: ...
```

Repository attributes are typed by their **domain protocols**, never by concrete adapters.

### Unit of work — the SQLAlchemy implementation

```python
# src/<root>/infrastructure/postgres/sqlalchemy_unit_of_work.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myapp.infrastructure.postgres.repositories import FooRepository, AuditRepository

__all__ = ["SqlAlchemyUnitOfWork"]

class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._sf()
        await self._session.__aenter__()
        await self._session.begin()
        self.foos = FooRepository(self._session)
        self.audit = AuditRepository(self._session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            await self._session.rollback()
        await self._session.__aexit__(exc_type, exc, tb)

    async def commit(self) -> None:
        await self._session.commit()
```

The implementation does **not** inherit from `IUnitOfWork` — satisfaction is structural, see
`domain-ports`.

### Unit of work — handler integration

The handler receives `uow_factory: Callable[[], IUnitOfWork]` and opens a fresh unit of work per
`execute`:

```python
from collections.abc import Callable

import structlog

from myapp.domain import IUnitOfWork

__all__ = ["CreateFooHandler"]

logger = structlog.get_logger()

class CreateFooHandler:
    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, cmd: CreateFooCommand) -> uuid.UUID:
        async with self._uow_factory() as uow:
            await uow.foos.create(foo)
            await uow.audit.append(AuditEvent(...))
            await uow.commit()
        logger.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))
        return foo.id
```

### Both patterns together — compensation outside, unit of work inside

```python
storage_key = await self._storage.put(...)
try:
    async with self._uow_factory() as uow:
        ...
        await uow.commit()
except Exception:
    await self._storage.delete_many_best_effort([storage_key])
    raise
```

### Session-injected repository (required when joining a unit of work)

A repository joining the unit of work takes a live `session: AsyncSession`, not a factory. One class
cannot be both unit-of-work-managed and standalone — pick one form.

```python
class FooRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, foo: Foo) -> None:
        try:
            await self._session.execute(...)
        except IntegrityError as exc:
            raise _map_integrity_error(exc) from exc
```

Methods use `self._session.execute(...)` directly, and **never `commit()` or `rollback()`** — the unit of
work owns those. Committing inside a repository breaks atomicity.

## Naming (unit of work)

- One `IUnitOfWork` per transactional **scope**, not per aggregate. The default name is `IUnitOfWork` in
  `i_unit_of_work.py`.
- Several units of work are justified only for genuinely different scopes: different backends →
  `IPostgresUnitOfWork`, `IRedisUnitOfWork` in `i_<backend>_unit_of_work.py`; a read/write split, which
  is rare → `IReadUnitOfWork`, `IWriteUnitOfWork` in `i_<scope>_unit_of_work.py`.
- **Never name one after an aggregate.** `IFooUnitOfWork` conflates "what is inside the transaction" with
  "what kind of transaction it is".

## Rules

### Compensating transaction

1. **This `try/except Exception` is the only `try/except` allowed in a handler**, alongside the
   failure-state transition `application` sanctions. Needing another means the design is wrong — push the
   catch into infrastructure or remove it.
2. **Catch `Exception`, not specific exceptions.** Compensation must run regardless of the cause.
3. **The undo must never let its own failure mask the original error.** It is best-effort, in one of two
   sanctioned shapes — the choice is the author's, do not assume one:
   - a dedicated **`*_best_effort` method** on the protocol (`delete_many_best_effort`) that swallows its
     internal errors, called directly as the templates show; **or**
   - the **plain protocol method** (`delete` / `revert`) wrapped in a nested swallow at the call site when
     no `*_best_effort` variant exists:
     ```python
     except Exception:
         try:
             await self._storage.delete(storage_key)
         except Exception:
             pass  # best-effort — the undo's own failure must not mask the original error
         raise
     ```
   Never call a raising `delete` / `revert` *unguarded* inside `except` — if it raises, the original error
   is lost. When the undo is called often enough to deserve a first-class name, model a `*_best_effort`
   method; until then the call-site swallow is correct and needs no new protocol method.
4. **Bare `raise` at the end of `except`.** Never `raise NewException(...)`, never `raise ... from exc`.
   The original exception propagates unchanged.
5. **No logging inside `except`.** The central error handler logs once.
6. **The side effect runs *outside* the `try`.** Only the fallible *next* step goes inside.
7. **Pre-side-effect validation runs *before* the side effect.** Fail fast without compensation whenever
   possible.

### Unit of work

1. **One per scope, not per aggregate.** Every repository that may ever join a transaction is an
   attribute on the same protocol.
2. **`commit()` is the last statement** inside the `async with`. Anything after it must be idempotent —
   logging, returning the new id.
3. **Exiting without `commit()` rolls back.** Treat it as opt-in success.
4. **Do not catch exceptions inside the block** unless implementing compensation. Let them propagate so
   `__aexit__` rolls back.
5. **One unit of work per `execute`.** Do not share across calls, do not pool.
6. **A joining repository takes `session: AsyncSession`.** The same class cannot serve both
   `session_factory` and unit-of-work callers; split into two adapters if both forms are genuinely needed.
7. **Do not retry a failing unit of work in the handler.** Let it propagate to the central error handler.
8. **The container wires it as a `Factory` and passes `uow_factory.provider`** — the `.provider` attribute
   is the zero-argument callable matching `Callable[[], IUnitOfWork]`. The declarations themselves belong
   to `infra-wiring`.

## Hard stops

- The capability protocol has no cleanup method to call in the undo → stop, add it via `domain-ports`
  first.
- The undo method can itself raise non-trivially — it calls a flaky third-party DELETE, say → stop, the
  protocol contract is wrong; the method must swallow its own errors internally.
- Compensation would span two unrelated backends in both directions (Postgres and Redis) → stop, that is
  a saga, not a compensating transaction, and it is out of scope here.
- Only one repository participates in the "atomic group" → stop, this is not a unit-of-work case; keep the
  handler on `session_factory` via `infra-persistence`.
- The atomic group spans two backends (Postgres and S3) → stop, that is compensation, not a unit of work.
- Spec asks for a unit of work per aggregate (`IFooUnitOfWork`) → stop, wrong shape; one shared unit of
  work for the scope.
