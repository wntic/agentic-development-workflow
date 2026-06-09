---
name: restapi-middleware
description: Apply when a request needs cross-cutting handling that wraps every route rather than living in one — a correlation/request id bound into logs, a request-body size cap, rate limiting, timing. Produces one raw ASGI middleware class under `restapi/middleware/<snake>.py` (`__init__(self, app, …)` + `async def __call__(self, scope, receive, send)`), wired once via `app.add_middleware(...)`. A middleware that rejects a request emits an `ErrorResponse`-shaped JSON body with a stable code string. Does not produce the app shell (use `restapi-app-bootstrap`), a per-route concern (use `restapi-endpoint`), or auth (use `restapi-auth-dependency`).
---

# REST API Middleware

Produces one ASGI middleware — a class that wraps the whole app to handle **any** cross-cutting request/response concern that belongs to no single route (correlation ids, a body-size cap, rate limiting, timing — an open list, not a fixed catalog). One class per file under `restapi/middleware/<snake>.py`, named `<Name>Middleware`.

## When to use vs. neighbours

- A concern that wraps **every** request (correlation id, size cap, rate limit, timing) → this skill.
- The app shell — CORS, the central `DomainError` handler, lifespan → `restapi-app-bootstrap`.
- Logic for **one** route → `restapi-endpoint` (a thin route over an application handler).
- Authenticating / authorizing a route → `restapi-auth-dependency` (a FastAPI dependency, **not** a middleware).
- Advertising an HTTP code a route can return → `restapi-error-responses`.

## Template(s)

Two shapes, picked by whether the middleware ever stops a request — one template per shape. Both share
the same skeleton (non-`http` passthrough, `app` + config on `self`); they differ only in whether
`__call__` grows a reject branch. The concerns shown are illustrations, not a fixed catalog.

### Pass-through — observes/annotates, never short-circuits (e.g. a correlation id)

```python
import uuid

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

### Short-circuit with an error — rejects before the route runs (e.g. a request-size cap)

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

The cap reads the **declared** `Content-Length` and rejects before the body is read — nothing is
buffered. It does not catch a chunked upload that omits the header or a client that lies about its
length; that absolute byte ceiling is an **edge** concern (a reverse proxy's `client_max_body_size`),
and this middleware is the app-layer defense-in-depth on top of it.

## Rules

1. **One class per file**, named `<Name>Middleware`, under `restapi/middleware/`. It is a **raw ASGI callable**, not a `starlette.middleware.base.BaseHTTPMiddleware` subclass (that buffers the whole body and breaks streaming + the size cap).
2. **Exact ASGI shape.** `__init__(self, app: ASGIApp, <config…>)` stores `app` + the config on `self`; `async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None`. Configuration arrives as constructor keyword arguments — passed at `app.add_middleware(Cls, **config)` — and the constructor validates them at wiring time (a bad value fails fast on startup, not mid-request).
3. **Pass non-`http` scopes straight through** — `if scope["type"] != "http": await self._app(scope, receive, send); return`. Lifespan and websocket scopes must not be intercepted.
4. **A middleware that REJECTS a request emits an `ErrorResponse`-shaped JSON body** — `{"code": "<STABLE_STRING>", "message": "...", "context": {}}` — with the HTTP status it owns, and `return`s **before** `await self._app(...)`; a pass-through, by contrast, always reaches the call. Keep the code string stable: the API contract and `restapi/schemas/errors.py`'s `MIDDLEWARE_ERRORS` key on it (see `restapi-error-responses`).
5. **No business/domain logic.** A middleware is transport-level — bytes, headers, timing, the structlog context. Anything needing a domain entity, a repository, or an application handler is not a middleware.
6. **`self` holds only `app` + config** (built once, at wiring time). Any per-request value is a local inside `__call__` (e.g. the request id, the declared content length), never an instance attribute.
7. **Ordering is significant — Starlette wraps the last-added outermost.** Each `app.add_middleware(...)` call wraps the app as a new **outermost** layer, so the **last** middleware added is the first to see a request and the last to touch a response. A middleware that must see the raw request before anything else (a size cap) is therefore added **last**. The relative order is the consuming app's wiring decision.

## Inlined typing / import rules

- ASGI types from `starlette.types` (`ASGIApp`, `Scope`, `Receive`, `Send`; add `Message` only if a `__call__` wraps `receive`/`send`). `X | None` over `Optional[X]`; full annotations on `__init__` and `__call__`. No `from __future__ import annotations`.
- A middleware that rejects emits its body through the shared `ErrorResponse` schema (`from ..schemas.errors import ErrorResponse`) — never hand-roll the `{"code", "message", "context"}` dict, so the wire shape stays single-sourced.
- When the middleware logs, `import structlog` (+ `structlog.contextvars` helpers) at module top — see `general-logging`.

## Package wiring

Register the module in `restapi/middleware/__init__.py` per `general-python-package`.

## Hard stops

- The concern is for one route, not all → stop, use `restapi-endpoint` + a handler.
- It needs a domain entity / repository / application handler → stop, that's application logic, not a middleware.
- It authenticates or authorizes a request → stop, use `restapi-auth-dependency` (a FastAPI dependency on the route).
- You reach for `BaseHTTPMiddleware` → stop, use the raw ASGI class (BaseHTTPMiddleware buffers the body, breaking the size cap and streaming downloads).
- The middleware introduces an HTTP status with no domain exception behind it → stop, register the code via `restapi-error-responses` (the middleware-code path).
