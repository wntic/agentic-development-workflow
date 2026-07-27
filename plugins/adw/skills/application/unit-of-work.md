<!-- merged from pattern-unit-of-work -->

# Application Unit of Work

Produces the cross-cutting transactional-boundary abstraction. Three artifacts:

1. **Protocol:** `src/<root>/domain/i_unit_of_work.py` (or `i_<scope>_unit_of_work.py` if multiple scopes).
2. **Implementation:** `src/<root>/infrastructure/postgres/sqlalchemy_unit_of_work.py`.
3. **Handler integration:** a command handler that needs atomic multi-repository commits takes `uow_factory: Callable[[], IUnitOfWork]` and wraps its mutations in `async with self._uow_factory() as uow: ...` (the handler form `command.md` writes for this case).

## When to use it

Use when a handler writes to **two or more repositories in one transaction** (write + audit; aggregate + outbox).

Skip when:

- Only one repository → the `session_factory` style (`infra-sqlalchemy-repository`) is simpler.
- Atomic group is blob upload + DB write → that's `compensating-tx.md`. The patterns nest: compensation outside, UoW inside.
- The only motivation is read performance → `expire_on_commit=False` already covers it.

## Naming

- One `IUnitOfWork` per transactional scope, not per aggregate. Default name: `IUnitOfWork` in `i_unit_of_work.py`.
- Multiple UoWs are justified only for genuinely different scopes:
  - Different backends → `IPostgresUnitOfWork`, `IRedisUnitOfWork` (`i_<backend>_unit_of_work.py`).
  - Read/write split (rare) → `IReadUnitOfWork`, `IWriteUnitOfWork` (`i_<scope>_unit_of_work.py`).
- **Never name a UoW after an aggregate.** `IFooUnitOfWork` is wrong; it conflates "what's inside the transaction" with "what kind of transaction it is".

## Template — protocol

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

## Template — SQLAlchemy implementation

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

The implementation does **not** inherit from `IUnitOfWork` — structural subtyping (see `domain-repository-protocol`).

## Template — handler integration

The handler receives `uow_factory: Callable[[], IUnitOfWork]` and opens a fresh UoW per `execute`:

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

When compensation is also required, compensation wraps the UoW block (see `compensating-tx.md`):

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

## Session-injected repository (required when joining a UoW)

A repository joining the UoW takes a live `session: AsyncSession`, not a factory. A class cannot be both UoW-managed and standalone — pick one form.

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

- Methods use `self._session.execute(...)` directly.
- **Methods never `commit()` or `rollback()`** — the UoW owns those. Committing in a repo breaks atomicity.

## Rules

1. **One `IUnitOfWork` per scope, not per aggregate.** Every repository that may ever join a transaction is an attribute on the same protocol.
2. **`commit()` is the last statement** inside the `async with`. Anything after must be idempotent (logging, returning the new id).
3. **Exit without `commit()` rolls back.** Treat the UoW as "opt-in success".
4. **Don't catch exceptions inside the UoW block** unless implementing compensation. Let exceptions propagate so `__aexit__` rolls back.
5. **One UoW per `execute`.** Don't share across calls. Don't pool.
6. **Repositories joining the UoW take `session: AsyncSession`.** The same repository class cannot serve both `session_factory` and UoW callers — split into two adapters if you genuinely need both forms.
7. **Don't retry a failing UoW in the handler.** Propagate to the central error handler.

## DI wiring (owned by `infra-di-provider`)

The container wires the UoW as a `Factory` and passes `uow_factory.provider` — the `.provider` attribute exposes the zero-arg callable that matches `Callable[[], IUnitOfWork]`. The provider declarations themselves are `infra-di-provider`'s.

## Hard stops

- Only one repository participates → stop, this isn't a UoW case; keep the handler on `session_factory` via `infra-sqlalchemy-repository`.
- The "atomic group" spans two backends (Postgres + S3) → stop, this is `compensating-tx.md` or a saga, not a UoW.
- Spec asks for a UoW per aggregate (`IFooUnitOfWork`) → stop, that's the wrong shape; one shared UoW for the scope.
