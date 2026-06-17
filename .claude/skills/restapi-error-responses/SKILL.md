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

## Reference — `errors.py` and the translator are owned by `restapi-app-bootstrap`

`restapi/schemas/errors.py` and `restapi/error_handler.py` are created **once** by `restapi-app-bootstrap`, which is their single source of truth — this skill never restates their content (that is what let the two copies drift). Bootstrap owns the `ErrorResponse` wire model, the `error_responses(...)` helper, the `_DESCR` status→label map, and the central `DomainError` translator (one handler over every subclass; `WWW-Authenticate` only for `UnauthorizedError`). This skill **uses** two symbols from `errors.py` and **writes** exactly one, on the rare middleware path:

- **`error_responses(*codes: int) -> dict[int | str, dict[str, Any]]`** — the helper you put on a route decorator. It validates each code against the known set — `{cls.http_status for cls in domain.exceptions.__all__} ∪ set(MIDDLEWARE_ERRORS.values())` — and raises `ValueError` on an unknown one, so OpenAPI can never advertise a status nothing produces. The domain side is **derived dynamically**: a new `DomainError` subclass (via `domain-exception`) widens it automatically, with no append here.
- **`MIDDLEWARE_ERRORS: dict[str, int]`** — the **only** manually-maintained entry in `errors.py`, and this skill's sole write target. Bootstrap creates it **empty** (`{}` — no middleware is presumed); the middleware-code path below adds one row when a declared middleware introduces a status with no `DomainError` behind it (e.g. a size-cap middleware → `{"PAYLOAD_TOO_LARGE": 413}`).

## Standard code sets per operation

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

## Procedure — routine path (route only)

1. Choose the code set from the table above.
2. Add `responses=error_responses(<codes>)` to the route decorator.

That's it. The catalog is dynamic; no further registration needed.

## Procedure — middleware-code path

1. Confirm the status truly has no `DomainError` behind it (the body comes from middleware before the exception handler runs). Otherwise the right answer is `domain-exception`, not this path.
2. Append `("CODE_STRING", <http_status>)` to `MIDDLEWARE_ERRORS` in `restapi/schemas/errors.py` (the only hand-edit to that bootstrap-owned file).
3. If the status is not already a key in the `_DESCR` map (in the same `errors.py`), add a short description there.
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
