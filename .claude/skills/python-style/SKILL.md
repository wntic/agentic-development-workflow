---
name: python-style
description: Cross-cutting Python style for every layer: typing conventions (`X | None`, immutable collections in the domain, `Any` only at raw boundaries, the project-wide prohibition on `from __future__ import annotations`) and logging (`structlog` setup, per-layer rules, success-only events in `application/`, never log-and-re-raise).
when_to_use: Writing or reviewing any Python module and deciding an annotation form, a collection type, or how and where to log. Consulted alongside the artifact-specific skill, not instead of it.
---
# Python style — typing & logging

This merged skill covers 2 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from general-typing-conventions -->

## Typing Conventions

Project-wide typing rules. They apply to every layer — domain, application, infrastructure, restapi — and are stricter than CPython's defaults to keep runtime introspection cheap and the type-checker honest.

### When to use vs. neighbours

- Writing or modifying any type annotation anywhere in the codebase → consult this skill.
- Package mechanics (one class per module, `__all__`, re-exports) → `general-python-package`.
- Import shape (relative vs absolute, collapsed imports) → `general-imports-conventions`.
- Layer boundaries (what each layer may import) → `general-layered-architecture`.
- Domain object collection types (`frozenset` vs `set`) — same rules; this skill is referenced by `domain-entity`, `domain-value-object`, `domain-filter`.

### Core rules

#### `X | None`, not `Optional[X]`

```python
# yes
name: str | None = None
def find(id: UUID) -> User | None: ...

# no
from typing import Optional
name: Optional[str] = None
```

PEP 604 union syntax is the project default. `Union[A, B]` is also banned — write `A | B`. This applies at every layer, including Pydantic models in `restapi/schemas/`.

#### Never `from __future__ import annotations`

Do not add this import to any module. The project relies on **runtime annotation introspection** (Pydantic's validation, `dependency-injector`'s providers, dataclass `__post_init__` checks). Stringified annotations break those tools silently. Python 3.10+ is the runtime, so PEP 604 syntax already works without the future import.

If a third-party tool tells you to add it, the right fix is to change the annotation, not silence the runtime.

#### Full coverage on every signature

Every function, method, and `__init__` parameter is fully annotated, including the return type. `-> None` is required for procedures. Lambdas inside business logic are forbidden (use named functions); lambdas inside `dataclasses.field(default_factory=...)` are fine because they don't carry annotations.

#### `Any` only at raw external boundaries

`typing.Any` is permitted only where data has not yet been parsed:

- raw deserialized JSON before Pydantic validation
- third-party SDK return types we haven't yet narrowed
- `dict[str, Any]` for `context: dict[str, object] = ...` in `ErrorResponse`-style payloads — note this codebase uses `object`, not `Any`, when collecting heterogeneous values, because `object` requires explicit narrowing at consumption time

Inside `domain/`, `application/`, and the body of any handler, `Any` is forbidden. If a type is hard to express, introduce a `TypeAlias` or a small dataclass; do not reach for `Any`.

#### `TypeAlias` for repeated complex types

```python
from typing import TypeAlias
FooKey: TypeAlias = tuple[UUID, int]
```

Use a `TypeAlias` whenever the same composite (`tuple[..., ...]`, `dict[str, frozenset[UUID]]`, callable signatures) appears in more than one signature. Place the alias at the top of the module that owns the concept, after imports and before classes. Re-export it via `__all__` if it crosses module boundaries.

For module-internal one-shot types, write the type out directly — premature aliases hide intent.

### Domain-layer collection types

Domain code uses **immutable** collection types so entities and value objects can hash/compare safely and so frozen dataclasses don't expose mutable state.

| Mutable (avoid in domain) | Immutable (use in domain) |
|--------------------------|---------------------------|
| `list[T]` | `tuple[T, ...]` for ordered, `Sequence[T]` for read-only views |
| `set[T]` | `frozenset[T]` |
| `dict[K, V]` | `Mapping[K, V]` for read-only views, frozen dataclass for fixed-shape records |

```python
# domain — frozen dataclass with immutable collections
@dataclass(frozen=True)
class Foo:
    id: UUID
    bar_ids: frozenset[UUID]
    items: tuple[Item, ...]
```

When a command DTO accepts collections from the entrypoint, the route converts on the boundary: `bar_ids=frozenset(payload.bar_ids)`, `items=tuple(item_inputs)`. The schema layer can hold `list[...]` (Pydantic's natural shape); the domain stores the frozen form.

`Sequence[T]` and `Mapping[K, V]` (from `collections.abc`) are the right return-type annotations for read-only views — they accept both `list`/`tuple` and `dict`/`MappingProxyType` at runtime.

Application and infrastructure code may use mutable collections **internally** (loop accumulators, building rows), but anything that crosses into a domain object is converted to its immutable counterpart.

### Protocols

- Use `typing.Protocol` for all interfaces (see `domain-protocols`).
- Apply `@runtime_checkable` **only** when `isinstance(x, IProtocol)` is genuinely needed. Avoid runtime checks against protocols in hot paths — they walk the protocol's `__protocol_attrs__` on every call.
- Protocol method signatures carry full annotations like any other function. Do not write `...` as a parameter default; the protocol body is `...` for the **method body**, not the parameters.

### Pydantic and FastAPI specifics

- `BaseModel` field types use the same `X | None` and PEP 585 generic forms (`list[int]`, `dict[str, str]`) — not `List[int]`, `Dict[str, str]`.
- `Annotated[T, Field(...)]` and `Annotated[T, Query(...)]` are the canonical form for adding constraints. Don't use the legacy `field: int = Field(default=...)` shape when there is no default — write `field: Annotated[int, Field(ge=1)]`.
- Schemas live in `restapi/schemas/` and never import from domain entities (see `restapi-schema`).

### Collections from `collections.abc`

Prefer `collections.abc` over `typing` for runtime-checkable abstract types:

| Use | Not |
|-----|-----|
| `collections.abc.Sequence` | `typing.Sequence` (deprecated alias) |
| `collections.abc.Mapping` | `typing.Mapping` |
| `collections.abc.Iterable` | `typing.Iterable` |
| `collections.abc.AsyncIterator` | `typing.AsyncIterator` |
| `collections.abc.Callable` | `typing.Callable` |

`typing.*` aliases for these are deprecated since 3.9; using `collections.abc` keeps imports consistent and avoids unnecessary `typing` imports.

### Hard stops

- `from __future__ import annotations` anywhere → stop, runtime annotation introspection (Pydantic, `dependency-injector`, dataclass `__post_init__`) breaks silently with stringified annotations.
- `Optional[X]` or `Union[A, B]` → stop, use `X | None` / `A | B`.
- Bare `Any` outside the documented external-boundary cases → stop, introduce a `TypeAlias` or a small dataclass; do not let `Any` spread.
- Untyped `**kwargs` / `*args` in domain or application code → stop, you're likely missing a dataclass.
- `cast(...)` to silence a type error → stop, fix the type. `cast` is acceptable only for narrowing after a runtime guard the checker can't follow (rare).
- `# type: ignore` without a reason → stop, use `# type: ignore[<rule>]` with a brief explanation.
- `TYPE_CHECKING`-only imports purely to break a circular import → stop, the cycle is usually a layering violation (see `general-layered-architecture`); fix the structure, not the import.


<!-- merged from general-logging -->

## Logging

Use `structlog` throughout. The setup is the same everywhere; the rules about *when* to log differ per layer, and getting them wrong produces either silent failures or duplicate entries for the same event.

### When to use vs. neighbours

- Adding or modifying any log call anywhere in the codebase → consult this skill.
- The `application/` success-event log line → this skill, plus `application-command` (which embeds the per-handler `logger.info(...)` template).
- The `infrastructure/` `IntegrityError` → domain exception log + raise pattern → this skill, plus `infra-sqlalchemy-repository`.
- The central `DomainError` → JSON translation log → this skill, plus `restapi-error-responses` / `restapi-app-bootstrap`.

### Setup

Call `structlog.get_logger()` at module level. Bind context with `.bind()` for repeated fields, or pass fields inline on each call.

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

**Never use `print()` in non-entrypoint code.** Never use stdlib `general-logging` directly — `structlog` is the only logger.

### Per-layer rules

The rules describe **what each layer logs and what each layer must NOT log**. The combination is what produces a single coherent log entry per event with no duplicates.

#### `domain/` — never log

Domain has zero IO. That includes logging. If a domain function "needs" to log, the rule belongs on the entity (raised as an exception with `context`) and the entrypoint logs it.

#### `infrastructure/` — log low-level failures, then re-raise

When an adapter catches a low-level exception (DB constraint, network timeout, third-party error) and re-raises it as a domain exception, log the low-level detail **before re-raising**:

```python
try:
    await self._session.execute(stmt)
except IntegrityError as exc:
    if "uq_foos_name" in str(exc.orig):
        log.warning(
            "foo_name_conflict",
            foo_name=foo.name,
        )
        raise ConflictError("foo name already exists", context={"field": "name"}) from exc
    raise
```

Level guide:

- `log.warning` for expected business-rule violations surfacing at the infra layer (uniqueness, FK).
- `log.error` for unexpected failures (network timeouts, third-party 5xx, malformed data).

**Do not log the resulting domain exception** — the entrypoint logs it. Logging at both layers produces duplicate entries.

#### `application/` — log on success only

Handlers log a structured business event **after** `execute()` completes successfully. Use `log.info` with a `snake_case` event name as the first positional argument:

```python
log.info(
    "foo_created",
    foo_id=str(foo.id),
    caller_id=str(cmd.caller_id),
)
```

Event-name convention: `<resource>_<past_tense_verb>` — `foo_created`, `bar_archived`, `foos_imported`, `foo_renamed`. Stable strings; **don't rename once shipped** (downstream dashboards/alerts key on them).

Required fields (when applicable):

- Primary resource id: `<resource>_id` (e.g. `foo_id`).
- Actor: `caller_id` (always for commands). `role` when role-rank is load-bearing.
- For bulk operations: counts (`imported`, `skipped`, `errors`).

**Do not log errors in handlers.** Domain exceptions propagate up; the central error handler in the entrypoint logs them. Logging in both places duplicates entries.

The one sanctioned `try/except` in `application/` (compensating transactions, see `pattern-compensating-tx`) is **not** an exception to this rule — the catch undoes a side effect and re-raises. **No log call inside the `except`.**

#### Entrypoints (`restapi/`, `cli/`, `worker/`) — log errors at the point of handling

The central error handler is the **only** place that logs error events. It receives the propagated `DomainError`, logs it once with the request context, and translates to the HTTP/CLI response.

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

Level guide:

- `log.warning` for 4xx-class errors (`ValidationError`, `ConflictError`, `NotFoundError`, `UnauthorizedError`).
- `log.error` for 5xx-class (unexpected internal errors that escaped the domain-exception protocol).

Unhandled exceptions (anything that isn't a `DomainError`) also log here, at `error` level, before the framework converts them to a 500.

### Hard stops

- `log.x(...); raise` in the same scope → stop, logging and re-raising in the same scope produces two entries for one event. The single sanctioned use is in `infrastructure/` translating a low-level exception to a domain one — even there, only the *low-level* detail is logged; the domain exception itself is logged later by the entrypoint.
- Any log call in `domain/` → stop, zero IO includes the log socket.
- `log.error(...)` or `log.warning(...)` in `application/` → stop, application handlers log successes only; errors are the entrypoint's job.
- A handler catches an exception just to log it → stop, the catch must do something else (compensation, re-raising different shape); logging belongs at the entrypoint.
- An infrastructure adapter logs the domain exception it just raised → stop, the entrypoint logs it; remove the duplicate.
- `print()` anywhere outside the entrypoint debug paths that ship behind a flag → stop, use `structlog`.
- `import logging` (stdlib logger) or `logging.getLogger(...)` → stop, `structlog.get_logger()` everywhere.
- `event` name not snake_case past tense (`FooCreated`, `create-foo`) → stop, rename to `foo_created`. Once shipped, never rename — dashboards depend on the string.
- Logging a `UUID` object instead of `str(uuid_value)` → stop, some log sinks render `UUID(...)` poorly.
- Logging a full request or response body → stop, log identifiers and counts only. Bodies may contain PII or secrets.
- Binding sensitive fields (passwords, bearer tokens, API keys) → stop, log a length or a hash instead, never the value.
