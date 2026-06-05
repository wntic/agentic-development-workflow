---
name: restapi-auth-dependency
description: Reference skill consulted by `restapi-endpoint` and `restapi-file-transfer` when they need to decide which auth dependency a route attaches. Routes use exactly two FastAPI dependencies, declared once by `restapi-app-bootstrap` in `restapi/dependencies.py`: `get_current_user` (any-authenticated) and `require_role(Role.X)` (role-gated). This skill is a decision rule plus binding convention (`_: CurrentUser` vs `user: CurrentUser`) — it produces no file. Does not write the route (use `restapi-endpoint`), advertise the error codes the chosen dependency raises (use `restapi-error-responses`), or change the dependency module itself (that lives in `restapi-app-bootstrap`).
---

# REST API Auth Dependency

A reference rule for choosing the right auth dependency on each route. Both dependencies live in `src/<root>/restapi/dependencies.py` (produced by `restapi-app-bootstrap`) and are imported as `from ..dependencies import get_current_user, require_role` inside router files.

## When to use vs. neighbours

- Picking the dependency for a specific endpoint → this skill (the choice is then encoded as `auth_mode` input to `restapi-endpoint` / `restapi-file-transfer`).
- Writing the endpoint function body and signature → `restapi-endpoint` (which consumes this decision).
- Advertising the matching error codes (401, optionally 403) on the route decorator → `restapi-error-responses`.
- Adding a new auth-related error class → `domain-exception` then `restapi-error-responses`.
- Authorization rules finer than a single role-rank check → push them into the application handler (`application-command` / `application-query`); the handler raises `ForbiddenError`.
- Modifying `restapi/dependencies.py` itself or adding a third dependency → `restapi-app-bootstrap` owns that file; this skill consults the existing two.

## Rules

### Decision rule

| Operation | Dependency on the route | Binding name |
|-----------|--------------------------|--------------|
| Read (any authenticated caller), handler does not need `caller_id` | `Depends(get_current_user)` | `_: CurrentUser` |
| Read, handler needs `caller_id` (auth-scoped lists) | `Depends(get_current_user)` | `user: CurrentUser` |
| Mutation, requires role rank ≥ `<Role>` | `Depends(require_role(Role.<MIN_RANK>))` | `user: CurrentUser` |
| Public (health/info only) | none | n/a |

**Pick the lowest privilege the operation actually requires.** If a list endpoint shows different rows depending on role, do the row filtering in the handler based on `caller_id`; do not promote the dependency to a higher role.

### `_` vs `user` — binding name is significant

- **`_: CurrentUser = Depends(get_current_user)`** when the value is unused. The underscore makes the intent explicit.
- **`user: CurrentUser = Depends(require_role(...))`** or `Depends(get_current_user)` when the value flows into a command/query as `caller_id=user.id`.

Don't bind to `user` and leave it unused — code review will read it as "did the author forget to pass caller_id?".

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
    user: CurrentUser = Depends(require_role(Role.SUPER_ADMIN)),
) -> FooResponse:
    ...
    await handler.execute(CreateFooCommand(caller_id=user.id, ...))
```

### Role rank (reference)

`Role` is a `StrEnum` ordered by rank — `COLLABORATOR < ADMIN < SUPER_ADMIN`. `user.role.satisfies(required)` returns `true` when the caller's rank meets or exceeds the requirement. `require_role(Role.ADMIN)` admits both `ADMIN` and `SUPER_ADMIN`.

### Constraints on every route that uses an auth dependency

1. **Auth dependency is the last parameter on every route.** Path/body/`request`/query params come first; identity last.
2. **`require_role(Role.X)` is called inline** at each route. Don't memoize at module level (`_admin = require_role(Role.ADMIN)`) — keeping the role visible at the call site is the most important detail in a route review.
3. **Don't combine `Depends(get_current_user)` with a role check.** Use `require_role(...)` instead.
4. **Never hand-roll auth checks in a route body.** No `if user.role != Role.ADMIN: raise ...`. If the rule is more nuanced than a single-role rank, that's an application-handler concern; let the handler raise `ForbiddenError`.
5. **Never decode the bearer token outside `get_current_user`.** No `jwt.decode` in routes, no manual `Authorization` header parsing.
6. **Never catch `UnauthorizedError` / `ForbiddenError`.** They propagate to the central error handler.
7. **Authentication is mandatory by default.** "Trusted internal" routes that skip auth are forbidden; internal-only access is enforced at the network/gateway layer.

### Coordinated error-code advertisement

Every route that uses an auth dependency must list the matching status codes when `restapi-error-responses` runs:

- `Depends(get_current_user)` → include `401`.
- `Depends(require_role(...))` → include `401` **and** `403`.

The auth choice from this skill drives the `error_codes` input to `restapi-error-responses` — if a route uses `require_role(...)` but the spec omits `403` from `error_codes`, that's a spec bug.

## Hard stops

- Spec asks the route to inline a role check after `get_current_user` → stop, use `require_role(...)` instead.
- Spec asks for a custom JWT verifier per route → stop, the verifier lives in `containers.py`; routes use the standard dependency.
- Spec asks the route to read the `Authorization` header directly → stop, that's what the bearer scheme is for.
- Spec asks to omit auth on a non-public route → stop, default is authenticated; only health/info endpoints are public.
- Spec proposes a third auth dependency type → stop, the two declared by `restapi-app-bootstrap` are exhaustive; introduce a finer-grained authorization rule in the application handler instead.
- Role-gated route's `error_codes` (for `restapi-error-responses`) omits `403` → stop, the advertised codes must match the chosen dependency.
