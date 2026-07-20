---
name: application
description: House style for the application (CQRS) layer: command handlers (frozen command DTO + handler returning `UUID | None`, success-only logging), query handlers (frozen query DTO + optional `*Result` DTO), the compensating-transaction pattern (the sanctioned try/except: catch external side-effect, undo, re-raise), and the unit-of-work pattern (one atomic commit across two or more repositories).
when_to_use: Producing an application command or query handler, or shaping a handler that needs a compensating undo or a multi-repository atomic commit.
---
# Application — CQRS handlers & sanctioned try/except

This merged skill covers 4 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from application-command -->

## Application Command

Produces a mutation use case as two files in `application/<subdomain>/`:

1. `<verb>_<noun>_command.py` — the frozen-dataclass DTO.
2. `<verb>_<noun>_handler.py` — the handler class.

### When to use vs. neighbours

- Mutation (create/update/delete/rename/move) → this skill.
- Read (get/list/count/search) → `application-query`.
- The mutation includes an external IO step before the DB write (file upload, third-party POST) and needs rollback → still this skill, but the handler body follows `pattern-compensating-tx`.
- Multiple repositories must update atomically (write + audit log) → still this skill, plus inject an `IUnitOfWork` (see `pattern-unit-of-work`).

### File layout

```
src/<root>/application/<subdomain>/
├── <verb>_<noun>_command.py   # CreateFooCommand
└── <verb>_<noun>_handler.py   # CreateFooHandler
```

### Template — command DTO

(Authenticated form — carries `caller_id`. A command dispatched only by anonymous routes, or any command in an app that declares no auth, drops `caller_id` entirely; see DTO rule 2.)

```python
from dataclasses import dataclass
from uuid import UUID

from myapp.domain.foos import FooCategory

__all__ = ["CreateFooCommand"]

@dataclass(frozen=True)
class CreateFooCommand:
    caller_id: UUID
    name: str
    category: FooCategory
    sort_order: int = 0
```

### Template — create handler (returns `UUID`)

```python
import uuid

import structlog

from myapp.domain.foos import Foo, IFooRepository

from .create_foo_command import CreateFooCommand

__all__ = ["CreateFooHandler"]

logger = structlog.get_logger()

class CreateFooHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: CreateFooCommand) -> uuid.UUID:
        foo = Foo(
            id=uuid.uuid7(),
            name=cmd.name,
            category=cmd.category,
            sort_order=cmd.sort_order,
        )
        await self._repo.create(foo)
        logger.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))
        return foo.id
```

### Template — update/delete handler (returns `None`)

```python
class DeleteFooHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: DeleteFooCommand) -> None:
        await self._repo.delete(cmd.id)
        logger.info("foo_deleted", foo_id=str(cmd.id), caller_id=str(cmd.caller_id))
```

### Rules

#### Command DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **`caller_id: UUID` is the first field — when the command runs behind an authenticated route.** Auth is app-declared (`restapi-auth-dependency`), so the actor is conditional: a command dispatched only by anonymous routes — or any command in an app that declares no auth — has no caller to thread, so it **omits `caller_id`** (there is no source to populate it). The templates here show the authenticated form; for the auth-free case drop the field. Presence is derived from whether the dispatching endpoint(s) are authenticated, never a blanket convention.
   - **Other auth-derived fields stamp the same way.** A multi-tenant app threads more than the actor: a `workspace_id` / `tenant_id` / `org_id` the token carries is a field on the command **stamped by the endpoint from `CurrentUser`** (`workspace_id=user.workspace_id`), exactly like `caller_id=user.id` — never read from the request body or path (a client must not choose its own tenant). The handler then scopes every repository call by it. The same rule holds for a query (rule below) and the endpoint (`restapi-endpoint` / `restapi-auth-dependency`): auth-derived inputs come from the token, request-derived inputs from the body/path.
3. **No methods, no behavior.** Just data.
4. **Optional fields use `field: T | None = None`** or a concrete default — never sentinel strings.

#### Handler

1. **One class per module, one public method.** `async def execute(self, cmd: <CommandClass>) -> <ReturnType>`. Nothing else public.
2. **Constructor takes only domain protocols / services / unit-of-work / tunable value objects.** Never a session, never an HTTP client, never `Any`.
3. **Return type:** `UUID` for create, `None` for everything else. Never return the entity. A synchronous "do work, then show the result" use case (process X, then display X) is still a **command returning the affected id**, NOT a handler that returns a view — the caller re-reads the result through the matching `application-query` (e.g. `ProcessMeeting` returns the meeting id; the READY view is read via the `GetMeeting` query). Modelling it as one mutate-and-return-a-view op would straddle the command(→id)/query(read-only) split; keep the two halves separate.
4. **No business logic in the handler.** Build/mutate domain entities; let `__post_init__` and domain policies enforce rules. The handler orchestrates: load entities, mutate them, call the repository. **Normalization (strip / lowercase / canonicalize) is a domain concern — it lives in the entity's `__post_init__` or a value object, never in the handler.** Pass `cmd.name`, not `cmd.name.strip()`.
5. **No `try/except`, with two sanctioned exceptions.** (a) The compensating-transaction pattern — see `pattern-compensating-tx`. (b) A **failure-state transition then re-raise**: when the contract requires the aggregate to record that it failed before the error propagates (e.g. a processing pipeline that must persist `status=FAILED` so a later read/retry sees it), the handler may `try: <pipeline> except <Err>: <load-or-mutate>; entity.status = FAILED; await repo.update(entity); raise`. The `except` writes the caller-visible state and **re-raises** (never swallows, never logs-and-re-raises — `general-logging`); chain with `raise ... from exc` (`B904`). Anything beyond these two — translating a `DomainError`, catching to swallow, control-flow via exceptions — is still forbidden (the central handler translates; see hard stops).
6. **Log on success only, after the mutation completes.**
   - Event name: snake_case past tense (`foo_created`, `bar_renamed`).
   - Always include the affected resource id; include `caller_id=str(cmd.caller_id)` **only when the command carries `caller_id`** (the authenticated form — see DTO rule 2). An auth-free command logs just the resource id.
   - Never log on failure — exceptions propagate; the central handler logs once.
7. **No transaction management inside the handler.** Transaction lifecycle is wired in the entrypoint via DI (typically through `IUnitOfWork` if multiple writes must be atomic).

### Inlined typing / import rules

- `X | None` (never `Optional[X]`). Full annotations on `__init__`, `execute`, and every parameter.
- Cross-subdomain imports are absolute through the subpackage: `from myapp.domain.foos import Foo, IFooRepository`. Same-module imports are relative (`from .create_foo_command import CreateFooCommand`).
- `import structlog` and `logger = structlog.get_logger()` at module top — never inside the class.
- No `from __future__ import annotations`.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `general-python-package` to register both modules in the subpackage `__init__.py`. The DI provider that constructs this handler is the responsibility of `infra-di-provider`.

### Hard stops

- Spec asks the handler to return a list, a `Result`, or the entity → stop, use `application-query` (and re-read the spec — mutations don't return data).
- Spec asks the handler to catch a `DomainError` and translate it → stop, that's the central error handler's job (`restapi-error-responses`).
- Spec asks the handler to validate cross-aggregate state inline → stop, extract a `domain-service` and inject it.
- Spec implies multiple writes must be atomic → stop, request an `IUnitOfWork` dependency (see `pattern-unit-of-work`).
- Spec implies an external IO step before the DB write → stop, this still uses this skill but the body must follow `pattern-compensating-tx`.


<!-- merged from application-query -->

## Application Query

Produces a read use case as two or three files in `application/<subdomain>/`:

1. `<verb>_<noun>_query.py` — the frozen-dataclass DTO.
2. `<verb>_<noun>_handler.py` — the handler class.
3. `<verb>_<noun>_result.py` — only when the return shape is more than a single domain entity.

### When to use vs. neighbours

- Read (get/list/count/search/detect) → this skill.
- Mutation → `application-command`.
- Domain filter dataclass that the query handler passes into the repository → `domain-filter` (this skill consumes it).
- Authorization-scoped read ("things I can see") → still this skill; the query DTO carries `caller_id`.

### Read models — the CQRS read/write split

The domain entity is the **write** model: commands load and mutate it, and it carries the invariants.
A **read** that needs more than the entity exposes — **audit timestamps** (`created_at`/`updated_at`,
which are deliberately *not* entity fields), denormalized or computed values, a join across
aggregates, date-range filtering — returns a **read-model DTO** that the repository projects
**directly from the row**, bypassing the domain entity. The `*Result` DTO below is exactly this
mechanism: it holds whatever the API needs, not necessarily a bare `Foo`.

So "the screen shows a creation date" or "filter by `updated_at`" is satisfied by a read-model + a
repository filter — **never** by pulling the timestamp onto the domain aggregate (that would make the
write model carry display-only state). When a query's output is exposed by the API and needs fields
the entity does not (and should not) carry, return a read-model rather than the bare entity.

### File layout

```
src/<root>/application/<subdomain>/
├── list_foos_query.py    # ListFoosQuery
├── list_foos_handler.py  # ListFoosHandler
└── list_foos_result.py   # ListFoosResult   (only when the return shape is more than a single entity)
```

### Template — query DTO (non-auth-scoped list)

```python
from dataclasses import dataclass

from myapp.domain.foos import FooListFilter

__all__ = ["ListFoosQuery"]

@dataclass(frozen=True)
class ListFoosQuery:
    filter: FooListFilter
```

### Template — query DTO (auth-scoped)

```python
from dataclasses import dataclass
from uuid import UUID

from myapp.domain.foos import FooListFilter

__all__ = ["ListFoosQuery"]

@dataclass(frozen=True)
class ListFoosQuery:
    caller_id: UUID
    filter: FooListFilter
```

### Template — single-entity read handler

```python
from uuid import UUID

from myapp.domain.foos import Foo, IFooRepository

from .get_foo_query import GetFooQuery

__all__ = ["GetFooHandler"]

class GetFooHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, query: GetFooQuery) -> Foo:
        return await self._repo.get_by_id(query.id)
```

For `entity-or-none` reads, the return annotation is `Foo | None` and the repository method is the one that returns `Foo | None` (e.g. `get_by_name`).

### Template — list handler + Result DTO

```python
# list_foos_handler.py
from myapp.domain.foos import IFooRepository

from .list_foos_query import ListFoosQuery
from .list_foos_result import ListFoosResult

__all__ = ["ListFoosHandler"]

class ListFoosHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, query: ListFoosQuery) -> ListFoosResult:
        items = await self._repo.list(filter=query.filter)
        total = await self._repo.count(filter=query.filter)
        return ListFoosResult(items=items, total=total)
```

```python
# list_foos_result.py
from collections.abc import Sequence
from dataclasses import dataclass

from myapp.domain.foos import Foo

__all__ = ["ListFoosResult"]

@dataclass(frozen=True)
class ListFoosResult:
    items: Sequence[Foo]
    total: int
```

### Rules

#### Query DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **`caller_id` only when the query is authorization-scoped.** Non-scoped reads omit it.
   - **A tenant-scoped read also carries an auth-derived `workspace_id` / `tenant_id`.** In a multi-tenant app the query DTO carries the tenant the token names, stamped by the endpoint from `CurrentUser` (`workspace_id=user.workspace_id`, route binds `user: CurrentUser`) — never a request param (a client must not read another tenant's data). The handler scopes every repository call by it. Same rule as the command side (`application-command` DTO rule 2).
3. **No methods.** Just data.
4. **Domain filter records are passed by reference, not flattened.** Carry `filter: FooListFilter`, not loose `parent_ids` / `created_from` fields.

#### Result DTO (when present)

1. **`@dataclass(frozen=True)`.** No methods.
2. **Holds domain types only.** Never Pydantic models, never ORM rows.
3. **`items: Sequence[Foo]`**, never `list[Foo]`. Pagination metadata (`total`, `next_cursor`) lives here too.
4. **A read that must expose a DB-managed audit column (`created_at` / `updated_at`) returns a domain READ-MODEL, not the entity.** Audit timestamps are not entity fields (they live on the table, `PRINCIPLES.md` §E2) — but a read that displays or sorts by them needs them. Model that as a **read-model**: a `@dataclass(frozen=True)` in `domain/<subdomain>/` (e.g. `FooSummary` / `FooListRow`) that carries the displayed columns **including** the audit fields, which the **repository projects from the row** (the repository protocol method returns the read-model). Write model = the entity; read model = this projection. It stays a *domain* type so the domain repository returns it without importing `application` (a repo may never return an application/Pydantic DTO), and the entity stays audit-field-free. Don't reach for a heavyweight value object per read, and don't bolt audit fields onto the entity to make a read easier.

#### Handler

1. **One class per module, one public method.** `async def execute(self, query: <QueryClass>) -> <ReturnType>`.
2. **Constructor takes only domain protocols / policies.** Never a session, never an HTTP client.
3. **Return type follows the read shape** (derived from the query's `output` plus whether the response needs more than one entity):
   - a single domain entity → the entity; the repository raises `NotFoundError` when missing.
   - an optional single entity → `Entity | None`; the repository returns `None` when missing (e.g. `get_by_name`).
   - more than one entity (or entity + pagination metadata) → the `*Result` DTO.
4. **No business logic in the handler.** Reads pass parameters to the repository, optionally consult a domain service for "can this caller see this?" semantics, and return.
5. **No logging.** Reads are not business events. If audit logging is genuinely required, do it at the entrypoint, not here.
6. **No `try/except`.** Exceptions propagate to the central error handler.
7. **No transaction management.** Reads do not open transactions.

### Inlined typing / import rules

- `X | None`. Full annotations on `__init__`, `execute`, and every parameter.
- `Sequence[T]` from `collections.abc` for read-only views in `*Result` DTOs. Never `list[T]` for collections in domain-bordering DTOs.
- Cross-subdomain imports are absolute through the subpackage. Same-module imports are relative.
- No `from __future__ import annotations`. No `import structlog` — queries do not log.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `general-python-package` to register all produced modules in the subpackage `__init__.py`. The DI provider that constructs this handler is the responsibility of `infra-di-provider`.

### Hard stops

- Spec asks the query handler to mutate state → stop, use `application-command`.
- Spec asks for the response to include a Pydantic model → stop, that translation is the entrypoint's job (`restapi-schema`).
- Result shape exceeds ~3 fields and starts looking like a different concept → stop, model the response as a domain value object and return that instead of a `*Result`.
- Spec asks the handler to log a read event → stop, audit logging belongs in the entrypoint.


<!-- merged from pattern-compensating-tx -->

## Compensating Transactions

A pattern applied inside a command handler when it has already done something the outside world can see (an upload, a webhook, a file) before a later step (usually the DB write) can still fail. The handler must undo the visible side effect before letting the exception propagate.

This skill produces **no new file** — it shapes a command handler's `execute` body (the form `application-command` writes when compensation is required): the try → undo → re-raise structure around the visible side effect.

### When to use vs. neighbours

- The handler creates an external side effect (blob upload, third-party POST, file write) **before** a DB write that can still fail, and the side effect must be undone on failure → this skill.
- The handler performs writes across multiple repositories atomically → `pattern-unit-of-work` (the patterns nest: compensation outside, UoW inside).
- The handler has no external side effect, only a DB write → no compensation needed; the default `application-command` shape (no `try/except`) suffices.
- The side effect is harmless if left behind (cache warm-up), is the *last* step (nothing after to fail), or can be reordered after the DB write → skip this skill.

### Template — single side effect

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

    # caller_id is logged only when the command carries it (authenticated form);
    # an auth-less command has no caller_id field — drop it (see application-command DTO rule 2).
    logger.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))
    return foo.id
```

### Template — multi-step side effects

Accumulate work-to-undo in a list so partial progress is also cleaned:

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

The helper appends to `uploaded_keys` after each successful upload, so a failure mid-loop still rolls back what already landed.

### Successful-path cleanup is **not** compensation

When an upsert *replaces* a previous resource, the old one is cleaned **after** the DB commit:

```python
previous_key = await self._repo.upsert_foo(...)
# ... try/except wraps only the upsert above ...

if previous_key is not None:
    await self._storage.delete_many_best_effort([previous_key])
```

That trailing call is normal cleanup, not compensation — it runs only on success and disposes of the *old* resource. Don't conflate the two.

### Rules

1. **The `try/except Exception` block is the ONLY `try/except` allowed in a handler.** If you need another, the design is wrong — push the catch into infrastructure or remove it.
2. **Catch `Exception`, not specific exceptions.** Compensation must run regardless of failure cause.
3. **The compensation must never let its OWN failure mask the original error** — the undo is best-effort. Two sanctioned shapes, the architect's choice (do not assume one):
   - a dedicated **`*_best_effort` method** on the protocol (e.g. `delete_many_best_effort`) that swallows its internal errors — call it directly, as the templates show; **or**
   - the **plain protocol method** (`delete` / `revert`) wrapped in a nested swallow at the call site when no `*_best_effort` variant is modelled:
     ```python
     except Exception:
         try:
             await self._storage.delete(storage_key)
         except Exception:
             pass  # best-effort — the undo's own failure must not mask the original error
         raise
     ```
   Never call a raising `delete` / `revert` *unguarded* in the `except` — if it raises, the original error is lost. If the undo is called often enough to deserve a first-class name, the architect models a `*_best_effort` method; until then the call-site swallow is correct and needs no new protocol method.
4. **Bare `raise` at the end of `except`.** Never `raise NewException(...)`, never `raise ... from exc`. The original exception propagates unchanged.
5. **No logging inside `except`.** The central error handler logs once.
6. **The side effect runs *outside* the `try`.** Only the fallible *next* step is inside.
7. **Pre-side-effect validation runs *before* the upload.** Fail fast without compensation when possible.
8. **Compensation pairs with `pattern-unit-of-work` cleanly** — compensation wraps the UoW; the patterns nest: try / async with uow / commit / except / undo / raise.

### Hard stops

- The capability protocol lacks a `*_best_effort` cleanup method → stop, update the protocol via `domain-capability-protocol` first.
- The compensation method can itself raise non-trivially (e.g. it calls a flaky third-party DELETE) → stop, the protocol contract is wrong; the method must internally swallow its own errors.
- The handler needs to compensate across two unrelated backends (Postgres + Redis) → stop, this is a saga, not a single compensating-tx. Out of scope for this skill.


<!-- merged from pattern-unit-of-work -->

## Application Unit of Work

Produces the cross-cutting transactional-boundary abstraction. Three artifacts:

1. **Protocol:** `src/<root>/domain/i_unit_of_work.py` (or `i_<scope>_unit_of_work.py` if multiple scopes).
2. **Implementation:** `src/<root>/infrastructure/postgres/sqlalchemy_unit_of_work.py`.
3. **Handler integration:** a command handler that needs atomic multi-repository commits takes `uow_factory: Callable[[], IUnitOfWork]` and wraps its mutations in `async with self._uow_factory() as uow: ...` (the handler form `application-command` writes for this case).

### When to use it

Use when a handler writes to **two or more repositories in one transaction** (write + audit; aggregate + outbox).

Skip when:

- Only one repository → the `session_factory` style (`infra-sqlalchemy-repository`) is simpler.
- Atomic group is blob upload + DB write → that's `pattern-compensating-tx`. The patterns nest: compensation outside, UoW inside.
- The only motivation is read performance → `expire_on_commit=False` already covers it.

### Naming

- One `IUnitOfWork` per transactional scope, not per aggregate. Default name: `IUnitOfWork` in `i_unit_of_work.py`.
- Multiple UoWs are justified only for genuinely different scopes:
  - Different backends → `IPostgresUnitOfWork`, `IRedisUnitOfWork` (`i_<backend>_unit_of_work.py`).
  - Read/write split (rare) → `IReadUnitOfWork`, `IWriteUnitOfWork` (`i_<scope>_unit_of_work.py`).
- **Never name a UoW after an aggregate.** `IFooUnitOfWork` is wrong; it conflates "what's inside the transaction" with "what kind of transaction it is".

### Template — protocol

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

### Template — SQLAlchemy implementation

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

### Template — handler integration

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

When compensation is also required, compensation wraps the UoW block (see `pattern-compensating-tx`):

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

### Session-injected repository (required when joining a UoW)

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

### Rules

1. **One `IUnitOfWork` per scope, not per aggregate.** Every repository that may ever join a transaction is an attribute on the same protocol.
2. **`commit()` is the last statement** inside the `async with`. Anything after must be idempotent (logging, returning the new id).
3. **Exit without `commit()` rolls back.** Treat the UoW as "opt-in success".
4. **Don't catch exceptions inside the UoW block** unless implementing compensation. Let exceptions propagate so `__aexit__` rolls back.
5. **One UoW per `execute`.** Don't share across calls. Don't pool.
6. **Repositories joining the UoW take `session: AsyncSession`.** The same repository class cannot serve both `session_factory` and UoW callers — split into two adapters if you genuinely need both forms.
7. **Don't retry a failing UoW in the handler.** Propagate to the central error handler.

### DI wiring (owned by `infra-di-provider`)

The container wires the UoW as a `Factory` and passes `uow_factory.provider` — the `.provider` attribute exposes the zero-arg callable that matches `Callable[[], IUnitOfWork]`. The provider declarations themselves are `infra-di-provider`'s.

### Hard stops

- Only one repository participates → stop, this isn't a UoW case; keep the handler on `session_factory` via `infra-sqlalchemy-repository`.
- The "atomic group" spans two backends (Postgres + S3) → stop, this is `pattern-compensating-tx` or a saga, not a UoW.
- Spec asks for a UoW per aggregate (`IFooUnitOfWork`) → stop, that's the wrong shape; one shared UoW for the scope.


## Harvested handler-body rules

Two rules govern a handler's body, carried over from the v2 implementer prompt (notes/16 I2, I3):

- **Don't duplicate a guarantee the called method already gives.** No defensive pre-check that re-asserts a declared `raises`: if `delete(id)` is documented to raise `NotFoundError`, call it directly — never precede it with a `get_by_id(id)` whose only purpose is to trigger the same error. Load-then-act is only for a mutation that genuinely needs the entity in hand (to read a field, to compute the next state).
- **A blocked contract is the signal of a contract defect, not a workaround.** When the handler cannot be written cleanly against the current protocol — e.g. a lookup typed to *raise* `NotFoundError` where this use case treats not-found as a normal outcome — the fix is upstream: change the protocol to a `T | None` return, never bury a `try/except` in the handler or add a default argument to please a test. This is exactly the signal that the Interface sketch needs the contract-change protocol, never a silent local patch.
