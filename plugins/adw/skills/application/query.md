<!-- merged from application-query -->

# Application Query

Produces a read use case as two or three files in `application/<subdomain>/`:

1. `<verb>_<noun>_query.py` — the frozen-dataclass DTO.
2. `<verb>_<noun>_handler.py` — the handler class.
3. `<verb>_<noun>_result.py` — only when the return shape is more than a single domain entity.

## When to use vs. neighbours

- Read (get/list/count/search/detect) → this skill.
- Mutation → `command.md`.
- Domain filter dataclass that the query handler passes into the repository → `domain-filter` (this skill consumes it).
- Authorization-scoped read ("things I can see") → still this skill; the query DTO carries `caller_id`.

## Read models — the CQRS read/write split

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

## File layout

```
src/<root>/application/<subdomain>/
├── list_foos_query.py    # ListFoosQuery
├── list_foos_handler.py  # ListFoosHandler
└── list_foos_result.py   # ListFoosResult   (only when the return shape is more than a single entity)
```

## Template — query DTO (non-auth-scoped list)

```python
from dataclasses import dataclass

from myapp.domain.foos import FooListFilter

__all__ = ["ListFoosQuery"]

@dataclass(frozen=True)
class ListFoosQuery:
    filter: FooListFilter
```

## Template — query DTO (auth-scoped)

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

## Template — single-entity read handler

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

## Template — list handler + Result DTO

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

### Query DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **`caller_id` only when the query is authorization-scoped.** Non-scoped reads omit it.
   - **A tenant-scoped read also carries an auth-derived `workspace_id` / `tenant_id`.** In a multi-tenant app the query DTO carries the tenant the token names, stamped by the endpoint from `CurrentUser` (`workspace_id=user.workspace_id`, route binds `user: CurrentUser`) — never a request param (a client must not read another tenant's data). The handler scopes every repository call by it. Same rule as the command side (`command.md` DTO rule 2).
3. **No methods.** Just data.
4. **Domain filter records are passed by reference, not flattened.** Carry `filter: FooListFilter`, not loose `parent_ids` / `created_from` fields.

### Result DTO (when present)

1. **`@dataclass(frozen=True)`.** No methods.
2. **Holds domain types only.** Never Pydantic models, never ORM rows.
3. **`items: Sequence[Foo]`**, never `list[Foo]`. Pagination metadata (`total`, `next_cursor`) lives here too.
4. **A read that must expose a DB-managed audit column (`created_at` / `updated_at`) returns a domain READ-MODEL, not the entity.** Audit timestamps are not entity fields — they are a DB-managed table convention — but a read that displays or sorts by them needs them. Model that as a **read-model**: a `@dataclass(frozen=True)` in `domain/<subdomain>/` (e.g. `FooSummary` / `FooListRow`) that carries the displayed columns **including** the audit fields, which the **repository projects from the row** (the repository protocol method returns the read-model). Write model = the entity; read model = this projection. It stays a *domain* type so the domain repository returns it without importing `application` (a repo may never return an application/Pydantic DTO), and the entity stays audit-field-free. Don't reach for a heavyweight value object per read, and don't bolt audit fields onto the entity to make a read easier.

### Handler

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

## Inlined typing / import rules

- `X | None`. Full annotations on `__init__`, `execute`, and every parameter.
- `Sequence[T]` from `collections.abc` for read-only views in `*Result` DTOs. Never `list[T]` for collections in domain-bordering DTOs.
- Cross-subdomain imports are absolute through the subpackage. Same-module imports are relative.
- No `from __future__ import annotations`. No `import structlog` — queries do not log.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to register all produced modules in the subpackage `__init__.py`. The DI provider that constructs this handler is the responsibility of `infra-di-provider`.

## Hard stops

- Spec asks the query handler to mutate state → stop, use `command.md`.
- Spec asks for the response to include a Pydantic model → stop, that translation is the entrypoint's job (`restapi-schema`).
- Result shape exceeds ~3 fields and starts looking like a different concept → stop, model the response as a domain value object and return that instead of a `*Result`.
- Spec asks the handler to log a read event → stop, audit logging belongs in the entrypoint.
