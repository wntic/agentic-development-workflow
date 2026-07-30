---
name: python-style
description: Cross-cutting Python style for every layer — typing conventions (`X | None`, immutable collections in the domain, `Any` only at raw boundaries, the project-wide ban on `from __future__ import annotations`) and logging (the `structlog` setup, what each layer may log, success-only events in `application/`, and never log-and-re-raise).
when_to_use: Deciding an annotation form, a collection type, or how and where to log. Consulted alongside the skill that owns the artifact, not instead of it.
---

# Python Style

Project-wide rules that apply at every layer and are stricter than CPython's defaults. Two subjects,
each with a per-layer edge: what the types look like, and who is allowed to log what.

## When to use vs. neighbours

- Writing or changing any annotation, or any log call → this skill.
- Where a module lives, how it is packaged, how it imports → `architecture`.
- Deriving a concrete path or class name → `conventions`.
- The shape of a specific artifact → its own skill (`domain-model`, `application`, `infra-persistence`,
  `restapi-endpoint`, …). This skill is consulted alongside them.

## Typing

### `X | None`, not `Optional[X]`

```python
# yes
name: str | None = None
def find(id: UUID) -> User | None: ...

# no
from typing import Optional
name: Optional[str] = None
```

PEP 604 union syntax is the default. `Union[A, B]` is equally banned — write `A | B`. This holds at every
layer, including Pydantic models in `restapi/schemas/`.

### Never `from __future__ import annotations`

Do not add this import to any module. The project relies on **runtime annotation introspection** —
Pydantic's validation, `dependency-injector`'s providers, dataclass `__post_init__` checks. Stringified
annotations break those tools silently. The runtime is Python 3.12, so PEP 604 syntax already works
without it.

If a third-party tool tells you to add it, the fix is to change the annotation, not to silence the
runtime.

### Full coverage on every signature

Every function, method and `__init__` parameter is fully annotated, return type included. `-> None` is
required on a procedure. Lambdas inside business logic are forbidden — use a named function; a lambda in
`dataclasses.field(default_factory=...)` is fine because it carries no annotations.

### `Any` only at raw external boundaries

`typing.Any` is permitted only where data has not yet been parsed:

- raw deserialized JSON before Pydantic validation;
- a third-party SDK return type not yet narrowed.

Note the related convention: when collecting heterogeneous values this codebase uses
`dict[str, object]`, not `dict[str, Any]` — as in `context: dict[str, object]` on a domain exception —
because `object` forces explicit narrowing at the point of consumption.

Inside `domain/`, `application/`, and the body of any handler, `Any` is forbidden. If a type is hard to
express, introduce a `TypeAlias` or a small dataclass.

### `TypeAlias` for repeated complex types

```python
from typing import TypeAlias

FooKey: TypeAlias = tuple[UUID, int]
```

Use one whenever the same composite — a `tuple[…, …]`, a `dict[str, frozenset[UUID]]`, a callable
signature — appears in more than one signature. Place it at the top of the module owning the concept,
after imports and before classes, and re-export it via `__all__` if it crosses module boundaries. For a
module-internal one-shot type, write the type out; a premature alias hides intent.

### Domain-layer collection types

Domain code uses **immutable** collections so entities and value objects hash and compare safely, and so
frozen dataclasses do not expose mutable state.

| Mutable (avoid in domain) | Immutable (use in domain) |
|---|---|
| `list[T]` | `tuple[T, ...]` when ordered, `Sequence[T]` for a read-only view |
| `set[T]` | `frozenset[T]` |
| `dict[K, V]` | `Mapping[K, V]` for a read-only view, a frozen dataclass for a fixed-shape record |

```python
@dataclass(frozen=True)
class Foo:
    id: UUID
    bar_ids: frozenset[UUID]
    items: tuple[Item, ...]
```

Conversion happens at the boundary: when a command DTO takes collections from the entrypoint, the route
converts — `bar_ids=frozenset(payload.bar_ids)`, `items=tuple(item_inputs)`. The schema layer may hold
`list[...]`, Pydantic's natural shape; the domain stores the frozen form.

`Sequence[T]` and `Mapping[K, V]` from `collections.abc` are the right return annotations for read-only
views: they accept `list`/`tuple` and `dict`/`MappingProxyType` at runtime.

Application and infrastructure code may use mutable collections **internally** — loop accumulators,
row building — but anything crossing into a domain object is converted first.

### Protocols

- `typing.Protocol` for every interface (`domain-ports`).
- `@runtime_checkable` **only** when `isinstance(x, IProtocol)` is genuinely needed, and never in a hot
  path: it walks the protocol's `__protocol_attrs__` on every call.
- A protocol's method signatures carry full annotations like any other function. The `...` is the
  **method body**, never a parameter default.

### Pydantic and FastAPI specifics

- `BaseModel` field types use the same `X | None` and PEP 585 generic forms — `list[int]`,
  `dict[str, str]`, not `List[int]` / `Dict[str, str]`.
- `Annotated[T, Field(...)]` and `Annotated[T, Query(...)]` are the canonical way to add constraints.
  Do not use the legacy `field: int = Field(default=...)` shape when there is no default — write
  `field: Annotated[int, Field(ge=1)]`.
- Schemas live in `restapi/schemas/` and never import domain entities (`restapi-schema`).

### Collections from `collections.abc`

| Use | Not |
|---|---|
| `collections.abc.Sequence` | `typing.Sequence` |
| `collections.abc.Mapping` | `typing.Mapping` |
| `collections.abc.Iterable` | `typing.Iterable` |
| `collections.abc.AsyncIterator` | `typing.AsyncIterator` |
| `collections.abc.Callable` | `typing.Callable` |

The `typing.*` aliases have been deprecated since 3.9; `collections.abc` keeps imports consistent and
avoids a needless `typing` import.

## Logging

`structlog` throughout. The setup is the same everywhere; the rules about *when* to log differ per layer,
and getting them wrong produces either a silent failure or two entries for one event.

### Setup

Call `structlog.get_logger()` at module level. Bind context with `.bind()` for repeated fields, or pass
fields inline per call.

```python
import structlog

log = structlog.get_logger()

# inline fields
log.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))

# bound context for a sequence of calls
log_ctx = log.bind(import_id=str(import_id))
log_ctx.info("import_started", row_count=len(rows))
log_ctx.info("import_completed", imported=imported, skipped=skipped)
```

**Never `print()` in non-entrypoint code, and never the stdlib `logging` module directly** —
`structlog` is the only logger.

### `domain/` — never log

The domain does zero IO, and that includes the log socket. If a domain function seems to need a log, the
rule belongs on the entity — raised as an exception carrying `context` — and the entrypoint logs it.

### `infrastructure/` — log the low-level failure, then re-raise

When an adapter catches a low-level exception (a DB constraint, a network timeout, a third-party error)
and re-raises it as a domain exception, log the low-level detail **before** re-raising:

```python
try:
    await self._session.execute(stmt)
except IntegrityError as exc:
    if "uq_foos_name" in str(exc.orig):
        log.warning("foo_name_conflict", foo_name=foo.name)
        raise ConflictError("foo name already exists", context={"field": "name"}) from exc
    raise
```

Level guide: `log.warning` for an expected business-rule violation surfacing at the infra layer —
uniqueness, a foreign key; `log.error` for an unexpected failure — a network timeout, a third-party 5xx,
malformed data.

**Do not log the resulting domain exception.** The entrypoint logs it; logging at both layers duplicates
the entry.

### `application/` — log on success only

A handler logs a structured business event **after** `execute()` completes successfully, with
`log.info` and a snake_case event name as the first positional argument.

The event name is `<resource>_<past_tense_verb>` — `foo_created`, `bar_archived`, `foos_imported`,
`foo_renamed`. These are stable strings: **do not rename once shipped**, because dashboards and alerts
key on them.

Required fields where applicable: the primary resource id as `<resource>_id`; the actor as `caller_id`,
always for a command that carries one; `role` when role rank is load-bearing; and counts
(`imported`, `skipped`, `errors`) for a bulk operation.

**Do not log errors in a handler.** Domain exceptions propagate and the central error handler logs them
once. The sanctioned `try/except` blocks in `application/` (`patterns`, and the failure-state transition)
are **not** exceptions to this: the catch undoes a side effect or records state and re-raises, with **no
log call inside the `except`**.

### Entrypoints (`restapi/`, `cli/`, `worker/`) — log errors at the point of handling

The central error handler is the **only** place that logs an error event. It receives the propagated
`DomainError`, logs it once with the request context, and translates it to the response.

```python
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    log.warning(
        "domain_error",
        code=exc.code,
        http_status=exc.http_status,
        path=request.url.path,
        method=request.method,
        context=exc.context,
    )
    return JSONResponse(status_code=exc.http_status, content=...)
```

Level guide: `log.warning` for the 4xx class — `ValidationError`, `ConflictError`, `NotFoundError`,
`UnauthorizedError`; `log.error` for the 5xx class, an unexpected internal error that escaped the
domain-exception protocol. Anything that is not a `DomainError` also logs here, at `error` level, before
the framework converts it to a 500.

## Hard stops

Typing:

- `from __future__ import annotations` anywhere → stop, runtime annotation introspection (Pydantic,
  `dependency-injector`, dataclass `__post_init__`) breaks silently with stringified annotations.
- `Optional[X]` or `Union[A, B]` → stop, use `X | None` / `A | B`.
- Bare `Any` outside the documented external-boundary cases → stop, introduce a `TypeAlias` or a small
  dataclass; do not let `Any` spread.
- Untyped `**kwargs` / `*args` in domain or application code → stop, a dataclass is missing.
- `cast(...)` to silence a type error → stop, fix the type. `cast` is acceptable only to narrow after a
  runtime guard the checker cannot follow, which is rare.
- `# type: ignore` with no reason → stop, write `# type: ignore[<rule>]` with a brief explanation.
- `TYPE_CHECKING`-only imports purely to break a cycle → stop, the cycle is usually a layering
  violation (`architecture`); fix the structure, not the import.

Logging:

- `log.x(...); raise` in the same scope → stop, that is two entries for one event. The single sanctioned
  use is in `infrastructure/`, translating a low-level exception to a domain one — and even there only
  the *low-level* detail is logged; the domain exception is logged later by the entrypoint.
- Any log call in `domain/` → stop, zero IO includes the log socket.
- `log.error(...)` or `log.warning(...)` in `application/` → stop, a handler logs successes only; errors
  are the entrypoint's job.
- A handler catches an exception just to log it → stop, the catch must do something else — compensation,
  a state transition — and the logging belongs at the entrypoint.
- An infrastructure adapter logs the domain exception it just raised → stop, remove the duplicate.
- `print()` anywhere outside an entrypoint debug path behind a flag → stop, use `structlog`.
- `import logging` or `logging.getLogger(...)` → stop, `structlog.get_logger()` everywhere.
- An event name that is not snake_case past tense (`FooCreated`, `create-foo`) → stop, rename it to
  `foo_created`. Once shipped, never rename — dashboards depend on the string.
- Logging a `UUID` object instead of `str(uuid_value)` → stop, some sinks render `UUID(...)` poorly.
- Logging a full request or response body → stop, log identifiers and counts only; bodies may carry PII
  or secrets.
- Binding a sensitive field — a password, a bearer token, an API key → stop, log a length or a hash,
  never the value.
