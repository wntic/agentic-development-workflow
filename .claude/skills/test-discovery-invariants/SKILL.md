---
name: test-discovery-invariants
description: Apply once per project to install the cross-cutting integration tests that derive their inputs from the running FastAPI app instead of from hand-maintained registries. Produces five test files under `tests/integration/api/` — `test_unauth_returns_401.py` (every authenticated route, discovered via `app.routes`, returns 401 with the documented `code` and `WWW-Authenticate` header when called with no token), `test_openapi_advertises_error_codes.py` (every operation in `app.openapi()` declares all the error codes the route can produce, derived from the `error_responses(...)` decorator), `test_cors.py`, `test_request_size_limit.py` (`413` when exceeding `MaxRequestSizeMiddleware`), and `test_info.py` (or `test_health.py`). Adding a new endpoint never requires editing any of these files — discovery handles it. Does not produce per-endpoint tests (use `test-restapi-endpoint`), the rollback fixture (use `test-integration-isolation`), the `authed_client` factory (use `test-integration-authed-client`), or any registry-style table.
---

# Test — Discovery Invariants

One-shot per project. Five test files. Each one iterates the running app and asserts a single global property; none of them needs to be edited when an endpoint is added or removed.

## When to use vs. neighbours

- First-time scaffold of the cross-cutting tests → this skill.
- A per-endpoint integration test → `test-restapi-endpoint`.
- The rollback fixture / containers / `real_app` → `test-integration-isolation` (owns `real_app`, which every test here imports).
- The `authed_client` factory → `test-integration-authed-client` (not consumed here — see Rule 8).
- A grep-firewall static rule → `test-architecture-rule` (compile-time, not runtime).

## Template(s)

```
tests/integration/api/
├── test_unauth_returns_401.py
├── test_openapi_advertises_error_codes.py
├── test_cors.py
├── test_request_size_limit.py
└── test_info.py
```

### `test_unauth_returns_401.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from myapp.restapi.dependencies import get_current_user

def _is_protected(route: APIRoute) -> bool:
    """A route is protected iff its dependency tree includes `get_current_user`
    or `require_role`. Public routes (info, health, OpenAPI itself) are
    naturally excluded."""
    for dep in route.dependant.dependencies:
        if dep.call is get_current_user:
            return True
        if getattr(dep.call, "__wrapped_role__", None) is not None:
            return True  # require_role(Role.X) marker (see restapi-auth-dependency)
    return False

def _protected_routes(app: FastAPI) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_protected(route):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            out.append((method, route.path))
    return out

@pytest.mark.parametrize("method,path", _protected_routes_at_collection_time := None)
async def test_protected_route_returns_401_without_token(method: str, path: str, real_app):
    # The parametrize id is recomputed at collection time below — see _ids() helper.
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
    assert body["code"] == "UNAUTHORIZED"
    assert response.headers.get("WWW-Authenticate", "").startswith('Bearer realm="myapp"')

def pytest_generate_tests(metafunc):
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
from fastapi.routing import APIRoute

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

def _expected_codes_from_route(route: APIRoute) -> set[int]:
    """The set of error codes the route's decorator advertised. FastAPI
    stores them on `route.responses` as the dict produced by `error_responses(...)`."""
    return {code for code in route.responses if isinstance(code, int) and code >= 400}

async def test_every_route_advertises_what_its_decorator_declared(real_app):
    declared = _declared_codes(real_app)
    mismatches: list[str] = []

    for route in real_app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            spec_codes = declared.get((method, route.path), set())
            decorator_codes = _expected_codes_from_route(route)
            missing = decorator_codes - spec_codes
            extra = spec_codes - decorator_codes
            if missing or extra:
                mismatches.append(
                    f"{method} {route.path}: decorator={sorted(decorator_codes)} "
                    f"spec={sorted(spec_codes)} missing={sorted(missing)} extra={sorted(extra)}"
                )

    assert mismatches == [], "OpenAPI / decorator mismatch:\n" + "\n".join(mismatches)
```

### `test_cors.py`

```python
import pytest
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient


def _configured_origin(app) -> str | None:
    """Read a real allowed origin off the app's CORS middleware, instead of
    hardcoding one. Returns None when the app configures no CORS."""
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            origins = mw.kwargs.get("allow_origins", [])
            return origins[0] if origins else None
    return None


async def test_cors_preflight_echoes_a_configured_origin(real_app):
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
import pytest
from httpx import ASGITransport, AsyncClient


def _max_request_bytes(app) -> int | None:
    """The configured cap of the request-size middleware, read off the app.
    Returns None when the app declares no such middleware (the kwarg name
    matches the middleware's config field — see restapi-middleware)."""
    for mw in app.user_middleware:
        if mw.cls.__name__ == "MaxRequestSizeMiddleware":
            return mw.kwargs.get("max_bytes")
    return None


async def test_oversize_payload_returns_413(real_app):
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
from httpx import ASGITransport, AsyncClient

async def test_info_endpoint_is_public_and_returns_200(real_app):
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

## Inlined typing / import rules

- `pytest`, `fastapi`, `fastapi.routing`, `httpx`, `myapp.containers`, `myapp.restapi.main`, `myapp.restapi.dependencies`.
- Full annotations on every helper.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks to maintain a hand-rolled list of `(method, path, codes)` to compare against → stop, the whole point is discovery from `real_app` / `app.openapi()`.
- Spec asks to add a `@pytest.mark.integration` marker → stop, path-scoped collection handles it.
- Spec asks to fold a new per-endpoint test into one of these files (e.g. "test that POST /foos returns 401 unauth") → stop, the parametrized 401 test already covers it via discovery; add the endpoint and it joins the suite automatically.
- Spec writes the 401 test against a hardcoded URL with literal placeholders (`/foos/{id}`) → stop, substitute UUID-shaped dummies so the route resolves before the auth dependency runs.
- Spec uses string matching to identify "protected" routes (`if "auth" in route.name`) → stop, walk `route.dependant.dependencies` and compare callables by identity.
- Spec compares the OpenAPI spec to a hardcoded `_EXPECTED` table → stop, derive expectations from `route.responses` so the source of truth is the decorator.
- The `real_app` fixture is not defined up-tree (owned by `test-integration-isolation`) → stop, the suite cannot collect without it. (The `authed_client` factory is not consumed here — Rule 8 — so its absence does not block this skill.)
- Spec hardcodes a CORS origin (e.g. `http://localhost:3000`) in `test_cors.py` → stop, read a configured origin off `real_app`'s `CORSMiddleware` and `pytest.skip` when none is configured; never freeze the source app's dev origin or assume `allow_credentials`.
- Spec hardcodes the request-size limit (e.g. 10 MiB) in `test_request_size_limit.py`, or presumes the middleware is always present → stop, read the cap off the app's `MaxRequestSizeMiddleware` and compute `limit + 1`; `pytest.skip` when no size middleware is declared (it is a per-app `restapi.middlewares` entry, not universal).
- Project has no `/info` (or `/health`) endpoint and the spec sets `info_endpoint = none` → produce four files, skip `test_info.py`.
