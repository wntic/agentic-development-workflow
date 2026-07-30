---
name: application-command
description: The house form for a mutation use case — a frozen command DTO plus a handler with a single `async def execute(self, cmd) -> UUID | None`, success-only structured logging, no business logic in the handler body, and no `try/except`.
when_to_use: Producing or editing an application command handler — create, update, delete, rename, any write.
paths: src/**/application/**
---

# Application Command

Produces a mutation use case as two files in `application/<subdomain>/`:

1. `<verb>_<noun>_command.py` — the frozen-dataclass DTO.
2. `<verb>_<noun>_handler.py` — the handler class.

## When to use vs. neighbours

- Mutation (create/update/delete/rename/move) → this skill.
- Read (get/list/count/search) → `application-query`.
- The mutation includes an external IO step before the DB write (file upload, third-party POST) and needs rollback → still this skill, but the handler body follows `pattern-compensating-tx`.
- Multiple repositories must update atomically (write + audit log) → still this skill, plus inject an `IUnitOfWork` (see `pattern-unit-of-work`).

## File layout

```
src/<root>/application/<subdomain>/
├── <verb>_<noun>_command.py   # CreateFooCommand
└── <verb>_<noun>_handler.py   # CreateFooHandler
```

## Template — command DTO

(Authenticated form — carries `caller_id`. A command reached only by anonymous routes, or any command in an app with no auth at all, drops `caller_id` entirely; see DTO rule 2.)

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

## Template — create handler (returns `UUID`)

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

## Template — update/delete handler (returns `None`)

```python
class DeleteFooHandler:
    def __init__(self, repo: IFooRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: DeleteFooCommand) -> None:
        await self._repo.delete(cmd.id)
        logger.info("foo_deleted", foo_id=str(cmd.id), caller_id=str(cmd.caller_id))
```

## Rules

### Command DTO

1. **`@dataclass(frozen=True)`.** Always frozen.
2. **`caller_id: UUID` is the first field — when the command runs behind an authenticated route.** Whether an app has auth at all is a property of its routes (`restapi-auth-dependency`), so the actor is conditional: a command reached only by anonymous routes — or any command in an app with no auth — has no caller to thread, so it **omits `caller_id`** (there is no source to populate it). The templates here show the authenticated form; for the auth-free case drop the field. Presence follows from whether the calling endpoints are authenticated, never a blanket convention.
   - **Other auth-derived fields stamp the same way.** A multi-tenant app threads more than the actor: a `workspace_id` / `tenant_id` / `org_id` the token carries is a field on the command **stamped by the endpoint from `CurrentUser`** (`workspace_id=user.workspace_id`), exactly like `caller_id=user.id` — never read from the request body or path (a client must not choose its own tenant). The handler then scopes every repository call by it. The same rule holds for a query (rule below) and the endpoint (`restapi-endpoint` / `restapi-auth-dependency`): auth-derived inputs come from the token, request-derived inputs from the body/path.
3. **No methods, no behavior.** Just data.
4. **Optional fields use `field: T | None = None`** or a concrete default — never sentinel strings.

### Handler

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

## Inlined typing / import rules

- `X | None` (never `Optional[X]`). Full annotations on `__init__`, `execute`, and every parameter.
- Cross-subdomain imports are absolute through the subpackage: `from myapp.domain.foos import Foo, IFooRepository`. Same-module imports are relative (`from .create_foo_command import CreateFooCommand`).
- `import structlog` and `logger = structlog.get_logger()` at module top — never inside the class.
- No `from __future__ import annotations`.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to register both modules in the subpackage `__init__.py`. The DI provider that constructs this handler is the responsibility of `infra-di-provider`.

## Hard stops

- Spec asks the handler to return a list, a `Result`, or the entity → stop, use `application-query` (and re-read the spec — mutations don't return data).
- Spec asks the handler to catch a `DomainError` and translate it → stop, that's the central error handler's job (`restapi-error-responses`).
- Spec asks the handler to validate cross-aggregate state inline → stop, extract a `domain-service` and inject it.
- Spec implies multiple writes must be atomic → stop, request an `IUnitOfWork` dependency (see `pattern-unit-of-work`).
- Spec implies an external IO step before the DB write → stop, this still uses this skill but the body must follow `pattern-compensating-tx`.
