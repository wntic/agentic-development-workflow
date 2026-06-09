---
name: restapi-auth-dependency
description: Reference skill consulted by `restapi-endpoint` and `restapi-file-transfer` when they need to decide which auth dependency a route attaches. Routes use exactly two FastAPI dependencies, declared once by `restapi-app-bootstrap` in `restapi/dependencies.py`: `get_current_user` (any-authenticated) and `require_role(Role.X)` (role-gated). This skill is a decision rule plus binding convention (`_: CurrentUser` vs `user: CurrentUser`) — it produces no file. Does not write the route (use `restapi-endpoint`), advertise the error codes the chosen dependency raises (use `restapi-error-responses`), or change the dependency module itself (that lives in `restapi-app-bootstrap`).
---

# REST API Auth Dependency

A reference rule for choosing the right auth dependency on each route. Both dependencies live in `src/<root>/restapi/dependencies.py` (produced by `restapi-app-bootstrap`) and are imported as `from ..dependencies import get_current_user, require_role` inside router files.

**Auth is a manifest-declared feature, not a universal.** A route is authenticated only when its endpoint declares `auth != anonymous`; "this app has auth" is a property of the graph — true when any endpoint declares `auth != anonymous`, or a token-verifier capability is wired — not a separate manifest flag. An app whose every endpoint is anonymous has **no auth layer at all**: no `restapi/dependencies.py`, no `CurrentUser`/`Role`, no `get_current_user`/`require_role`, and every route attaches **no** auth dependency (and advertises no 401/403). Everything below applies only to the routes an authed app gates; on an auth-less app there is nothing here to apply — that is not "skipping auth", it is the absence of the feature.

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
| Public route (health/info), **or any route in an app that declares no auth** | none | n/a |

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
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    ...
    await handler.execute(CreateFooCommand(caller_id=user.id, ...))
```

### Role rank (reference)

`Role` is a rank-ordered `StrEnum` whose members the manifest's `domain.enums` declares (the Helpdesk fixture's are `COLLABORATOR < ADMIN < SUPER_ADMIN`, illustrative only — another app may have a two-tier or differently-named ladder). `user.role.satisfies(required)` returns `true` when the caller's rank meets or exceeds the requirement, and `require_role(Role.<MIN_RANK>)` admits that rank and every higher one. Use the placeholder `Role.<MIN_RANK>` in templates — the concrete member comes from the route's declared auth requirement against the app's own `Role`, never a fixed `SUPER_ADMIN`.

### Constraints on every route that uses an auth dependency

1. **Auth dependency is the last parameter on every route.** Path/body/`request`/query params come first; identity last.
2. **`require_role(Role.X)` is called inline** at each route. Don't memoize at module level (`_admin = require_role(Role.ADMIN)`) — keeping the role visible at the call site is the most important detail in a route review.
3. **Don't combine `Depends(get_current_user)` with a role check.** Use `require_role(...)` instead.
4. **Never hand-roll auth checks in a route body.** No `if user.role != Role.ADMIN: raise ...`. If the rule is more nuanced than a single-role rank, that's an application-handler concern; let the handler raise `ForbiddenError`.
5. **Never decode the bearer token outside `get_current_user`.** No `jwt.decode` in routes, no manual `Authorization` header parsing.
6. **Never catch `UnauthorizedError` / `ForbiddenError`.** They propagate to the central error handler.
7. **Within an app that declares auth, authentication is the default for non-public routes.** "Trusted internal" routes that skip auth (in an authed app) are forbidden; internal-only access is enforced at the network/gateway layer. This does **not** manufacture auth on an app whose manifest declares none — see the opening note: an auth-less app has no auth layer to default to.

### Coordinated error-code advertisement

Every route that uses an auth dependency must list the matching status codes when `restapi-error-responses` runs:

- `Depends(get_current_user)` → include `401`.
- `Depends(require_role(...))` → include `401` **and** `403`.

The auth choice from this skill drives the `error_codes` input to `restapi-error-responses` — if a route uses `require_role(...)` but the spec omits `403` from `error_codes`, that's a spec bug.

## Hard stops

- Spec asks the route to inline a role check after `get_current_user` → stop, use `require_role(...)` instead.
- Spec asks for a custom JWT verifier per route → stop, the verifier lives in `containers.py`; routes use the standard dependency.
- Spec asks the route to read the `Authorization` header directly → stop, that's what the bearer scheme is for.
- Spec asks to omit auth on a non-public route of an app that **does** declare auth → stop, default is authenticated; only health/info endpoints are public. (Distinct from an app that declares no auth at all — there every route is auth-free by construction; that is the absence of the feature, not "omitting auth".)
- Spec proposes a third auth dependency type → stop, the two declared by `restapi-app-bootstrap` are exhaustive; introduce a finer-grained authorization rule in the application handler instead.
- Role-gated route's `error_codes` (for `restapi-error-responses`) omits `403` → stop, the advertised codes must match the chosen dependency.
