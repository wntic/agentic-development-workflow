---
name: testing-integration-setup
description: The one-shot scaffolding the whole integration suite rests on — `tests/integration/conftest.py` with session-scoped containers, a session engine, a function-scoped outer transaction and the `sf` fixture that rolls back at teardown, plus `tests/integration/api/conftest.py` with the `authed_client` factory that mints a fresh JWT per call. Every integration test consumes one or both.
when_to_use: Laying the integration suite's fixtures for a project, or changing the rollback, the containers, or the authenticated-client and JWT fixtures.
paths: tests/**
---

# Testing — Integration Setup

One-shot per project, and everything else in the integration suite depends on it. Two conftest files:

- **`tests/integration/conftest.py`** — the containers, the engine, and the transaction-rollback `sf`.
  The contract: every integration test starts with an empty database, and rows the test (and its handler)
  commit are rolled back at teardown.
- **`tests/integration/api/conftest.py`** — the `authed_client` factory, minting a fresh JWT per call over
  `ASGITransport(real_app)`. Only for an app that has auth.

They are one skill because they are one hierarchy: `real_app` is defined in the outer conftest and
consumes `jwt_settings` from the inner one, and getting that resolution wrong makes every authenticated
test fail with 401. The coupling section below is the reason this pair cannot be documented separately.

**This is the relational-store isolation strategy.** The engine, the Alembic migration run, and the savepoint-rollback `sf` all assume a relational store — the per-test transaction that ROLLBACKs is a SQL-database mechanism. An app whose only datastore is client-style (qdrant / redis / …) has no engine, no migration chain, and cannot use savepoint rollback; it isolates by **per-test namespace + best-effort cleanup** instead (the `s3_prefix` block below is exactly that pattern). Lay the Postgres machinery only when the app has a relational store.

## When to use vs. neighbours

- Laying either conftest for the first time, or changing a fixture in one → this skill.
- Per-resource row factories (`make_org`, `make_tag`, …) → not this skill; declare them in `tests/integration/api/<resource>/conftest.py` next to the tests that use them.
- A repository contract test → `testing-contract` (consumes `sf`).
- An API endpoint test → `test-restapi-endpoint` (consumes both `sf` and `authed_client`).
- The cross-cutting unauth / OpenAPI invariants → `test-discovery-invariants` (consumes `real_app`
  directly, never `authed_client`).
- The route-side auth dependencies (`get_current_user`, `require_role`) → `restapi-route-contracts`.
- Cross-cutting "every route returns 401 unauth" / "OpenAPI codes match `error_responses(...)`" → `test-discovery-invariants`.

## Template(s)

### `tests/integration/conftest.py`

```python
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from typing import TypedDict

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from myapp.infrastructure.jwt.settings import JwtSettings  # AUTH-ONLY: drop with the jwt_settings param below on an auth-less app
from myapp.infrastructure.postgres.engine import create_engine, dispose_engine
from myapp.infrastructure.postgres.settings import DbSettings
from myapp.infrastructure.s3.settings import StorageSettings

# ---------- container lifecycle (session-scoped) ----------

class PgConn(TypedDict):
    host: str
    port: int
    user: str
    password: str
    name: str

@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PgConn]:
    if os.getenv("CI"):
        yield {
            "host": os.environ["MYAPP_DB_HOST"],
            "port": int(os.environ.get("MYAPP_DB_PORT", "5432")),
            "user": os.environ["MYAPP_DB_USER"],
            "password": os.environ["MYAPP_DB_PASSWORD"],
            "name": os.environ["MYAPP_DB_NAME"],
        }
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine") as pg:
        yield {
            "host": pg.get_container_host_ip(),
            "port": int(pg.get_exposed_port(5432)),
            "user": pg.username,
            "password": pg.password,
            "name": pg.dbname,
        }

@pytest.fixture(scope="session")
def minio_container() -> Iterator[dict[str, str]]:
    if os.getenv("CI"):
        yield {
            "endpoint_url": os.environ["MYAPP_STORAGE_ENDPOINT_URL"],
            "access_key": os.environ["MYAPP_STORAGE_ACCESS_KEY"],
            "secret_key": os.environ["MYAPP_STORAGE_SECRET_KEY"],
        }
        return

    from testcontainers.minio import MinioContainer

    # Pin the image tag — never float on :latest (mirrors postgres:17-alpine above
    # and the conventions "no floating versions" rule; :latest makes the suite
    # non-reproducible). MinIO publishes RELEASE.<date> tags; the specific pin is a
    # per-deployment choice, bumped deliberately, not a frozen constant.
    with MinioContainer("minio/minio:RELEASE.2025-04-22T22-12-26Z") as minio:
        yield {
            "endpoint_url": f"http://{minio.get_container_host_ip()}:{minio.get_exposed_port(9000)}",
            "access_key": minio.access_key,
            "secret_key": minio.secret_key,
        }

@pytest.fixture(scope="session")
def db_settings(postgres_container: PgConn) -> DbSettings:
    return DbSettings(
        host=postgres_container["host"],
        port=postgres_container["port"],
        user=postgres_container["user"],
        password=postgres_container["password"],
        name=postgres_container["name"],
        pool_pre_ping=False,
    )

@pytest.fixture(scope="session")
def storage_settings(minio_container: dict[str, str]) -> StorageSettings:
    return StorageSettings(
        endpoint_url=minio_container["endpoint_url"],
        access_key=minio_container["access_key"],
        secret_key=minio_container["secret_key"],
        public_endpoint_url=None,
    )

# ---------- safety guard ----------

@pytest.fixture(scope="session", autouse=True)
def _guard_against_real_db(db_settings: DbSettings) -> None:
    looks_like_testcontainer = db_settings.port != 5432
    has_test_in_name = "test" in db_settings.name.lower()
    if not (looks_like_testcontainer or has_test_in_name):
        raise RuntimeError(
            f"Integration tests refuse to run against "
            f"{db_settings.host}:{db_settings.port}/{db_settings.name}. "
            "The DSN looks like a developer's local database."
        )

# ---------- migrations (once per session) ----------

def _run_alembic(db_settings: DbSettings, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "MYAPP_DB_HOST": db_settings.host,
        "MYAPP_DB_PORT": str(db_settings.port),
        "MYAPP_DB_USER": db_settings.user,
        "MYAPP_DB_PASSWORD": db_settings.password.get_secret_value(),
        "MYAPP_DB_NAME": db_settings.name,
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )

@pytest.fixture(scope="session", autouse=True)
def _migrated_db(_guard_against_real_db: None, db_settings: DbSettings) -> DbSettings:
    result = _run_alembic(db_settings, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return db_settings

# ---------- engine (session-scoped, one per session) ----------

@pytest.fixture(scope="session")
async def _engine(_migrated_db: DbSettings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(_migrated_db)
    try:
        yield engine
    finally:
        await dispose_engine(engine)

# ---------- the load-bearing pair: outer transaction + bound sessionmaker ----------

@pytest.fixture
async def _outer_connection(_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One connection per test. Open it, begin a transaction, hand it out,
    roll it back at teardown. The handler under test can `commit()` as many
    times as it wants — each commit lands as a SAVEPOINT release inside this
    outer transaction, and the final ROLLBACK undoes everything."""
    async with _engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()

@pytest.fixture
def sf(_outer_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    """Sessionmaker bound to the per-test outer connection. Every session
    opened through this factory joins the outer transaction; its commit()
    creates and releases a SAVEPOINT instead of committing to disk.

    This is the *only* sanctioned sessionmaker inside `tests/integration/`.
    Direct `async_sessionmaker(bind=engine, ...)` or `bind=_engine` bypasses
    rollback and leaks rows across tests — never do it."""
    return async_sessionmaker(
        bind=_outer_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

# ---------- DI container override (for API tests) ----------

@pytest.fixture
async def real_app(
    sf: async_sessionmaker[AsyncSession],
    db_settings: DbSettings,
    storage_settings: StorageSettings,  # BLOB-ONLY: present only when the app has a blob store. Drop this param + the storage_settings override/reset below on an app with no S3/MinIO (see the storage-strip Hard stop).
    jwt_settings: JwtSettings,  # AUTH-ONLY: present only when the app declares auth (from test-integration-authed-client). On an auth-less app drop this param (and its import) AND the jwt_settings override/reset lines below — there is no jwt_settings provider to override.
) -> AsyncIterator[FastAPI]:
    """FastAPI app whose container has its DB / storage / session-factory
    / JWT settings overridden to the per-test fixtures. Repositories
    resolved through the container therefore participate in the same
    outer transaction the test fixtures use, and ROLLBACK at teardown
    drops everything they wrote — including rows the route under test
    committed via its handler. The `jwt_settings` override is what makes
    `authed_client`-minted tokens verify against the running app.

    Resolution note: `jwt_settings` is defined down-tree in
    `tests/integration/api/conftest.py`. This fixture works only for
    tests under `tests/integration/api/` (the only place that needs
    `real_app`). Tests in `tests/integration/postgres/` use `sf` directly and
    do not need `real_app`.
    """
    from myapp.containers import Container
    from myapp.restapi.main import create_app

    container = Container()
    container.db_settings.override(db_settings)
    container.storage_settings.override(storage_settings)
    container.session_factory.override(sf)
    container.jwt_settings.override(jwt_settings)

    app = create_app(container=container)
    try:
        yield app
    finally:
        container.jwt_settings.reset_override()
        container.session_factory.reset_override()
        container.storage_settings.reset_override()
        container.db_settings.reset_override()

# ---------- S3 prefix (per-test namespace, no transactions in S3) ----------

@pytest.fixture
def s3_prefix() -> str:
    """Each test owns a unique prefix under the shared bucket. Tests that
    upload blobs must put everything under this prefix; tests that assert
    on bucket contents must filter by it. There is no S3 ROLLBACK — the
    bucket is reset only at session end. Cross-test isolation is by
    namespace, not by cleanup."""
    import uuid
    return f"test-{uuid.uuid4().hex}/"

@pytest.fixture(scope="session", autouse=True)
async def _cleanup_bucket_at_session_end(storage_settings: StorageSettings) -> AsyncIterator[None]:
    yield
    # session-end best-effort cleanup; implementation depends on the s3 helper
```

### `tests/conftest.py` (top-level, optional sub-template)

Leave empty:

```python
```

`pytest-asyncio` mode and plugin declarations belong in `pyproject.toml` under `[tool.pytest.ini_options]`, not here. That block **must** carry `asyncio_mode = "auto"` **and** a **session** loop scope — `asyncio_default_fixture_loop_scope = "session"` + `asyncio_default_test_loop_scope = "session"`. The engine fixture above is session-scoped, so every test and fixture must share ONE event loop: under the default function loop scope the session engine's `asyncpg` connections outlive the loop they were opened on, and any integration test that runs a real statement which errors (a constraint violation through a repository, the canonical repo-contract case) crashes at teardown with `RuntimeError: Event loop is closed` (asyncpg cannot cancel the aborted command on a closed loop). The cheap api-discovery tests hide this — their routes (401 / CORS / OpenAPI) short-circuit before touching Postgres, so no real command runs — which is why it only surfaces once a repository contract test exercises the DB.

**The root `tests/conftest.py` must NOT import `create_app` / `myapp.restapi.main` (nor define a `real_app` / `client` fixture).** pytest applies the root conftest to the WHOLE suite, so a *module-level* `from myapp.restapi.main import create_app` there makes every `tests/unit/**` collection pay the entire infrastructure import chain — and a domain-VO red→green is then blocked by an unfilled sibling (e.g. a column-less table) the unit test never touches (F-013). The app-construction fixture (`real_app`) lives in `tests/integration/conftest.py` and imports `create_app` **inside the fixture body** (deferred, as the template above does), so only the integration suite — which legitimately constructs the app — pays that import. Keep app construction out of any conftest a unit test inherits.

### Optional sub-template — reset captured Singletons (only if any exist)

When `containers.py` has a `Singleton(...)` that captures settings or a sessionmaker by value at construction time, add an autouse function-scoped fixture inside `tests/integration/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_captured_singletons(real_app: FastAPI) -> Iterator[None]:
    yield
    c = real_app.state.container
    c.<captured_singleton>.reset()
```

One `.reset()` line per such Singleton. Skip the entire fixture if none exist — confirm by inspecting every `Singleton(...)` constructor in `containers.py`.

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

## Fixture-resolution coupling between the two conftests

`real_app` (defined up-tree in `tests/integration/conftest.py` by the outer conftest) declares `jwt_settings` as one of its parameters and calls `container.jwt_settings.override(jwt_settings)`. Pytest resolves that name by walking the conftest hierarchy from the running test outward — for tests under `tests/integration/api/`, the `jwt_settings` fixture produced in the api conftest is visible. Without this override, every `authed_client`-minted token would be signed with the test keypair but verified against the production public key the container loaded at startup — every authenticated test would fail with 401.

The coupling has a cost: `real_app` cannot be used from tests outside `tests/integration/api/` (e.g. `tests/integration/postgres/`), because `jwt_settings` isn't visible there. That's fine — repository contract tests use `sf` directly and never construct the FastAPI app.

## Rules

### Isolation

1. **`sf` is the only sanctioned sessionmaker.** Every integration test, fixture, and overridden DI provider binds through `sf` (function-scoped, joins the outer transaction). Direct `async_sessionmaker(bind=engine, ...)` inside `tests/integration/` bypasses rollback and leaks rows. The `test-architecture-rule` skill enforces this with a grep.
2. **`join_transaction_mode="create_savepoint"` is non-negotiable.** Without it, the handler's `session.commit()` either commits to disk (defeating rollback) or raises `InvalidRequestError`. With it, commit() releases a SAVEPOINT inside the outer transaction — exactly what the test needs.
3. **`expire_on_commit=False`** keeps loaded entities usable after a savepoint release. With `True`, every commit detaches attributes; tests asserting on returned entities then trigger lazy loads against a closed session.
4. **The outer connection is function-scoped, engine is session-scoped.** One Postgres container + one engine for the whole run; one connection (and one transaction) per test. Reversing this — session-scoped connection — serializes the whole suite and defeats `pytest-xdist`. Reversing the engine — function-scoped — re-establishes the pool every test and adds seconds.
5. **No `make test-unit` deselection.** Integration tests live under `tests/integration/`; pytest collects by path, not by marker. The `@pytest.mark.integration` ceremony is unnecessary if the path split is enforced. (Skill consumers stop adding the marker; the architecture rule asserts no test file outside `tests/integration/` opens a `_engine` or `sf`.)
6. **Fixed natural keys are now allowed.** Without rollback, every UNIQUE column needed a `uuid4().hex[:8]` suffix to avoid collisions across tests. With rollback, the DB is empty at test start — `name="alpha"` is fine. Builders may still use unique suffixes for readability, but it's no longer load-bearing.
7. **`assert len(items) == N` is now correct.** Tests may assert exact counts; no defensive `any(...)` filters; no `+1` for the test's own row in a shared list. The fixture model gives the test sole ownership of the DB during its run.
8. **The DI container override happens at `real_app`-construction time.** Provider override (`.override(value)`) intercepts at the provider level, before any cache — so it works on `Factory` *and* `Singleton` providers, and on first or subsequent resolution. **What it does NOT cover**: a downstream provider that *captures* the resolved value by closure or by storing it as an attribute at construction time. The classic example is a `Singleton(Policy, settings=settings.provided.foo)` where `Policy.__init__` snapshots `settings.foo` into `self._foo`. Overriding `settings` *after* the Policy has been resolved leaves `self._foo` pointing at the old value. The fix is an autouse function-scoped fixture that calls `.reset()` on every such capturing Singleton at teardown. Audit `containers.py` once: any `Singleton(...)` whose constructor stores a derived value from `session_factory` / settings / engine needs a reset entry.
9. **The override accepts plain values.** `container.session_factory.override(sf)` with a plain `async_sessionmaker` works (no `providers.Object(sf)` wrapper required). Same for `db_settings`, `storage_settings`.
10. **S3 has no transactions.** Per-test `s3_prefix` is the substitute: each test writes under its own prefix; the bucket is cleaned at session end (best effort). Tests must not assert on global bucket contents — only on contents under their `s3_prefix`.
11. **Container fixtures are session-scoped autouse for migration + guard.** Postgres + MinIO start once per session. The guard refuses to run if the DSN looks like a developer's local DB.
12. **Add the reset-captured-singletons fixture if any exist** — see the optional sub-template under Template(s). Skip the fixture entirely when no `Singleton(...)` in `containers.py` captures settings or sessionmaker by value at construction time.

### Authenticated client

13. **`authed_client` is the single sanctioned authenticated client.** Direct `AsyncClient(transport=ASGITransport(app=real_app))` with a hand-rolled `Authorization` header is forbidden in any test file. Raw `AsyncClient` with no Authorization header is allowed only for `test-discovery-invariants` unauth probes.
14. **Always `async with authed_client(...) as client:`.** Bare assignment (`client = authed_client(role=...)`) leaks the ASGI transport and produces "Cannot reuse a consumed `AsyncClient`" or resource-warning noise in CI. The async-context-manager form is non-negotiable.
15. **Each call mints a fresh JWT.** Tokens are not reused across tests, calls, or roles. A test that needs two roles in one body calls `authed_client(...)` twice.
16. **Mint only the universal claims; pass app-specific ones via `extra_claims`.** The factory bakes in just `sub` and `role` — the claims every verifier needs. Any app-specific claim (tenant/org id, display name, …) is the caller's to pass via `extra_claims`, pinned only when a test must share it with a fixture row (don't reuse such a value across unrelated tests). Never hardcode one app's identity model into the factory.
17. **`rsa_keypair` and `jwt_settings` are session-scoped.** Generating an RSA key is expensive (~100ms); generating per test would dominate suite wall time.
18. **Algorithm matches production.** If production verifies `RS256`, the fixture signs `RS256` — never substitute `HS256` "for speed". The verifier in `real_app` uses `jwt_settings.algorithm`, so the test and prod paths must agree.
19. **No `localhost` / `127.0.0.1` base URL.** `http://testserver` is the convention; the ASGI transport short-circuits the network anyway, but `testserver` makes route logs distinguishable from real traffic in CI logs.
20. **No mocking of JWT verification.** The verifier in `real_app` validates the token end-to-end against the `jwt_settings.public_key` provided by this skill — that's the integration contract under test.
21. **No global token cache.** Per-test mint is fast (~1ms) and avoids "this test passed because the previous test's token was still cached" failures.
22. **Helpers live in `tests/helpers/`, not in `conftest.py`.** A test that needs `sign_token(...)` for an edge case (expired token, invalid issuer) imports the helper directly. The helper is a plain function — no fixtures wrap it.

## Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, `subprocess`, `os`, `sys`, stdlib `collections.abc` — and the project's `infrastructure.postgres.*` + `infrastructure.s3.*`.
- Full annotations on every fixture signature. `AsyncIterator[T]` for yielding fixtures with cleanup.
- No `from __future__ import annotations`.

The api conftest adds `httpx`, `jwt` (PyJWT), `cryptography.hazmat.*`, `myapp.domain.auth` and
`myapp.infrastructure.jwt.settings`; full annotations on the factory and its `_factory` closure.

## Hard stops

- The container has no overridable `session_factory` provider → stop, `infra-wiring` first, to introduce the provider and the override hook.
- Spec asks to keep `function`-scoped engine (one engine per test) → stop, that's the old slow model; engine is session-scoped, only the connection is function-scoped.
- Spec asks to drop `join_transaction_mode="create_savepoint"` → stop, that flag is the whole point — without it the handler's commits either escape or fail.
- Spec asks for session-scoped row fixtures (`make_org` returning the same id across tests) → stop, rows are per-test; factories return fresh rows per call.
- Spec asks the `sf` fixture to bind to the engine directly (skipping the outer connection) → stop, that bypasses rollback and reintroduces every old failure mode.
- Spec asks to add a `truncate_all_tables` teardown alongside rollback → stop, rollback alone is sufficient; truncate is the fallback for DBs without nested transactions and is strictly slower.
- Project does not use S3 / MinIO but spec includes the bucket fixtures → strip the storage block; no need to start MinIO every session.
- The app has no relational store — a qdrant/redis-only app, say → stop laying the Postgres engine / Alembic / savepoint-`sf` machinery; there is no SQL transaction to roll back. Isolate the client stores by per-test namespace + session-end cleanup (the `s3_prefix` pattern), not by this fixture.
- The app has no auth (every endpoint anonymous) but the JWT override is present → strip the `jwt_settings` parameter and the `container.jwt_settings.override(...)` / `reset_override()` lines from `real_app`. An auth-less app has no `jwt_settings` provider, so the override raises `AttributeError`; whether an app has auth follows from its routes (see `restapi-route-contracts`), it is not a universal.
- Spec proposes a session-scoped `authed_client` "to speed up tests" → stop, the factory is function-scoped because each test's transport must be closed at teardown; the cost is negligible.
- Spec asks to mock the JWT verifier → stop, the integration test signs a real token against the same keypair the verifier validates.
- Spec uses `HS256` in tests while production uses `RS256` (or vice versa) → stop, the algorithm matches production.
- Spec adds a per-resource row factory inside this conftest → stop, those live in `tests/integration/api/<resource>/conftest.py`.
- Spec writes the bearer header by hand inside a test → stop, use `authed_client(...)` so role / org / claim shape are uniform.
- Spec hardcodes `Authorization: Bearer <literal-jwt>` for "expired token" or "invalid claim" tests → stop, mint the test-specific token via `sign_token(...)` from the helper.
