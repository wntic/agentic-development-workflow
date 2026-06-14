---
name: test-integration-authed-client
description: Apply once per project to install the authenticated HTTP client factory the integration suite uses. Produces `tests/integration/api/conftest.py` with the `authed_client` fixture (an async-context-manager factory minting fresh JWTs and wrapping `httpx.AsyncClient` over `ASGITransport(real_app)`), the supporting `rsa_keypair` + `jwt_settings` session fixtures, and the `tests/helpers/jwt.py` `sign_token(...)` helper. After this skill lands, every integration test that needs an authenticated HTTP call uses `async with authed_client(role=...) as client:` (app-specific claims passed as keyword args) — no raw `AsyncClient` construction, no token minting at the test site, no per-resource JWT helpers. Does not produce the rollback fixture (use `test-integration-isolation`), per-resource row fixtures (those live in the sibling `<resource>/conftest.py`), or any test file (use `test-restapi-endpoint`).
---

# Test — Integration Authed Client

One-shot per project. Owns the JWT-minting `authed_client` factory and the keys it depends on. Every integration test that needs an authenticated HTTP call consumes this fixture; no other place in the test tree may construct `AsyncClient(transport=ASGITransport(...))` directly for an authenticated request.

**Applies only to an app that declares auth.** This is the auth test-bootstrap — the same trigger that pulls `cryptography` into the dependency manifest (`conventions` block D). An auth-less app (every endpoint anonymous) has no authenticated client to mint, so it skips this skill and the auth fixtures it owns — `authed_client`, `rsa_keypair`, `jwt_settings`. It does **not** skip `tests/integration/api/conftest.py` as a file: that module is the api-integration suite's shared-fixture container (the standard pytest convention for fixtures visible to every test under `tests/integration/api/`), and auth is merely its current sole occupant. An auth-less app simply has none of these auth fixtures in that conftest (and, until something else populates it, no reason to create the file at all) — the skip is of the auth fixtures, not of the shared container per se.

## When to use vs. neighbours

- First-time scaffold of `tests/integration/api/conftest.py` → this skill.
- The rollback fixture, `sf`, `real_app` (DI override) → `test-integration-isolation` (one-shot, runs first).
- The cross-cutting "every protected route returns 401 unauth" / OpenAPI invariants → `test-discovery-invariants` (consumes `real_app` directly, not `authed_client`).
- A per-endpoint integration test → `test-restapi-endpoint` (consumes `authed_client`).
- The auth dependencies on the route side (`get_current_user`, `require_role`) → `restapi-auth-dependency` (route-side, not test-side).

## Template(s)

```
tests/
├── helpers/
│   ├── __init__.py
│   └── jwt.py
└── integration/api/
    └── conftest.py
```

### `tests/helpers/jwt.py`

```python
import datetime as _dt
from uuid import uuid4

import jwt

__all__ = ["sign_token"]

def sign_token(
    claims: dict[str, object],
    *,
    private_pem: str,
    issuer: str,
    audience: str,
    algorithm: str = "RS256",
    ttl_seconds: int = 300,
) -> str:
    now = _dt.datetime.now(_dt.UTC)
    payload = {
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + _dt.timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": uuid4().hex,
        **claims,
    }
    return jwt.encode(payload, private_pem, algorithm=algorithm)
```

### `tests/integration/api/conftest.py`

```python
from collections.abc import Callable
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from myapp.domain.auth import Role
from myapp.infrastructure.jwt.settings import JwtSettings

from tests.helpers.jwt import sign_token

@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem

@pytest.fixture(scope="session")
def jwt_settings(rsa_keypair: tuple[str, str]) -> JwtSettings:
    _, public_pem = rsa_keypair
    return JwtSettings(
        algorithm="RS256",
        public_key=public_pem,
        issuer="test-issuer",
        audience="test-audience",
    )

@pytest.fixture
def authed_client(
    real_app: FastAPI,
    rsa_keypair: tuple[str, str],
    jwt_settings: JwtSettings,
) -> Callable[..., AsyncClient]:
    """Factory that mints a fresh JWT and returns an `AsyncClient` bound to
    `real_app`. Each call mints a new token; the client is an async context
    manager — always use `async with authed_client(...) as client:` so the
    underlying ASGI transport is closed at the end of the test."""
    private_pem, _ = rsa_keypair

    def _factory(
        role: Role,
        **extra_claims: object,
    ) -> AsyncClient:
        # Mint only the universal claims every verifier needs (sub + role). Any
        # app-specific claim (tenant/org id, display names, …) is the caller's to
        # pass via **extra_claims — never bake one app's identity model in here.
        claims = {
            "sub": str(uuid4()),
            "role": role.value,
            **extra_claims,
        }
        token = sign_token(
            claims,
            private_pem=private_pem,
            issuer=jwt_settings.issuer,
            audience=jwt_settings.audience,
            algorithm=jwt_settings.algorithm,
        )
        transport = ASGITransport(app=real_app)
        return AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        )

    return _factory
```

### Per-resource `conftest.py` is **not** owned here

Per-resource fixtures (`make_foo`, `foo_id`, `bar_id`, …) live in `tests/integration/api/<resource>/conftest.py` next to the endpoint tests that use them. This skill does not write them; `test-restapi-endpoint` references them but expects the consuming spec to declare what it needs.

## Fixture-resolution coupling with `test-integration-isolation`

`real_app` (defined up-tree in `tests/integration/conftest.py` by `test-integration-isolation`) declares `jwt_settings` as one of its parameters and calls `container.jwt_settings.override(jwt_settings)`. Pytest resolves that name by walking the conftest hierarchy from the running test outward — for tests under `tests/integration/api/`, the `jwt_settings` fixture produced here is visible. Without this override, every `authed_client`-minted token would be signed with the test keypair but verified against the production public key the container loaded at startup — every authenticated test would fail with 401.

The coupling has a cost: `real_app` cannot be used from tests outside `tests/integration/api/` (e.g. `tests/integration/postgres/`), because `jwt_settings` isn't visible there. That's fine — repository contract tests use `sf` directly and never construct the FastAPI app.

## Rules

1. **`authed_client` is the single sanctioned authenticated client.** Direct `AsyncClient(transport=ASGITransport(app=real_app))` with a hand-rolled `Authorization` header is forbidden in any test file. Raw `AsyncClient` with no Authorization header is allowed only for `test-discovery-invariants` unauth probes.
2. **Always `async with authed_client(...) as client:`.** Bare assignment (`client = authed_client(role=...)`) leaks the ASGI transport and produces "Cannot reuse a consumed `AsyncClient`" or resource-warning noise in CI. The async-context-manager form is non-negotiable.
3. **Each call mints a fresh JWT.** Tokens are not reused across tests, calls, or roles. A test that needs two roles in one body calls `authed_client(...)` twice.
4. **Mint only the universal claims; pass app-specific ones via `extra_claims`.** The factory bakes in just `sub` and `role` — the claims every verifier needs. Any app-specific claim (tenant/org id, display name, …) is the caller's to pass via `extra_claims`, pinned only when a test must share it with a fixture row (don't reuse such a value across unrelated tests). Never hardcode one app's identity model into the factory.
5. **`rsa_keypair` and `jwt_settings` are session-scoped.** Generating an RSA key is expensive (~100ms); generating per test would dominate suite wall time.
6. **Algorithm matches production.** If production verifies `RS256`, the fixture signs `RS256` — never substitute `HS256` "for speed". The verifier in `real_app` uses `jwt_settings.algorithm`, so the test and prod paths must agree.
7. **No `localhost` / `127.0.0.1` base URL.** `http://testserver` is the convention; the ASGI transport short-circuits the network anyway, but `testserver` makes route logs distinguishable from real traffic in CI logs.
8. **No mocking of JWT verification.** The verifier in `real_app` validates the token end-to-end against the `jwt_settings.public_key` provided by this skill — that's the integration contract under test.
9. **No global token cache.** Per-test mint is fast (~1ms) and avoids "this test passed because the previous test's token was still cached" failures.
10. **Helpers live in `tests/helpers/`, not in `conftest.py`.** A test that needs `sign_token(...)` for an edge case (expired token, invalid issuer) imports the helper directly. The helper is a plain function — no fixtures wrap it.

## Inlined typing / import rules

- `pytest`, `httpx`, `jwt` (PyJWT), `cryptography.hazmat.*`, stdlib `uuid` / `datetime`, `myapp.domain.auth`, `myapp.infrastructure.jwt.settings`.
- Full annotations on the factory and `_factory` closure.
- No `from __future__ import annotations`.

## Hard stops

- `tests/integration/conftest.py` does not exist (no `real_app` fixture) → stop, install `test-integration-isolation` first.
- Spec proposes a session-scoped `authed_client` "to speed up tests" → stop, the factory is function-scoped because each test's transport must be closed at teardown; the cost is negligible.
- Spec asks to mock the JWT verifier → stop, the integration test signs a real token against the same keypair the verifier validates.
- Spec uses `HS256` in tests while production uses `RS256` (or vice versa) → stop, the algorithm matches production.
- Spec adds a per-resource row factory inside this conftest → stop, those live in `tests/integration/api/<resource>/conftest.py`.
- Spec writes the bearer header by hand inside a test → stop, use `authed_client(...)` so role / org / claim shape are uniform.
- Spec hardcodes `Authorization: Bearer <literal-jwt>` for "expired token" or "invalid claim" tests → stop, mint the test-specific token via `sign_token(...)` from the helper.
