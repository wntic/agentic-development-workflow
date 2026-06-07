---
name: test-restapi-endpoint
description: Apply when adding or modifying an integration test for one REST endpoint. Produces one self-contained test file under `tests/integration/api/<resource>/test_<verb>_<noun>.py` that drives the real FastAPI app over ASGI against the rolled-back database from `test-integration-isolation`. Consumes the `real_app`, `authed_client`, `sf`, and `s3_prefix` fixtures; declares any per-resource fixtures it needs in the sibling `conftest.py`. Validates 2xx response bodies through the Pydantic response schema. Does not own the rollback fixture (use `test-integration-isolation`), the auth-client factory (use `test-integration-authed-client`), the cross-cutting "every route returns 401 unauth" / "OpenAPI codes match `error_responses(...)`" tests (use `test-discovery-invariants`), the repository contract (use `test-repository-contract`), or any unit test.
---

# Test — REST API Endpoint

Produces one integration-test file per endpoint. Self-contained: every test in the file constructs its own state by calling factory fixtures or POSTing through the API; no cross-test state, no shared registries, no cross-file edits when a new endpoint is added.

## When to use vs. neighbours

- A new or modified endpoint added by `restapi-endpoint` → this skill.
- A new resource introduces several endpoints (create + list + get + update + delete) → invoke this skill once per endpoint file. Sibling files share a per-resource `conftest.py`.
- The `tests/integration/conftest.py` itself (rollback, container fixtures) → `test-integration-isolation` (one-shot).
- The `authed_client` factory → `test-integration-authed-client` (one-shot).
- Cross-cutting "every route 401 unauth" / "every route's OpenAPI codes match `error_responses(...)`" → `test-discovery-invariants` (one-shot; discovers from `app.routes` and `app.openapi()`).
- Repository contract (real DB, no HTTP) → `test-repository-contract`.
- Pure domain unit test → `test-domain-entity` / `test-domain-value-object` / `test-domain-enum` / `test-domain-service`.

## Template(s)

```
tests/integration/api/<resource>/
├── conftest.py                                  # per-resource fixtures (sibling-shared)
└── test_<verb>_<noun>.py                        # one file per endpoint
```

### `test_<verb>_<noun>.py` — JSON mutation, role-gated, tenant-scoped

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

### `test_<verb>_<noun>.py` — GET, tenant-scoped, cross-org returns 404 (not 403)

```python
import uuid

import pytest

from myapp.domain.auth import Role
from myapp.restapi.schemas import FooResponse

async def test_get_foo_returns_payload(authed_client, foo_in_org):
    foo_id, org_id = foo_in_org
    async with authed_client(role=Role.COLLABORATOR, org_id=org_id) as client:
        response = await client.get(f"/foos/{foo_id}")

    assert response.status_code == 200
    FooResponse.model_validate(response.json())

async def test_get_foo_in_other_org_returns_404(authed_client, foo_in_org):
    foo_id, _ = foo_in_org
    other_org = uuid.uuid4()

    async with authed_client(role=Role.COLLABORATOR, org_id=other_org) as client:
        response = await client.get(f"/foos/{foo_id}")

    assert response.status_code == 404  # NOT 403 — prevents enumeration
```

### Per-resource `conftest.py`

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

### Multipart upload — single-test skeleton

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

### Streaming download — single-test skeleton

```python
async def test_download_attachment_streams_bytes(authed_client, foo_id, attachment_id):
    async with authed_client(role=Role.ADMIN) as client:
        response = await client.get(f"/foos/{foo_id}/attachments/{attachment_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert len(response.content) > 0
```

## Rules

1. **One file per endpoint.** Filename mirrors the route: `test_create_foo.py`, `test_list_foos.py`, `test_delete_foo.py`. Each file holds the happy path + every error path for that one endpoint. No mega-files spanning a whole resource.
2. **Every 2xx body is validated through the Pydantic response schema.** `body = FooResponse.model_validate(response.json())`. Catches contract drift that field-by-field assertions miss. Import schemas from the subpackage root (`from myapp.restapi.schemas import FooResponse`), never from the inner module — the wildcard re-export is the contract.
3. **No cross-cutting registries.** Adding a new endpoint touches exactly one new test file. The "every route returns 401 unauth" and "every route declares its error codes in OpenAPI" checks are owned by `test-discovery-invariants` and derive their inputs from `app.routes` / `app.openapi()` — no `_endpoints()` / `_EXPECTED` tables to extend.
4. **Self-contained tests.** Each test builds its own state via per-resource factory fixtures (`make_foo`) or by POSTing through the API. Since the rollback contract guarantees an empty DB at test start, fixed natural keys (`name="alpha"`) are safe — no `uuid4().hex[:8]` suffix required.
5. **Exact counts and orderings are now correct.** `assert len(items) == N`, `assert items[0].id == ...`, `assert response.json()["total"] == 3` — the empty-DB-at-start contract makes these reliable. Defensive `any(...)` filters belong to the pre-rollback world; remove them.
6. **`authed_client` is the only sanctioned client.** `async with authed_client(role=Role.ADMIN, org_id=...) as client:` — the `async with` form is non-negotiable; bare assignment leaks the ASGI transport. Raw `AsyncClient(transport=ASGITransport(...))` is for unauth probes only and lives in `test-discovery-invariants`, not here.
7. **Cross-org reads return 404, not 403.** Tenant-scoped resources prevent enumeration: "this resource exists but you can't see it" leaks existence. Test the 404 path explicitly when `cross_org_visibility = tenant-scoped`.
8. **Per-resource fixtures live in the sibling `conftest.py`.** Factory fixtures (`make_foo`) return one fresh row per call. Single-row fixtures (`foo_id`) wrap a factory call. Both are function-scoped; no session-scoped row fixtures, ever.
9. **Error responses are asserted by `code`, not by message.** `assert response.json()["code"] == ConflictError.code` — message text drifts, the `code` constant is the contract. The actual HTTP status is asserted separately.
10. **No `@pytest.mark.integration` and no `@pytest.mark.asyncio`.** Path-scoped collection covers integration; `pytest-asyncio` is in auto mode. Markers are not needed and not added.
11. **No mocking inside this file.** No `unittest.mock`, no `monkeypatch` on infrastructure. If a test needs to mock, it isn't an integration test; move it to a domain unit test or to `pattern-compensating-tx` coverage at the repository-contract level.
12. **The S3 prefix is per-test.** Tests that upload/download blobs pass `s3_prefix` through to the route under test (typically via a header, query param, or payload field) and assert only on contents under that prefix.

## Inlined typing / import rules

- `pytest`, `httpx` (only for unauth probes — not used here), `myapp.restapi.schemas`, `myapp.domain.auth`, `myapp.domain.exceptions`. No `myapp.application.*` or `myapp.infrastructure.*` imports — the test drives over HTTP, not by reaching in.
- Full annotations on every fixture signature. Test signatures may omit return types (none has a return).
- No `from __future__ import annotations`.

## Hard stops

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
