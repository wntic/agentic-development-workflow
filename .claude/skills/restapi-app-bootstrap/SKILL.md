---
name: restapi-app-bootstrap
description: Apply once per project to bootstrap the FastAPI entrypoint. Produces four always-on files — `restapi/main.py`, `restapi/error_handler.py`, `restapi/schemas/errors.py`, `restapi/schemas/__init__.py` — plus `restapi/dependencies.py` when the app declares auth — that file is FastAPI's home for shared route dependencies, and today the auth pair (`get_current_user`/`require_role`) is its only content, so an auth-less app has none for now (auth-presence is derived from the graph: any endpoint with `auth != anonymous` / a token-verifier capability), and the error handler's auth branch is likewise dropped. Registers the DI container, lifespan hooks, the central `DomainError` handler, and CORS. Application middleware (request-size caps, request-id logging, …) is NOT bootstrapped here — it is declared per app (the `restapi.middlewares` manifest section) and produced by `restapi-middleware`. Does not produce any router or per-resource schema — those come from `restapi-endpoint` and `restapi-schema`, which land their work inside the shell this skill creates (an `app.include_router(...)` into its `main.py`) — so the shell is their structural precondition.
---

# REST API App Bootstrap

One-shot per project. Creates the FastAPI app skeleton so subsequent skills (`restapi-endpoint`, `restapi-schema`, `restapi-error-responses`, etc.) have somewhere to land their work. After bootstrap, the only file this skill ever touches again is `restapi/main.py` (when a router needs to be registered or a CORS-exposed header added), and that's normally folded into the consuming skill.

**Auth is conditional, not presumed.** Authentication is a manifest-declared feature (derived from the graph: an app has auth when some endpoint declares `auth != anonymous`, or a token-verifier capability is wired). The auth machinery this skill can emit — the auth dependencies in `restapi/dependencies.py` (`get_current_user` / `require_role`) and the `UnauthorizedError` branch of `error_handler.py` — is produced **only** for an app that declares auth. `dependencies.py` is FastAPI's home for shared route dependencies, but the auth pair is its only current occupant, so an auth-less app (e.g. an all-anonymous API) has **no** `dependencies.py` today and a bare `DomainError` translator with no auth import or branch. (A non-auth shared route dependency, if one is ever introduced, lives in the same file independent of auth.) Each affected file below shows the authed form and, where they differ, the public (auth-less) variant.

## When to use vs. neighbours

- First-time FastAPI scaffold for the project → this skill.
- A new router added afterwards → `restapi-endpoint` (which also `app.include_router(...)`s itself).
- A new domain exception is plumbed → `domain-exception` (creates/extends `domain/exceptions.py`). The catalog used by `error_responses(...)` derives from `domain.exceptions.__all__` automatically.
- A new middleware needs a new HTTP status registered → `restapi-error-responses` middleware-code path.

**This is the app shell; per-resource work lands inside it.** Produced once per project. `restapi-endpoint` and `restapi-schema` add their routers and schema modules into the `main.py` / `schemas/` this skill creates, and `restapi-error-responses` / `restapi-file-transfer` extend routes the shell hosts — so the shell must already exist when they run. That is a structural precondition (the artifacts depend on the shell), not a fixed run-schedule this skill dictates. **Application middleware is not part of this bootstrap** — it is declared per app (the `restapi.middlewares` manifest section) and produced by `restapi-middleware`. This skill presumes **none** (no request-size cap, no request-id); `main.py` leaves a placeholder where declared middlewares are wired in manifest order.

## Template(s)

```
src/<root>/restapi/
├── __init__.py
├── main.py
├── error_handler.py
├── dependencies.py          # shared route deps; today only the auth pair → emitted only when the app has auth
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
    # Teardown disposes the long-lived resources the container actually owns,
    # derived from the graph's datastores. An app whose datastores open no
    # disposable client (or none at all) has an empty teardown — there is no
    # provider to call here. The relational variant below disposes the
    # SQLAlchemy engine; a client-store app disposes its store clients instead.

def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container()

    app = FastAPI(title="Foo Service", lifespan=_lifespan)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        # Allowed origins are deployment config, not a code constant — set them from
        # the app's settings/env. Empty default = no cross-origin until configured;
        # never bake a dev origin like "http://localhost:3000".
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Empty by default. A route that needs the browser to read a non-default
        # response header adds it here — e.g. a file-download route adds
        # "Content-Disposition" (see restapi-file-transfer). Don't pre-list it.
        expose_headers=[],
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

#### `restapi/main.py` — relational teardown variant (app has a `uses_bootstrap` store)

When a relational (`uses_bootstrap`) store backs a repository, the container exposes an `engine()` provider whose connection pool must be disposed. The `_lifespan` teardown then disposes it (and any client-store clients the graph also wired); the body after `yield` becomes:

```python
    yield
    await container.engine().dispose()
```

This line is emitted **only** for an app whose graph carries a relational store — an app with no `engine()` provider (qdrant/redis-only) would `AttributeError` on it, so its teardown stays empty (or disposes only the clients its datastores opened).

Notes:

- **`lifespan` is the resource-teardown hook.** Disposal of long-lived clients happens here, not via `providers.Resource` in the container. Dispose what the container actually owns — derived from the graph's datastores — not a fixed engine: the relational variant above disposes the SQLAlchemy connection pool, a client-style app (qdrant/redis/…) disposes those clients, and an app that opens no disposable client has an empty teardown.
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

The translator stays minimal forever. New domain exceptions plug in without touching this file — they inherit `code`/`http_status`/`__init__` from `DomainError` and the handler dispatches on those. The block above is the **authenticated** variant: the only `isinstance` branch is the RFC-7235-mandated `WWW-Authenticate` header for `UnauthorizedError`, and that import + branch exist only because the app declares auth (`UnauthorizedError` is a manifest-declared exception that an auth-less app does not have).

#### `error_handler.py` — public variant (app declares no auth)

When the app declares no auth, there is no `UnauthorizedError` class: drop its import and the `isinstance` branch. The translator is the bare `DomainError` dispatcher:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from myapp.domain.exceptions import DomainError

from .schemas.errors import ErrorResponse

__all__ = ["register_error_handlers"]

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                code=exc.code,
                message=str(exc),
                context=exc.context,
            ).model_dump(),
        )
```

### `restapi/dependencies.py` (the auth dependencies — when the app declares auth)

`dependencies.py` is FastAPI's home for shared route dependencies; in this catalog its only current content is the auth pair, so today the file is emitted **only** for an app that declares auth. An auth-less app (every endpoint `anonymous`, no token-verifier capability) has no `get_current_user`/`require_role`, no `CurrentUser`/`Role` import, and routes attach no auth dependency (see `restapi-auth-dependency`) — hence no `dependencies.py`. Emit the file below when the graph carries auth (a non-auth shared route dependency, if ever added, would belong here too, independent of auth):

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

This file is the **single source of truth** for the error wire-shape, the `error_responses(...)` helper, the `_DESCR` map, and `MIDDLEWARE_ERRORS`. `restapi-error-responses` only *references* it and appends to `MIDDLEWARE_ERRORS` on the rare middleware-code path — it never restates this template (the two copies once drifted; do not reintroduce a second copy).

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
4. **Resource teardown lives in `lifespan`**, not in the container. The container builds the long-lived resources; `main.py`'s lifespan disposes whatever the graph's datastores actually opened — the relational engine when one exists, store clients otherwise, nothing when none are disposable. Never a hardcoded `engine().dispose()` in an app that has no engine provider.
5. **DI access is uniform:** `request.app.state.container.<name>()`. Never module-level resolution, never `@inject` decorators on routes.

## Hard stops

- The spec asks to add `domain/error_catalog.py` → stop, the catalog is dynamic; reject as obsolete.
- The spec asks to attach business logic to lifespan → stop, lifespan handles infrastructure teardown only (disposing the resources the graph's datastores opened).
- The spec asks the translator to branch on more than `UnauthorizedError` → stop, encode new behavior via subclass `code`/`http_status` instead.
- `domain/exceptions.py` does not exist yet → stop, run `domain-exception` bootstrap first.
- `<root>/containers.py` does not exist yet → stop, run `infra-di-provider` first.
