---
name: infra-capability-adapter
description: Apply when a spec needs the infrastructure adapter that satisfies a `domain/.../i_can_<verb>.py` capability protocol — object storage, token verifier, file renderer, third-party HTTP gateway, message publisher. Produces one adapter class under `infrastructure/<adapter>/` — grouped by the external tech (`s3/`, `jwt/`, `openai/`), never by domain concern — that wraps an SDK client (boto3, httpx, PyJWT, python-docx, …) and translates SDK exceptions into domain exceptions at the boundary. Does not produce the protocol (use `domain-capability-protocol`), the settings class (use `infra-settings`), the DI wiring (use `infra-di-provider`), or the SQLAlchemy repository for an aggregate (use `infra-sqlalchemy-repository`).

---

# Infrastructure Capability Adapter

Produces one adapter class that adapts a domain `ICan<Verb>` capability protocol to a concrete external system. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract. Boundary translation of SDK exceptions to domain exceptions is the central rule.

## When to use vs. neighbours

- Aggregate-root CRUD over Postgres → `infra-sqlalchemy-repository`, not this skill.
- The `ICan<Verb>` protocol file → `domain-capability-protocol`.
- The settings class (`<Tech>Settings`) the adapter consumes → `infra-settings`.
- The DI provider that constructs this adapter → `infra-di-provider` (almost always `Singleton`).
- An in-memory test stand-in for this capability → `test-fake-repository` (the `Fake<Capability>` flavor).

## File layout

```
src/<root>/infrastructure/<adapter>/    # <adapter> = the external tech: s3, jwt, openai, …
├── __init__.py            # update to re-export the new module
└── s3_foo_storage.py      # this skill writes this file
```

`<adapter>` is the external tech the adapter wraps (the manifest `adapter:` token): `s3/`, `jwt/`, `openai/`, `docx/`, `<vendor>/`. Infra groups by tech, not by domain concern. The filename names the tech too (`s3_*`, `pyjwt_*`, `docx_*`, `<vendor>_*`); the class follows (`<AdapterPascal><Role>`).

## Template — async, SDK-client form

```python
from collections.abc import Mapping

import aioboto3
from botocore.exceptions import ClientError

from myapp.domain.exceptions import (
    NotFoundError, UpstreamError, ValidationError,
)
from myapp.domain.foos import ICanStoreFoos

from .settings import StorageSettings

__all__ = ["S3FooStorage"]

_ERROR_CODE_MAP: Mapping[str, type[Exception]] = {
    "NoSuchKey": NotFoundError,
    "NoSuchBucket": NotFoundError,
    "InvalidRequest": ValidationError,
}

def _map_client_error(exc: ClientError, *, key: str) -> Exception:
    code = exc.response.get("Error", {}).get("Code", "")
    target = _ERROR_CODE_MAP.get(code)
    if target is NotFoundError:
        return NotFoundError("object not found", {"key": key, "code": code})
    if target is ValidationError:
        return ValidationError("invalid storage request", {"key": key, "code": code})
    return UpstreamError(
        "storage call failed",
        {"key": key, "code": code or "unknown"},
    )

class S3FooStorage:
    def __init__(self, session: aioboto3.Session, settings: StorageSettings) -> None:
        self._session = session
        self._bucket = settings.bucket
        self._endpoint_url = str(settings.endpoint_url)

    async def upload(self, key: str, body: bytes) -> None:
        try:
            async with self._session.client("s3", endpoint_url=self._endpoint_url) as s3:
                await s3.put_object(Bucket=self._bucket, Key=key, Body=body)
        except ClientError as exc:
            raise _map_client_error(exc, key=key) from exc

    async def delete(self, key: str) -> None:
        try:
            async with self._session.client("s3", endpoint_url=self._endpoint_url) as s3:
                await s3.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise _map_client_error(exc, key=key) from exc
```

## Template — async, HTTP-gateway form

```python
import httpx

from myapp.domain.exceptions import NotFoundError, UpstreamError, ValidationError
from myapp.domain.bars import BarToken, ICanFetchBarToken

from .settings import BarGatewaySettings

__all__ = ["HttpBarGateway"]

class HttpBarGateway:
    def __init__(self, client: httpx.AsyncClient, settings: BarGatewaySettings) -> None:
        self._client = client
        self._base_url = str(settings.base_url)
        self._api_key = settings.api_key.get_secret_value()

    async def fetch_token(self, subject: str) -> BarToken:
        try:
            response = await self._client.post(
                f"{self._base_url}/tokens",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"subject": subject},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _map_status(exc, subject=subject) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(
                "bar gateway unreachable",
                {"subject": subject, "reason": exc.__class__.__name__},
            ) from exc
        payload = response.json()
        return BarToken(value=payload["token"], expires_at=payload["expires_at"])

def _map_status(exc: httpx.HTTPStatusError, *, subject: str) -> Exception:
    status = exc.response.status_code
    if status == 404:
        return NotFoundError("bar subject not found", {"subject": subject, "status": status})
    if status == 400:
        return ValidationError("bar gateway rejected request", {"subject": subject, "status": status})
    return UpstreamError(
        "bar gateway error",
        {"subject": subject, "status": status},
    )
```

## Template — sync, pure-CPU form

For verifiers / canonicalizers / renderers with no IO. No `try/except` for IO; only translate the SDK's parse/verify errors.

```python
import jwt

from myapp.domain.auth import BarToken, ICanVerifyBarToken
from myapp.domain.exceptions import AuthError

from .settings import JwtSettings

__all__ = ["PyJwtBarTokenVerifier"]

class PyJwtBarTokenVerifier:
    def __init__(self, settings: JwtSettings) -> None:
        self._public_key = settings.public_key.get_secret_value()
        self._algorithm = settings.algorithm
        self._audience = settings.audience

    def verify(self, token: str) -> BarToken:
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self._algorithm],
                audience=self._audience,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token expired", {"reason": "expired"}) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(
                "invalid token",
                {"reason": exc.__class__.__name__},
            ) from exc
        return BarToken(subject=payload["sub"], expires_at=payload["exp"])
```

## Rules

### Form

1. **One class per module.** Filename names the tech (`s3_foo_storage.py`, `http_bar_gateway.py`, `pyjwt_bar_token_verifier.py`); class follows. The class name carries the concrete tech (`S3FooStorage`, not `FooStorage`).
2. **No explicit `(ICanX)` inheritance.** Structural subtyping at the DI site is the contract.
3. **Method signatures match the protocol exactly**, including keyword-only markers and async/sync mode.
4. **Place the module in `infrastructure/<adapter>/`** — its own external-tech directory (`s3/`, `jwt/`, `openai/`, …). Infra groups by external tech, never by domain concern; relational artifacts live under `infrastructure/postgres/`, each capability adapter under its own tech dir.

### Constructor

5. **Inject the SDK client and the settings class.** Both come from `containers.py`. Never construct an SDK client inline (`boto3.client(...)`, `httpx.AsyncClient(...)`) inside a method.
6. **Stash only what the methods need.** Pull `bucket`, `endpoint_url`, secrets, etc. out of settings in `__init__`; do not stash the whole settings object unless multiple methods read multiple fields.
7. **Secrets:** `SecretStr` fields are read once in `__init__` via `.get_secret_value()`; never log or expose them in `context`.

### Exception translation

8. **Catch the SDK's exception family at the boundary and raise a domain exception.** This is the capability-adapter analogue of `infra-sqlalchemy-repository`'s `IntegrityError` rule. Use `raise <DomainException>(...) from exc` so the original cause is preserved for logging.
9. **The SDK's exception type never escapes the adapter.** No `ClientError`, `HTTPStatusError`, `jwt.InvalidTokenError`, etc., crosses into application or entrypoints. The application layer catches only `DomainError`.
10. **Mandatory fallback.** When no specific case matches, raise a sensible default: `UpstreamError` for third-party / network failures, `AuthError` for auth-verifier failures, `ValidationError` only when the input was demonstrably malformed. Never return the raw exception; never `pass`.
11. **Populate `context` with the stable identifying inputs** (`key`, `subject`, `tenant_id`) plus the upstream code/status (`code`, `status`). Tests assert on these, and the central error handler logs them.
12. **Pick the most specific domain exception.** `NotFoundError` for "object/subject does not exist", `ValidationError` for "the upstream rejected the inputs as malformed", `AuthError` for token / credential rejection, `UpstreamError` for everything else (network, 5xx, unknown codes).

### No business logic, no logging

13. **Adapters are thin.** No retries (use the SDK's built-in retry policy via settings), no caching, no batching, no domain reasoning. If the spec asks for retry or backoff, it goes in the SDK config or a dedicated wrapper — not in this class body.
14. **No logging in the adapter.** The central error handler logs the resulting `DomainError`. The calling handler logs success. Adapters never log, never `print`. See `general-logging`.
15. **No instance state across calls** beyond constructor-injected handles. An adapter is safe to share as a `Singleton`.

### Compensating-transaction contract

16. **Mutating capabilities expose both the forward operation and the undo.** A storage adapter has `upload` *and* `delete`; a publisher that supports retraction has `publish` *and* `retract`. The catch-and-undo logic lives in the application handler (see `pattern-compensating-tx`), not in the adapter. The adapter's job is to make the undo callable.

## Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.foos import ICanStoreFoos`). Sibling modules within the same `infrastructure/<adapter>/` package use relative imports (`from .settings import BlobsSettings`).
- No `from __future__ import annotations`. Full annotations on every method.
- `X | None` over `Optional`. `Mapping[K, V]` / `Sequence[T]` (from `collections.abc`) for read-only views.
- SDK types stay inside the adapter; method signatures use domain types or primitives only.
- No `Any` except at the immediate raw-SDK-payload boundary (e.g. `payload: dict[str, Any] = response.json()` — convert to the domain type on the next line).

## Package wiring

The `infrastructure/<adapter>/__init__.py` re-exports the new module via `from .s3_foo_storage import *`. Follow `general-python-package`.

## Hard stops

- Spec asks the adapter to talk to Postgres / SQLAlchemy / Alembic → stop, use `infra-sqlalchemy-repository` and `infra-sqlalchemy-table`.
- Spec asks the adapter to inherit from `ICanX` explicitly → stop, structural subtyping is the contract.
- Spec asks the adapter to log → stop, adapters do not log; the central error handler owns failure logs.
- Spec asks the adapter to retry, cache, or batch internally → stop, configure that on the SDK client (in `containers.py`) or extract a separate wrapper class.
- Spec asks the adapter to construct its own SDK client (`boto3.client(...)`, `httpx.AsyncClient()`) → stop, both the client and the settings are injected from DI.
- Spec asks the adapter to raise an SDK exception type or `Exception` → stop, every SDK exception must be translated into a `DomainError` subclass at the boundary.
- Spec has no `exception_map` for a method that can fail → stop, request the mapping before writing the method body.
