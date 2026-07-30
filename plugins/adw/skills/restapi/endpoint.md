<!-- merged from restapi-endpoint -->

# REST API Endpoint

Produces one HTTP endpoint for one resource. Routers grow incrementally — this skill adds one route at a time. A "router file" exists once per resource; subsequent endpoint additions extend it.

## When to use vs. neighbours

- One new endpoint or modification of an existing one → this skill.
- Pydantic request/response schemas → `schema.md` (this skill consumes them).
- The auth dependency choice (`get_current_user` vs `require_role`) → `auth-dependency.md`.
- The `responses=error_responses(...)` declaration → `error-responses.md`.
- Multipart upload or streaming download → `file-transfer.md`.
- The `Container.<handler>()` provider this route resolves → `infra-di-provider`.

## File location

```
src/<root>/restapi/routers/<resource>.py
```

One router file per resource holds **all** of that resource's endpoint functions; the file declares the `APIRouter`, defines each endpoint function (ordered per Route ordering), and is registered once in `src/<root>/restapi/main.py` via `app.include_router(...)`. The skeleton below is the whole-file shape; an endpoint function is the per-route shape that follows it.

## Skeleton — router file

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
- **The auth imports are conditional.** `from myapp.domain.auth import CurrentUser, Role` and `from ..dependencies import get_current_user, require_role` appear **only** when the app declares auth (`auth-dependency.md`) and this resource has ≥1 authenticated route. An auth-less app — or a router whose every route is public — omits both imports entirely; importing them would reference a `domain/auth` module and a `dependencies.py` that an auth-less app does not have. See Auth variants below.

## Templates — one per `kind`

**The per-`kind` templates below show the AUTHENTICATED form** (an authed app, a gated route). Auth is app-declared (see `auth-dependency.md` — derived from the graph, no separate flag). When the route is **public** (`auth: anonymous`), or the whole app declares no auth, derive the public form by dropping four things and nothing else: the auth-dependency parameter, the `domain.auth` + `..dependencies` imports, the `401`/`403` codes in `error_responses(...)`, and the `caller_id=user.id` argument to the command/query. The two shapes side by side:

### Authenticated vs public — the two shapes

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

### `list` (paginated read) — pagination shape mirrors `domain-filter`

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

The `schema.md`-produced `FooListResponse` must match the chosen pagination shape (either `total/limit/offset` or `next_cursor/limit`).

### `get` (single read)

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

### `create` (with post-write read-back)

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

### `update` (PATCH with read-back)

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

### `delete` (204)

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

### `reorder` (static collection PATCH, 204)

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

## Parameter order (load-bearing for readability, not FastAPI)

1. Path params (`id: UUID`)
2. Body (`body: FooCreateRequest`)
3. `request: Request` (needed to reach the container)
4. Query params with defaults (`limit`, `offset`)
5. Auth dep **last** (`_` or `user`)

## Status codes (defaults)

| Operation | Decorator | Return type |
|-----------|-----------|-------------|
| `GET` list | default 200 | `<Resource>ListResponse` |
| `GET` single | default 200 | `<Resource>Response` |
| `POST` create | `status_code=201` | `<Resource>Response` (read-back) |
| `PATCH` update | default 200 | `<Resource>Response` (read-back) |
| `PATCH /reorder` | `status_code=204` | `Response(status_code=204)` |
| `DELETE` | `status_code=204` | `Response(status_code=204)` |

For 204 endpoints, the function return annotation is `-> Response` and the body is `return Response(status_code=204)`. **Do not return `None`** — FastAPI then emits an empty 200.

## Handler resolution

```python
handler: ListFoosHandler = request.app.state.container.list_foos_handler()
```

- The container method name is `<handler_class_snake>()`: `ListFoosHandler` → `list_foos_handler()`. The provider name is mechanical — see `infra-di-provider`.
- Always annotate the local `handler:` with the concrete handler class so the type checker sees `execute`.
- Resolve inside the route function. **Never at module level** — that captures container state too early and breaks per-request container overrides in tests.
- For create/update with read-back, resolve `handler` and `get_handler` as two separate locals with distinct names.

## Route ordering (load-bearing gotcha)

FastAPI matches routes in declaration order. A path like `/reorder` will be captured by `/{id}` if `/{id}` is declared first — `"reorder"` parses as a string UUID until validation fails, by which time the wrong handler ran.

**Declare every static collection-level path (`/reorder`, `/detect`, `/bars`) above the `/{id}` route.** Same applies to `GET /detect`, `GET /bars`, and any non-parameterized sibling of `/{id}`.

When extending an existing router file, place a `reorder` or other static endpoint **above** the `update`/`get_by_id`/`delete` routes for `/{id}`.

## What never goes in a route

- **No `try/except`.** Domain exceptions propagate to the central error handler. The only sanctioned exception is the mixed multipart+JSON parse in `file-transfer.md`.
- **No logging.** Application handlers log success; the central error handler logs failures.
- **No business logic, no policy checks, no domain construction beyond mapping body→command.**
- **No infrastructure imports.** Only `application/*` and `domain/*` types.
- **No `Depends` factories at module level** beyond `get_current_user` / `require_role(...)`. `require_role` is called inline; it returns a fresh dependency each time.

## Inlined typing / import rules

- `Annotated` from `typing`. `UUID` from `uuid`.
- `APIRouter`, `Depends`, `Query`, `Request` from `fastapi`. `Response` from `fastapi.responses`.
- Application handlers imported through the subpackage (`from myapp.application.foos import ...`) — relies on the collapsed-import convention.
- `error_responses` from `..schemas`. `get_current_user` / `require_role` from `..dependencies`.
- Full annotations on every parameter and on the return type.
- No `from __future__ import annotations`.

## When the router file is new

After adding the route(s), register the router in `src/<root>/restapi/main.py`:

```python
from .routers.foos import router as foos_router

app.include_router(foos_router)
```

## Hard stops

- Spec asks the route to log → stop, that's a layering violation; let the handler log on success or the central handler log on failure.
- Spec asks for a `try/except` in the route body → stop, the only sanctioned case is `file-transfer.md`.
- Spec asks the route to construct a domain entity → stop, that's the handler's job; the route maps body fields to a command.
- Static collection path would be declared after `/{id}` in the file → stop, reorder.
- Response schema requires fields the command/query result doesn't provide → stop, add a read-back via `GetFooHandler` (or extend the result DTO via `application-query`).
