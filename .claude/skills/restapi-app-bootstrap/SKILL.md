---
name: restapi-app-bootstrap
description: Apply once per project to bootstrap the FastAPI entrypoint. Produces five files — `restapi/main.py`, `restapi/error_handler.py`, `restapi/dependencies.py`, `restapi/schemas/errors.py`, `restapi/schemas/__init__.py` — and registers the DI container, lifespan hooks, the central `DomainError` handler, and CORS. Application middleware (request-size caps, request-id logging, …) is NOT bootstrapped here — it is declared per app (the `restapi.middlewares` manifest section) and produced by `restapi-middleware`. Does not produce any router or per-resource schema — those come from `restapi-endpoint` and `restapi-schema`. Run this skill first, then per-resource skills can land their endpoints in `app.include_router(...)`.
---

# REST API App Bootstrap

One-shot per project. Creates the FastAPI app skeleton so subsequent skills (`restapi-endpoint`, `restapi-schema`, `restapi-error-responses`, etc.) have somewhere to land their work. After bootstrap, the only file this skill ever touches again is `restapi/main.py` (when a router needs to be registered or a CORS-exposed header added), and that's normally folded into the consuming skill.

## When to use vs. neighbours

- First-time FastAPI scaffold for the project → this skill.
- A new router added afterwards → `restapi-endpoint` (which also `app.include_router(...)`s itself).
- A new domain exception is plumbed → `domain-exception` (creates/extends `domain/exceptions.py`). The catalog used by `error_responses(...)` derives from `domain.exceptions.__all__` automatically.
- A new middleware needs a new HTTP status registered → `restapi-error-responses` middleware-code path.

**Catalog ordering.** This skill runs once, early. The expected sequence is: `domain-exception` (bootstrap) → `infra-di-provider` (initial scaffold so `Container()` is importable) → **this skill** → `restapi-schema` (per-resource modules) → `restapi-endpoint` (per route) → `restapi-error-responses` and `restapi-file-transfer` as applicable. **Application middleware is not part of this bootstrap** — it is declared per app (the `restapi.middlewares` manifest section) and produced by `restapi-middleware`. This skill presumes **none** (no request-size cap, no request-id); `main.py` leaves a placeholder where declared middlewares are wired in manifest order.

## Template(s)

```
src/<root>/restapi/
├── __init__.py
├── main.py
├── error_handler.py
├── dependencies.py
└── schemas/
    ├── __init__.py
    └── errors.py
```

### `restapi/main.py`

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from myapp.containers import Container

from .error_handler import register_error_handlers

__all__ = ["create_app"]

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: Container = app.state.container
    yield
    await container.engine().dispose()

def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container()

    app = FastAPI(title="Foo Service", lifespan=_lifespan)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    # Application middlewares (from the manifest) are added here, in manifest order,
    # AFTER CORS. Starlette wraps the last-added outermost, so the last middleware
    # listed is the request's outermost layer; CORS (added above) sits innermost.
    # None are presumed — not even a request-size cap.

    register_error_handlers(app)

    # Routers added by restapi-endpoint:
    # from .routers.foos import router as foos_router
    # app.include_router(foos_router)

    return app
```

Notes:

- **`lifespan` is the engine teardown hook.** Connection-pool disposal happens here, not via `providers.Resource` in the container.
- **DI container attached to `app.state.container`** — routes resolve handlers via `request.app.state.container.<name>_handler()` (see `restapi-endpoint`).
- **The router-include block is a placeholder.** Subsequent `restapi-endpoint` invocations add their own `app.include_router(...)` line.

### `restapi/error_handler.py`

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from myapp.domain.exceptions import DomainError, UnauthorizedError

from .schemas.errors import ErrorResponse

__all__ = ["register_error_handlers"]

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers: dict[str, str] = {}
        if isinstance(exc, UnauthorizedError):
            headers["WWW-Authenticate"] = 'Bearer realm="myapp"'
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                code=exc.code,
                message=str(exc),
                context=exc.context,
            ).model_dump(),
            headers=headers or None,
        )
```

The translator stays minimal forever. New domain exceptions plug in without touching this file — they inherit `code`/`http_status`/`__init__` from `DomainError` and the handler dispatches on those. The only `isinstance` branch is the RFC-7235-mandated `WWW-Authenticate` header for `UnauthorizedError`.

### `restapi/dependencies.py`

```python
from collections.abc import Callable
from typing import cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from myapp.domain.auth import CurrentUser, Role
from myapp.domain.exceptions import ForbiddenError, UnauthorizedError

__all__ = ["get_current_user", "require_role"]

_bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing bearer token", {"reason": "missing_credentials"})
    verifier = request.app.state.container.jwt_verifier()
    # The DI container resolves untyped (`app.state` is `Any`) — cast at this boundary
    # so the function honours its `-> CurrentUser` contract under strict mypy.
    return cast(CurrentUser, verifier.verify(creds.credentials))

def require_role(required: Role) -> Callable[..., CurrentUser]:
    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.role.satisfies(required):
            raise ForbiddenError(
                "Insufficient role",
                {"required": required.value, "actual": user.role.value},
            )
        return user

    # Marker so test-discovery-invariants can detect role-gated routes via
    # introspecting the dependency tree without re-implementing FastAPI's
    # closure layout.
    _dep.__wrapped_role__ = required  # type: ignore[attr-defined]
    return _dep
```

The bearer scheme is declared **once** at module level. `get_current_user` resolves the verifier via the DI container — never instantiate verifiers in routes or dependencies. See `restapi-auth-dependency` for how routes consume these.

### `restapi/schemas/errors.py`

```python
from typing import Any

from pydantic import BaseModel, Field

from myapp.domain import exceptions as _domain_exceptions
from myapp.domain.exceptions import DomainError

__all__ = ["ErrorResponse", "MIDDLEWARE_ERRORS", "error_responses"]

class ErrorResponse(BaseModel):
    code: str
    message: str
    context: dict[str, object] = Field(default_factory=dict)

# Status codes emitted by middleware that have no DomainError class behind them.
# Empty by default — no middleware is presumed. The restapi-error-responses
# middleware-code path adds an entry when a declared middleware introduces a code
# (e.g. a size-cap middleware → PAYLOAD_TOO_LARGE 413).
MIDDLEWARE_ERRORS: dict[str, int] = {}

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
    domain_statuses: set[int] = set()
    for name in _domain_exceptions.__all__:
        cls = getattr(_domain_exceptions, name)
        if isinstance(cls, type) and issubclass(cls, DomainError):
            domain_statuses.add(cls.http_status)
    return domain_statuses | set(MIDDLEWARE_ERRORS.values())

def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    known = _all_known_statuses()
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValueError(
            f"HTTP statuses not produced by any DomainError or middleware: {unknown}"
        )
    # `dict[int | str, dict[str, Any]]` is exactly FastAPI's `responses=` parameter type —
    # a narrower `dict[str, object]` value trips a strict-mypy arg-type error at the decorator.
    out: dict[int | str, dict[str, Any]] = {
        c: {"model": ErrorResponse, "description": _DESCR.get(c, str(c))}
        for c in codes
    }
    return out
```

The domain-side registry is **derived dynamically** from `domain.exceptions.__all__`. Adding a new `DomainError` subclass automatically widens the allowed `error_responses(...)` codes — no manual append, no `domain/error_catalog.py` to maintain.

### `restapi/schemas/__init__.py`

```python
from . import errors
from .errors import *

__all__ = errors.__all__
```

Per-resource schema modules (e.g. `foos.py`) are added later by `restapi-schema`; each invocation appends a new `from . import <module>` + `from .<module> import *` line and extends the package `__all__`.

### `restapi/__init__.py`

```python
```

Empty file — `restapi/` is the entrypoint package and does not re-export anything.

## Rules

1. **One-shot.** This skill runs once per project. After bootstrap, this file set is stable; updates to `main.py` go through whichever skill needs them (typically `restapi-endpoint` appending an `include_router(...)` line).
2. **The catalog is dynamic.** Never reintroduce `domain/error_catalog.py`. The registry derives from `domain.exceptions.__all__` at import time.
3. **The translator stays minimal.** `restapi/error_handler.py` has exactly one `isinstance` branch (`UnauthorizedError` → `WWW-Authenticate`). All other behavior comes from the `DomainError` subclass's `code` / `http_status`.
4. **Engine teardown lives in `lifespan`**, not in the container. The container builds the engine; `main.py`'s lifespan disposes it.
5. **DI access is uniform:** `request.app.state.container.<name>()`. Never module-level resolution, never `@inject` decorators on routes.

## Hard stops

- The spec asks to add `domain/error_catalog.py` → stop, the catalog is dynamic; reject as obsolete.
- The spec asks to attach business logic to lifespan → stop, lifespan handles infrastructure teardown only (engine dispose).
- The spec asks the translator to branch on more than `UnauthorizedError` → stop, encode new behavior via subclass `code`/`http_status` instead.
- `domain/exceptions.py` does not exist yet → stop, run `domain-exception` bootstrap first.
- `<root>/containers.py` does not exist yet → stop, run `infra-di-provider` first.
