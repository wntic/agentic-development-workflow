---
name: test-discovery-invariants
description: The one-shot cross-cutting tests that derive their inputs from the running app instead of a hand-kept registry — unauthenticated routes return 401, every OpenAPI operation advertises the codes its route can produce, CORS, the request-size cap, plus a unit-level smoke that constructs the app so a construct-time failure goes red. Adding an endpoint never edits them.
when_to_use: Laying the discovery-driven cross-cutting tests for a project, or changing one of them.
paths: tests/**
---

# Test — Discovery Invariants

One-shot per project. Four or five integration files under `tests/integration/api/` (the `test_unauth_returns_401.py` probe is emitted only when the app declares auth — see Rules) plus one unit-level app-construction smoke. Each one iterates — or constructs — the running app and asserts a single global property; none of them needs to be edited when an endpoint is added or removed.

## When to use vs. neighbours

- Laying the cross-cutting tests for the first time → this skill.
- A per-endpoint integration test → `test-restapi-endpoint`.
- The rollback fixture / containers / `real_app` → `testing-integration-setup` (owns `real_app`, which every test here imports).
- The `authed_client` factory → `testing-integration-setup` (not consumed here — see Rule 8).
- A grep-firewall static rule → `test-architecture-rule` (compile-time, not runtime).

## Template(s)

```
tests/integration/api/
├── test_openapi_advertises_error_codes.py   # always
├── test_cors.py                             # always
├── test_unauth_returns_401.py               # auth apps only (Rule 11)
├── test_request_size_limit.py               # only if a size-cap middleware is declared (Hard stops)
└── test_info.py                             # only if an info/health endpoint is declared (Rule 11)
tests/unit/restapi/
└── test_app_constructs.py                   # always — unit-level construct smoke, no DB (Rule 12)
```

### `tests/unit/restapi/test_app_constructs.py`

```python
from myapp.containers import Container
from myapp.restapi.main import create_app


def test_app_constructs_and_renders_openapi() -> None:
    """Smoke: the composition root + app shell wire up, and the OpenAPI schema
    renders over every route. This is the ONLY place a construct-time failure
    surfaces — a missing framework dependency FastAPI imports at app-build time
    (e.g. `python-multipart` for a Form(...)/UploadFile route, raised at
    create_app, never at type-check), broken middleware wiring, or a route
    whose response schema won't build. mypy / ruff / handler unit tests all
    stay green through these; constructing the app does not."""
    app = create_app(container=Container())
    assert app.openapi()["paths"]  # forces the full schema build over every route
```

This lives at the **unit** layer, not under `tests/integration/`, on purpose: `create_app` needs **no** database — `dependency-injector` providers are lazy, so it wires routers/middleware/error-handlers without resolving a handler or opening a connection. Placing it under `tests/integration/` would drag that tree's session-autouse `_migrated_db` / `_guard_against_real_db` fixtures and require Postgres, defeating the point — the construct-time defect class must be catchable with no Docker daemon (exactly the environment where mypy/ruff/unit run green and miss it). The test is structural, not a body test: it passes on freshly laid routes (the functions exist with valid signatures; their `NotImplementedError` bodies are never *called* by construction or `openapi()`), so a missing dependency reds it as soon as the routes exist, before their bodies are filled.

### `test_unauth_returns_401.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from httpx import ASGITransport, AsyncClient

from myapp.domain.exceptions import UnauthorizedError
from myapp.restapi.dependencies import get_current_user

def _api_operations(app: FastAPI) -> list[RouteContext]:
    """Every API operation the app serves, one route context each.

    Walked with `iter_route_contexts` and NOT by filtering `app.routes` for
    `APIRoute`: a FastAPI that defers `include_router` leaves a router
    placeholder in `app.routes` and not one `APIRoute`, so the filtering walk
    finds zero on a live version of the framework — measured. The context walk
    is the one FastAPI's own OpenAPI generator uses, and it finds the
    operations whether the framework expanded the routers or not.

    Two things come with the context and not with the route object: the
    EFFECTIVE path (the `include_router(prefix=...)` one, which is what a
    client must request) and the dependencies that `include_router(...,
    dependencies=[...])` added — so router-level auth is seen here."""
    return [
        context
        for context in iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute)
    ]

def _is_protected(context: RouteContext) -> bool:
    """A route is protected iff its dependency tree includes `get_current_user`
    or `require_role`. Public routes (info, health, OpenAPI itself) are
    naturally excluded.

    `dependant` is a FastAPI route INTERNAL — not part of the typed public
    surface, and across FastAPI versions mypy may not see it. Reach it via
    `getattr` so the test type-checks on whatever version `uv` pins; the
    attribute is present at runtime."""
    dependant = getattr(context, "dependant", None)
    for dep in getattr(dependant, "dependencies", []):
        if dep.call is get_current_user:
            return True
        if getattr(dep.call, "required_role", None) is not None:
            return True  # a _RoleDependency from require_role(Role.X) (see restapi-auth-dependency)
    return False

def _protected_routes(app: FastAPI) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for context in _api_operations(app):
        path = context.path
        if path is None or not _is_protected(context):
            continue
        for method in context.methods or set():  # Starlette types `methods` as set[str] | None
            if method == "HEAD":
                continue
            out.append((method, path))
    return out

async def test_the_walk_found_protected_routes_to_probe(real_app: FastAPI) -> None:
    """The net under the parametrized probe below, and the reason it is a test
    of its own: an empty parameter set does not fail, it SKIPS — measured,
    pytest reports `got empty parameter set` and the run stays green. So a walk
    that discovers nothing takes this whole file out of the run in silence, and
    the silence is indistinguishable from an app with no protected routes. This
    net runs whatever the walk returns, and it tells the two apart."""
    assert _api_operations(real_app), "no API operation was discovered, so nothing was probed"
    assert _protected_routes(real_app), (
        "API operations were discovered but none of them is protected, in an app that "
        "declares auth — either the auth dependency is not wired or the walk missed it"
    )

async def test_protected_route_returns_401_without_token(
    method: str, path: str, real_app: FastAPI
) -> None:
    # `method` / `path` are parametrized by `pytest_generate_tests` below.
    async with AsyncClient(
        transport=ASGITransport(app=real_app),
        base_url="http://testserver",
    ) as client:
        # Substitute path params with `0` / dummy UUIDs to satisfy routing.
        url = path
        for placeholder in ("{id}", "{foo_id}", "{bar_id}"):
            url = url.replace(placeholder, "00000000-0000-0000-0000-000000000000")
        response = await client.request(method, url)

    assert response.status_code == 401
    body = response.json()
    # The code CONSTANT is the contract, not its literal string — assert against
    # the domain exception's own `.code` (mirrors test-restapi-endpoint Rule 9).
    assert body["code"] == UnauthorizedError.code
    # Only the challenge SCHEME is load-bearing (RFC 7235). The realm is app-specific;
    # assert the scheme is present, never freeze a `realm="<app>"` string.
    assert response.headers.get("WWW-Authenticate", "").startswith("Bearer")

def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Discover protected routes at collection time by importing `create_app`
    once. Keeps test parametrization tied to the actual route graph instead
    of a hand-maintained list."""
    if "method" in metafunc.fixturenames and "path" in metafunc.fixturenames:
        from myapp.containers import Container
        from myapp.restapi.main import create_app

        app = create_app(container=Container())
        cases = _protected_routes(app)
        metafunc.parametrize("method,path", cases, ids=[f"{m} {p}" for m, p in cases])
```

### `test_openapi_advertises_error_codes.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

def _declared_codes(app: FastAPI) -> dict[tuple[str, str], set[int]]:
    """For each (METHOD, path), the set of HTTP error codes the route
    declares in OpenAPI via `responses=error_responses(...)`."""
    spec = app.openapi()
    out: dict[tuple[str, str], set[int]] = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method.upper() == "HEAD":
                continue
            codes = {int(c) for c in op.get("responses", {}) if c.isdigit() and int(c) >= 400}
            out[(method.upper(), path)] = codes
    return out

def _api_operations(app: FastAPI) -> list[RouteContext]:
    """Every API operation the app serves, one route context each.

    Walked with `iter_route_contexts` and NOT by filtering `app.routes` for
    `APIRoute`: a FastAPI that defers `include_router` leaves a router
    placeholder in `app.routes` and not one `APIRoute`, so the filtering walk
    finds zero on a live version of the framework — measured. The context walk
    is the one FastAPI's own OpenAPI generator uses, and it finds the
    operations whether the framework expanded the routers or not. It also
    reports each route under its EFFECTIVE path — the one the document keys
    on — so an include-time prefix does not desynchronise the two sides."""
    return [
        context
        for context in iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute)
    ]

def _expected_codes_from_route(context: RouteContext) -> set[int]:
    """The set of error codes the route's decorator advertised. FastAPI
    stores them on `responses` as the dict produced by `error_responses(...)`.
    `responses` is a route internal mypy may not see (see `_is_protected`'s
    note in the 401 probe) — reach it via `getattr`; present at runtime."""
    responses = getattr(context, "responses", {})
    return {code for code in responses if isinstance(code, int) and code >= 400}

async def test_every_route_advertises_what_its_decorator_declared(
    real_app: FastAPI,
) -> None:
    operations = _api_operations(real_app)
    # The failure this file must not have is silence: a walk that discovers no
    # operation compares no operation, and `mismatches == []` then passes green
    # having proved nothing. Measured on a live FastAPI, so this is not a
    # precaution — it is the shape the previous walk actually degenerated into.
    assert operations, "no API operation was discovered, so nothing was compared"

    declared = _declared_codes(real_app)
    mismatches: list[str] = []

    for context in operations:
        path = context.path
        if path is None:
            continue
        for method in context.methods or set():  # Starlette types `methods` as set[str] | None
            if method == "HEAD":
                continue
            spec_codes = declared.get((method, path), set())
            decorator_codes = _expected_codes_from_route(context)
            missing = decorator_codes - spec_codes
            extra = spec_codes - decorator_codes
            if missing or extra:
                mismatches.append(
                    f"{method} {path}: decorator={sorted(decorator_codes)} "
                    f"spec={sorted(spec_codes)} missing={sorted(missing)} extra={sorted(extra)}"
                )

    assert mismatches == [], "OpenAPI / decorator mismatch:\n" + "\n".join(mismatches)
```

### `test_cors.py`

```python
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _configured_origin(app: FastAPI) -> str | None:
    """Read a real allowed origin off the app's CORS middleware, instead of
    hardcoding one. Returns None when the app configures no CORS."""
    # Starlette types `Middleware.cls` as `_MiddlewareFactory[P]` and `.kwargs`
    # as `P.kwargs` (effectively untyped) — match by class name and `cast` the
    # kwargs to a dict to read off them under strict mypy (no `# type: ignore`).
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", "") == "CORSMiddleware":
            origins = cast(dict[str, Any], mw.kwargs).get("allow_origins", [])
            return origins[0] if origins else None
    return None


async def test_cors_preflight_echoes_a_configured_origin(real_app: FastAPI) -> None:
    origin = _configured_origin(real_app)
    if origin is None:
        pytest.skip("app configures no CORS allow_origins")

    async with AsyncClient(
        transport=ASGITransport(app=real_app),
        base_url="http://testserver",
    ) as client:
        response = await client.options(
            "/",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    assert response.headers.get("access-control-allow-origin") == origin
```

### `test_request_size_limit.py`

```python
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _max_request_bytes(app: FastAPI) -> int | None:
    """The configured cap of the request-size middleware, read off the app.
    Returns None when the app declares no such middleware (the kwarg name
    matches the middleware's config field — see restapi-middleware)."""
    # See `_configured_origin` in test_cors.py — `Middleware.cls` / `.kwargs`
    # are effectively untyped; match by class name and `cast` the kwargs.
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", "") == "MaxRequestSizeMiddleware":
            max_bytes = cast(dict[str, Any], mw.kwargs).get("max_bytes")
            return max_bytes if isinstance(max_bytes, int) else None
    return None


async def test_oversize_payload_returns_413(real_app: FastAPI) -> None:
    limit = _max_request_bytes(real_app)
    if limit is None:
        pytest.skip("app declares no request-size middleware")

    payload = b"x" * (limit + 1)
    async with AsyncClient(
        transport=ASGITransport(app=real_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/foos",
            content=payload,
            headers={"Content-Type": "application/octet-stream"},
        )

    assert response.status_code == 413
```

### `test_info.py`

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

async def test_info_endpoint_is_public_and_returns_200(real_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=real_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/info")

    assert response.status_code == 200
```

## Rules

1. **Every test discovers its inputs from `real_app`** — never from a hand-written `_endpoints()` / `_EXPECTED` / `RESOURCES` table. The cost of adding a new endpoint must be zero in this directory.
2. **Protected-route detection is structural, not by-name.** Walk `route.dependant.dependencies`; check identity against `get_current_user` / `require_role` instead of string-matching the function name. Renamed dependencies are caught by import, not by silent miss.
3. **The 401 test substitutes path placeholders with valid-shaped dummies.** A test for `GET /foos/{id}` with literal `{id}` in the URL hits the router as 404 instead of triggering auth. UUID-shaped placeholders (`00000000-...`) route correctly and the request reaches the auth dependency.
4. **OpenAPI cross-check compares decorator-declared codes to spec codes.** `route.responses` is FastAPI's authoritative store of what the `responses=error_responses(...)` decorator put there. The OpenAPI spec is generated from the same source; this test catches FastAPI bugs and decorator mismatches alike.
5. **Each file holds one invariant.** Don't merge `test_cors.py` and `test_request_size_limit.py` even though both are tiny — failures in one don't mask the other, and the file names form the spec.
6. **CORS test uses an OPTIONS preflight.** Asserting on a GET response's `Access-Control-Allow-Origin` is a softer test; the preflight is the one browsers actually consult.
7. **Request-size test uses raw bytes**, not JSON-encoded data, to bypass schema validation and hit the middleware directly. Otherwise the response is `422` (validation) before the middleware sees the body.
8. **No `authed_client` here.** All discovery tests are either unauth probes or read OpenAPI / route metadata. If a discovery test needs auth, it's a per-endpoint concern that belongs in `test-restapi-endpoint`.
9. **No `@pytest.mark.integration` and no `@pytest.mark.asyncio`** — path-based collection and auto mode handle both.
10. **`pytest_generate_tests` for parametrized discovery.** Using `pytest.fixture` + parametrize at function scope can't both reference the same dynamically-discovered list cleanly; `pytest_generate_tests` is the standard hook.
11. **`test_unauth_returns_401.py` is auth-gated, like `test_info.py` is `/info`-gated.** Its module-level `from myapp.restapi.dependencies import get_current_user` + `from myapp.domain.exceptions import UnauthorizedError` exist **only** when the app declares auth (auth-presence is graph-derived — any endpoint `auth != anonymous` / a token-verifier capability). In an all-anonymous app there is no `dependencies.py`, no `UnauthorizedError`, and no protected route to probe, so the file would fail to import at collection time and take down the whole `tests/integration/api/` package. Emit five files when the app declares auth, four (drop the 401 file) when it does not.
12. **`test_app_constructs.py` is the always-emitted, unit-level construct smoke.** It is the one file this skill places at `tests/unit/restapi/`, not `tests/integration/api/`, because it needs no database (lazy DI providers → `create_app` opens nothing) and must run with no Docker daemon — the environment where the other gates pass and a construct-time dependency gap (`python-multipart`, …) slips through. Construct via `create_app(container=Container())` directly (no `real_app` fixture), assert `app.openapi()["paths"]`. Sync, no fixtures, no `await`. It is structural (green on freshly laid routes), so every app gets it, auth or not.

## Inlined typing / import rules

- `pytest`, `fastapi`, `fastapi.routing`, `httpx`, `myapp.containers`, `myapp.restapi.main`, `myapp.restapi.dependencies`, `myapp.domain.exceptions` (for the `UnauthorizedError.code` constant the 401 test asserts against).
- Full annotations on every helper.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks to maintain a hand-rolled list of `(method, path, codes)` to compare against → stop, the whole point is discovery from `real_app` / `app.openapi()`.
- Spec asks to add a `@pytest.mark.integration` marker → stop, path-scoped collection handles it.
- Spec asks to fold a new per-endpoint test into one of these files (e.g. "test that POST /foos returns 401 unauth") → stop, the parametrized 401 test already covers it via discovery; add the endpoint and it joins the suite automatically.
- Spec writes the 401 test against a hardcoded URL with literal placeholders (`/foos/{id}`) → stop, substitute UUID-shaped dummies so the route resolves before the auth dependency runs.
- Spec uses string matching to identify "protected" routes (`if "auth" in route.name`) → stop, walk `route.dependant.dependencies` and compare callables by identity.
- Spec compares the OpenAPI spec to a hardcoded `_EXPECTED` table → stop, derive expectations from `route.responses` so the source of truth is the decorator.
- The `real_app` fixture is not defined up-tree (owned by `testing-integration-setup`) → stop, the suite cannot collect without it. (The `authed_client` factory is not consumed here — Rule 8 — so its absence does not block this skill.)
- Spec hardcodes a CORS origin (e.g. `http://localhost:3000`) in `test_cors.py` → stop, read a configured origin off `real_app`'s `CORSMiddleware` and `pytest.skip` when none is configured; never freeze the source app's dev origin or assume `allow_credentials`.
- Spec hardcodes the request-size limit (e.g. 10 MiB) in `test_request_size_limit.py`, or presumes the middleware is always present → stop, read the cap off the app's `MaxRequestSizeMiddleware` and compute `limit + 1`; `pytest.skip` when no size middleware is declared (it is a per-app `restapi.middlewares` entry, not universal).
- Project has no `/info` (or `/health`) endpoint and the spec sets `info_endpoint = none` → produce four files, skip `test_info.py`.
- Project declares no auth (every endpoint anonymous) → do not produce `test_unauth_returns_401.py`; its `get_current_user` / `UnauthorizedError` imports do not exist in an auth-less app, and there are no protected routes to probe (Rule 11).
- Spec freezes the `WWW-Authenticate` challenge to a specific realm (`Bearer realm="myapp"`) → stop, only the scheme is load-bearing (`.startswith("Bearer")`); the realm is app-specific.
- Spec pins the 401 body code to a literal string (`"UNAUTHORIZED"`) → stop, assert against the domain exception's `.code` constant, not a frozen literal.
- Spec proposes placing `test_app_constructs.py` under `tests/integration/` (next to the other discovery tests) → stop, it stays at `tests/unit/restapi/`: under `tests/integration/` the session-autouse `_migrated_db` / `_guard_against_real_db` fixtures would force Postgres on a check that opens no connection, so it could no longer run without a Docker daemon — the one place the construct-time defect class is catchable.
- Spec makes the construct smoke `async` / gives it `real_app` or any DB fixture → stop, it constructs via `create_app(container=Container())` directly and is plain sync; needing a fixture means it is no longer the Docker-less unit smoke.
