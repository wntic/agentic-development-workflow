---
name: test-integration-isolation
description: The one-shot per-test isolation for the integration suite — `tests/integration/conftest.py` with session-scoped containers and engine, a function-scoped outer transaction, and the `sf` fixture that rolls back at teardown so each test starts on an empty database. Every integration test depends on it.
when_to_use: Laying the integration suite's isolation for a project, or changing the rollback or container fixtures.
paths: tests/**
---

# Test — Integration Isolation

One-shot per project. Produces `tests/integration/conftest.py` with the transaction-rollback fixture every other integration skill depends on. The contract this skill enforces: every integration test starts with an empty database; rows the test (and its handler) commit are rolled back at teardown.

**This is the relational-store isolation strategy.** The engine, the Alembic migration run, and the savepoint-rollback `sf` all assume a relational store — the per-test transaction that ROLLBACKs is a SQL-database mechanism. An app whose only datastore is client-style (qdrant / redis / …) has no engine, no migration chain, and cannot use savepoint rollback; it isolates by **per-test namespace + best-effort cleanup** instead (the `s3_prefix` block below is exactly that pattern). Lay the Postgres machinery only when the app has a relational store.

## When to use vs. neighbours

- Laying `tests/integration/conftest.py` for the first time → this skill.
- Per-resource row factories (`make_org`, `make_tag`, …) → not this skill; declare them in `tests/integration/api/<resource>/conftest.py` next to the tests that use them.
- The authed `httpx.AsyncClient` factory → `test-integration-authed-client`.
- A repository contract test → `test-repository-contract` (consumes the `sf` fixture this skill provides).
- An API endpoint test → `test-restapi-endpoint` (consumes both `sf` and `authed_client`).
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

## Rules

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

## Inlined typing / import rules

- `pytest`, `sqlalchemy.ext.asyncio`, `subprocess`, `os`, `sys`, stdlib `collections.abc` — and the project's `infrastructure.postgres.*` + `infrastructure.s3.*`.
- Full annotations on every fixture signature. `AsyncIterator[T]` for yielding fixtures with cleanup.
- No `from __future__ import annotations`.

## Hard stops

- Container has no overridable `session_factory` provider → stop, run `infra-di-provider` first to introduce the provider and the override hook.
- Spec asks to keep `function`-scoped engine (one engine per test) → stop, that's the old slow model; engine is session-scoped, only the connection is function-scoped.
- Spec asks to drop `join_transaction_mode="create_savepoint"` → stop, that flag is the whole point — without it the handler's commits either escape or fail.
- Spec asks for session-scoped row fixtures (`make_org` returning the same id across tests) → stop, rows are per-test; factories return fresh rows per call.
- Spec asks the `sf` fixture to bind to the engine directly (skipping the outer connection) → stop, that bypasses rollback and reintroduces every old failure mode.
- Spec asks to add a `truncate_all_tables` teardown alongside rollback → stop, rollback alone is sufficient; truncate is the fallback for DBs without nested transactions and is strictly slower.
- Project does not use S3 / MinIO but spec includes the bucket fixtures → strip the storage block; no need to start MinIO every session.
- The app has no relational store — a qdrant/redis-only app, say → stop laying the Postgres engine / Alembic / savepoint-`sf` machinery; there is no SQL transaction to roll back. Isolate the client stores by per-test namespace + session-end cleanup (the `s3_prefix` pattern), not by this fixture.
- The app has no auth (every endpoint anonymous) but the JWT override is present → strip the `jwt_settings` parameter and the `container.jwt_settings.override(...)` / `reset_override()` lines from `real_app`. An auth-less app has no `jwt_settings` provider, so the override raises `AttributeError`; whether an app has auth follows from its routes (see `restapi-auth-dependency`), it is not a universal.
