---
name: testing-integration
description: "House style for real-backend integration tests via testcontainers: repository contract tests (relational and client-style store), REST endpoint tests, discovery-invariant tests over `app.routes` / `app.openapi()`, capability-adapter tests, and the isolation / authed-client fixtures. Carries the testcontainers discipline, per-test rollback and per-namespace isolation, and the Docker-absence skip rule (a clean `pytest.skip`, never a fixture that raises)."
when_to_use: Writing an integration test that touches a real store, the real FastAPI app, or an external adapter — anything under `tests/integration/`.
---
# Testing — integration tier

This merged skill covers 7 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from test-integration-isolation -->

## Test — Integration Isolation

One-shot per project. Produces `tests/integration/conftest.py` with the transaction-rollback fixture every other integration skill depends on. The contract this skill enforces: every integration test starts with an empty database; rows the test (and its handler) commit are rolled back at teardown.

**This is the relational-store isolation strategy.** The engine, the Alembic migration run, and the savepoint-rollback `sf` all assume a relational (`uses_bootstrap`) store — the per-test transaction that ROLLBACKs is a SQL-database mechanism. An app whose only datastore is client-style (qdrant / redis / …) has no engine, no migration chain, and cannot use savepoint rollback; it isolates by **per-test namespace + best-effort cleanup** instead (the `s3_prefix` block below is exactly that pattern). Emit the Postgres machinery only when the graph carries a relational store.

### When to use vs. neighbours

- First-time scaffold of `tests/integration/conftest.py` → this skill.
- Per-resource row factories (`make_org`, `make_tag`, …) → not this skill; declare them in `tests/integration/api/<resource>/conftest.py` next to the tests that use them.
- The authed `httpx.AsyncClient` factory → `test-integration-authed-client`.
- A repository contract test → `test-repository-contract` (consumes the `sf` fixture this skill provides).
- An API endpoint test → `test-restapi-endpoint` (consumes both `sf` and `authed_client`).
- Cross-cutting "every route returns 401 unauth" / "OpenAPI codes match `error_responses(...)`" → `test-discovery-invariants`.

### Template(s)

#### `tests/integration/conftest.py`

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

#### `tests/conftest.py` (top-level, optional sub-template)

Leave empty:

```python
```

`pytest-asyncio` mode and plugin declarations belong in `pyproject.toml` under `[tool.pytest.ini_options]`, not here. That block **must** carry `asyncio_mode = "auto"` **and** a **session** loop scope — `asyncio_default_fixture_loop_scope = "session"` + `asyncio_default_test_loop_scope = "session"`. The engine fixture above is session-scoped, so every test and fixture must share ONE event loop: under the default function loop scope the session engine's `asyncpg` connections outlive the loop they were opened on, and any integration test that runs a real statement which errors (a constraint violation through a repository, the canonical repo-contract case) crashes at teardown with `RuntimeError: Event loop is closed` (asyncpg cannot cancel the aborted command on a closed loop). The cheap api-discovery tests hide this — their routes (401 / CORS / OpenAPI) short-circuit before touching Postgres, so no real command runs — which is why it only surfaces once a repository contract test exercises the DB.

**The root `tests/conftest.py` must NOT import `create_app` / `myapp.restapi.main` (nor define a `real_app` / `client` fixture).** pytest applies the root conftest to the WHOLE suite, so a *module-level* `from myapp.restapi.main import create_app` there makes every `tests/unit/**` collection pay the entire infrastructure import chain — and a domain-VO red→green is then blocked by an unfilled sibling (e.g. a column-less table) the unit test never touches (F-013). The app-construction fixture (`real_app`) lives in `tests/integration/conftest.py` and imports `create_app` **inside the fixture body** (deferred, as the template above does), so only the integration suite — which legitimately constructs the app — pays that import. Keep app construction out of any conftest a unit test inherits.

#### Optional sub-template — reset captured Singletons (only if any exist)

When `containers.py` has a `Singleton(...)` that captures settings or a sessionmaker by value at construction time, add an autouse function-scoped fixture inside `tests/integration/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_captured_singletons(real_app: FastAPI) -> Iterator[None]:
    yield
    c = real_app.state.container
    c.<captured_singleton>.reset()
```

One `.reset()` line per such Singleton. Skip the entire fixture if none exist — confirm by inspecting every `Singleton(...)` constructor in `containers.py`.

### Rules

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

### Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, `subprocess`, `os`, `sys`, stdlib `collections.abc` — and the project's `infrastructure.postgres.*` + `infrastructure.s3.*`.
- Full annotations on every fixture signature. `AsyncIterator[T]` for yielding fixtures with cleanup.
- No `from __future__ import annotations`.

### Hard stops

- Container has no overridable `session_factory` provider → stop, run `infra-di-provider` first to introduce the provider and the override hook.
- Spec asks to keep `function`-scoped engine (one engine per test) → stop, that's the old slow model; engine is session-scoped, only the connection is function-scoped.
- Spec asks to drop `join_transaction_mode="create_savepoint"` → stop, that flag is the whole point — without it the handler's commits either escape or fail.
- Spec asks for session-scoped row fixtures (`make_org` returning the same id across tests) → stop, rows are per-test; factories return fresh rows per call.
- Spec asks the `sf` fixture to bind to the engine directly (skipping the outer connection) → stop, that bypasses rollback and reintroduces every old failure mode.
- Spec asks to add a `truncate_all_tables` teardown alongside rollback → stop, rollback alone is sufficient; truncate is the fallback for DBs without nested transactions and is strictly slower.
- Project does not use S3 / MinIO but spec includes the bucket fixtures → strip the storage block; no need to start MinIO every session.
- App has no relational (`uses_bootstrap`) store — e.g. a qdrant/redis-only app → stop emitting the Postgres engine / Alembic / savepoint-`sf` machinery; there is no SQL transaction to roll back. Isolate the client stores by per-test namespace + session-end cleanup (the `s3_prefix` pattern), not by this fixture.
- Project declares no auth (every endpoint anonymous) but spec includes the JWT override → strip the `jwt_settings` parameter and the `container.jwt_settings.override(...)` / `reset_override()` lines from `real_app`. An auth-less app has no `jwt_settings` provider, so the override raises `AttributeError`; auth is an app-declared feature (see `restapi-auth-dependency`), not a universal.


<!-- merged from test-integration-authed-client -->

## Test — Integration Authed Client

One-shot per project. Owns the JWT-minting `authed_client` factory and the keys it depends on. Every integration test that needs an authenticated HTTP call consumes this fixture; no other place in the test tree may construct `AsyncClient(transport=ASGITransport(...))` directly for an authenticated request.

**Applies only to an app that declares auth.** This is the auth test-bootstrap — the same trigger that pulls `cryptography` into the dependency set (`conventions` block D). An auth-less app (every endpoint anonymous) has no authenticated client to mint, so it skips this skill and the auth fixtures it owns — `authed_client`, `rsa_keypair`, `jwt_settings`. It does **not** skip `tests/integration/api/conftest.py` as a file: that module is the api-integration suite's shared-fixture container (the standard pytest convention for fixtures visible to every test under `tests/integration/api/`), and auth is merely its current sole occupant. An auth-less app simply has none of these auth fixtures in that conftest (and, until something else populates it, no reason to create the file at all) — the skip is of the auth fixtures, not of the shared container per se.

### When to use vs. neighbours

- First-time scaffold of `tests/integration/api/conftest.py` → this skill.
- The rollback fixture, `sf`, `real_app` (DI override) → `test-integration-isolation` (one-shot, runs first).
- The cross-cutting "every protected route returns 401 unauth" / OpenAPI invariants → `test-discovery-invariants` (consumes `real_app` directly, not `authed_client`).
- A per-endpoint integration test → `test-restapi-endpoint` (consumes `authed_client`).
- The auth dependencies on the route side (`get_current_user`, `require_role`) → `restapi-auth-dependency` (route-side, not test-side).

### Template(s)

```
tests/
├── helpers/
│   ├── __init__.py
│   └── jwt.py
└── integration/api/
    └── conftest.py
```

#### `tests/helpers/jwt.py`

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

#### `tests/integration/api/conftest.py`

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

#### Per-resource `conftest.py` is **not** owned here

Per-resource fixtures (`make_foo`, `foo_id`, `bar_id`, …) live in `tests/integration/api/<resource>/conftest.py` next to the endpoint tests that use them. This skill does not write them; `test-restapi-endpoint` references them but expects the consuming spec to declare what it needs.

### Fixture-resolution coupling with `test-integration-isolation`

`real_app` (defined up-tree in `tests/integration/conftest.py` by `test-integration-isolation`) declares `jwt_settings` as one of its parameters and calls `container.jwt_settings.override(jwt_settings)`. Pytest resolves that name by walking the conftest hierarchy from the running test outward — for tests under `tests/integration/api/`, the `jwt_settings` fixture produced here is visible. Without this override, every `authed_client`-minted token would be signed with the test keypair but verified against the production public key the container loaded at startup — every authenticated test would fail with 401.

The coupling has a cost: `real_app` cannot be used from tests outside `tests/integration/api/` (e.g. `tests/integration/postgres/`), because `jwt_settings` isn't visible there. That's fine — repository contract tests use `sf` directly and never construct the FastAPI app.

### Rules

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

### Inlined typing / import rules

- `pytest`, `httpx`, `jwt` (PyJWT), `cryptography.hazmat.*`, stdlib `uuid` / `datetime`, `myapp.domain.auth`, `myapp.infrastructure.jwt.settings`.
- Full annotations on the factory and `_factory` closure.
- No `from __future__ import annotations`.

### Hard stops

- `tests/integration/conftest.py` does not exist (no `real_app` fixture) → stop, install `test-integration-isolation` first.
- Spec proposes a session-scoped `authed_client` "to speed up tests" → stop, the factory is function-scoped because each test's transport must be closed at teardown; the cost is negligible.
- Spec asks to mock the JWT verifier → stop, the integration test signs a real token against the same keypair the verifier validates.
- Spec uses `HS256` in tests while production uses `RS256` (or vice versa) → stop, the algorithm matches production.
- Spec adds a per-resource row factory inside this conftest → stop, those live in `tests/integration/api/<resource>/conftest.py`.
- Spec writes the bearer header by hand inside a test → stop, use `authed_client(...)` so role / org / claim shape are uniform.
- Spec hardcodes `Authorization: Bearer <literal-jwt>` for "expired token" or "invalid claim" tests → stop, mint the test-specific token via `sign_token(...)` from the helper.


<!-- merged from test-repository-contract -->

## Test — Repository Contract

Produces one integration-test file per repository. Catches what unit-level coverage cannot: real `UNIQUE` / `FK` violations, real `ON DELETE CASCADE` semantics, the `IntegrityError`-to-domain-exception translator's constraint-name map, and the `onupdate=` clause on `updated_at`.

### When to use vs. neighbours

- A new or modified repository adapter under `infrastructure/postgres/repositories/` (a relational `uses_bootstrap` store) → this skill.
- A repository on a client-style store (qdrant/redis/…, `infra-store-repository`) → `test-store-repository-contract` (namespace isolation, not `sf`/rollback).
- Schema-only checks (an index exists, a migration carries data correctly) → separate flat files under `tests/integration/postgres/` (`test_indexes.py`, `test_<NNNN>_migration.py`) that use `db_settings` and `run_alembic`, not `sf`.
- HTTP-layer integration (route, auth, OpenAPI) → `test-restapi-endpoint`.
- The rollback `conftest.py` itself → `test-integration-isolation` (one-shot).
- Pure domain test → `test-domain-entity` / `test-domain-value-object` / `test-domain-enum` / `test-domain-service`.

### Template(s)

```
tests/integration/postgres/
└── test_<aggregate_snake>_repository.py
```

Large surfaces may concern-split (`test_<aggregate>_repository_create.py`, `test_<aggregate>_repository_update.py`) — but only when the single file exceeds ~300 lines. Default is one file per repository.

#### Standard CRUD test file

```python
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myapp.domain.exceptions import ConflictError, NotFoundError
from myapp.domain.foos import Foo, FooListFilter
from myapp.infrastructure.postgres.repositories.foo_repository import FooRepository

def _foo(name: str = "alpha") -> Foo:
    return Foo(id=uuid.uuid7(), name=name)

async def test_crud_roundtrip(sf: async_sessionmaker[AsyncSession]) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()

    await repo.create(foo)
    loaded = await repo.get_by_id(foo.id)
    assert loaded == foo

    foo.name = "beta"
    await repo.update(foo)
    assert (await repo.get_by_id(foo.id)).name == "beta"

    await repo.delete(foo.id)
    with pytest.raises(NotFoundError):
        await repo.get_by_id(foo.id)

async def test_duplicate_name_on_insert_raises_conflict(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))

    with pytest.raises(ConflictError) as exc:
        await repo.create(_foo("alpha"))

    assert exc.value.context["constraint"] == "uq_foos_name"

async def test_duplicate_name_on_update_raises_conflict(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))
    second = _foo("beta")
    await repo.create(second)

    second.name = "alpha"
    with pytest.raises(ConflictError) as exc:
        await repo.update(second)

    assert exc.value.context["constraint"] == "uq_foos_name"

async def test_updated_at_advances_on_update(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    before = (await repo.get_by_id(foo.id)).updated_at

    foo.name = "beta"
    await repo.update(foo)
    after = (await repo.get_by_id(foo.id)).updated_at

    assert after >= before

async def test_get_by_name_returns_match(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    await repo.create(_foo("alpha"))

    loaded = await repo.get_by_name("alpha")
    assert loaded is not None
    assert loaded.name == "alpha"

async def test_get_by_name_returns_none_when_absent(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)

    assert await repo.get_by_name("alpha") is None

async def test_list_respects_pagination_and_sort(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    for name in ("c", "a", "b"):
        await repo.create(_foo(name))

    page = await repo.list(filter=FooListFilter(limit=2, offset=0))
    assert [f.name for f in page] == ["a", "b"]
```

#### Cascade — parent + sub-collection

```python
async def test_cascade_delete_removes_attachments(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    await repo.add_attachment(foo.id, _attachment(foo.id))

    await repo.delete(foo.id)

    assert await repo.count_attachments(foo.id) == 0

async def test_attachment_with_wrong_parent_raises_not_found(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    repo = FooRepository(session_factory=sf)
    foo = _foo()
    await repo.create(foo)
    att = _attachment(foo.id)
    await repo.add_attachment(foo.id, att)

    with pytest.raises(NotFoundError):
        await repo.get_attachment(uuid.uuid4(), att.id)
```

### Rules

1. **Every test takes `sf: async_sessionmaker[AsyncSession]`.** The rollback fixture from `test-integration-isolation` makes the DB empty at test start and discards everything at teardown. No marker, no other DB fixture.
2. **`_<aggregate>()` builder is a module-level `def`, not a `@pytest.fixture`.** Defaults must be valid; no-override construction succeeds.
3. **No unique-suffix natural keys.** Rollback isolation guarantees an empty DB; `name="alpha"` is safe across tests. The old `uuid4().hex[:8]` floor is obsolete here.
4. **`assert exc.value.context["constraint"] == "<constraint_name>"` on every `ConflictError`.** This is the only place the `IntegrityError`-to-domain-exception translator's name map is exercised end-to-end — the fake-based unit-test path can't verify it.
5. **Insert AND update paths for every unique field.** The bug class "translator handles INSERT but not UPDATE" only surfaces when both are tested. Skipping the update test is the most common gap in repository contracts.
6. **`updated_at` advance is asserted as `>=`, not `>`.** Postgres `now()` may return identical timestamps within a transaction; `>=` pins the `onupdate=` clause without flaking.
7. **Every cascade gets its own test.** Naming: `test_cascade_delete_removes_<child>`. Test the count after parent-delete is zero — only this proves the schema's `ON DELETE CASCADE` works.
8. **Every `get_by_<field>` gets both a found and a not-found test.** For case-sensitivity-sensitive fields, add a mixed-case test that asserts the documented behavior.
9. **`assert list_result == expected_list`** — exact equality, not `any(...)`. Empty DB makes this correct.
10. **No raw INSERTs for seed data on the table under test.** Drive setup through the repository's own `create`. Cross-aggregate seed rows (a referenced `Bar` for a `Foo` test) may use raw INSERT when no `BarRepository.create` is in scope — or inject the bar's repo and use it.
11. **No FastAPI, no `httpx`, no DI container.** This test imports the repository class, takes `sf`, calls methods, asserts. The HTTP surface is `test-restapi-endpoint`.
12. **Migration regression tests are separate.** They live flat at `tests/integration/postgres/test_<NNNN>_migration.py`, take `db_settings`, invoke `run_alembic`, and may `downgrade` / `upgrade`. Ordinary repository tests cannot — they assume `head` is applied.

### Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, stdlib `uuid`, `myapp.domain.*`, `myapp.infrastructure.postgres.repositories.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature including `sf: async_sessionmaker[AsyncSession]`.
- Builder `_<aggregate>()` returns the entity type; overrides keyword-only.
- No `from __future__ import annotations`.

### Hard stops

- `tests/integration/conftest.py` missing or `sf` not provided → stop, install `test-integration-isolation` first.
- Spec asks for `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- Spec asks the test to `dispose_engine` / start its own connection / instantiate `async_sessionmaker(bind=engine)` directly → stop, that bypasses rollback; use `sf`.
- Spec asks to assert on `len(items) == N + 1` or use `any(...)` defensively → stop, rollback isolation makes exact equality correct.
- Spec asks to assert on `ConflictError` without checking `context["constraint"]` → stop, the constraint-name map is the load-bearing contract this test exists to pin.
- Spec adds raw INSERT for seed data on the table under test → stop, drive setup through `repo.create`.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asks to run Alembic from this test → stop, that's a migration regression test in a separate flat file.
- Spec uses `uuid4().hex[:8]` suffixes "to avoid duplicate-key flakes" → stop, rollback removes the need; use fixed values for clarity.


<!-- merged from test-store-repository-contract -->

## Test — Store Repository Contract

Produces one integration-test file per client-style store repository. This is the non-relational sibling of `test-repository-contract`: same goal (prove the real adapter against the real backend), different mechanics. A client store has **no SQL transaction to roll back** and **no `IntegrityError` constraint map** — so isolation is by a per-test namespace, and the load-bearing contract is the entity↔record mapping plus the SDK-error → domain-exception translation the adapter performs at its boundary.

### When to use vs. neighbours

- A repository adapter under `infrastructure/<store-kind>/repositories/` (qdrant/redis/…) → this skill.
- A repository on the relational (`uses_bootstrap`) store → `test-repository-contract` (it uses `sf` + transaction rollback).
- The repository being tested → `infra-store-repository`.
- An in-memory fake of the same protocol for handler unit tests → `test-fake-repository`.
- HTTP-layer integration (route, auth, OpenAPI) → `test-restapi-endpoint`.

### Isolation — namespace, not rollback

A client store has no nested transaction, so the `sf`-rollback model does not apply (see `test-integration-isolation`, which is relational-only). Isolate exactly as the `s3_prefix` pattern does: **each test owns a fresh namespace** — a unique collection name (qdrant/chroma), key-prefix (redis), or database/bucket — created in a fixture and dropped at teardown. Bring the real store up once per session via testcontainers; create/destroy the per-test namespace per test. This skill's fixtures live in the sibling `tests/integration/<store-kind>/conftest.py` (not in `test-integration-isolation`, which owns only the relational + blob fixtures).

### Template(s)

```
tests/integration/<store-kind>/
├── conftest.py                         # session container + per-test namespace fixture
└── test_<aggregate_snake>_repository.py
```

#### `conftest.py` — real store + per-test namespace (qdrant example)

```python
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

_DIM = 3  # the test vectors' dimension — small; production dimension lives in settings

@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    if os.getenv("CI"):
        yield os.environ["MYAPP_QDRANT_URL"]
        return
    from testcontainers.qdrant import QdrantContainer

    # Pin the image tag — never float on :latest (mirrors test-integration-isolation's
    # postgres/MinIO pins; :latest makes the suite non-reproducible). The specific pin
    # is a per-deployment choice, bumped deliberately, not a frozen constant.
    with QdrantContainer("qdrant/qdrant:v1.12.4") as q:
        yield f"http://{q.get_container_host_ip()}:{q.get_exposed_port(6333)}"

@pytest.fixture
async def store(qdrant_url: str) -> AsyncIterator[tuple[AsyncQdrantClient, str]]:
    """A fresh collection per test = namespace isolation (no transaction rollback
    for a client store). Create it, hand out (client, collection), drop at teardown."""
    client = AsyncQdrantClient(url=qdrant_url)
    collection = f"test_{uuid.uuid4().hex}"
    await client.create_collection(
        collection, vectors_config=VectorParams(size=_DIM, distance=Distance.COSINE)
    )
    try:
        yield client, collection
    finally:
        await client.delete_collection(collection)
        await client.close()
```

#### `test_<aggregate_snake>_repository.py`

```python
import uuid

import pytest
from qdrant_client import AsyncQdrantClient

from myapp.domain.exceptions import UpstreamError
from myapp.domain.foos import Foo
from myapp.infrastructure.qdrant.repositories.foo_repository import FooRepository
from myapp.infrastructure.qdrant.settings import FoosVectorSettings

def _foo(text: str = "alpha", *, vector: list[float] | None = None, bar_id: uuid.UUID | None = None) -> Foo:
    return Foo(
        id=uuid.uuid4(),
        bar_id=bar_id or uuid.uuid4(),
        text=text,
        vector=vector or [0.1, 0.2, 0.3],
    )

def _repo(store: tuple[AsyncQdrantClient, str]) -> FooRepository:
    client, collection = store
    return FooRepository(client=client, settings=FoosVectorSettings(collection=collection))

async def test_add_many_then_search_roundtrip(store: tuple[AsyncQdrantClient, str]) -> None:
    repo = _repo(store)
    foo = _foo()
    await repo.add_many((foo,))

    hits = await repo.search(query_vector=foo.vector, k=1)
    assert len(hits) == 1
    found, score = hits[0]
    assert found.id == foo.id
    assert found.text == "alpha"
    assert isinstance(score, float)

async def test_search_returns_nearest_first(store: tuple[AsyncQdrantClient, str]) -> None:
    repo = _repo(store)
    near = _foo("near", vector=[0.1, 0.0, 0.0])
    far = _foo("far", vector=[0.9, 0.9, 0.9])
    await repo.add_many((near, far))

    hits = await repo.search(query_vector=[0.1, 0.0, 0.0], k=2)
    assert [f.text for f, _ in hits] == ["near", "far"]

async def test_delete_by_bar_removes_only_that_bars_points(
    store: tuple[AsyncQdrantClient, str],
) -> None:
    repo = _repo(store)
    keep, drop = uuid.uuid4(), uuid.uuid4()
    await repo.add_many((
        _foo("keep", vector=[0.1, 0.0, 0.0], bar_id=keep),
        _foo("drop", vector=[0.0, 0.1, 0.0], bar_id=drop),
    ))

    await repo.delete_by_bar(drop)

    remaining = await repo.search(query_vector=[0.1, 0.1, 0.1], k=10)
    assert {f.bar_id for f, _ in remaining} == {keep}

async def test_search_against_unreachable_store_raises_upstream_error() -> None:
    dead = AsyncQdrantClient(url="http://127.0.0.1:1")  # nothing listening
    repo = FooRepository(client=dead, settings=FoosVectorSettings(collection="x"))

    with pytest.raises(UpstreamError):
        await repo.search(query_vector=[0.0, 0.0, 0.0], k=1)
```

### Rules

1. **Each test runs against the real store via testcontainers** — never a fake, never a mock. The fake (`test-fake-repository`) is for handler unit tests; this layer exists to prove the adapter against the actual backend, which is the only place the SDK call shape and error mapping are exercised.
2. **Isolate by a per-test namespace, not rollback.** A fresh collection / key-prefix / database per test, created in the `store` (or equivalently-named) fixture and dropped at teardown. There is no transaction to roll back; do not reach for `sf`.
3. **The container is session-scoped; the namespace is function-scoped.** One store per run (expensive to start); one namespace per test (cheap, gives each test sole ownership). CI reads a provided endpoint from env (the `os.getenv("CI")` branch) instead of starting a container.
4. **Exercise the full protocol**, CRUD verbs and non-CRUD alike — `add_many`/`get`/`delete` AND the store's own verbs (`search`, `delete_by_<field>`, range/scan). A `search` test asserts ordering (nearest-first / score-ordered), not just membership.
5. **Assert the entity↔record mapping round-trips.** What was written comes back as the same entity (ids, payload fields, and — when the read path hydrates it — the vector). A returned scored pair asserts both the entity and that the score is a real `float`, not a placeholder.
6. **Assert the SDK-error → domain-exception translation end-to-end.** This is the load-bearing contract (the client-store analogue of the relational `context["constraint"]` assertion): point the repository at an unreachable/closed client, or trigger a store rejection, and assert the boundary raises the domain exception the adapter promises — `UpstreamError` for a network / store failure, `NotFoundError` for an absent record — never the raw SDK exception. These are the app-declared domain exceptions `infra-store-repository` translates into at its boundary (shown here as placeholders); assert whichever ones that adapter actually raises, not a frozen literal. Assert the `context` keys the adapter promises.
7. **Fixed test values are fine.** Namespace isolation gives each test an empty store at start; no unique-suffix natural keys needed (same as the relational contract's rollback guarantee).
8. **Small test vectors.** Use a tiny dimension (e.g. 3) created on the per-test collection; the production embedding dimension is a settings concern, not the contract's.
9. **No FastAPI, no `httpx`, no DI container.** Import the repository class, construct it with the real client + a settings object scoped to the per-test namespace, call methods, assert. The HTTP surface is `test-restapi-endpoint`.
10. **No assertions on global store contents.** Assert only within this test's namespace — exactly the `s3_prefix` discipline, because cleanup is namespace-scoped, not transactional.

### Inlined typing / import rules

- `pytest`, the store SDK (`qdrant_client` / `redis` / …), stdlib `uuid` / `os`, `myapp.domain.*`, `myapp.infrastructure.<store-kind>.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature and fixture, including the `store` fixture's `tuple[<Client>, str]` shape. Yielding fixtures use `AsyncIterator[T]` / `Iterator[T]`.
- No `from __future__ import annotations`.

### Hard stops

- The repository is on the relational (`uses_bootstrap`) store → stop, use `test-repository-contract` (`sf` + rollback), not this skill.
- Spec asks to use `sf` / transaction rollback for a client store → stop, there is no nested transaction; isolate by per-test namespace + teardown.
- Spec asks to mock the store SDK or assert against a fake → stop, this layer drives the real backend; the fake belongs to `test-fake-repository` at the handler-unit layer.
- Spec asserts on `ConflictError` + `context["constraint"]` → stop, that is the relational `IntegrityError` contract; a client store asserts the domain exceptions its adapter translates SDK errors into (`UpstreamError` / `NotFoundError`) instead.
- Spec includes FastAPI / `httpx` / DI container references → stop, that's `test-restapi-endpoint`.
- Spec asserts on store contents outside the test's own namespace → stop, assert only within the per-test collection/prefix.


<!-- merged from test-restapi-endpoint -->

## Test — REST API Endpoint

Produces one integration-test file per endpoint. Self-contained: every test in the file constructs its own state by calling factory fixtures or POSTing through the API; no cross-test state, no shared registries, no cross-file edits when a new endpoint is added.

### When to use vs. neighbours

- A new or modified endpoint added by `restapi-endpoint` → this skill.
- A new resource introduces several endpoints (create + list + get + update + delete) → invoke this skill once per endpoint file. Sibling files share a per-resource `conftest.py`.
- The `tests/integration/conftest.py` itself (rollback, container fixtures) → `test-integration-isolation` (one-shot).
- The `authed_client` factory → `test-integration-authed-client` (one-shot).
- Cross-cutting "every route 401 unauth" / "every route's OpenAPI codes match `error_responses(...)`" → `test-discovery-invariants` (one-shot; discovers from `app.routes` and `app.openapi()`).
- Repository contract (real DB, no HTTP) → `test-repository-contract`.
- Pure domain unit test → `test-domain-entity` / `test-domain-value-object` / `test-domain-enum` / `test-domain-service`.

### Template(s)

```
tests/integration/api/<resource>/
├── conftest.py                                  # per-resource fixtures (sibling-shared)
└── test_<verb>_<noun>.py                        # one file per endpoint
```

**The templates below assume an authenticated, role-gated, multi-tenant app** — `authed_client`, `Role.<MEMBER>`, and the `org_id` / cross-org examples are that app's model, not universal. Auth is app-declared (`restapi-auth-dependency`). For a **public route, or an app that declares no auth**, there is no `authed_client`, no `Role`, no `domain.auth` import — drive the route with a plain ASGI client (template below). A tenancy claim is passed to `authed_client` as a keyword arg whose name matches the app's JWT claim (e.g. `organization_id=...`); there is no built-in `org_id` parameter.

#### `test_<verb>_<noun>.py` — public route (app declares no auth)

```python
from httpx import ASGITransport, AsyncClient

from myapp.restapi.schemas import FooResponse


async def test_create_foo_happy_path(real_app):
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/foos", json={"name": "alpha"})

    assert response.status_code == 201
    FooResponse.model_validate(response.json())
```

(No `authed_client`, no `Role`, no `domain.auth` — the plain `AsyncClient` over `real_app` is the sanctioned client when the app has no auth, the one case Rule 6 carves out.)

#### `test_<verb>_<noun>.py` — JSON mutation, role-gated, tenant-scoped

```python
import pytest

from myapp.domain.auth import Role
from myapp.domain.exceptions import ConflictError, NotFoundError
from myapp.restapi.schemas import FooResponse

async def test_create_foo_happy_path(authed_client, bar_id):
    async with authed_client(role=Role.ADMIN) as client:
        response = await client.post("/foos", json={"name": "alpha", "bar_id": str(bar_id)})

    assert response.status_code == 201
    body = FooResponse.model_validate(response.json())
    assert body.name == "alpha"
    assert body.bar_id == bar_id

async def test_create_foo_duplicate_name_returns_409(authed_client, bar_id):
    async with authed_client(role=Role.ADMIN) as client:
        first = await client.post("/foos", json={"name": "alpha", "bar_id": str(bar_id)})
        assert first.status_code == 201

        second = await client.post("/foos", json={"name": "alpha", "bar_id": str(bar_id)})

    assert second.status_code == 409
    assert second.json()["code"] == ConflictError.code

async def test_create_foo_unknown_bar_returns_404(authed_client):
    import uuid
    async with authed_client(role=Role.ADMIN) as client:
        response = await client.post(
            "/foos",
            json={"name": "alpha", "bar_id": str(uuid.uuid4())},
        )

    assert response.status_code == 404
    assert response.json()["code"] == NotFoundError.code

async def test_create_foo_forbidden_for_lower_role(authed_client, bar_id):
    async with authed_client(role=Role.COLLABORATOR) as client:
        response = await client.post("/foos", json={"name": "alpha", "bar_id": str(bar_id)})

    assert response.status_code == 403
```

#### `test_<verb>_<noun>.py` — GET, tenant-scoped, cross-org returns 404 (not 403)

```python
import uuid

import pytest

from myapp.domain.auth import Role
from myapp.restapi.schemas import FooResponse

async def test_get_foo_returns_payload(authed_client, foo_in_org):
    foo_id, org_id = foo_in_org
    # The tenancy keyword is the app's JWT claim name, forwarded via authed_client's
    # **extra_claims (there is no built-in org_id parameter — see the note above).
    async with authed_client(role=Role.COLLABORATOR, organization_id=org_id) as client:
        response = await client.get(f"/foos/{foo_id}")

    assert response.status_code == 200
    FooResponse.model_validate(response.json())

async def test_get_foo_in_other_org_returns_404(authed_client, foo_in_org):
    foo_id, _ = foo_in_org
    other_org = uuid.uuid4()

    async with authed_client(role=Role.COLLABORATOR, organization_id=other_org) as client:
        response = await client.get(f"/foos/{foo_id}")

    assert response.status_code == 404  # NOT 403 — prevents enumeration
```

#### Per-resource `conftest.py`

The `make_foo` factory below seeds via a raw SQL `INSERT` through `sf` — that is the **relational-store** variant, valid when the resource is backed by a relational (`uses_bootstrap`) store. A resource backed by a client-style store (qdrant / redis / …) has no `sf` and no SQL table: seed it either by **POSTing through the API** (drive the create endpoint, then test against the result) or via the **store's own client** in the fixture. Pick the path from the resource's datastore kind; don't reach for `INSERT INTO` when there is no SQL table.

```python
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

@pytest.fixture
def make_foo(sf: async_sessionmaker[AsyncSession]) -> Callable[..., Awaitable[uuid.UUID]]:
    async def _make(*, name: str | None = None) -> uuid.UUID:
        fid = uuid.uuid7()
        async with sf() as session:
            await session.execute(
                text(
                    "INSERT INTO foos(id, name, created_at, updated_at)"
                    " VALUES(:id, :name, now(), now())"
                ),
                {"id": str(fid), "name": name or "foo"},
            )
            await session.commit()
        return fid
    return _make

@pytest.fixture
async def foo_id(make_foo: Callable[..., Awaitable[uuid.UUID]]) -> uuid.UUID:
    return await make_foo()
```

#### Multipart upload — single-test skeleton

```python
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

async def test_upload_attachment_returns_201(authed_client, foo_id):
    async with authed_client(role=Role.ADMIN) as client:
        response = await client.post(
            f"/foos/{foo_id}/attachments",
            data={"data": '{"caption": "test"}'},
            files=[("attachments", ("a.png", PNG, "image/png"))],
        )

    assert response.status_code == 201
    AttachmentResponse.model_validate(response.json())
```

#### Streaming download — single-test skeleton

```python
async def test_download_attachment_streams_bytes(authed_client, foo_id, attachment_id):
    async with authed_client(role=Role.ADMIN) as client:
        response = await client.get(f"/foos/{foo_id}/attachments/{attachment_id}")

    assert response.status_code == 200
    # The media type and disposition are THIS resource's contract — match the
    # route's declared media_type and disposition mode (attachment vs inline) per
    # restapi-file-transfer. The `image/png` + `attachment` shown is this example
    # resource's choice, not a universal download shape.
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert len(response.content) > 0
```

### Rules

1. **One file per endpoint.** Filename mirrors the route: `test_create_foo.py`, `test_list_foos.py`, `test_delete_foo.py`. Each file holds the happy path + every error path for that one endpoint. No mega-files spanning a whole resource.
2. **Every 2xx body is validated through the Pydantic response schema.** `body = FooResponse.model_validate(response.json())`. Catches contract drift that field-by-field assertions miss. Import schemas from the subpackage root (`from myapp.restapi.schemas import FooResponse`), never from the inner module — the wildcard re-export is the contract.
3. **No cross-cutting registries.** Adding a new endpoint touches exactly one new test file. The "every route returns 401 unauth" and "every route declares its error codes in OpenAPI" checks are owned by `test-discovery-invariants` and derive their inputs from `app.routes` / `app.openapi()` — no `_endpoints()` / `_EXPECTED` tables to extend.
4. **Self-contained tests.** Each test builds its own state via per-resource factory fixtures (`make_foo`) or by POSTing through the API. Since the rollback contract guarantees an empty DB at test start, fixed natural keys (`name="alpha"`) are safe — no `uuid4().hex[:8]` suffix required.
5. **Exact counts and orderings are now correct.** `assert len(items) == N`, `assert items[0].id == ...`, `assert response.json()["total"] == 3` — the empty-DB-at-start contract makes these reliable. Defensive `any(...)` filters belong to the pre-rollback world; remove them.
6. **In an app that declares auth, `authed_client` is the only sanctioned client.** `async with authed_client(role=Role.<MEMBER>, ...) as client:` — the `async with` form is non-negotiable; bare assignment leaks the ASGI transport. Raw `AsyncClient(transport=ASGITransport(...))` is otherwise reserved for `test-discovery-invariants` unauth probes. **Exception — an auth-less app** (no auth declared): there is no `authed_client`; drive the route with a plain `AsyncClient` over `real_app` (the public template above), still via `async with`.
7. **Cross-tenant reads return 404, not 403.** When a resource is tenant-scoped — the endpoint reads rows owned by a tenant other than the caller's — answering 403 leaks existence ("this resource exists but you can't see it"), so the route must return 404. Tenancy is derived from the auth claim plus the repository's owner filter, not from a declared field; test the 404 path explicitly whenever the resource is tenant-scoped.
8. **Per-resource fixtures live in the sibling `conftest.py`.** Factory fixtures (`make_foo`) return one fresh row per call. Single-row fixtures (`foo_id`) wrap a factory call. Both are function-scoped; no session-scoped row fixtures, ever.
9. **Error responses are asserted by `code`, not by message.** `assert response.json()["code"] == ConflictError.code` — message text drifts, the `code` constant is the contract. The actual HTTP status is asserted separately.
10. **No `@pytest.mark.integration` and no `@pytest.mark.asyncio`.** Path-scoped collection covers integration; `pytest-asyncio` is in auto mode. Markers are not needed and not added.
11. **No mocking inside this file.** No `unittest.mock`, no `monkeypatch` on infrastructure. If a test needs to mock, it isn't an integration test; move it to a domain unit test or to `pattern-compensating-tx` coverage at the repository-contract level.
12. **The S3 prefix is per-test.** Tests that upload/download blobs pass `s3_prefix` through to the route under test (typically via a header, query param, or payload field) and assert only on contents under that prefix.

### Inlined typing / import rules

- `pytest`, `httpx` (only for unauth probes — not used here), `myapp.restapi.schemas`, `myapp.domain.auth`, `myapp.domain.exceptions`. No `myapp.application.*` or `myapp.infrastructure.*` imports — the test drives over HTTP, not by reaching in.
- Full annotations on every fixture signature. Test signatures may omit return types (none has a return).
- No `from __future__ import annotations`.

### Hard stops

- `tests/integration/conftest.py` does not exist or does not provide `sf` / `real_app` → stop, install `test-integration-isolation` first.
- Spec asks to add a row to `RESOURCES.append(...)` / `_endpoints()` / `_EXPECTED` → stop, those registries are deleted; the equivalent check lives in `test-discovery-invariants` and derives from the running app.
- Spec asks the test to use `unittest.mock` / `MagicMock` / `AsyncMock` / `monkeypatch` → stop, integration tests use the real app + real DB.
- Spec asserts on a response field that is not in the Pydantic response schema → stop, extend the schema first via `restapi-schema`.
- Spec uses `[:4]` or `[:5]` natural-key suffixes "to avoid collisions" → stop, rollback isolation makes the DB empty; fixed names are fine.
- Spec asserts `len(items) == N + 1` to account for "the test's own row plus seed rows" → stop, rollback isolation drops everything; assert the exact count.
- Spec uses `AsyncClient(transport=ASGITransport(...))` directly for an authenticated request → stop, use `authed_client(...)`.
- Spec adds `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used; remove.
- Spec defines a fixture that returns the same row across multiple tests (session-scoped row) → stop, rows are per-test; factory + function-scoped wrapper only.
- Endpoint touches multipart or streaming and the spec does not describe the encoding → stop, consult `restapi-file-transfer` for the route side first.


<!-- merged from test-infra-capability-adapter -->

## Test — Infrastructure Capability Adapter

Produces one test file per capability adapter. Catches what unit-level coverage cannot: real SDK exception shapes, real upstream wire format, real crypto/parsing behavior, and the SDK-exception-to-domain-exception translator's mapping. This is the capability-adapter analogue of `test-repository-contract` for SQLAlchemy repositories.

### When to use vs. neighbours

- A new or modified adapter under `infrastructure/<adapter>/` (not `infrastructure/postgres/repositories/`) → this skill.
- A SQLAlchemy repository → `test-repository-contract`, not this skill.
- A fake the unit-test layer consumes → `test-fake-repository`. The fake's exception contract must match what the integration test pins here.
- The rollback / container `conftest.py` itself → `test-integration-isolation` (one-shot).
- A handler test that consumes a fake of this capability → `test-application-handler`.
- HTTP-layer (route + auth + OpenAPI) → `test-restapi-endpoint`.

### Pick the flavor

- **Containerized backend.** Adapter speaks to a service that runs in a Testcontainer (MinIO for S3, Postgres for non-aggregate stores, Redis, Kafka). Drives the real client against the real container; consumes a resource fixture (`s3`, `minio_bucket`, `redis`) from the integration conftest. **Lives under `tests/integration/<adapter>/`.**
- **HTTP gateway with `respx`.** Adapter speaks `httpx` to a third-party HTTP API. Wraps the real `httpx.AsyncClient` with `respx.mock` and asserts the request shape (URL, headers, body) on the way out and the translated response on the way back. The adapter code is real; only the network is intercepted. **Lives under `tests/integration/<adapter>/`.**
- **Pure-CPU.** Adapter does no IO — a JWT verifier, a canonicalizer, a renderer over in-memory bytes. Stdlib + the real crypto / parsing library. No fixtures, no containers. **Lives under `tests/unit/infrastructure/<adapter>/`.**

The flavor mirrors the adapter's template in `infra-capability-adapter` (real-SDK, HTTP gateway, sync pure-CPU). If the spec asks for two flavors in one file, split — one file per adapter, but `unit/` for pure-CPU and `integration/` for IO-bearing means a containerized adapter and a CPU adapter live in different roots regardless.

### Template(s)

#### Containerized backend (S3 / MinIO via the `s3` fixture)

```
tests/integration/<adapter>/
└── test_<tech>_<aggregate>_<adapter>.py
```

```python
import pytest
from aioboto3 import Session

from myapp.domain.exceptions import NotFoundError, UpstreamError
from myapp.infrastructure.s3.s3_foo_storage import S3FooStorage
from myapp.infrastructure.s3.settings import StorageSettings

async def test_upload_then_head_object_succeeds(
    s3_session: Session,
    storage_settings: StorageSettings,
) -> None:
    adapter = S3FooStorage(session=s3_session, settings=storage_settings)
    await adapter.upload(key="foos/alpha", body=b"payload")

    async with s3_session.client("s3", endpoint_url=str(storage_settings.endpoint_url)) as s3:
        head = await s3.head_object(Bucket=storage_settings.bucket, Key="foos/alpha")
    assert head["ContentLength"] == len(b"payload")

async def test_delete_removes_object(
    s3_session: Session,
    storage_settings: StorageSettings,
) -> None:
    adapter = S3FooStorage(session=s3_session, settings=storage_settings)
    await adapter.upload(key="foos/alpha", body=b"payload")

    await adapter.delete(key="foos/alpha")

    async with s3_session.client("s3", endpoint_url=str(storage_settings.endpoint_url)) as s3:
        with pytest.raises(Exception):  # boto raises ClientError("NoSuchKey")
            await s3.head_object(Bucket=storage_settings.bucket, Key="foos/alpha")

async def test_delete_missing_object_raises_not_found(
    s3_session: Session,
    storage_settings: StorageSettings,
) -> None:
    adapter = S3FooStorage(session=s3_session, settings=storage_settings)

    with pytest.raises(NotFoundError) as exc:
        await adapter.delete(key="foos/never-uploaded")

    assert exc.value.context["key"] == "foos/never-uploaded"
    assert exc.value.context["code"] == "NoSuchKey"

async def test_upload_to_nonexistent_bucket_raises_upstream_error(
    s3_session: Session,
    storage_settings: StorageSettings,
) -> None:
    bad_settings = storage_settings.model_copy(update={"bucket": "does-not-exist"})
    adapter = S3FooStorage(session=s3_session, settings=bad_settings)

    with pytest.raises((NotFoundError, UpstreamError)) as exc:
        await adapter.upload(key="foos/x", body=b"x")

    assert "code" in exc.value.context
```

#### HTTP gateway with `respx`

```
tests/integration/<adapter>/
└── test_http_<vendor>_gateway.py
```

```python
import httpx
import pytest
import respx

from myapp.domain.bars import BarToken
from myapp.domain.exceptions import NotFoundError, UpstreamError, ValidationError
from myapp.infrastructure.bar.http_bar_gateway import HttpBarGateway
from myapp.infrastructure.bar.settings import BarGatewaySettings

_BASE_URL = "https://api.bar.example"

@pytest.fixture
def settings() -> BarGatewaySettings:
    return BarGatewaySettings(base_url=_BASE_URL, api_key="test-key")

@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as c:
        yield c

@respx.mock
async def test_fetch_token_happy_path(
    client: httpx.AsyncClient, settings: BarGatewaySettings,
) -> None:
    route = respx.post(f"{_BASE_URL}/tokens").mock(
        return_value=httpx.Response(200, json={"token": "tok-1", "expires_at": "2030-01-01T00:00:00Z"}),
    )
    adapter = HttpBarGateway(client=client, settings=settings)

    token = await adapter.fetch_token(subject="alice")

    assert token == BarToken(value="tok-1", expires_at="2030-01-01T00:00:00Z")
    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read() == b'{"subject": "alice"}'

@respx.mock
async def test_fetch_token_404_raises_not_found(
    client: httpx.AsyncClient, settings: BarGatewaySettings,
) -> None:
    respx.post(f"{_BASE_URL}/tokens").mock(return_value=httpx.Response(404))
    adapter = HttpBarGateway(client=client, settings=settings)

    with pytest.raises(NotFoundError) as exc:
        await adapter.fetch_token(subject="missing")

    assert exc.value.context == {"subject": "missing", "status": 404}

@respx.mock
async def test_fetch_token_400_raises_validation(
    client: httpx.AsyncClient, settings: BarGatewaySettings,
) -> None:
    respx.post(f"{_BASE_URL}/tokens").mock(return_value=httpx.Response(400))
    adapter = HttpBarGateway(client=client, settings=settings)

    with pytest.raises(ValidationError) as exc:
        await adapter.fetch_token(subject="malformed")

    assert exc.value.context == {"subject": "malformed", "status": 400}

@respx.mock
async def test_fetch_token_503_raises_upstream(
    client: httpx.AsyncClient, settings: BarGatewaySettings,
) -> None:
    respx.post(f"{_BASE_URL}/tokens").mock(return_value=httpx.Response(503))
    adapter = HttpBarGateway(client=client, settings=settings)

    with pytest.raises(UpstreamError) as exc:
        await adapter.fetch_token(subject="alice")

    assert exc.value.context == {"subject": "alice", "status": 503}

@respx.mock
async def test_fetch_token_network_error_raises_upstream(
    client: httpx.AsyncClient, settings: BarGatewaySettings,
) -> None:
    respx.post(f"{_BASE_URL}/tokens").mock(side_effect=httpx.ConnectError("boom"))
    adapter = HttpBarGateway(client=client, settings=settings)

    with pytest.raises(UpstreamError) as exc:
        await adapter.fetch_token(subject="alice")

    assert exc.value.context["reason"] == "ConnectError"
```

#### Pure-CPU verifier / renderer

```
tests/unit/infrastructure/<adapter>/
└── test_<tech>_<verb>.py
```

```python
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from myapp.domain.auth import BarToken
from myapp.domain.exceptions import AuthError
from myapp.infrastructure.jwt.pyjwt_bar_token_verifier import PyJwtBarTokenVerifier
from myapp.infrastructure.jwt.settings import JwtSettings

def _keypair() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pem_public = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return pem_private, pem_public

_PRIVATE_PEM, _PUBLIC_PEM = _keypair()

def _settings() -> JwtSettings:
    return JwtSettings(public_key=_PUBLIC_PEM, algorithm="RS256", audience="myapp")

def _sign(claims: dict[str, object]) -> str:
    return jwt.encode(claims, _PRIVATE_PEM, algorithm="RS256")

def test_verify_valid_token_returns_bar_token() -> None:
    verifier = PyJwtBarTokenVerifier(settings=_settings())
    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    token = _sign({"sub": "alice", "aud": "myapp", "exp": exp})

    result = verifier.verify(token)

    assert result == BarToken(subject="alice", expires_at=exp)

def test_verify_expired_token_raises_auth_error() -> None:
    verifier = PyJwtBarTokenVerifier(settings=_settings())
    exp = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    token = _sign({"sub": "alice", "aud": "myapp", "exp": exp})

    with pytest.raises(AuthError) as exc:
        verifier.verify(token)

    assert exc.value.context == {"reason": "expired"}

def test_verify_wrong_audience_raises_auth_error() -> None:
    verifier = PyJwtBarTokenVerifier(settings=_settings())
    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    token = _sign({"sub": "alice", "aud": "other-app", "exp": exp})

    with pytest.raises(AuthError) as exc:
        verifier.verify(token)

    assert exc.value.context["reason"] == "InvalidAudienceError"

def test_verify_tampered_signature_raises_auth_error() -> None:
    verifier = PyJwtBarTokenVerifier(settings=_settings())
    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    token = _sign({"sub": "alice", "aud": "myapp", "exp": exp})

    with pytest.raises(AuthError) as exc:
        verifier.verify(token[:-4] + "AAAA")

    assert exc.value.context["reason"] in {
        "InvalidSignatureError", "DecodeError",
    }
```

### Rules

#### Form

1. **One test file per adapter.** Naming: `test_<tech>_<aggregate_or_area>.py` (containerized / respx) or `test_<tech>_<verb>.py` (CPU). Mirrors the adapter's module name.
2. **Path follows the flavor.** Containerized + respx → `tests/integration/<adapter>/`. CPU → `tests/unit/infrastructure/<adapter>/`.
3. **Module-level helpers, not fixtures, for keypairs / canonical inputs** in CPU tests. Construct once at module scope.

#### Coverage

4. **Every public method gets a happy-path test.** Drive the adapter; assert the observable side effect (object exists in S3, response matches schema, return value equals literal).
5. **Every row of the adapter's `exception_map` gets a dedicated test.** The bug class "translator handles error code X but not Y" only surfaces when each row is exercised. Skipping translator rows is the most common gap.
6. **`assert exc.value.context["<key>"] == <value>` on every translated exception.** This is the capability-adapter analogue of the `context["constraint"]` rule in `test-repository-contract`. The fake-based handler test cannot verify this — only this test can.
7. **For HTTP gateways, also assert the request shape** at least once: URL, method, headers (especially `Authorization`), and body. This pins the wire contract against the upstream, not just the error translation.
8. **Network-layer failures are tested as upstream errors.** For respx flavor, include a `ConnectError` / `ReadTimeout` test that asserts `UpstreamError`. For containerized flavor, a bad-bucket / bad-credentials test that asserts the fallback translation.

#### Real, not mocked

9. **Use the real SDK client.** No `unittest.mock`, no `MagicMock`. The SDK is the boundary; mocking it defeats the test's purpose (catching mismatches between assumed and actual SDK exception shapes).
10. **`respx` is not a mock of our code** — it intercepts the network only. The `httpx.AsyncClient` and the adapter under test are both real. This is the HTTP analogue of "real Postgres via Testcontainer."
11. **No fake / in-memory implementation of the protocol in this test.** Fakes are for handler unit tests (`test-fake-repository` / `test-application-handler`). This test exercises the real adapter — that's the whole point.

#### Containerized flavor specifics

12. **Take the resource fixture, not raw settings.** Containerized adapters need a live client (`s3_session`, `redis`). The fixture comes from the integration conftest, scoped session for the container and function for per-test isolation.
13. **No rollback assumption.** Unlike Postgres + `sf`, S3 / Redis / Kafka may not roll back. Either the fixture cleans up (preferred — extend `test-integration-isolation`) or each test uses a unique key prefix scoped to the test. Specify which in the spec.
14. **Don't bypass the adapter to drive setup.** For success assertions, you may inspect the backend directly (`s3.head_object`) — that is the observation. But for setup that exists to drive the test, go through the adapter (`adapter.upload(...)` then `adapter.delete(...)`).

#### respx flavor specifics

15. **Mark every test with `@respx.mock`** — pytest fixtures interact badly with respx context managers; the decorator is the canonical form.
16. **Pin the URL pattern exactly.** `respx.post(f"{_BASE_URL}/tokens")`, not `respx.post(re.compile(".*"))`. A pattern broad enough to also match accidental other requests hides bugs.
17. **Assert `route.called` on happy-path tests.** Forgetting to await the upstream call would otherwise pass silently because respx returns a default 200.
18. **Network errors via `side_effect=httpx.ConnectError(...)`** — that exercises the `except httpx.HTTPError` arm of the adapter, which the status-code path does not.

#### CPU flavor specifics

19. **Real crypto, real parsing.** For a JWT verifier, generate a real RSA keypair at module scope and sign with `jwt.encode(...)`. For a canonicalizer, feed it real inputs and assert literal outputs.
20. **One `test_*` per `except` arm in the adapter.** `ExpiredSignatureError`, `InvalidAudienceError`, `InvalidSignatureError`, generic `InvalidTokenError` — each gets a test that triggers exactly that exception.
21. **No fixtures.** Pure-CPU adapters are constructed in-line in each test from module-level settings. They have no lifecycle.

### Inlined typing / import rules

- `pytest`, `respx` (HTTP flavor), `httpx`, `jwt` / `cryptography` (CPU flavor), the real SDK, `myapp.domain.*`, `myapp.infrastructure.<adapter>.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature. Resource-fixture types (`Session`, `httpx.AsyncClient`) come from the SDK / library, not the project.
- No `from __future__ import annotations`.

### Hard stops

- `tests/integration/conftest.py` does not provide the required resource fixture (`s3_session`, `redis`, …) for a containerized flavor → stop, extend `test-integration-isolation` first.
- Spec asks for `unittest.mock` / `MagicMock` of the SDK client → stop, the SDK boundary is exactly what this test exists to verify; use containers or `respx` instead.
- Spec asks to mock the adapter itself → stop, that's a handler unit test (`test-application-handler` + `test-fake-repository`).
- Spec asks for `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither marker is used in this project.
- Spec asks to assert `pytest.raises(<SdkExceptionClass>)` directly → stop, the SDK exception must never escape the adapter; the test asserts the translated `DomainError` subclass.
- Spec asks to assert on a translated exception without checking `context` keys → stop, the context map is the load-bearing contract this test exists to pin.
- Spec asks for a happy-path test only with no error-translation cases → stop, the exception map must be covered row-by-row.
- Spec includes FastAPI / `httpx.AsyncClient` over `ASGITransport` / DI container references → stop, that's `test-restapi-endpoint`.
- CPU adapter spec asks to use `respx` or a container → stop, pure-CPU code needs neither; if IO has crept in, the adapter is mis-classified.


<!-- merged from test-discovery-invariants -->

## Test — Discovery Invariants

One-shot per project. Four or five integration files under `tests/integration/api/` (the `test_unauth_returns_401.py` probe is emitted only when the app declares auth — see Rules) plus one unit-level app-construction smoke. Each one iterates — or constructs — the running app and asserts a single global property; none of them needs to be edited when an endpoint is added or removed.

### When to use vs. neighbours

- First-time scaffold of the cross-cutting tests → this skill.
- A per-endpoint integration test → `test-restapi-endpoint`.
- The rollback fixture / containers / `real_app` → `test-integration-isolation` (owns `real_app`, which every test here imports).
- The `authed_client` factory → `test-integration-authed-client` (not consumed here — see Rule 8).
- A grep-firewall static rule → `test-architecture-rule` (compile-time, not runtime).

### Template(s)

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

#### `tests/unit/restapi/test_app_constructs.py`

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

This lives at the **unit** layer, not under `tests/integration/`, on purpose: `create_app` needs **no** database — `dependency-injector` providers are lazy, so it wires routers/middleware/error-handlers without resolving a handler or opening a connection. Placing it under `tests/integration/` would drag that tree's session-autouse `_migrated_db` / `_guard_against_real_db` fixtures and require Postgres, defeating the point — the construct-time defect class must be catchable with no Docker daemon (exactly the environment where mypy/ruff/unit run green and miss it). The test is structural, not a body test: it passes on a fresh scaffold (route functions exist with valid signatures; their `NotImplementedError` bodies are never *called* by construction or `openapi()`), so a missing dependency reds it at scaffold time, before any implementer runs.

#### `test_unauth_returns_401.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from myapp.domain.exceptions import UnauthorizedError
from myapp.restapi.dependencies import get_current_user

def _is_protected(route: APIRoute) -> bool:
    """A route is protected iff its dependency tree includes `get_current_user`
    or `require_role`. Public routes (info, health, OpenAPI itself) are
    naturally excluded.

    `dependant` is a FastAPI route INTERNAL — not part of the typed public
    surface, and across FastAPI versions mypy may not see it on `APIRoute`
    (0.137 stopped exposing `.dependant`/`.responses`). Reach it via `getattr`
    so the test type-checks on whatever version `uv` pins; the attribute is
    present at runtime on every version."""
    dependant = getattr(route, "dependant", None)
    for dep in getattr(dependant, "dependencies", []):
        if dep.call is get_current_user:
            return True
        if getattr(dep.call, "required_role", None) is not None:
            return True  # a _RoleDependency from require_role(Role.X) (see restapi-auth-dependency)
    return False

def _protected_routes(app: FastAPI) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_protected(route):
            continue
        for method in route.methods or set():  # Starlette types `methods` as set[str] | None
            if method == "HEAD":
                continue
            out.append((method, route.path))
    return out

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

#### `test_openapi_advertises_error_codes.py`

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
    stores them on `route.responses` as the dict produced by `error_responses(...)`.
    `responses` is a route internal mypy may not see on `APIRoute` (see
    `_is_protected`'s note) — reach it via `getattr`; present at runtime."""
    responses = getattr(route, "responses", {})
    return {code for code in responses if isinstance(code, int) and code >= 400}

async def test_every_route_advertises_what_its_decorator_declared(
    real_app: FastAPI,
) -> None:
    declared = _declared_codes(real_app)
    mismatches: list[str] = []

    for route in real_app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():  # Starlette types `methods` as set[str] | None
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

#### `test_cors.py`

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

#### `test_request_size_limit.py`

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

#### `test_info.py`

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

### Rules

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
12. **`test_app_constructs.py` is the always-emitted, unit-level construct smoke.** It is the one file this skill places at `tests/unit/restapi/`, not `tests/integration/api/`, because it needs no database (lazy DI providers → `create_app` opens nothing) and must run with no Docker daemon — the environment where the other gates pass and a construct-time dependency gap (`python-multipart`, …) slips through. Construct via `create_app(container=Container())` directly (no `real_app` fixture), assert `app.openapi()["paths"]`. Sync, no fixtures, no `await`. It is structural (green on a fresh scaffold), so it is emitted for every app, auth or not.

### Inlined typing / import rules

- `pytest`, `fastapi`, `fastapi.routing`, `httpx`, `myapp.containers`, `myapp.restapi.main`, `myapp.restapi.dependencies`, `myapp.domain.exceptions` (for the `UnauthorizedError.code` constant the 401 test asserts against).
- Full annotations on every helper.
- No `from __future__ import annotations`.

### Hard stops

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
- Project declares no auth (every endpoint anonymous) → do not produce `test_unauth_returns_401.py`; its `get_current_user` / `UnauthorizedError` imports do not exist in an auth-less app, and there are no protected routes to probe (Rule 11).
- Spec freezes the `WWW-Authenticate` challenge to a specific realm (`Bearer realm="myapp"`) → stop, only the scheme is load-bearing (`.startswith("Bearer")`); the realm is app-specific.
- Spec pins the 401 body code to a literal string (`"UNAUTHORIZED"`) → stop, assert against the domain exception's `.code` constant, not a frozen literal.
- Spec proposes placing `test_app_constructs.py` under `tests/integration/` (next to the other discovery tests) → stop, it stays at `tests/unit/restapi/`: under `tests/integration/` the session-autouse `_migrated_db` / `_guard_against_real_db` fixtures would force Postgres on a check that opens no connection, so it could no longer run without a Docker daemon — the one place the construct-time defect class is catchable.
- Spec makes the construct smoke `async` / gives it `real_app` or any DB fixture → stop, it constructs via `create_app(container=Container())` directly and is plain sync; needing a fixture means it is no longer the Docker-less unit smoke.


## The integration testing constitution (shared)

These rules govern the integration tier and were part of the catalog-level testing constitution; they live here now (they moved out of `test-principles`, which is reduced to the paid-fixes guard). The pyramid, fixture-vs-builder, AAA, no-mocks and naming rules live in `testing-unit`.

## The conftest hierarchy

```
tests/
├── conftest.py                                  # empty; pytest-asyncio mode lives in pyproject.toml
├── helpers/
│   └── jwt.py                                   # sign_token(...) — auth apps only
├── unit/
│   ├── fakes/
│   │   └── fake_<aggregate>_repository.py       # no __init__.py, no conftest, direct import
│   ├── domain/                                  # domain unit tests
│   ├── application/                             # handler unit tests
│   ├── restapi/                                 # test_app_constructs.py — construct smoke, no DB (test-discovery-invariants)
│   └── test_architecture.py                     # grep firewalls
└── integration/
    ├── conftest.py                              # OWNED BY test-integration-isolation
    │                                            #   - postgres_container (session) — relational apps
    │                                            #   - db_settings (session) — relational apps
    │                                            #   - _migrated_db, _guard_against_real_db, _engine (session) — relational apps
    │                                            #   - _outer_connection, sf (function) — relational apps
    │                                            #   - real_app (function) — consumes jwt_settings from down-tree WHEN the app has auth
    │                                            #   - minio_container, storage_settings (session) — blob-store apps only
    │                                            #   - s3_prefix (function), _cleanup_bucket_at_session_end — blob-store apps only
    ├── postgres/                                # repository contract tests; uses `sf` only
    │   └── test_<aggregate>_repository.py
    └── api/
        ├── conftest.py                          # OWNED BY test-integration-authed-client (auth apps only)
        │                                        #   - rsa_keypair (session) — auth apps only
        │                                        #   - jwt_settings (session) — consumed by real_app; auth apps only
        │                                        #   - authed_client (function; consumes real_app) — auth apps only
        ├── test_unauth_returns_401.py           # OWNED BY test-discovery-invariants
        ├── test_openapi_advertises_error_codes.py
        ├── test_cors.py
        ├── test_request_size_limit.py
        ├── test_info.py
        └── <resource>/
            ├── conftest.py                      # per-resource fixtures (make_foo, foo_id, bar_id)
            │                                    # owned by the team adding the resource;
            │                                    # not by any single skill
            └── test_<verb>_<noun>.py            # one file per endpoint
```

Two coupling points are deliberate and load-bearing:

1. **A fixture may consume a setting defined down-tree** — the canonical case being `real_app` (in `tests/integration/conftest.py`) consuming `jwt_settings` from down-tree `tests/integration/api/conftest.py`, **when the app declares auth**. Pytest's fixture resolution walks the conftest hierarchy from the *consuming test* outward, so a test under `tests/integration/api/` resolves the down-tree `jwt_settings` before pytest binds it into `real_app`. The down-tree-resolution mechanism is the universal, load-bearing point; the `jwt_settings` instance is **conditional** — an auth-less app has no such fixture and `real_app` does not consume or override it (see `test-integration-isolation`). Either way **`real_app` is only usable from tests under `tests/integration/api/`** — repository contract tests don't need it.
2. **No `tests/unit/fakes/__init__.py` and no `__all__`** — handler tests import fakes via the full path (`from tests.unit.fakes.fake_foo_repository import FakeFooRepository`). This is deliberate: fakes never leak into the production import graph.

## Fixture scope rules

- **Session-scoped fixtures** — the expensive, stateless-across-tests ones the app's features require: the postgres container + engine + test-DB guard + migration autouse (relational apps), the minio container (blob-store apps), the RSA keypair + JWT settings (auth apps). Anything expensive to construct and stateless across tests; a feature the app doesn't have contributes none of these.
- **Function-scoped fixtures** — everything else. `sf`, `real_app`, `authed_client`, all row factories (`make_foo`, `make_org`, …), `s3_prefix`. Per-test rows are non-negotiable: rollback isolation requires them.
- **No `module`-scoped or `class`-scoped fixtures** in this project. The two scopes that exist (session, function) are sufficient and easier to reason about.
- **No autouse fixtures except**: the session-scoped DB guard, the session-scoped migration runner, the session-end bucket cleanup, and (optionally) a per-test `_reset_captured_singletons` if `containers.py` snapshots settings at construction time. Each autouse is documented; no one ever adds a "convenience" autouse.

## Reliability rules (local-vs-CI parity)

1. **All persistent state is ephemeral.** Postgres and MinIO come from testcontainers in dev and CI alike. No "developer's local Postgres" mode.
2. **Per-test rollback isolation.** Every integration test starts with an empty DB; nothing leaks between tests. Tests can assert exact counts.
3. **Tests don't depend on execution order.** Each test constructs its own state. Running the suite with `-p no:randomly` and with random ordering must produce the same result.
4. **No `time.sleep`.** If a test "needs to wait", it needs the right `await` instead.
5. **Datetimes asserted with `>=`, not `==`.** Postgres `now()` can return identical timestamps within a transaction; clock-based equality flakes.
6. **UUIDs used in assertions are constructed inside the test**, not pulled from `uuid.uuid4()` at module scope (except `_CALLER` which is conventional and irrelevant to assertion shape).
7. **No environment-dependent values.** Tests must not read `os.environ` or check `os.getenv("CI")` to alter behavior. The isolation skill handles the local/CI fork once, in `postgres_container`.
8. **`@pytest.mark.integration` / `@pytest.mark.asyncio` are never used.** Path-based collection separates unit from integration; `pytest-asyncio` runs in auto mode (declared once in `pyproject.toml`).


## Docker-absence is a clean skip, never a raising fixture

An integration test's environment guard MUST be a clean `pytest.skip(...)` / `@pytest.mark.skipif(...)` on daemon absence — **never** a fixture that *raises* when Docker is missing. The change cycle's gate carves out exactly one exception to its "a skipped baseline test is RED" inventory rule: a baseline integration test that the gate's **own probe** found Docker-absent, and that therefore *skipped*, is exempt (spec §5.1, ruling on T04b). A fixture that raises or errors instead of skipping is not covered by that carve-out, so on a Docker-less machine it turns the whole gate permanently RED. Guard on the daemon with a skip; let the gate's environment probe — not a skip-reason string — decide the carve-out.
