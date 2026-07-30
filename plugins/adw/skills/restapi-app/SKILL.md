---
name: restapi-app
description: The FastAPI entrypoint shell and the middleware that wraps it — `main.py`, `error_handler.py`, `schemas/errors.py`, `schemas/__init__.py`, plus `dependencies.py` when the app has auth; the DI container, lifespan teardown, CORS and the central `DomainError` handler; and one raw ASGI middleware class per cross-cutting per-request concern.
when_to_use: Laying the FastAPI entrypoint for a project, changing the app shell or the central error handler or the lifespan teardown, or adding cross-cutting per-request handling that wraps every route.
paths: src/**/restapi/**
---

# REST App

The shell every route lands inside, and the middleware layers that wrap it. The shell is laid once per project so subsequent work (`restapi-endpoint`, `restapi-schema`, `restapi-route-contracts`) has somewhere to go; a middleware is added whenever a cross-cutting per-request concern appears. After bootstrap, the only file this skill ever touches again is `restapi/main.py` (when a router needs to be registered or a CORS-exposed header added), and that's normally folded into the consuming skill.

**Auth is conditional, not presumed.** An app has auth when some endpoint is non-anonymous, or a token-verifier capability is wired — there is no separate flag for it. The auth machinery this skill can emit — the auth dependencies in `restapi/dependencies.py` (`get_current_user` / `require_role`) and the `UnauthorizedError` branch of `error_handler.py` — is produced **only** for an app that declares auth. `dependencies.py` is FastAPI's home for shared route dependencies, but the auth pair is its only current occupant, so an auth-less app (e.g. an all-anonymous API) has **no** `dependencies.py` today and a bare `DomainError` translator with no auth import or branch. (A non-auth shared route dependency, if one is ever introduced, lives in the same file independent of auth.) Each affected file below shows the authed form and, where they differ, the public (auth-less) variant.

## When to use vs. neighbours

- Laying the FastAPI entrypoint for the first time → this skill.
- A new router added afterwards → `restapi-endpoint` (which also `app.include_router(...)`s itself).
- A new domain exception is plumbed → `domain-exception` (creates/extends `domain/exceptions.py`). The catalog used by `error_responses(...)` derives from `domain.exceptions.__all__` automatically.
- A middleware introducing a new HTTP status that needs registering → `restapi-route-contracts`, the middleware-code path.
- Logic for **one** route → `restapi-endpoint`, a thin route over an application handler.
- Authenticating or authorizing a route → `restapi-route-contracts`; that is a FastAPI dependency, **not** a middleware.

**This is the app shell; per-resource work lands inside it.** Produced once per project. `restapi-endpoint` and `restapi-schema` add their routers and schema modules into the `main.py` / `schemas/` this skill creates, and `restapi-route-contracts` / `restapi-file-transfer` extend routes the shell hosts — so the shell must already exist when they run. That is a structural precondition (the artifacts depend on the shell), not a fixed run-schedule this skill dictates. **The shell presumes no middleware** — no request-size cap, no request id. `main.py` leaves a placeholder where they are wired in, after CORS, and the middleware section below is the form each one takes.

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
    # An app whose datastores open no
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

    # Custom application middlewares are added here, AFTER CORS. Starlette wraps the last-added outermost, so the last middleware
    # listed is the request's outermost layer; CORS (added above) sits innermost.
    # None are presumed — not even a request-size cap.

    register_error_handlers(app)

    # Routers added by restapi-endpoint:
    # from .routers.foos import router as foos_router
    # app.include_router(foos_router)

    return app
```

#### `restapi/main.py` — relational teardown variant (the app has a relational store)

When a relational store backs a repository, the container exposes an `engine()` provider whose connection pool must be disposed. The `_lifespan` teardown then disposes it, along with any client-store clients the app also wired; the body after `yield` becomes:

```python
    yield
    await container.engine().dispose()
```

This line belongs **only** to an app with a relational store — an app with no `engine()` provider (qdrant/redis-only) would `AttributeError` on it, so its teardown stays empty (or disposes only the clients its datastores opened).

Notes:

- **`lifespan` is the resource-teardown hook.** Disposal of long-lived clients happens here, not via `providers.Resource` in the container. Dispose what the container actually owns — whichever datastores the app opened — not a fixed engine: the relational variant above disposes the SQLAlchemy connection pool, a client-style app (qdrant/redis/…) disposes those clients, and an app that opens no disposable client has an empty teardown.
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
            # The `Bearer` scheme is the load-bearing part (RFC 7235); the realm is
            # app-specific — drive it from settings/env or omit it, never freeze a
            # literal realm (see test-discovery-invariants, which asserts only the scheme).
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

The translator stays minimal forever. New domain exceptions plug in without touching this file — they inherit `code`/`http_status`/`__init__` from `DomainError` and the handler dispatches on those. The block above is the **authenticated** variant: the only `isinstance` branch is the RFC-7235-mandated `WWW-Authenticate` header for `UnauthorizedError`, and that import + branch exist only because the app has auth — an auth-less app has no `UnauthorizedError` in its catalog.

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

class _RoleDependency:
    """A role-gated route dependency. A callable CLASS, not a closure, so the gated role is a
    TYPED attribute (`required_role`) rather than a `# type: ignore`-stashed function attribute —
    test-discovery-invariants detects a role-gated route by reading `required_role` off the
    dependency (see restapi-auth-dependency). FastAPI inspects `__call__` like any callable."""

    def __init__(self, required: Role) -> None:
        self.required_role = required

    def __call__(self, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.role.satisfies(self.required_role):
            raise ForbiddenError(
                "Insufficient role",
                {"required": self.required_role.value, "actual": user.role.value},
            )
        return user

def require_role(required: Role) -> _RoleDependency:
    return _RoleDependency(required)
```

The bearer scheme is declared **once** at module level. `get_current_user` resolves the verifier via the DI container — never instantiate verifiers in routes or dependencies. `require_role` returns a `_RoleDependency` instance — a callable class so the gated role rides as a typed attribute (no inline `# type: ignore`, `conventions` block E). See `restapi-auth-dependency` for how routes consume these.

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

## Middleware

One ASGI middleware per file under `restapi/middleware/<snake>.py`, named `<Name>Middleware`, handling a
cross-cutting request/response concern that belongs to no single route — a correlation id, a body-size
cap, rate limiting, timing. That list is open, not a fixed catalog.

Two shapes, picked by whether the middleware ever stops a request. Both share the same skeleton — the
non-`http` passthrough, `app` plus config on `self` — and differ only in whether `__call__` grows a reject
branch.

### Middleware — pass-through (observes or annotates, never short-circuits)

```python
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

__all__ = ["RequestIdMiddleware"]


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header: str) -> None:
        self._app = app
        self._header = header.lower().encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(self._header, b"").decode()
        request_id = incoming or str(uuid.uuid4())
        bind_contextvars(request_id=request_id)
        try:
            await self._app(scope, receive, send)
        finally:
            clear_contextvars()
```

### Middleware — short-circuit with an error (rejects before the route runs)

```python
from starlette.types import ASGIApp, Receive, Scope, Send

from ..schemas.errors import ErrorResponse

__all__ = ["MaxRequestSizeMiddleware"]

_PAYLOAD_TOO_LARGE = 413


class MaxRequestSizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and int(declared) > self._max_bytes:
            await _send_error(send, _PAYLOAD_TOO_LARGE, "PAYLOAD_TOO_LARGE", "Request body too large")
            return
        await self._app(scope, receive, send)


async def _send_error(send: Send, status: int, code: str, message: str) -> None:
    body = ErrorResponse(code=code, message=message).model_dump_json().encode()
    await send(
        {"type": "http.response.start", "status": status,
         "headers": [(b"content-type", b"application/json")]}
    )
    await send({"type": "http.response.body", "body": body})
```

The cap reads the **declared** `Content-Length` and rejects before the body is read, so nothing is
buffered. It does not catch a chunked upload that omits the header, or a client that lies about its
length; that absolute byte ceiling is an **edge** concern — a reverse proxy's `client_max_body_size` —
and this middleware is the app-layer defence in depth on top of it.

## Rules

1. **One-shot.** This skill runs once per project. After bootstrap, this file set is stable; updates to `main.py` go through whichever skill needs them (typically `restapi-endpoint` appending an `include_router(...)` line).
2. **The catalog is dynamic.** Never reintroduce `domain/error_catalog.py`. The registry derives from `domain.exceptions.__all__` at import time.
3. **The translator stays minimal.** `restapi/error_handler.py` has exactly one `isinstance` branch (`UnauthorizedError` → `WWW-Authenticate`). All other behavior comes from the `DomainError` subclass's `code` / `http_status`.
4. **Resource teardown lives in `lifespan`**, not in the container. The container builds the long-lived resources; `main.py`'s lifespan disposes whatever the app's datastores actually opened — the relational engine when one exists, store clients otherwise, nothing when none are disposable. Never a hardcoded `engine().dispose()` in an app that has no engine provider.
5. **DI access is uniform:** `request.app.state.container.<name>()`. Never module-level resolution, never `@inject` decorators on routes.

6. **One class per file**, named `<Name>Middleware`, under `restapi/middleware/`. It is a **raw ASGI
   callable**, never a `starlette.middleware.base.BaseHTTPMiddleware` subclass — that buffers the whole
   body and breaks streaming and the size cap.
7. **Exact ASGI shape.** `__init__(self, app: ASGIApp, <config…>)` stores `app` plus the config on `self`;
   `async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None`. Configuration arrives
   as constructor keyword arguments, passed at `app.add_middleware(Cls, **config)`, and the constructor
   validates them at wiring time so a bad value fails on startup rather than mid-request.
8. **Pass non-`http` scopes straight through** —
   `if scope["type"] != "http": await self._app(scope, receive, send); return`. Lifespan and websocket
   scopes must not be intercepted.
9. **A middleware that rejects a request emits an `ErrorResponse`-shaped JSON body** —
   `{"code": "<STABLE_STRING>", "message": "…", "context": {}}` — with the status it owns, and `return`s
   **before** `await self._app(...)`. A pass-through always reaches that call. Keep the code string
   stable: the API contract and `MIDDLEWARE_ERRORS` in `schemas/errors.py` key on it
   (`restapi-route-contracts`).
10. **No business or domain logic.** A middleware is transport-level — bytes, headers, timing, the
    structlog context. Anything needing a domain entity, a repository or an application handler is not a
    middleware.
11. **`self` holds only `app` plus config**, built once at wiring time. Any per-request value is a local
    inside `__call__` — the request id, the declared content length — never an instance attribute.
12. **Ordering is significant: Starlette wraps the last-added outermost.** Each `app.add_middleware(...)`
    call wraps the app as a new **outermost** layer, so the **last** one added is the first to see a
    request and the last to touch a response. A middleware that must see the raw request before anything
    else — a size cap — is therefore added **last**. The relative order is the consuming app's decision.

## Inlined typing / import rules

- Middleware: ASGI types from `starlette.types` (`ASGIApp`, `Scope`, `Receive`, `Send`; add `Message` only
  when `__call__` wraps `receive` / `send`). A middleware that rejects emits its body through the shared
  `ErrorResponse` schema (`from ..schemas.errors import ErrorResponse`) — never hand-roll the
  `{"code", "message", "context"}` dict, so the wire shape stays single-sourced. When it logs,
  `import structlog` and the `structlog.contextvars` helpers at module top (`python-style`).
- `X | None` over `Optional[X]`, full annotations on every signature, no
  `from __future__ import annotations`.

## Package wiring

`restapi/__init__.py` stays empty — the entrypoint package re-exports nothing. `restapi/middleware/__init__.py`
**does** re-export its classes (`from .max_request_size import *`, …), so `main.py` can import them
through the collapsed package form. Mechanics and the reason for the asymmetry: `architecture`,
carve-out 2.

## Hard stops

- The spec asks to add `domain/error_catalog.py` → stop, the catalog is dynamic; reject as obsolete.
- Asked to attach business logic to lifespan → stop, lifespan handles infrastructure teardown only: disposing the resources the app's datastores opened.
- The spec asks the translator to branch on more than `UnauthorizedError` → stop, encode new behavior via subclass `code`/`http_status` instead.
- `domain/exceptions.py` does not exist yet → stop, run `domain-exception` bootstrap first.
- `<root>/containers.py` does not exist yet → stop, `infra-wiring` first.
- A concern is for one route rather than all → stop, use `restapi-endpoint` plus a handler.
- A middleware needs a domain entity, a repository or an application handler → stop, that is application
  logic.
- A middleware authenticates or authorizes → stop, that is a route dependency (`restapi-route-contracts`).
- Reaching for `BaseHTTPMiddleware` → stop, use the raw ASGI class; `BaseHTTPMiddleware` buffers the body
  and breaks the size cap and streaming downloads.
- A middleware introduces an HTTP status with no domain exception behind it → stop, register the code via
  `restapi-route-contracts`, the middleware-code path.
