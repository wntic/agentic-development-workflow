---
name: restapi-error-responses
description: Apply when a route must advertise the HTTP error codes it can produce. Touches the route decorator (adding `responses=error_responses(...)`). In the rare case a middleware introduces a brand-new HTTP status code with no `DomainError` class behind it, also touches `restapi/schemas/errors.py` to register the middleware code. Does not produce the domain error class (use `domain-exception`) or the central translator at `restapi/error_handler.py` (created once by `restapi-app-bootstrap` and not modified afterwards).
---

# REST API Error Responses

The REST API has exactly one place that turns exceptions into HTTP responses: `register_error_handlers` in `restapi/error_handler.py`. Every `DomainError` carries `code: str` + `http_status: int` class attributes; the handler maps them to JSON via `ErrorResponse`. Routes do not catch — they only **advertise** which codes they can raise so OpenAPI documents the contract.

This skill produces two outputs depending on the input:

1. **Routine route work** — pass `responses=error_responses(<codes>)` on the route decorator. No new file.
2. **Middleware-introduced status code** — when a brand-new HTTP status comes from a middleware (no `DomainError` class behind it), register the code in `MIDDLEWARE_ERRORS` inside `restapi/schemas/errors.py`. Rare.

Domain exception classes themselves are registered automatically: `error_responses(...)` derives its allowed-code list from `domain.exceptions.__all__` at import time. Adding a new `DomainError` subclass (via `domain-exception`) is sufficient — no registry append needed.

## When to use vs. neighbours

- Adding `responses=error_responses(...)` on a new endpoint → this skill (routine path).
- Defining the new error class itself (the `class FooConflictError(ConflictError)` body in `domain/exceptions.py`) → `domain-exception`. After that runs, the new code is automatically valid for `error_responses(...)`.
- A middleware emits a status no domain class produces (e.g. 413 from `MaxRequestSizeMiddleware`) → this skill, middleware-code path.
- Producing a multipart-or-streaming route that needs the sanctioned `try/except` → `restapi-file-transfer`.
- First-time setup of `restapi/error_handler.py`, `restapi/schemas/errors.py`, etc. → `restapi-app-bootstrap`.

## Reference — the three components (do not modify the translator or the bootstrap files)

### 1. `restapi/schemas/errors.py` — wire shape + helper + middleware registry

```python
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from myapp.domain import exceptions as _domain_exceptions
from myapp.domain.exceptions import DomainError

__all__ = ["ErrorResponse", "error_responses", "MIDDLEWARE_ERRORS"]

class ErrorResponse(BaseModel):
    code: str
    message: str
    context: dict[str, object] = Field(default_factory=dict)

# Status codes emitted by middleware, with no DomainError class behind them.
MIDDLEWARE_ERRORS: dict[str, int] = {
    "PAYLOAD_TOO_LARGE": 413,
}

_DESCR: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    422: "Unprocessable entity",
}

def _all_known_statuses() -> set[int]:
    domain_statuses = {
        getattr(cls, "http_status")
        for name in _domain_exceptions.__all__
        if isinstance(cls := getattr(_domain_exceptions, name), type)
        and issubclass(cls, DomainError)
    }
    return domain_statuses | set(MIDDLEWARE_ERRORS.values())

def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    known = _all_known_statuses()
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValueError(f"HTTP statuses not produced by any DomainError or middleware: {unknown}")
    out: dict[int | str, dict[str, Any]] = {
        c: {"model": ErrorResponse, "description": _DESCR.get(c, str(c))} for c in codes
    }
    return out
```

The domain-side registry is derived dynamically from `domain.exceptions.__all__` — no manual list to maintain. Adding a new `DomainError` subclass automatically widens the allowed statuses on the next import.

### 2. `restapi/error_handler.py` — the translator (do not modify)

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from myapp.domain.exceptions import DomainError, UnauthorizedError

from .schemas.errors import ErrorResponse

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {}
        if isinstance(exc, UnauthorizedError):
            headers["WWW-Authenticate"] = 'Bearer realm="myapp"'
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(code=exc.code, message=str(exc), context=exc.context).model_dump(),
            headers=headers or None,
        )
```

One handler covers every `DomainError` subclass. New exceptions plug in automatically.

## Standard code sets per operation

| Operation | `error_responses(...)` |
|-----------|------------------------|
| Read (auth-only) | `401` |
| Read by id | `401, 404` |
| Create | `401, 403, 409` (+ `422` for input validation) |
| Update | `401, 403, 404, 409` (+ `422`) |
| Delete | `401, 403, 404, 409` (`409` covers in-use) |
| Reorder | `401, 403, 422` |
| Lookup / detect (read with input) | `401, 404, 422` |
| Multipart upload | add `413` to whichever set applies |

**List a code only if the route can actually produce it.** Don't list `403` on a public endpoint, don't list `409` on a read.

## Procedure — routine path (route only)

1. Choose the code set from the table above.
2. Add `responses=error_responses(<codes>)` to the route decorator.

That's it. The catalog is dynamic; no further registration needed.

## Procedure — middleware-code path

1. Confirm the status truly has no `DomainError` behind it (the body comes from middleware before the exception handler runs). Otherwise the right answer is `domain-exception`, not this path.
2. Append `("CODE_STRING", <http_status>)` to `MIDDLEWARE_ERRORS` in `restapi/schemas/errors.py`.
3. If the status is not in `_DESCR`, add a short description.
4. Have the middleware emit an `ErrorResponse`-shaped JSON body with the same `code` string.

## Rules

1. **Routes only advertise.** They never:
   - catch `DomainError` or any subclass.
   - inspect `exc.code` to map to status.
   - log errors (the central handler is the single logging point for failures).
   - return `JSONResponse` directly.
2. **`UnauthorizedError` and `WWW-Authenticate`.** The handler attaches `WWW-Authenticate: Bearer realm="myapp"` **only** for `UnauthorizedError` (401). Do not generalize. A new auth-related exception that needs the header must subclass `UnauthorizedError`, not extend the `isinstance` branch.
3. **Never manually construct `responses={401: {...}}` dicts.** Always go through `error_responses(...)` so the catalog stays authoritative.
4. **No `raise HTTPException(...)` anywhere.** Raise a domain exception so the body stays `ErrorResponse`-shaped and the code stays cataloged.
5. **`MIDDLEWARE_ERRORS` is the only manually-maintained registry.** Everything domain-side derives from `domain.exceptions.__all__`.

## Hard stops

- Spec asks to add branching logic in `restapi/error_handler.py` → stop, the translator stays minimal. New behavior is encoded via subclassing or via `http_status` / `code` on the new class.
- Spec asks a route to catch a domain exception and translate it → stop, that's the central handler's job.
- Spec lists an HTTP status that no `DomainError` subclass produces and is not in `MIDDLEWARE_ERRORS` → stop, define a `domain-exception` first or take the middleware-code path.
- Spec asks for `WWW-Authenticate` on a 403 → stop, that header is 401-specific by RFC 7235.
