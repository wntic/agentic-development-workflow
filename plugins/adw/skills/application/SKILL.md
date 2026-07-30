---
name: application
description: The house forms for the CQRS application layer — a command (frozen DTO plus a handler returning `UUID | None`, success-only logging) and a query (frozen DTO, a handler, and a `*Result` DTO when the response is more than one entity). Reads never mutate and never log business events.
when_to_use: Producing or editing an application command or query handler, or deciding what a read returns when it needs fields the domain entity does not carry.
paths: src/**/application/**
---

# Application

The use-case layer, split by CQRS: **commands** mutate and return an id, **queries** read and return
data. Both are thin — a frozen DTO plus a handler class whose only public method is `execute`.

Files land in `application/<subdomain>/`, where the subdomain is derived rather than chosen
(`conventions` block A).

## When to use vs. neighbours

- A mutation — create, update, delete, rename, move → **command**.
- A read — get, list, count, search, detect → **query**.
- An authorization-scoped read ("things I can see") → **query**, whose DTO carries `caller_id`.
- The mutation performs an external IO step before the DB write and must undo it on failure → still a
  command, but the handler body follows `patterns` (the compensating-transaction form).
- Two or more repositories must commit atomically → still a command, with an `IUnitOfWork` injected; see
  `patterns`.
- The entity, value object or filter record the DTOs mention → `domain-model`.
- The `IFooRepository` a handler depends on → `domain-ports`.
- Turning the return value into JSON → `restapi-schema`. A handler never returns a Pydantic model.

## Read models — the read/write split that decides a query's return type

The domain entity is the **write** model: commands load and mutate it, and it carries the invariants.

A read that needs more than the entity exposes — **audit timestamps** (`created_at` / `updated_at`,
which are deliberately *not* entity fields), denormalized or computed values, a join across aggregates,
date-range filtering — returns a **read-model DTO** that the repository projects **directly from the
row**, bypassing the entity.

So "the screen shows a creation date" or "filter by `updated_at`" is satisfied by a read-model plus a
repository filter, **never** by pulling the timestamp onto the aggregate — that would make the write
model carry display-only state.

The read-model is a `@dataclass(frozen=True)` in `domain/<subdomain>/` (`FooSummary`, `FooListRow`),
carrying the displayed columns including the audit fields, and the repository protocol method returns
it. It stays a *domain* type so the repository can return it without importing `application` — a
repository may never return an application or Pydantic DTO. Do not reach for a heavyweight value object
per read, and do not bolt audit fields onto the entity to make a read easier.

## File layout

```
src/<root>/application/<subdomain>/
├── create_foo_command.py   # CreateFooCommand
├── create_foo_handler.py   # CreateFooHandler
├── list_foos_query.py      # ListFoosQuery
├── list_foos_handler.py    # ListFoosHandler
└── list_foos_result.py     # ListFoosResult  (only when the read returns more than one entity)
```

## Template(s)

### Command DTO

The authenticated form, carrying `caller_id`. A command reached only by anonymous routes, or any command
in an app with no auth, drops the field entirely — see the auth-derived-fields rule.

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

### Command handler — create (returns `UUID`)

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

### Command handler — update or delete (returns `None`)

```python
class DeleteFooHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: DeleteFooCommand) -> None:
        await self._repo.delete(cmd.id)
        logger.info("foo_deleted", foo_id=str(cmd.id), caller_id=str(cmd.caller_id))
```

### Query DTO — not authorization-scoped

```python
from dataclasses import dataclass

from myapp.domain.foos import FooListFilter

__all__ = ["ListFoosQuery"]

@dataclass(frozen=True)
class ListFoosQuery:
    filter: FooListFilter
```

### Query DTO — authorization-scoped

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

### Query handler — single entity

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

For an entity-or-none read the annotation is `Foo | None` and the repository method is the one returning
`Foo | None`, such as `get_by_name`.

### Query handler — list, plus its Result DTO

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

## Rules

### Auth-derived fields (both sides)

1. **`caller_id: UUID` is the first field of a command DTO — when the command runs behind an
   authenticated route.** Whether an app has auth at all is a property of its routes
   (`restapi-route-contracts`), so the actor is conditional: a command reached only by anonymous routes,
   or any command in an app with no auth, has no caller to thread and **omits `caller_id`** entirely.
   The templates show the authenticated form. On a query DTO the same field appears **only when the read
   is authorization-scoped**; a non-scoped read omits it.
2. **Every auth-derived field is stamped by the endpoint from the token, never read from the request.**
   A multi-tenant app threads more than the actor: a `workspace_id` / `tenant_id` / `org_id` the token
   carries is a field on the DTO set by the endpoint from `CurrentUser`
   (`workspace_id=user.workspace_id`), exactly like `caller_id=user.id` — never from the request body or
   path, because a client must not choose its own tenant or read another's data. The handler then scopes
   every repository call by it. Auth-derived inputs come from the token; request-derived inputs from the
   body or path.

### Command DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **No methods, no behaviour.** Just data.
3. **Optional fields use `field: T | None = None`** or a concrete default — never a sentinel string.

### Query DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **No methods.** Just data.
3. **Domain filter records are passed by reference, not flattened.** Carry `filter: FooListFilter`, not
   loose `parent_ids` / `created_from` fields.

### Result DTO (when present)

1. **`@dataclass(frozen=True)`, no methods.**
2. **Holds domain types only.** Never Pydantic models, never ORM rows.
3. **`items: Sequence[Foo]`**, never `list[Foo]`. Pagination metadata (`total`, `next_cursor`) lives here
   too.
4. **A read that must expose an audit column returns a read-model, not the entity** — see the read/write
   split above.

### Command handler

1. **One class per module, one public method.**
   `async def execute(self, cmd: <CommandClass>) -> <ReturnType>`. Nothing else public.
2. **Constructor takes only domain protocols, domain services, a unit of work, or tunable value
   objects.** Never a session, never an HTTP client, never `Any`.
3. **Return type:** `UUID` for a create, `None` for everything else. Never return the entity. A "do the
   work, then show the result" use case is still a command returning the affected id — the caller
   re-reads through the matching query (`ProcessMeeting` returns the meeting id; the READY view comes
   from `GetMeeting`). One mutate-and-return-a-view operation would straddle the command/query split.
4. **No business logic in the handler.** Build and mutate domain entities; let `__post_init__` and domain
   services enforce the rules. The handler orchestrates: load, mutate, call the repository.
   **Normalization — strip, lowercase, canonicalize — is a domain concern** living in the entity's
   `__post_init__` or a value object. Pass `cmd.name`, not `cmd.name.strip()`.
5. **No `try/except`, with two sanctioned exceptions.** (a) The compensating-transaction pattern, see
   `patterns`. (b) A **failure-state transition then re-raise**: when the contract requires the aggregate
   to record that it failed before the error propagates — a pipeline that must persist `status=FAILED` so
   a later read or retry sees it — the handler may
   `try: <pipeline> except <Err>: <load-or-mutate>; entity.status = FAILED; await repo.update(entity); raise`.
   The `except` writes the caller-visible state and **re-raises**: never swallows, never
   logs-and-re-raises (`general-logging`), and chains with `raise ... from exc` (`B904`). Anything beyond
   these two — translating a `DomainError`, catching to swallow, control flow via exceptions — stays
   forbidden.
6. **Log on success only, after the mutation completes.** The event name is snake_case past tense
   (`foo_created`, `bar_renamed`). Always include the affected resource id; include
   `caller_id=str(cmd.caller_id)` **only when the command carries it**. Never log on failure —
   exceptions propagate and the central handler logs once.
7. **No transaction management inside the handler.** The transaction lifecycle is wired at the entrypoint
   through DI, typically an `IUnitOfWork` when several writes must be atomic.

### Query handler

1. **One class per module, one public method.**
   `async def execute(self, query: <QueryClass>) -> <ReturnType>`.
2. **Constructor takes only domain protocols and domain services.** Never a session, never an HTTP
   client.
3. **Return type follows the read shape:**
   - a single entity → the entity; the repository raises `NotFoundError` when missing.
   - an optional single entity → `Entity | None`; the repository returns `None` when missing.
   - more than one entity, or entities plus pagination metadata → the `*Result` DTO.
   - fields the entity does not carry → a read-model (see above).
4. **No business logic.** A read passes parameters to the repository, optionally consults a domain
   service for "can this caller see this?", and returns.
5. **No logging.** A read is not a business event. If audit logging is genuinely required it happens at
   the entrypoint.
6. **No `try/except`.** Exceptions propagate to the central error handler.
7. **No transaction management.** Reads do not open transactions.

## Inlined typing / import rules

- `X | None`, never `Optional[X]`. Full annotations on `__init__`, `execute` and every parameter.
- `Sequence[T]` from `collections.abc` for read-only views in `*Result` DTOs — never `list[T]`.
- Cross-subdomain imports are absolute through the subpackage:
  `from myapp.domain.foos import Foo, IFooRepository`. Same-module imports are relative:
  `from .create_foo_command import CreateFooCommand`.
- A command handler puts `import structlog` and `logger = structlog.get_logger()` at module top, never
  inside the class. A query handler imports no `structlog` at all — queries do not log.
- No `from __future__ import annotations`.
- No comments unless a non-obvious *why*; one short line at most.

## Package wiring

Follow `general-python-package` to register every produced module in the subpackage `__init__.py`. The DI
provider that constructs a handler is `infra-wiring`.

## Hard stops

- Spec asks a command handler to return a list, a `Result`, or the entity → stop, that is a query — and
  re-read the spec, because mutations do not return data.
- Spec asks a query handler to mutate state → stop, that is a command.
- Spec asks a handler to catch a `DomainError` and translate it → stop, that is the central error
  handler's job (`restapi-app`).
- Spec asks a handler to validate cross-aggregate state inline → stop, extract a `domain-service` and
  inject it.
- Spec implies several writes must be atomic → stop, request an `IUnitOfWork` dependency (`patterns`).
- Spec implies an external IO step before the DB write → stop, still a command, but the body must follow
  the compensating-transaction form (`patterns`).
- Spec asks for a Pydantic model in a response → stop, that translation is the entrypoint's job
  (`restapi-schema`).
- A `*Result` grows past about three fields and starts looking like a different concept → stop, model the
  response as a domain value object or a read-model and return that.
- Spec asks a query handler to log a read event → stop, audit logging belongs at the entrypoint.
