---
name: restapi-route-contracts
description: The two contracts every route declares — which auth dependency it attaches (`get_current_user` for any authenticated caller, `require_role(Role.X)` when role-gated, with the `_` versus `user` binding convention) and which HTTP error codes it advertises through `responses=error_responses(...)`. The second follows from the first.
when_to_use: Deciding a route's auth dependency or the error codes it declares, or checking that a role-gated route binds and advertises consistently.
paths: src/**/restapi/**
---

# REST Route Contracts

Two declarations a route makes about itself, and they are one subject because **the advertised codes
follow from the chosen dependency**: `get_current_user` means the route can return 401,
`require_role(...)` means 401 **and** 403, and a public route means neither. Getting them out of step is
the failure this file exists to prevent — the discovery invariant that compares the decorator against
the OpenAPI spec fails on exactly that mismatch.

Neither half produces a file. Both dependencies live in `restapi/dependencies.py`, and `error_responses`
lives in `restapi/schemas/errors.py`; both files are created once by `restapi-app`, which is their single
source of truth.

**Auth is conditional, not a universal.** A route is authenticated only when it is non-anonymous, and
"this app has auth" is a property of its routes — true when any endpoint is non-anonymous, or a
token-verifier capability is wired — never a separate flag. An app whose every endpoint is anonymous has
**no auth layer at all**: no `restapi/dependencies.py`, no `CurrentUser` / `Role`, no `get_current_user`
/ `require_role`, and every route attaches no auth dependency and advertises no 401 or 403. On such an
app there is nothing here to apply, which is the absence of the feature rather than "skipping auth".

## When to use vs. neighbours

- Picking the dependency for an endpoint, or its code set → this skill.
- Writing the endpoint's signature and body → `restapi-endpoint`, which consumes both decisions.
- A multipart or streaming route → `restapi-file-transfer`, which also consumes them.
- Defining a new error class → `domain-exception`. Once it exists, its status is automatically valid for
  `error_responses(...)`.
- `restapi/dependencies.py`, `restapi/error_handler.py` or `restapi/schemas/errors.py` themselves, or a
  third auth dependency → `restapi-app` owns those files.
- Authorization finer than a single role-rank check → push it into the handler (`application`), which
  raises `ForbiddenError`.

## The auth dependency

### Decision rule

| Operation | Dependency on the route | Binding name |
|---|---|---|
| Read by any authenticated caller, handler does not need `caller_id` | `Depends(get_current_user)` | `_: CurrentUser` |
| Read where the handler needs `caller_id` (an auth-scoped list) | `Depends(get_current_user)` | `user: CurrentUser` |
| Mutation requiring role rank ≥ `<Role>` | `Depends(require_role(Role.<MIN_RANK>))` | `user: CurrentUser` |
| Public route (health, info), **or any route in an app with no auth** | none | n/a |

**Pick the lowest privilege the operation actually requires.** If a list endpoint shows different rows
depending on role, filter the rows in the handler using `caller_id`; do not promote the dependency to a
higher role.

### `_` vs `user` — the binding name is significant

- **`_: CurrentUser = Depends(get_current_user)`** when the value is unused. The underscore makes the
  intent explicit.
- **`user: CurrentUser = Depends(...)`** when the value flows into a command or query as
  `caller_id=user.id`.

Do not bind to `user` and leave it unused — a reviewer reads that as "did the author forget to pass
`caller_id`?".

**All auth-derived fields come from `CurrentUser`, never from the request.** In a multi-tenant app the
token also carries the tenant: stamp it from the bound user (`workspace_id=user.workspace_id`), exactly
like `caller_id=user.id`, and bind `user` rather than `_`. A tenant id must never be read from the path,
query or body — that would let a client choose another tenant's scope. The DTO carries the field
(`application`); the route stamps it.

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

### Role rank (reference)

`Role` is a rank-ordered `StrEnum` in the domain (`domain-model`); `MEMBER < AGENT < ADMIN` is
illustrative only — another app may have a two-tier or differently-named ladder.
`user.role.satisfies(required)` is true when the caller's rank meets or exceeds the requirement, and
`require_role(Role.<MIN_RANK>)` admits that rank and every higher one. Use the placeholder
`Role.<MIN_RANK>` in a template; the concrete member comes from the route's own requirement against the
app's `Role`, never a fixed `SUPER_ADMIN`.

### Rules — every route that attaches an auth dependency

1. **The auth dependency is the last parameter.** Path, body, `request` and query parameters come first;
   identity last.
2. **`require_role(Role.X)` is called inline** at each route. Do not memoize it at module level
   (`_admin = require_role(Role.ADMIN)`) — keeping the role visible at the call site is the most
   important detail in a route review.
3. **Do not combine `Depends(get_current_user)` with a role check.** Use `require_role(...)`.
4. **Never hand-roll an auth check in a route body.** No `if user.role != Role.ADMIN: raise …`. A rule
   more nuanced than a single role rank is a handler concern; the handler raises `ForbiddenError`.
5. **Never decode the bearer token outside `get_current_user`.** No `jwt.decode` in a route, no manual
   `Authorization` header parsing.
6. **Never catch `UnauthorizedError` or `ForbiddenError`.** They propagate to the central handler.
7. **In an app that has auth, authentication is the default for a non-public route.** A "trusted
   internal" route that skips auth is forbidden; internal-only access is enforced at the network or
   gateway layer. This does **not** manufacture auth on an app that has none.

## The advertised error codes

The REST layer has exactly one place that turns exceptions into HTTP responses:
`register_error_handlers` in `restapi/error_handler.py`. Every `DomainError` carries `code: str` and
`http_status: int`, and the handler maps them to JSON through `ErrorResponse`. Routes never catch — they
only **advertise** which codes they can raise, so OpenAPI documents the contract.

Domain exception classes register themselves: `error_responses(...)` derives its allowed-code list from
`domain.exceptions.__all__` at import time. Adding a subclass (`domain-exception`) is enough — there is
no registry to append to.

Two symbols come from `errors.py`, and only one of them is ever written here:

- **`error_responses(*codes: int) -> dict[int | str, dict[str, Any]]`** — the helper that goes on a route
  decorator. It validates each code against the known set —
  `{cls.http_status for cls in domain.exceptions.__all__} ∪ set(MIDDLEWARE_ERRORS.values())` — and raises
  `ValueError` on an unknown one, so OpenAPI can never advertise a status nothing produces.
- **`MIDDLEWARE_ERRORS: dict[str, int]`** — the **only** manually-maintained registry in `errors.py`, and
  this skill's sole write target. `restapi-app` creates it empty; a row is added when a middleware
  introduces a status with no `DomainError` behind it, such as a size cap →
  `{"PAYLOAD_TOO_LARGE": 413}`.

### Standard code sets per operation

The sets assume an **authenticated** route. `401` and `403` are auth codes, not universal: `401` appears
only when the route attaches an auth dependency, `403` only when it is role-gated. A **public** route, or
any route in an app with no auth, **drops both** — Create becomes just `409`, Read by id just `404`. This
is load-bearing rather than cosmetic: `error_responses(...)` validates against the known set, and an
auth-less app has no `UnauthorizedError` class, so a stray `401` raises `ValueError`.

| Operation | `error_responses(...)` on an authenticated route |
|---|---|
| Read, parameterless | `401` (plus `404` if it can not-find) |
| Read by id (`{id}` path param) | `401, 404, 422` |
| List / browse (filter or pagination params) | `401, 422` |
| Create (body) | `401, 403, 409, 422` |
| Update (`{id}` plus body) | `401, 403, 404, 409, 422` |
| Delete (`{id}` path param) | `401, 403, 404, 409, 422` — `409` covers in-use |
| Reorder | `401, 403, 422` |
| Lookup / detect (a read with input) | `401, 404, 422` |
| Multipart upload | add `413` to whichever set applies |

**Advertise `422` on every route carrying ANY validated input** — a path param, query, filter or
pagination params, or a body. FastAPI auto-injects a `422` request-validation response into the OpenAPI
for *every* such operation, so declaring it keeps the published document **honest**: a client reading the
schema sees the same failure set whether it comes from the decorator or from the framework, and nobody has
to know which half put it there. Do not expect a test to catch a miss — the
`test_openapi_advertises_error_codes` invariant (`test-discovery-invariants`) exempts exactly this code,
because the framework inserts it where the decorator cannot see it. The rule stands on the document
telling the truth, not on a red run. That is why Read-by-id and Delete carry `422` despite having no body:
the `{id}` path param alone produces it. Only a parameterless, body-less route — an authenticated
`GET /me` — omits it. The trap is reading `422` as "body validation"; it is *any-input* validation.

**List a code only if the route can actually produce it.** No `401` on a public route or in an auth-less
app, no `403` on a route that is not role-gated, no `409` on a read.

### Coordinated advertisement — the join between the two halves

- `Depends(get_current_user)` → the set includes `401`.
- `Depends(require_role(...))` → the set includes `401` **and** `403`.
- No auth dependency → the set includes neither.

### Procedure — routine route

1. Choose the code set from the table.
2. Add `responses=error_responses(<codes>)` to the route decorator.

The catalog is dynamic; nothing further is registered.

### Procedure — a middleware-introduced code

1. Confirm the status genuinely has no `DomainError` behind it — the body comes from middleware, before
   the exception handler runs. Otherwise the answer is `domain-exception`, not this path.
2. Append `("CODE_STRING", <http_status>)` to `MIDDLEWARE_ERRORS` in `restapi/schemas/errors.py` — the
   only hand-edit to that `restapi-app`-owned file.
3. If the status is not already a key in the `_DESCR` map in the same file, add a short description.
4. Have the middleware emit an `ErrorResponse`-shaped body with the same `code` string.

### Rules — advertisement

8. **Routes only advertise.** A route never catches `DomainError` or a subclass, never inspects
   `exc.code` to map a status, never logs an error — the central handler is the single logging point for
   failures — and never returns `JSONResponse` directly.
9. **`UnauthorizedError` and `WWW-Authenticate`.** The handler attaches
   `WWW-Authenticate: Bearer realm="myapp"` **only** for `UnauthorizedError`. Do not generalize it. A new
   auth-related exception needing the header subclasses `UnauthorizedError` rather than extending the
   `isinstance` branch.
10. **Never construct a `responses={401: {...}}` dict by hand.** Always go through `error_responses(...)`
    so the catalog stays authoritative.
11. **No `raise HTTPException(...)` anywhere.** Raise a domain exception so the body stays
    `ErrorResponse`-shaped and the code stays cataloged.
12. **`MIDDLEWARE_ERRORS` is the only manually-maintained registry.** Everything domain-side derives from
    `domain.exceptions.__all__`.

## Hard stops

- Spec asks a route to inline a role check after `get_current_user` → stop, use `require_role(...)`.
- Spec asks for a custom JWT verifier per route → stop, the verifier lives in `containers.py`; routes use
  the standard dependency.
- Spec asks a route to read the `Authorization` header directly → stop, that is what the bearer scheme is
  for.
- Spec asks to omit auth on a non-public route of an app that **does** have auth → stop, authenticated is
  the default and only health or info endpoints are public. This is distinct from an app with no auth at
  all, where every route is auth-free by construction.
- Spec proposes a third auth dependency type → stop, the two `restapi-app` declares are exhaustive;
  express a finer-grained rule in the handler instead.
- A role-gated route advertises `401` but not `403` → stop, the advertised codes must match the chosen
  dependency.
- Spec asks to add branching logic to `restapi/error_handler.py` → stop, the translator stays minimal;
  new behaviour is encoded by subclassing, or by `http_status` / `code` on the new class.
- Spec asks a route to catch a domain exception and translate it → stop, that is the central handler's
  job.
- Spec lists a status no `DomainError` subclass produces and that is not in `MIDDLEWARE_ERRORS` → stop,
  define the exception first or take the middleware path.
- Spec asks for `WWW-Authenticate` on a 403 → stop, that header is 401-specific by RFC 7235.
