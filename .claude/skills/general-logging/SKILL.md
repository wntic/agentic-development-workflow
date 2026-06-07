---
name: general-logging
description: Apply when adding or modifying any log call anywhere in the codebase. Defines the `structlog` setup, the per-layer rules (where to log, what to log, what NOT to log), the snake_case `event` naming convention for application-layer success logs, and the "never log and re-raise" rule that prevents duplicate entries. Cross-cutting — referenced by `application-command`, `infra-sqlalchemy-repository`, `restapi-error-responses`.
---

# Logging

Use `structlog` throughout. The setup is the same everywhere; the rules about *when* to log differ per layer, and getting them wrong produces either silent failures or duplicate entries for the same event.

## When to use vs. neighbours

- Adding or modifying any log call anywhere in the codebase → consult this skill.
- The `application/` success-event log line → this skill, plus `application-command` (which embeds the per-handler `logger.info(...)` template).
- The `infrastructure/` `IntegrityError` → domain exception log + raise pattern → this skill, plus `infra-sqlalchemy-repository`.
- The central `DomainError` → JSON translation log → this skill, plus `restapi-error-responses` / `restapi-app-bootstrap`.

## Setup

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

## Per-layer rules

The rules describe **what each layer logs and what each layer must NOT log**. The combination is what produces a single coherent log entry per event with no duplicates.

### `domain/` — never log

Domain has zero IO. That includes logging. If a domain function "needs" to log, the rule belongs on the entity (raised as an exception with `context`) and the entrypoint logs it.

### `infrastructure/` — log low-level failures, then re-raise

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

### `application/` — log on success only

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

### Entrypoints (`restapi/`, `cli/`, `worker/`) — log errors at the point of handling

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

## Hard stops

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
