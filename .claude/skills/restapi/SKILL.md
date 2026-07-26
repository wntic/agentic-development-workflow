---
name: restapi
description: "House style for the whole FastAPI REST layer: the one-shot app bootstrap shell (`main.py`, central `DomainError` handler, CORS, DI wiring), thin endpoints in `routers/`, Pydantic request/response schemas, the auth-dependency decision (`get_current_user` vs `require_role`), route-level error advertisement, multipart upload / streaming download, and custom middleware ordering."
when_to_use: "Producing or editing any REST-layer artifact: the app shell, an endpoint, a schema, the auth dependency, error responses, a file-transfer route, or a middleware."
---
# REST API

This merged skill covers 7 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from restapi-app-bootstrap -->

## REST API App Bootstrap

One-shot per project. Creates the FastAPI app skeleton so subsequent skills (`restapi-endpoint`, `restapi-schema`, `restapi-error-responses`, etc.) have somewhere to land their work. After bootstrap, the only file this skill ever touches again is `restapi/main.py` (when a router needs to be registered or a CORS-exposed header added), and that's normally folded into the consuming skill.

**Auth is conditional, not presumed.** Authentication is an app-declared feature (derived from the graph: an app has auth when some endpoint declares `auth != anonymous`, or a token-verifier capability is wired). The auth machinery this skill can emit — the auth dependencies in `restapi/dependencies.py` (`get_current_user` / `require_role`) and the `UnauthorizedError` branch of `error_handler.py` — is produced **only** for an app that declares auth. `dependencies.py` is FastAPI's home for shared route dependencies, but the auth pair is its only current occupant, so an auth-less app (e.g. an all-anonymous API) has **no** `dependencies.py` today and a bare `DomainError` translator with no auth import or branch. (A non-auth shared route dependency, if one is ever introduced, lives in the same file independent of auth.) Each affected file below shows the authed form and, where they differ, the public (auth-less) variant.

### When to use vs. neighbours

- First-time FastAPI scaffold for the project → this skill.
- A new router added afterwards → `restapi-endpoint` (which also `app.include_router(...)`s itself).
- A new domain exception is plumbed → `domain-exception` (creates/extends `domain/exceptions.py`). The catalog used by `error_responses(...)` derives from `domain.exceptions.__all__` automatically.
- A new middleware needs a new HTTP status registered → `restapi-error-responses` middleware-code path.

**This is the app shell; per-resource work lands inside it.** Produced once per project. `restapi-endpoint` and `restapi-schema` add their routers and schema modules into the `main.py` / `schemas/` this skill creates, and `restapi-error-responses` / `restapi-file-transfer` extend routes the shell hosts — so the shell must already exist when they run. That is a structural precondition (the artifacts depend on the shell), not a fixed run-schedule this skill dictates. **Application middleware is not part of this bootstrap** — it is declared per app and produced by `restapi-middleware`. This skill presumes **none** (no request-size cap, no request-id); `main.py` leaves a placeholder where declared middlewares are wired in declared order.

### Template(s)

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

#### `restapi/main.py`

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

    # Application middlewares (declared per app) are added here, in declared order,
    # AFTER CORS. Starlette wraps the last-added outermost, so the last middleware
    # listed is the request's outermost layer; CORS (added above) sits innermost.
    # None are presumed — not even a request-size cap.

    register_error_handlers(app)

    # Routers added by restapi-endpoint:
    # from .routers.foos import router as foos_router
    # app.include_router(foos_router)

    return app
```

##### `restapi/main.py` — relational teardown variant (app has a `uses_bootstrap` store)

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

#### `restapi/error_handler.py`

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

The translator stays minimal forever. New domain exceptions plug in without touching this file — they inherit `code`/`http_status`/`__init__` from `DomainError` and the handler dispatches on those. The block above is the **authenticated** variant: the only `isinstance` branch is the RFC-7235-mandated `WWW-Authenticate` header for `UnauthorizedError`, and that import + branch exist only because the app declares auth (`UnauthorizedError` is an app-declared exception that an auth-less app does not have).

##### `error_handler.py` — public variant (app declares no auth)

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

#### `restapi/dependencies.py` (the auth dependencies — when the app declares auth)

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

#### `restapi/schemas/errors.py`

```python
from typing import Any

from pydantic import BaseModel, Field

from myapp.domain import exceptions as _domain_exceptions
from myapp.domain.exceptions import DomainError

__all__ = ["MIDDLEWARE_ERRORS", "ErrorResponse", "error_responses"]

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

#### `restapi/schemas/__init__.py`

```python
from . import errors
from .errors import *  # noqa: F403

__all__ = errors.__all__
```

Per-resource schema modules (e.g. `foos.py`) are added later by `restapi-schema`; each invocation appends a new `from . import <module>` + `from .<module> import *  # noqa: F403` line and extends the package `__all__` (the wildcard re-export idiom and its `# noqa: F403` are `architecture`'s — see `general-python-package`).

#### `restapi/__init__.py`

```python
```

Empty file — `restapi/` is the entrypoint package and does not re-export anything.

### Rules

1. **One-shot.** This skill runs once per project. After bootstrap, this file set is stable; updates to `main.py` go through whichever skill needs them (typically `restapi-endpoint` appending an `include_router(...)` line).
2. **The catalog is dynamic.** Never reintroduce `domain/error_catalog.py`. The registry derives from `domain.exceptions.__all__` at import time.
3. **The translator stays minimal.** `restapi/error_handler.py` has exactly one `isinstance` branch (`UnauthorizedError` → `WWW-Authenticate`). All other behavior comes from the `DomainError` subclass's `code` / `http_status`.
4. **Resource teardown lives in `lifespan`**, not in the container. The container builds the long-lived resources; `main.py`'s lifespan disposes whatever the graph's datastores actually opened — the relational engine when one exists, store clients otherwise, nothing when none are disposable. Never a hardcoded `engine().dispose()` in an app that has no engine provider.
5. **DI access is uniform:** `request.app.state.container.<name>()`. Never module-level resolution, never `@inject` decorators on routes.

### Hard stops

- The spec asks to add `domain/error_catalog.py` → stop, the catalog is dynamic; reject as obsolete.
- The spec asks to attach business logic to lifespan → stop, lifespan handles infrastructure teardown only (disposing the resources the graph's datastores opened).
- The spec asks the translator to branch on more than `UnauthorizedError` → stop, encode new behavior via subclass `code`/`http_status` instead.
- `domain/exceptions.py` does not exist yet → stop, run `domain-exception` bootstrap first.
- `<root>/containers.py` does not exist yet → stop, run `infra-di-provider` first.


<!-- merged from restapi-endpoint -->

## REST API Endpoint

Produces one HTTP endpoint for one resource. Routers grow incrementally — this skill adds one route at a time. A "router file" exists once per resource; subsequent endpoint additions extend it.

### When to use vs. neighbours

- One new endpoint or modification of an existing one → this skill.
- Pydantic request/response schemas → `restapi-schema` (this skill consumes them).
- The auth dependency choice (`get_current_user` vs `require_role`) → `restapi-auth-dependency`.
- The `responses=error_responses(...)` declaration → `restapi-error-responses`.
- Multipart upload or streaming download → `restapi-file-transfer`.
- The `Container.<handler>()` provider this route resolves → `infra-di-provider`.

### File location

```
src/<root>/restapi/routers/<resource>.py
```

One router file per resource holds **all** of that resource's endpoint functions; the file declares the `APIRouter`, defines each endpoint function (ordered per Route ordering), and is registered once in `src/<root>/restapi/main.py` via `app.include_router(...)`. The skeleton below is the whole-file shape; an endpoint function is the per-route shape that follows it.

### Skeleton — router file

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from myapp.application.foos import (
    CreateFooCommand,
    CreateFooHandler,
    GetFooHandler,
    GetFooQuery,
    ListFoosHandler,
    ListFoosQuery,
)
from myapp.domain.auth import CurrentUser, Role
from myapp.domain.foos import FooListFilter

from ..dependencies import get_current_user, require_role
from ..schemas import (
    FooCreateRequest,
    FooListResponse,
    FooResponse,
    error_responses,
)

__all__ = ["router"]

router = APIRouter(prefix="/foos", tags=["foos"])
```

Rules:

- One module per resource. Snake_case file name.
- `__all__ = ["router"]` — only `router` is public.
- `prefix` is kebab-case and matches the file name's resource.
- `tags=[...]` echoes the resource word.
- **The auth imports are conditional.** `from myapp.domain.auth import CurrentUser, Role` and `from ..dependencies import get_current_user, require_role` appear **only** when the app declares auth (`restapi-auth-dependency`) and this resource has ≥1 authenticated route. An auth-less app — or a router whose every route is public — omits both imports entirely; importing them would reference a `domain/auth` module and a `dependencies.py` that an auth-less app does not have. See Auth variants below.

### Templates — one per `kind`

**The per-`kind` templates below show the AUTHENTICATED form** (an authed app, a gated route). Auth is app-declared (see `restapi-auth-dependency` — derived from the graph, no separate flag). When the route is **public** (`auth: anonymous`), or the whole app declares no auth, derive the public form by dropping four things and nothing else: the auth-dependency parameter, the `domain.auth` + `..dependencies` imports, the `401`/`403` codes in `error_responses(...)`, and the `caller_id=user.id` argument to the command/query. The two shapes side by side:

#### Authenticated vs public — the two shapes

Authenticated `create` (the form every per-`kind` template below uses):

```python
@router.post(
    "", response_model=FooResponse, status_code=201,
    responses=error_responses(401, 403, 409),
)
async def create_foo(
    body: FooCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    handler: CreateFooHandler = request.app.state.container.create_foo_handler()
    new_id = await handler.execute(CreateFooCommand(caller_id=user.id, name=body.name))
    ...  # read-back
```

Public `create` (route is `auth: anonymous`, or the app declares no auth) — no auth dep, no `domain.auth`/`..dependencies` import, no 401/403, no `caller_id`:

```python
@router.post(
    "", response_model=FooResponse, status_code=201,
    responses=error_responses(409),
)
async def create_foo(
    body: FooCreateRequest,
    request: Request,
) -> FooResponse:
    handler: CreateFooHandler = request.app.state.container.create_foo_handler()
    new_id = await handler.execute(CreateFooCommand(name=body.name))
    ...  # read-back
```

(A read — `list`/`get` — drops the same: the `_: CurrentUser = Depends(get_current_user)` line, the imports, and the `401`. The `caller_id` drop applies only where the command/query carried it.)

#### `list` (paginated read) — pagination shape mirrors `domain-filter`

Use the **`limit`/`offset`** template when the matching `domain-filter` declared `pagination: limit/offset`. Use the **`cursor`** template when it declared `pagination: cursor`. The two forms are mutually exclusive — never both.

`limit`/`offset`:

```python
@router.get("", response_model=FooListResponse, responses=error_responses(401))
async def list_foos(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: CurrentUser = Depends(get_current_user),
) -> FooListResponse:
    handler: ListFoosHandler = request.app.state.container.list_foos_handler()
    result = await handler.execute(
        ListFoosQuery(filter=FooListFilter(limit=limit, offset=offset)),
    )
    return FooListResponse(
        items=[FooResponse(...) for foo in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )
```

`cursor`:

```python
@router.get("", response_model=FooListResponse, responses=error_responses(401))
async def list_foos(
    request: Request,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    _: CurrentUser = Depends(get_current_user),
) -> FooListResponse:
    handler: ListFoosHandler = request.app.state.container.list_foos_handler()
    result = await handler.execute(
        ListFoosQuery(filter=FooListFilter(cursor=cursor, limit=limit)),
    )
    return FooListResponse(
        items=[FooResponse(...) for foo in result.items],
        next_cursor=result.next_cursor,
        limit=limit,
    )
```

The `restapi-schema`-produced `FooListResponse` must match the chosen pagination shape (either `total/limit/offset` or `next_cursor/limit`).

#### `get` (single read)

```python
@router.get("/{id}", response_model=FooResponse, responses=error_responses(401, 404))
async def get_foo(
    id: UUID,
    request: Request,
    _: CurrentUser = Depends(get_current_user),
) -> FooResponse:
    handler: GetFooHandler = request.app.state.container.get_foo_handler()
    foo = await handler.execute(GetFooQuery(id=id))
    return FooResponse(...)
```

#### `create` (with post-write read-back)

```python
@router.post(
    "",
    response_model=FooResponse,
    status_code=201,
    responses=error_responses(401, 403, 409),
)
async def create_foo(
    body: FooCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    handler: CreateFooHandler = request.app.state.container.create_foo_handler()
    new_id = await handler.execute(
        CreateFooCommand(caller_id=user.id, name=body.name),
    )
    get_handler: GetFooHandler = request.app.state.container.get_foo_handler()
    foo = await get_handler.execute(GetFooQuery(id=new_id))
    return FooResponse(...)
```

#### `update` (PATCH with read-back)

```python
@router.patch(
    "/{id}",
    response_model=FooResponse,
    responses=error_responses(401, 403, 404, 409),
)
async def update_foo(
    id: UUID,
    body: FooUpdateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    handler: UpdateFooHandler = request.app.state.container.update_foo_handler()
    await handler.execute(
        UpdateFooCommand(caller_id=user.id, id=id, name=body.name),
    )
    get_handler: GetFooHandler = request.app.state.container.get_foo_handler()
    foo = await get_handler.execute(GetFooQuery(id=id))
    return FooResponse(...)
```

#### `delete` (204)

```python
@router.delete(
    "/{id}",
    status_code=204,
    responses=error_responses(401, 403, 404, 409),
)
async def delete_foo(
    id: UUID,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> Response:
    handler: DeleteFooHandler = request.app.state.container.delete_foo_handler()
    await handler.execute(DeleteFooCommand(caller_id=user.id, id=id))
    return Response(status_code=204)
```

#### `reorder` (static collection PATCH, 204)

```python
@router.patch(
    "/reorder",
    status_code=204,
    responses=error_responses(401, 403, 422),
)
async def reorder_foos(
    body: ReorderRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> Response:
    handler: ReorderFoosHandler = request.app.state.container.reorder_foos_handler()
    await handler.execute(ReorderFoosCommand(caller_id=user.id, order=body.order))
    return Response(status_code=204)
```

### Parameter order (load-bearing for readability, not FastAPI)

1. Path params (`id: UUID`)
2. Body (`body: FooCreateRequest`)
3. `request: Request` (needed to reach the container)
4. Query params with defaults (`limit`, `offset`)
5. Auth dep **last** (`_` or `user`)

### Status codes (defaults)

| Operation | Decorator | Return type |
|-----------|-----------|-------------|
| `GET` list | default 200 | `<Resource>ListResponse` |
| `GET` single | default 200 | `<Resource>Response` |
| `POST` create | `status_code=201` | `<Resource>Response` (read-back) |
| `PATCH` update | default 200 | `<Resource>Response` (read-back) |
| `PATCH /reorder` | `status_code=204` | `Response(status_code=204)` |
| `DELETE` | `status_code=204` | `Response(status_code=204)` |

For 204 endpoints, the function return annotation is `-> Response` and the body is `return Response(status_code=204)`. **Do not return `None`** — FastAPI then emits an empty 200.

### Handler resolution

```python
handler: ListFoosHandler = request.app.state.container.list_foos_handler()
```

- The container method name is `<handler_class_snake>()`: `ListFoosHandler` → `list_foos_handler()`. The provider name is mechanical — see `infra-di-provider`.
- Always annotate the local `handler:` with the concrete handler class so the type checker sees `execute`.
- Resolve inside the route function. **Never at module level** — that captures container state too early and breaks per-request container overrides in tests.
- For create/update with read-back, resolve `handler` and `get_handler` as two separate locals with distinct names.

### Route ordering (load-bearing gotcha)

FastAPI matches routes in declaration order. A path like `/reorder` will be captured by `/{id}` if `/{id}` is declared first — `"reorder"` parses as a string UUID until validation fails, by which time the wrong handler ran.

**Declare every static collection-level path (`/reorder`, `/detect`, `/bars`) above the `/{id}` route.** Same applies to `GET /detect`, `GET /bars`, and any non-parameterized sibling of `/{id}`.

When extending an existing router file, place a `reorder` or other static endpoint **above** the `update`/`get_by_id`/`delete` routes for `/{id}`.

### What never goes in a route

- **No `try/except`.** Domain exceptions propagate to the central error handler. The only sanctioned exception is the mixed multipart+JSON parse in `restapi-file-transfer`.
- **No logging.** Application handlers log success; the central error handler logs failures.
- **No business logic, no policy checks, no domain construction beyond mapping body→command.**
- **No infrastructure imports.** Only `application/*` and `domain/*` types.
- **No `Depends` factories at module level** beyond `get_current_user` / `require_role(...)`. `require_role` is called inline; it returns a fresh dependency each time.

### Inlined typing / import rules

- `Annotated` from `typing`. `UUID` from `uuid`.
- `APIRouter`, `Depends`, `Query`, `Request` from `fastapi`. `Response` from `fastapi.responses`.
- Application handlers imported through the subpackage (`from myapp.application.foos import ...`) — relies on the collapsed-import convention.
- `error_responses` from `..schemas`. `get_current_user` / `require_role` from `..dependencies`.
- Full annotations on every parameter and on the return type.
- No `from __future__ import annotations`.

### When the router file is new

After adding the route(s), register the router in `src/<root>/restapi/main.py`:

```python
from .routers.foos import router as foos_router

app.include_router(foos_router)
```

### Hard stops

- Spec asks the route to log → stop, that's a layering violation; let the handler log on success or the central handler log on failure.
- Spec asks for a `try/except` in the route body → stop, the only sanctioned case is `restapi-file-transfer`.
- Spec asks the route to construct a domain entity → stop, that's the handler's job; the route maps body fields to a command.
- Static collection path would be declared after `/{id}` in the file → stop, reorder.
- Response schema requires fields the command/query result doesn't provide → stop, add a read-back via `GetFooHandler` (or extend the result DTO via `application-query`).


<!-- merged from restapi-schema -->

## REST API Schema

Produces one resource's schema module — the Pydantic models that define the HTTP wire format. Schemas are the boundary between FastAPI/JSON and the domain: domain entities never cross the wire, schemas never cross into application/domain code.

### When to use vs. neighbours

- Per-resource Pydantic schemas (request/response) → this skill.
- Cross-cutting `ErrorResponse` / `error_responses()` → `restapi-error-responses`.
- A cross-cutting request schema that **already exists** elsewhere (e.g. an auth login schema in `restapi/schemas/auth.py` when the app has auth, or a shared collection-reorder body when some resource has a reorder endpoint) → reuse it, don't re-declare it per resource. These are **feature-conditional**, not always present: an app with no auth has no `auth.py`, and an app with no reorderable resource has no `ReorderRequest` — don't assume either exists.
- The route that consumes these schemas → `restapi-endpoint`.

### File location

```
src/<root>/restapi/schemas/<module>.py        # the resource's schemas
src/<root>/restapi/schemas/__init__.py        # update to re-export
```

Sub-resource schemas live **in the same file as the parent** when they are only used through the parent router (e.g. `BarResponse` in `foos.py` if `bars` are nested under `/foos/{id}/bars`).

### Template

```python
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "FooCreateRequest",
    "FooListResponse",
    "FooResponse",
    "FooUpdateRequest",
]

class FooResponse(BaseModel):
    id: UUID
    name: str
    sort_order: int
    usage_count: int = 0

# This shows the OFFSET pagination shape. A resource whose domain-filter chose
# cursor paging (domain-filter Rule 5) instead carries `items`, `next_cursor:
# str | None`, `limit` — match whichever shape the filter declared (Rule 7).
class FooListResponse(BaseModel):
    items: Sequence[FooResponse]
    total: int
    limit: int
    offset: int

class FooCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    sort_order: int = 0

class FooUpdateRequest(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    sort_order: int | None = None
```

### Naming (exhaustive — do not invent alternates)

| Schema | Purpose |
|--------|---------|
| `<Resource>Response` | Single-entity GET / POST / PATCH response |
| `<Resource>ListResponse` | List GET response — `items` + the resource's pagination fields (offset: `total`/`limit`/`offset`; cursor: `next_cursor`/`limit`), matching `domain-filter` |
| `<Resource>CreateRequest` | POST body |
| `<Resource>UpdateRequest` | PATCH body — every field `T \| None = None` |
| `<Resource>WithXResponse` | Single-entity response that embeds a sub-resource collection |

Do **not** introduce alternates (`Dto`, `Schema`, `In`, `Out`). The five names above cover the wire surface.

### Rules

#### Class form

1. **Every schema inherits directly from `pydantic.BaseModel`.** No shared base classes for "common fields" — repetition is fine; schemas should read top-to-bottom as the wire format.
2. **Order in the file:** `Response`, `ListResponse`, `CreateRequest`, `UpdateRequest`, then sub-resource variants. Reads above writes; single above list.

#### Validation

3. **Validators live on `*Request` schemas only.** Use `Annotated[T, Field(min_length=..., max_length=..., ge=..., le=..., pattern=...)]`. Responses don't need validators — the data already passed domain invariants.
4. **`pydantic.Field` enforces input *shape* (length, range, pattern), not business rules.** Domain invariants belong on entities and policies, never here.

#### PATCH semantics

5. **Every field on `*UpdateRequest` is `T | None = None`.** The handler interprets `None` as "leave unchanged"; an explicit value as "set to this". Non-negotiable — the command DTO encodes the same partial-update contract.
6. **`*CreateRequest` lists required fields without `None`** and uses defaults (`sort_order: int = 0`) for genuinely optional inputs.

#### `*ListResponse`

7. **`*ListResponse` carries the resource's pagination shape — whichever one its `domain-filter` declared** (`domain-filter` Rule 5 picks exactly one), never a third:
   - **offset paging** → `items: Sequence[<Resource>Response]`, `total: int`, `limit: int`, `offset: int`.
   - **cursor paging** → `items: Sequence[<Resource>Response]`, `next_cursor: str | None`, `limit: int`.
   The route `restapi-endpoint` builds constructs whichever shape the filter uses, so the schema must match it (see `restapi-endpoint`'s cursor-list note). Don't mix the two.

#### `__all__`

8. **Immediately after imports, before the first class.** List every public schema **alphabetically**, one symbol per line, trailing comma. The wildcard re-export depends on this — anything missing is invisible to routers.

#### Imports

9. **Allowed:** `pydantic`, stdlib (`uuid`, `collections.abc`, `datetime`, `decimal`, `typing`), and **domain enums or value-object types only** (`FooCategory`, `Role`).
10. **Forbidden:** domain entities, dataclasses, repositories, application handlers, infrastructure types. Routers map field-by-field; the schema must not know about `Foo` the entity.
11. **No `from __future__ import annotations`** (project rule plus Pydantic needs runtime annotations).
12. **No `Optional[...]`** — `T | None`.

### What never goes in a schema file

- **No domain types beyond enums.** `FooResponse` does not import the `Foo` entity.
- **No business logic, computed properties, or `@validator`s that encode rules.** Use Pydantic's built-in `Field` constraints for shape; domain rules go elsewhere.
- **No persistence concerns.** No ORM mode, no `from_orm`, no SQLAlchemy types.
- **No shared base classes beyond `BaseModel`.**

### Package wiring

After writing the module, update `restapi/schemas/__init__.py`:

```python
from . import foos  # alphabetized with siblings
from .foos import *  # noqa: F403

__all__ = (
    foos.__all__
    # + sibling.__all__ ...
)
```

Both lines must be present — the wildcard import makes symbols reachable, and the package's own `__all__` advertises them. Routers `from ..schemas import (...)` only works because of these re-exports.

### Hard stops

- Spec asks `*Response` to validate input → stop, responses don't validate. The data already passed domain invariants.
- Spec asks `*CreateRequest` to allow all fields as `None` → stop, that's a `*UpdateRequest`.
- Spec asks for a shared base class to deduplicate fields across resources → stop, schemas are wire contracts; repetition is intentional.
- Spec asks to import a domain entity into the schema file → stop, mapping happens in the route.


<!-- merged from restapi-auth-dependency -->

## REST API Auth Dependency

A reference rule for choosing the right auth dependency on each route. Both dependencies live in `src/<root>/restapi/dependencies.py` (produced by `restapi-app-bootstrap`) and are imported as `from ..dependencies import get_current_user, require_role` inside router files.

**Auth is an app-declared feature, not a universal.** A route is authenticated only when its endpoint declares `auth != anonymous`; "this app has auth" is a property of the graph — true when any endpoint declares `auth != anonymous`, or a token-verifier capability is wired — not a separate flag. An app whose every endpoint is anonymous has **no auth layer at all**: no `restapi/dependencies.py`, no `CurrentUser`/`Role`, no `get_current_user`/`require_role`, and every route attaches **no** auth dependency (and advertises no 401/403). Everything below applies only to the routes an authed app gates; on an auth-less app there is nothing here to apply — that is not "skipping auth", it is the absence of the feature.

### When to use vs. neighbours

- Picking the dependency for a specific endpoint → this skill (`restapi-endpoint` / `restapi-file-transfer` consume the decision; the route's own `auth` declaration is what carries it).
- Writing the endpoint function body and signature → `restapi-endpoint` (which consumes this decision).
- Advertising the matching error codes (401, optionally 403) on the route decorator → `restapi-error-responses`.
- Adding a new auth-related error class → `domain-exception` then `restapi-error-responses`.
- Authorization rules finer than a single role-rank check → push them into the application handler (`application-command` / `application-query`); the handler raises `ForbiddenError`.
- Modifying `restapi/dependencies.py` itself or adding a third dependency → `restapi-app-bootstrap` owns that file; this skill consults the existing two.

### Rules

#### Decision rule

| Operation | Dependency on the route | Binding name |
|-----------|--------------------------|--------------|
| Read (any authenticated caller), handler does not need `caller_id` | `Depends(get_current_user)` | `_: CurrentUser` |
| Read, handler needs `caller_id` (auth-scoped lists) | `Depends(get_current_user)` | `user: CurrentUser` |
| Mutation, requires role rank ≥ `<Role>` | `Depends(require_role(Role.<MIN_RANK>))` | `user: CurrentUser` |
| Public route (health/info), **or any route in an app that declares no auth** | none | n/a |

**Pick the lowest privilege the operation actually requires.** If a list endpoint shows different rows depending on role, do the row filtering in the handler based on `caller_id`; do not promote the dependency to a higher role.

#### `_` vs `user` — binding name is significant

- **`_: CurrentUser = Depends(get_current_user)`** when the value is unused. The underscore makes the intent explicit.
- **`user: CurrentUser = Depends(require_role(...))`** or `Depends(get_current_user)` when the value flows into a command/query as `caller_id=user.id`.

Don't bind to `user` and leave it unused — code review will read it as "did the author forget to pass caller_id?".

**All auth-derived fields come from `CurrentUser`, never the request.** In a multi-tenant app the token also carries the tenant — stamp it from the bound user (`workspace_id=user.workspace_id`, `tenant_id=user.tenant_id`), exactly like `caller_id=user.id`, and bind `user` (not `_`). A tenant id must never be read from the path/query/body — that would let a client choose another tenant's scope. The command/query DTO carries the field (`application-command` / `application-query` DTO rule 2); the route stamps it here.

```python
# read — no caller_id needed
async def list_foos(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: CurrentUser = Depends(get_current_user),
) -> FooListResponse: ...

# mutation — caller_id flows into the command
async def create_foo(
    body: FooCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    ...
    await handler.execute(CreateFooCommand(caller_id=user.id, ...))
```

#### Role rank (reference)

`Role` is a rank-ordered `StrEnum` whose members the app's `domain.enums` declares (the Helpdesk fixture's are `MEMBER < AGENT < ADMIN`, illustrative only — another app may have a two-tier or differently-named ladder). `user.role.satisfies(required)` returns `true` when the caller's rank meets or exceeds the requirement, and `require_role(Role.<MIN_RANK>)` admits that rank and every higher one. Use the placeholder `Role.<MIN_RANK>` in templates — the concrete member comes from the route's declared auth requirement against the app's own `Role`, never a fixed `SUPER_ADMIN`.

#### Constraints on every route that uses an auth dependency

1. **Auth dependency is the last parameter on every route.** Path/body/`request`/query params come first; identity last.
2. **`require_role(Role.X)` is called inline** at each route. Don't memoize at module level (`_admin = require_role(Role.ADMIN)`) — keeping the role visible at the call site is the most important detail in a route review.
3. **Don't combine `Depends(get_current_user)` with a role check.** Use `require_role(...)` instead.
4. **Never hand-roll auth checks in a route body.** No `if user.role != Role.ADMIN: raise ...`. If the rule is more nuanced than a single-role rank, that's an application-handler concern; let the handler raise `ForbiddenError`.
5. **Never decode the bearer token outside `get_current_user`.** No `jwt.decode` in routes, no manual `Authorization` header parsing.
6. **Never catch `UnauthorizedError` / `ForbiddenError`.** They propagate to the central error handler.
7. **Within an app that declares auth, authentication is the default for non-public routes.** "Trusted internal" routes that skip auth (in an authed app) are forbidden; internal-only access is enforced at the network/gateway layer. This does **not** manufacture auth on an app that declares none — see the opening note: an auth-less app has no auth layer to default to.

#### Coordinated error-code advertisement

Every route that uses an auth dependency must list the matching status codes when `restapi-error-responses` runs:

- `Depends(get_current_user)` → include `401`.
- `Depends(require_role(...))` → include `401` **and** `403`.

A role-gated route must therefore advertise both 401 and 403 (a `get_current_user`-only route just 401). Advertising the codes is `restapi-error-responses`' job, derived from the chosen dependency — not a field this skill writes.

### Hard stops

- Spec asks the route to inline a role check after `get_current_user` → stop, use `require_role(...)` instead.
- Spec asks for a custom JWT verifier per route → stop, the verifier lives in `containers.py`; routes use the standard dependency.
- Spec asks the route to read the `Authorization` header directly → stop, that's what the bearer scheme is for.
- Spec asks to omit auth on a non-public route of an app that **does** declare auth → stop, default is authenticated; only health/info endpoints are public. (Distinct from an app that declares no auth at all — there every route is auth-free by construction; that is the absence of the feature, not "omitting auth".)
- Spec proposes a third auth dependency type → stop, the two declared by `restapi-app-bootstrap` are exhaustive; introduce a finer-grained authorization rule in the application handler instead.
- A role-gated route advertises `401` but not `403` (via `restapi-error-responses`) → stop, the advertised codes must match the chosen dependency (`require_role` → 401 **and** 403).


<!-- merged from restapi-error-responses -->

## REST API Error Responses

The REST API has exactly one place that turns exceptions into HTTP responses: `register_error_handlers` in `restapi/error_handler.py`. Every `DomainError` carries `code: str` + `http_status: int` class attributes; the handler maps them to JSON via `ErrorResponse`. Routes do not catch — they only **advertise** which codes they can raise so OpenAPI documents the contract.

This skill produces two outputs depending on the input:

1. **Routine route work** — pass `responses=error_responses(<codes>)` on the route decorator. No new file.
2. **Middleware-introduced status code** — when a brand-new HTTP status comes from a middleware (no `DomainError` class behind it), register the code in `MIDDLEWARE_ERRORS` inside `restapi/schemas/errors.py`. Rare.

Domain exception classes themselves are registered automatically: `error_responses(...)` derives its allowed-code list from `domain.exceptions.__all__` at import time. Adding a new `DomainError` subclass (via `domain-exception`) is sufficient — no registry append needed.

### When to use vs. neighbours

- Adding `responses=error_responses(...)` on a new endpoint → this skill (routine path).
- Defining the new error class itself (the `class FooConflictError(ConflictError)` body in `domain/exceptions.py`) → `domain-exception`. After that runs, the new code is automatically valid for `error_responses(...)`.
- A middleware emits a status no domain class produces (e.g. 413 from `MaxRequestSizeMiddleware`) → this skill, middleware-code path.
- Producing a multipart-or-streaming route that needs the sanctioned `try/except` → `restapi-file-transfer`.
- First-time setup of `restapi/error_handler.py`, `restapi/schemas/errors.py`, etc. → `restapi-app-bootstrap`.

### Reference — `errors.py` and the translator are owned by `restapi-app-bootstrap`

`restapi/schemas/errors.py` and `restapi/error_handler.py` are created **once** by `restapi-app-bootstrap`, which is their single source of truth — this skill never restates their content (that is what let the two copies drift). Bootstrap owns the `ErrorResponse` wire model, the `error_responses(...)` helper, the `_DESCR` status→label map, and the central `DomainError` translator (one handler over every subclass; `WWW-Authenticate` only for `UnauthorizedError`). This skill **uses** two symbols from `errors.py` and **writes** exactly one, on the rare middleware path:

- **`error_responses(*codes: int) -> dict[int | str, dict[str, Any]]`** — the helper you put on a route decorator. It validates each code against the known set — `{cls.http_status for cls in domain.exceptions.__all__} ∪ set(MIDDLEWARE_ERRORS.values())` — and raises `ValueError` on an unknown one, so OpenAPI can never advertise a status nothing produces. The domain side is **derived dynamically**: a new `DomainError` subclass (via `domain-exception`) widens it automatically, with no append here.
- **`MIDDLEWARE_ERRORS: dict[str, int]`** — the **only** manually-maintained entry in `errors.py`, and this skill's sole write target. Bootstrap creates it **empty** (`{}` — no middleware is presumed); the middleware-code path below adds one row when a declared middleware introduces a status with no `DomainError` behind it (e.g. a size-cap middleware → `{"PAYLOAD_TOO_LARGE": 413}`).

### Standard code sets per operation

The sets below assume an **authenticated** route. `401` and `403` are auth codes, not universal: `401` appears only when the route attaches an auth dependency, `403` only when it is role-gated (`require_role`) — see `restapi-auth-dependency`. A **public** route (`auth: anonymous`), or any route in an app that declares no auth, **drops `401` and `403`** from its set (Create → just `409`, Read by id → just `404`, etc.). This is load-bearing, not cosmetic: `error_responses(...)` validates each code against the known set, and on an auth-less app there is no `UnauthorizedError` class, so a stray `401` raises `ValueError`.

| Operation | `error_responses(...)` (authenticated route) |
|-----------|------------------------|
| Read, parameterless (no path/query param) | `401` (+ `404` if it can not-find) |
| Read by id (`{id}` path param) | `401, 404, 422` |
| List / browse (filter or pagination query params) | `401, 422` |
| Create (body) | `401, 403, 409, 422` |
| Update (`{id}` + body) | `401, 403, 404, 409, 422` |
| Delete (`{id}` path param) | `401, 403, 404, 409, 422` (`409` covers in-use) |
| Reorder | `401, 403, 422` |
| Lookup / detect (read with input) | `401, 404, 422` |
| Multipart upload | add `413` to whichever set applies |

**Advertise `422` on every route that carries ANY validated input** — a path param (`{id}`), query / filter / pagination params, OR a request body. FastAPI auto-injects a `422` (request-validation) response into the OpenAPI for *every* such operation, and the `test_openapi_advertises_error_codes` discovery invariant (`test-discovery-invariants`) requires the route decorator to match the OpenAPI spec **exactly** — so a route that omits `422` while carrying a param fails the gate with an *extra* `422` in the spec. This is why `Read by id` and `Delete` carry `422` despite having no body: the `{id}` path param alone produces it. Only a **parameterless, body-less** route (e.g. an authenticated `GET /me`) omits `422`. (`422` resolves through the catalog's `ValidationError` / `http_status=422`, present in any app whose inputs validate — the same class entity `__post_init__` invariants raise.) The trap is reading `422` as "body validation": it is *any-input* validation. *(Surfaced when mm's first real integration run flagged `GET /meetings`, `GET /meetings/{id}`, and a path-param command that followed the old body-only reading.)*

**List a code only if the route can actually produce it.** Don't list `401` on a public/unauthenticated route (or in an auth-less app — it would raise `ValueError`), don't list `403` on a route that is not role-gated, don't list `409` on a read.

### Procedure — routine path (route only)

1. Choose the code set from the table above.
2. Add `responses=error_responses(<codes>)` to the route decorator.

That's it. The catalog is dynamic; no further registration needed.

### Procedure — middleware-code path

1. Confirm the status truly has no `DomainError` behind it (the body comes from middleware before the exception handler runs). Otherwise the right answer is `domain-exception`, not this path.
2. Append `("CODE_STRING", <http_status>)` to `MIDDLEWARE_ERRORS` in `restapi/schemas/errors.py` (the only hand-edit to that bootstrap-owned file).
3. If the status is not already a key in the `_DESCR` map (in the same `errors.py`), add a short description there.
4. Have the middleware emit an `ErrorResponse`-shaped JSON body with the same `code` string.

### Rules

1. **Routes only advertise.** They never:
   - catch `DomainError` or any subclass.
   - inspect `exc.code` to map to status.
   - log errors (the central handler is the single logging point for failures).
   - return `JSONResponse` directly.
2. **`UnauthorizedError` and `WWW-Authenticate`.** The handler attaches `WWW-Authenticate: Bearer realm="myapp"` **only** for `UnauthorizedError` (401). Do not generalize. A new auth-related exception that needs the header must subclass `UnauthorizedError`, not extend the `isinstance` branch.
3. **Never manually construct `responses={401: {...}}` dicts.** Always go through `error_responses(...)` so the catalog stays authoritative.
4. **No `raise HTTPException(...)` anywhere.** Raise a domain exception so the body stays `ErrorResponse`-shaped and the code stays cataloged.
5. **`MIDDLEWARE_ERRORS` is the only manually-maintained registry.** Everything domain-side derives from `domain.exceptions.__all__`.

### Hard stops

- Spec asks to add branching logic in `restapi/error_handler.py` → stop, the translator stays minimal. New behavior is encoded via subclassing or via `http_status` / `code` on the new class.
- Spec asks a route to catch a domain exception and translate it → stop, that's the central handler's job.
- Spec lists an HTTP status that no `DomainError` subclass produces and is not in `MIDDLEWARE_ERRORS` → stop, define a `domain-exception` first or take the middleware-code path.
- Spec asks for `WWW-Authenticate` on a 403 → stop, that header is 401-specific by RFC 7235.


<!-- merged from restapi-file-transfer -->

## REST API File Transfer

File transfer breaks the otherwise-uniform CRUD shape: routes accept multipart bodies or return raw bytes. The conventions below must be repeated verbatim in any new file-transfer route — they encode several non-obvious rules and the single route-body `try/except` exemption.

The non-file-specific rules — parameter order, handler resolution via `request.app.state.container`, route ordering vs `/{id}`, the "no `try/except`, no logging, no business logic in routes" prohibitions — are owned by `restapi-endpoint`. Read that skill first; this one only adds the upload/download specializations on top. **Auth follows `restapi-endpoint`'s authed/public idiom:** the templates below show the authenticated form; a public route (`auth: anonymous`) — or any route in an app that declares no auth — drops the auth dependency, its `domain.auth`/`..dependencies` imports, the `401`/`403`, and the `caller_id`. The auth dependency is never a frozen role; it is the slot `restapi-auth-dependency` fills.

### When to use vs. neighbours

- Multipart upload route or streaming-binary download route → this skill.
- A regular JSON CRUD route → `restapi-endpoint` (this skill does not apply).
- The handler that consumes the bytes (upload) or produces them (download) → `application-command` / `application-query`. The handler's capability protocol for storage lives in `domain-capability-protocol`.
- The route's auth dependency (or none) → `restapi-auth-dependency`; it is not pre-wired here. Wiring `MaxRequestSizeMiddleware` and CORS `expose_headers` lives in `restapi/main.py`; this skill only extends `expose_headers` if a new response header is added.

### Upload templates

#### Pure file upload (`slot: single`)

```python
@router.post(
    "/import/xlsx",
    response_model=ImportFoosResponse,
    responses=error_responses(401, 403, 413, 422),
)
async def import_xlsx(
    request: Request,
    file: UploadFile,
    bar_id: UUID = Form(...),
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> ImportFoosResponse:
    data = await file.read()
    handler: ImportFoosXlsxHandler = (
        request.app.state.container.import_foos_xlsx_handler()
    )
    result = await handler.execute(
        ImportFoosXlsxCommand(caller_id=user.id, bar_id=bar_id, file_data=data),
    )
    return ImportFoosResponse(...)
```

Rules:

- `file: UploadFile` for the file slot. Companion scalar/UUID fields use `= Form(...)` — they share the same multipart envelope.
- `await file.read()` loads the body into memory. This is bounded **only** when the app declares a request-size cap middleware (`restapi-middleware`'s `MaxRequestSizeMiddleware`), which rejects oversize requests before the route runs. A request-size cap is a per-app `restapi.middlewares` choice, not a given: if the app declares none, the body is unbounded and `file.read()` is **not** safe — the app must add a size cap (or the route must stream-and-bound the read) before relying on it. The templates here assume the app declares such a cap.
- **Advertise `413`** in `responses=error_responses(...)` **only when the app declares a request-size cap middleware** — 413 is produced by that middleware (its code registered in `MIDDLEWARE_ERRORS`), not by a domain exception, so an app without one has no 413 to advertise, and the OpenAPI discovery check (`test-discovery-invariants`) would reject the orphan code. The `413` shown in the decorator templates is present because those templates assume a size-capped app; drop it for an app that declares no size middleware.
- The route does not parse the file — pass bytes to the handler via the command DTO (`file_data: bytes`).

#### Multiple optional uploads (`slot: optional-many`)

```python
attachments: list[UploadFile] | None = None,
...
attachment_inputs: list[CreateFooAttachment] = []
for f in attachments or []:
    raw = await f.read()
    attachment_inputs.append(CreateFooAttachment(data=raw, mime=f.content_type or ""))
```

- Slot type `list[UploadFile] | None = None` handles "no files attached" cleanly.
- Build a list of application input dataclasses inside the route; capture both `data` and `f.content_type or ""`. The empty-string fallback is deliberate — domain validates the mime and an empty value triggers a clear `ValidationError` rather than `None` slipping through.

#### Mixed multipart + JSON (`slot: mixed-multipart-json`) — the only sanctioned `try/except` in a route body

```python
@router.post(
    "",
    status_code=201,
    response_model=FooResponse,
    responses=error_responses(401, 409, 413, 422),
)
async def create_foo(
    request: Request,
    data: Annotated[str, Form()],
    attachments: list[UploadFile] | None = None,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    try:
        payload = CreateFooPayload.model_validate_json(data)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    ...
```

Rules:

- `data: Annotated[str, Form()]` receives the JSON blob as a string. Pydantic does not automatically validate it because the slot type is `str` — validation is explicit.
- `<Schema>.model_validate_json(data)` parses and validates.
- **The `try/except PydanticValidationError → raise ValidationError(str(exc)) from exc` is the single sanctioned `try/except` in a route body** in this codebase. It exists because Pydantic's exception is not a `DomainError` and would otherwise produce FastAPI's default 422 instead of an `ErrorResponse`-shaped body. **Use this pattern verbatim — no other forms of error catching belong in a route.**
- Always re-raise with `from exc` to preserve the chain.

This pattern is reserved for the multipart+JSON case. **Do not generalize it.** A JSON-only route uses `body: <Schema>` and lets FastAPI's normal validation flow through the central handler.

### Download template — streaming binary response

```python
@router.post("/export", responses=error_responses(401, 422))
async def export_foos(
    body: ExportFoosFilterRequest,
    request: Request,
    _: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    handler: ExportFoosHandler = request.app.state.container.export_foos_handler()
    data = await handler.execute(ExportFoosQuery(filter=_to_filter(body)))
    filename = _export_filename("csv")  # the extension this export actually produces
    return StreamingResponse(
        iter([data]),
        # The real content type the handler produces — csv / pdf / xlsx / … — not a
        # fixed format frozen from one app. Don't fall back to octet-stream for a known type.
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Rules:

- **Return annotation: `-> StreamingResponse`.** No `response_model` — FastAPI does not serialize the body.
- `StreamingResponse(iter([bytes]), media_type=..., headers={...})` is the canonical shape. `iter([data])` wraps already-materialized bytes in a single-chunk iterator. If the handler produces a true `AsyncIterator[bytes]`, pass it directly without `iter([...])`.
- **`media_type` is the real content type** (xlsx / docx / pdf MIME). Don't use `application/octet-stream` for known formats — clients render based on this.
- `Content-Disposition: attachment; filename="..."` triggers download instead of inline. Filename is double-quoted; a plain ASCII filename is the simplest default, and if you need RFC 5987 encoding for non-ASCII, document it inline.

#### `_export_filename` helper

```python
def _export_filename(ext: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"myapp-foos-{ts}.{ext}"
```

- Module-level helper named `_<purpose>_filename`. Underscore-prefixed because it's private to the router module.
- The shape shown (UTC timestamp `YYYYMMDD-HHMMSS`, a `<project>-<resource>` prefix, an extension parameter) is a reasonable default, not a fixed canon. The exact filename format — timestamp style, prefix, ASCII vs RFC 5987 — is an app-level choice; keep it consistent within one app, but don't freeze this particular shape as mandatory across apps.
- Filename construction lives in the route, not the handler. The handler returns content; the route names the artifact.

#### CORS `expose_headers`

`Content-Disposition` is not a default CORS-exposed header, so a browser strips it from the response visible to JS. **If the app has CORS configured** (`restapi-app-bootstrap`), a download route must ensure its response header is in the CORS middleware's `expose_headers` list — the bootstrap leaves that list **empty** by default, so a download route adds `"Content-Disposition"` (and any other non-default header it sets, e.g. `X-Total-Count`) there:

```python
expose_headers=["Content-Disposition"],
```

An app with no CORS configured has no such list to extend. **Verify `expose_headers` whenever you add a headered download response** (when CORS is enabled).

### Handler contract for downloads

- The handler returns **raw bytes** (or an `AsyncIterator[bytes]` for true streaming). It does not return a Pydantic model, a Response, or a file path.
- The route does not transform the bytes — it only wraps them in `StreamingResponse` and attaches the filename / `Content-Disposition`.
- Authorization, filtering, and content generation all live in the handler. The route is a transport adapter.

### What never goes in a file-transfer route

- **Writing the upload to disk inside the route.** Pass bytes (or an `UploadFile`) to the handler; storage is an infrastructure concern (`infra-sqlalchemy-repository`-style capability adapters).
- **Computing or enforcing a per-route size limit.** `MaxRequestSizeMiddleware` is the single chokepoint. If a specific route needs a tighter cap, add it as an application-layer rule that raises `ValidationError` after parsing.
- **Streaming without `media_type`.** Browsers and clients rely on it.
- **Catching exceptions other than the one sanctioned `PydanticValidationError → ValidationError` translation in mixed-multipart-json mode.** Do not extend the `try/except`.
- **Returning `FileResponse` from a path on disk.** All file content originates from the handler's bytes. The API does not serve filesystem paths.
- **`response_model` on a streaming route.** Meaningless and confuses OpenAPI.

### Inlined typing / import rules

- `from typing import Annotated`, `from uuid import UUID`, `from datetime import datetime, UTC`.
- `from fastapi import UploadFile, Form` (in addition to the standard `APIRouter, Depends, Query, Request`).
- `from fastapi.responses import StreamingResponse`.
- `from pydantic import ValidationError as PydanticValidationError` — alias so the import doesn't shadow the domain `ValidationError`.
- Full annotations on every parameter and return type.

### Hard stops

- Spec asks for a `try/except` other than the mixed-multipart-json one → stop, no other `try/except` belongs in a route body.
- Spec wants the route to compute file size limits → stop, that's the middleware's job.
- Spec wants the route to parse the file content → stop, that's the handler's job; the route passes bytes.
- Spec adds a download response header beyond `Content-Disposition` without updating CORS `expose_headers` (when CORS is configured) → stop, update both in the same change.


<!-- merged from restapi-middleware -->

## REST API Middleware

Produces one ASGI middleware — a class that wraps the whole app to handle **any** cross-cutting request/response concern that belongs to no single route (correlation ids, a body-size cap, rate limiting, timing — an open list, not a fixed catalog). One class per file under `restapi/middleware/<snake>.py`, named `<Name>Middleware`.

### When to use vs. neighbours

- A concern that wraps **every** request (correlation id, size cap, rate limit, timing) → this skill.
- The app shell — CORS, the central `DomainError` handler, lifespan → `restapi-app-bootstrap`.
- Logic for **one** route → `restapi-endpoint` (a thin route over an application handler).
- Authenticating / authorizing a route → `restapi-auth-dependency` (a FastAPI dependency, **not** a middleware).
- Advertising an HTTP code a route can return → `restapi-error-responses`.

### Template(s)

Two shapes, picked by whether the middleware ever stops a request — one template per shape. Both share
the same skeleton (non-`http` passthrough, `app` + config on `self`); they differ only in whether
`__call__` grows a reject branch. The concerns shown are illustrations, not a fixed catalog.

#### Pass-through — observes/annotates, never short-circuits (e.g. a correlation id)

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

#### Short-circuit with an error — rejects before the route runs (e.g. a request-size cap)

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

### Rules

1. **One class per file**, named `<Name>Middleware`, under `restapi/middleware/`. It is a **raw ASGI callable**, not a `starlette.middleware.base.BaseHTTPMiddleware` subclass (that buffers the whole body and breaks streaming + the size cap).
2. **Exact ASGI shape.** `__init__(self, app: ASGIApp, <config…>)` stores `app` + the config on `self`; `async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None`. Configuration arrives as constructor keyword arguments — passed at `app.add_middleware(Cls, **config)` — and the constructor validates them at wiring time (a bad value fails fast on startup, not mid-request).
3. **Pass non-`http` scopes straight through** — `if scope["type"] != "http": await self._app(scope, receive, send); return`. Lifespan and websocket scopes must not be intercepted.
4. **A middleware that REJECTS a request emits an `ErrorResponse`-shaped JSON body** — `{"code": "<STABLE_STRING>", "message": "...", "context": {}}` — with the HTTP status it owns, and `return`s **before** `await self._app(...)`; a pass-through, by contrast, always reaches the call. Keep the code string stable: the API contract and `restapi/schemas/errors.py`'s `MIDDLEWARE_ERRORS` key on it (see `restapi-error-responses`).
5. **No business/domain logic.** A middleware is transport-level — bytes, headers, timing, the structlog context. Anything needing a domain entity, a repository, or an application handler is not a middleware.
6. **`self` holds only `app` + config** (built once, at wiring time). Any per-request value is a local inside `__call__` (e.g. the request id, the declared content length), never an instance attribute.
7. **Ordering is significant — Starlette wraps the last-added outermost.** Each `app.add_middleware(...)` call wraps the app as a new **outermost** layer, so the **last** middleware added is the first to see a request and the last to touch a response. A middleware that must see the raw request before anything else (a size cap) is therefore added **last**. The relative order is the consuming app's wiring decision.

### Inlined typing / import rules

- ASGI types from `starlette.types` (`ASGIApp`, `Scope`, `Receive`, `Send`; add `Message` only if a `__call__` wraps `receive`/`send`). `X | None` over `Optional[X]`; full annotations on `__init__` and `__call__`. No `from __future__ import annotations`.
- A middleware that rejects emits its body through the shared `ErrorResponse` schema (`from ..schemas.errors import ErrorResponse`) — never hand-roll the `{"code", "message", "context"}` dict, so the wire shape stays single-sourced.
- When the middleware logs, `import structlog` (+ `structlog.contextvars` helpers) at module top — see `general-logging`.

### Package wiring

Register the module in `restapi/middleware/__init__.py` per `general-python-package`.

### Hard stops

- The concern is for one route, not all → stop, use `restapi-endpoint` + a handler.
- It needs a domain entity / repository / application handler → stop, that's application logic, not a middleware.
- It authenticates or authorizes a request → stop, use `restapi-auth-dependency` (a FastAPI dependency on the route).
- You reach for `BaseHTTPMiddleware` → stop, use the raw ASGI class (BaseHTTPMiddleware buffers the body, breaking the size cap and streaming downloads).
- The middleware introduces an HTTP status with no domain exception behind it → stop, register the code via `restapi-error-responses` (the middleware-code path).
