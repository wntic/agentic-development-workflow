---
name: test-infra-capability-adapter
description: The house form for one capability adapter's test in three flavours — a containerized backend for IO-bearing adapters, `respx` over real `httpx` for HTTP gateways, stdlib plus real crypto for pure-CPU verifiers — each asserting the SDK-exception to domain-exception map round-trip.
when_to_use: Writing or changing the test for an infrastructure capability adapter.
paths: tests/**
---

# Test — Infrastructure Capability Adapter

Produces one test file per capability adapter. Catches what unit-level coverage cannot: real SDK exception shapes, real upstream wire format, real crypto/parsing behavior, and the SDK-exception-to-domain-exception translator's mapping. This is the capability-adapter analogue of `test-repository-contract` for SQLAlchemy repositories.

## When to use vs. neighbours

- A new or modified adapter under `infrastructure/<adapter>/` (not `infrastructure/postgres/repositories/`) → this skill.
- A SQLAlchemy repository → `test-repository-contract`, not this skill.
- A fake the unit-test layer consumes → `test-fake-repository`. The fake's exception contract must match what the integration test pins here.
- The rollback / container `conftest.py` itself → `test-integration-isolation` (one-shot).
- A handler test that consumes a fake of this capability → `test-application-handler`.
- HTTP-layer (route + auth + OpenAPI) → `test-restapi-endpoint`.

## Pick the flavor

- **Containerized backend.** Adapter speaks to a service that runs in a Testcontainer (MinIO for S3, Postgres for non-aggregate stores, Redis, Kafka). Drives the real client against the real container; consumes a resource fixture (`s3`, `minio_bucket`, `redis`) from the integration conftest. **Lives under `tests/integration/<adapter>/`.**
- **HTTP gateway with `respx`.** Adapter speaks `httpx` to a third-party HTTP API. Wraps the real `httpx.AsyncClient` with `respx.mock` and asserts the request shape (URL, headers, body) on the way out and the translated response on the way back. The adapter code is real; only the network is intercepted. **Lives under `tests/integration/<adapter>/`.**
- **Pure-CPU.** Adapter does no IO — a JWT verifier, a canonicalizer, a renderer over in-memory bytes. Stdlib + the real crypto / parsing library. No fixtures, no containers. **Lives under `tests/unit/infrastructure/<adapter>/`.**

The flavor mirrors the adapter's template in `infra-capability-adapter` (real-SDK, HTTP gateway, sync pure-CPU). If the spec asks for two flavors in one file, split — one file per adapter, but `unit/` for pure-CPU and `integration/` for IO-bearing means a containerized adapter and a CPU adapter live in different roots regardless.

## Template(s)

### Containerized backend (S3 / MinIO via the `s3` fixture)

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

### HTTP gateway with `respx`

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

### Pure-CPU verifier / renderer

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

## Rules

### Form

1. **One test file per adapter.** Naming: `test_<tech>_<aggregate_or_area>.py` (containerized / respx) or `test_<tech>_<verb>.py` (CPU). Mirrors the adapter's module name.
2. **Path follows the flavor.** Containerized + respx → `tests/integration/<adapter>/`. CPU → `tests/unit/infrastructure/<adapter>/`.
3. **Module-level helpers, not fixtures, for keypairs / canonical inputs** in CPU tests. Construct once at module scope.

### Coverage

4. **Every public method gets a happy-path test.** Drive the adapter; assert the observable side effect (object exists in S3, response matches schema, return value equals literal).
5. **Every row of the adapter's `exception_map` gets a dedicated test.** The bug class "translator handles error code X but not Y" only surfaces when each row is exercised. Skipping translator rows is the most common gap.
6. **`assert exc.value.context["<key>"] == <value>` on every translated exception.** This is the capability-adapter analogue of the `context["constraint"]` rule in `test-repository-contract`. The fake-based handler test cannot verify this — only this test can.
7. **For HTTP gateways, also assert the request shape** at least once: URL, method, headers (especially `Authorization`), and body. This pins the wire contract against the upstream, not just the error translation.
8. **Network-layer failures are tested as upstream errors.** For respx flavor, include a `ConnectError` / `ReadTimeout` test that asserts `UpstreamError`. For containerized flavor, a bad-bucket / bad-credentials test that asserts the fallback translation.

### Real, not mocked

9. **Use the real SDK client.** No `unittest.mock`, no `MagicMock`. The SDK is the boundary; mocking it defeats the test's purpose (catching mismatches between assumed and actual SDK exception shapes).
10. **`respx` is not a mock of our code** — it intercepts the network only. The `httpx.AsyncClient` and the adapter under test are both real. This is the HTTP analogue of "real Postgres via Testcontainer."
11. **No fake / in-memory implementation of the protocol in this test.** Fakes are for handler unit tests (`test-fake-repository` / `test-application-handler`). This test exercises the real adapter — that's the whole point.

### Containerized flavor specifics

12. **Take the resource fixture, not raw settings.** Containerized adapters need a live client (`s3_session`, `redis`). The fixture comes from the integration conftest, scoped session for the container and function for per-test isolation.
13. **No rollback assumption.** Unlike Postgres + `sf`, S3 / Redis / Kafka may not roll back. Either the fixture cleans up (preferred — extend `test-integration-isolation`) or each test uses a unique key prefix scoped to the test. Specify which in the spec.
14. **Don't bypass the adapter to drive setup.** For success assertions, you may inspect the backend directly (`s3.head_object`) — that is the observation. But for setup that exists to drive the test, go through the adapter (`adapter.upload(...)` then `adapter.delete(...)`).

### respx flavor specifics

15. **Mark every test with `@respx.mock`** — pytest fixtures interact badly with respx context managers; the decorator is the canonical form.
16. **Pin the URL pattern exactly.** `respx.post(f"{_BASE_URL}/tokens")`, not `respx.post(re.compile(".*"))`. A pattern broad enough to also match accidental other requests hides bugs.
17. **Assert `route.called` on happy-path tests.** Forgetting to await the upstream call would otherwise pass silently because respx returns a default 200.
18. **Network errors via `side_effect=httpx.ConnectError(...)`** — that exercises the `except httpx.HTTPError` arm of the adapter, which the status-code path does not.

### CPU flavor specifics

19. **Real crypto, real parsing.** For a JWT verifier, generate a real RSA keypair at module scope and sign with `jwt.encode(...)`. For a canonicalizer, feed it real inputs and assert literal outputs.
20. **One `test_*` per `except` arm in the adapter.** `ExpiredSignatureError`, `InvalidAudienceError`, `InvalidSignatureError`, generic `InvalidTokenError` — each gets a test that triggers exactly that exception.
21. **No fixtures.** Pure-CPU adapters are constructed in-line in each test from module-level settings. They have no lifecycle.

## Inlined typing / import rules

- `pytest`, `respx` (HTTP flavor), `httpx`, `jwt` / `cryptography` (CPU flavor), the real SDK, `myapp.domain.*`, `myapp.infrastructure.<adapter>.*`. No `myapp.application.*`, no `myapp.restapi.*`.
- Full annotations on every test signature. Resource-fixture types (`Session`, `httpx.AsyncClient`) come from the SDK / library, not the project.
- No `from __future__ import annotations`.

## Hard stops

- `tests/integration/conftest.py` does not provide the required resource fixture (`s3_session`, `redis`, …) for a containerized flavor → stop, extend `test-integration-isolation` first.
- Spec asks for `unittest.mock` / `MagicMock` of the SDK client → stop, the SDK boundary is exactly what this test exists to verify; use containers or `respx` instead.
- Spec asks to mock the adapter itself → stop, that's a handler unit test (`test-application-handler` + `test-fake-repository`).
- Spec asks for `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither marker is used in this project.
- Spec asks to assert `pytest.raises(<SdkExceptionClass>)` directly → stop, the SDK exception must never escape the adapter; the test asserts the translated `DomainError` subclass.
- Spec asks to assert on a translated exception without checking `context` keys → stop, the context map is the load-bearing contract this test exists to pin.
- Spec asks for a happy-path test only with no error-translation cases → stop, the exception map must be covered row-by-row.
- Spec includes FastAPI / `httpx.AsyncClient` over `ASGITransport` / DI container references → stop, that's `test-restapi-endpoint`.
- CPU adapter spec asks to use `respx` or a container → stop, pure-CPU code needs neither; if IO has crept in, the adapter is mis-classified.
