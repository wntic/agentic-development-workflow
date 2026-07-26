---
name: infra-integration
description: "House style for non-persistence infrastructure: capability adapters wrapping SDKs (`ICan<Verb>` implementations with an SDK-exception-to-domain-exception translator at the boundary), `pydantic-settings` classes (one per integration, env prefix stemming on the product), and `dependency-injector` container wiring (the `Singleton` vs `Factory` choice and declaration order)."
when_to_use: Producing a capability adapter, a settings class, or wiring a class into `containers.py`.
---
# Infrastructure — integration (adapters, settings, DI)

This merged skill covers 3 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from infra-capability-adapter -->

## Infrastructure Capability Adapter

Produces one adapter class that adapts a domain `ICan<Verb>` capability protocol to a concrete external system. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract. Boundary translation of SDK exceptions to domain exceptions is the central rule.

### When to use vs. neighbours

- Aggregate-root CRUD over Postgres → `infra-sqlalchemy-repository`, not this skill.
- The `ICan<Verb>` protocol file → `domain-capability-protocol`.
- The settings class (`<Tech>Settings`) the adapter consumes → `infra-settings`.
- The DI provider that constructs this adapter → `infra-di-provider` (almost always `Singleton`).
- An in-memory test stand-in for this capability → `test-fake-repository` (the `Fake<Capability>` flavor).

### File layout

```
src/<root>/infrastructure/<adapter>/    # <adapter> = the external tech: s3, jwt, openai, …
├── __init__.py            # update to re-export the new module
└── s3_foo_storage.py      # this skill writes this file
```

`<adapter>` is the external tech the adapter wraps (the app's `adapter:` token): `s3/`, `jwt/`, `openai/`, `docx/`, `<vendor>/`. Infra groups by tech, not by domain concern. The filename names the tech too (`s3_*`, `pyjwt_*`, `docx_*`, `<vendor>_*`); the class follows (`<AdapterPascal><Role>`).

### Template — async, SDK-client form

```python
from collections.abc import Mapping
from typing import cast

import aioboto3
from botocore.exceptions import ClientError

from myapp.domain.exceptions import (
    NotFoundError, UpstreamError, ValidationError,
)
# No import of the protocol the adapter satisfies (ICanStoreFoos) — structural subtyping
# at the DI site is the contract (Rule 2); importing it leaves a dead F401.

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

    async def download(self, key: str) -> bytes:
        try:
            async with self._session.client("s3", endpoint_url=self._endpoint_url) as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                # `Body.read()` is typed `Any` by the SDK. Narrow it to the protocol's `bytes`
                # return with `cast` AT THE BOUNDARY — never an inline `# type: ignore[no-any-return]`
                # (conventions block E; the no-silenced-types gate forbids it).
                return cast(bytes, await response["Body"].read())
        except ClientError as exc:
            raise _map_client_error(exc, key=key) from exc
```

### Template — async, HTTP-gateway form

```python
import httpx

from myapp.domain.exceptions import NotFoundError, UpstreamError, ValidationError
from myapp.domain.bars import BarToken  # the protocol (ICanFetchBarToken) is NOT imported — Rule 2

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

### Template — sync, pure-CPU form

For verifiers / canonicalizers / renderers with no IO. No `try/except` for IO; only translate the SDK's parse/verify errors.

```python
import jwt

from myapp.domain.auth import BarToken  # the protocol (ICanVerifyBarToken) is NOT imported — Rule 2
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

### Rules

#### Form

1. **One class per module.** Filename names the tech (`s3_foo_storage.py`, `http_bar_gateway.py`, `pyjwt_bar_token_verifier.py`); class follows. The class name carries the concrete tech (`S3FooStorage`, not `FooStorage`).
2. **No explicit `(ICanX)` inheritance.** Structural subtyping at the DI site is the contract.
3. **Method signatures match the protocol exactly**, including keyword-only markers and async/sync mode.
4. **Place the module in `infrastructure/<adapter>/`** — its own external-tech directory (`s3/`, `jwt/`, `openai/`, …). Infra groups by external tech, never by domain concern; relational artifacts live under `infrastructure/postgres/`, each capability adapter under its own tech dir.

#### Constructor

5. **Inject the SDK client and the settings class.** Both come from `containers.py`. Never construct an SDK client inline (`boto3.client(...)`, `httpx.AsyncClient(...)`) inside a method.
6. **Stash only what the methods need.** Pull `bucket`, `endpoint_url`, secrets, etc. out of settings in `__init__`; do not stash the whole settings object unless multiple methods read multiple fields.
7. **Secrets:** `SecretStr` fields are read once in `__init__` via `.get_secret_value()`; never log or expose them in `context`.

#### Exception translation

8. **Catch the SDK's exception family at the boundary and raise a domain exception.** This is the capability-adapter analogue of `infra-sqlalchemy-repository`'s `IntegrityError` rule. Use `raise <DomainException>(...) from exc` so the original cause is preserved for logging.
9. **The SDK's exception type never escapes the adapter.** No `ClientError`, `HTTPStatusError`, `jwt.InvalidTokenError`, etc., crosses into application or entrypoints. The application layer catches only `DomainError`.
10. **Mandatory fallback.** When no specific case matches, raise a sensible default: `UpstreamError` for third-party / network failures, `AuthError` for auth-verifier failures, `ValidationError` only when the input was demonstrably malformed. Never return the raw exception; never `pass`.
11. **Populate `context` with the stable identifying inputs** (`key`, `subject`, `tenant_id`) plus the upstream code/status (`code`, `status`). Tests assert on these, and the central error handler logs them.
12. **Pick the most specific domain exception.** `NotFoundError` for "object/subject does not exist", `ValidationError` for "the upstream rejected the inputs as malformed", `AuthError` for token / credential rejection, `UpstreamError` for everything else (network, 5xx, unknown codes).

#### No business logic, no logging

13. **Adapters are thin.** No retries (use the SDK's built-in retry policy via settings), no caching, no batching, no domain reasoning. If the spec asks for retry or backoff, it goes in the SDK config or a dedicated wrapper — not in this class body.
14. **No logging in the adapter.** The central error handler logs the resulting `DomainError`. The calling handler logs success. Adapters never log, never `print`. See `general-logging`.
15. **No instance state across calls** beyond constructor-injected handles. An adapter is safe to share as a `Singleton`.

#### Compensating-transaction contract

16. **Mutating capabilities expose both the forward operation and the undo.** A storage adapter has `upload` *and* `delete`; a publisher that supports retraction has `publish` *and* `retract`. The catch-and-undo logic lives in the application handler (see `pattern-compensating-tx`), not in the adapter. The adapter's job is to make the undo callable.

### Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.bars import BarToken` — the entities/VOs the signatures name). **Never import the capability protocol the adapter satisfies** (`ICanStoreFoos`, `ICanFetchBarToken`, …) — structural subtyping needs no import (Rule 2); importing it is a dead F401. Sibling modules within the same `infrastructure/<adapter>/` package use relative imports (`from .settings import BlobsSettings`).
- No `from __future__ import annotations`. Full annotations on every method.
- `X | None` over `Optional`. `Mapping[K, V]` / `Sequence[T]` (from `collections.abc`) for read-only views.
- **A raw SDK value typed `Any` is narrowed with `cast`, never silenced.** An SDK return that mypy sees as `Any` (`response["Body"].read()`, an untyped client method) flowing into a typed protocol return is a `[no-any-return]`/`[return-value]` error — fix it with `cast(<protocol-return-type>, …)` at the boundary, the same way `restapi/dependencies.py` casts the DI-resolved verifier. An inline `# type: ignore[...]` on the adapter body is never sanctioned (`conventions` block E; the `/verify` no-silenced-types gate greps for it).
- SDK types stay inside the adapter; method signatures use domain types or primitives only.
- No `Any` except at the immediate raw-SDK-payload boundary (e.g. `payload: dict[str, Any] = response.json()` — convert to the domain type on the next line).

### Package wiring

The `infrastructure/<adapter>/__init__.py` re-exports the new module via `from .s3_foo_storage import *`. Follow `general-python-package`.

### Hard stops

- Spec asks the adapter to talk to Postgres / SQLAlchemy / Alembic → stop, use `infra-sqlalchemy-repository` and `infra-sqlalchemy-table`.
- Spec asks the adapter to inherit from `ICanX` explicitly → stop, structural subtyping is the contract.
- Spec asks the adapter to log → stop, adapters do not log; the central error handler owns failure logs.
- Spec asks the adapter to retry, cache, or batch internally → stop, configure that on the SDK client (in `containers.py`) or extract a separate wrapper class.
- Spec asks the adapter to construct its own SDK client (`boto3.client(...)`, `httpx.AsyncClient()`) → stop, both the client and the settings are injected from DI.
- Spec asks the adapter to raise an SDK exception type or `Exception` → stop, every SDK exception must be translated into a `DomainError` subclass at the boundary.
- Spec / `behaviour` doesn't say which SDK errors a fallible method raises → derive the SDK→domain mapping from the SDK's documented exception family plus the node's `notes`, and apply the mandatory fallback (Rule 10: `UpstreamError` for network/third-party, `AuthError` for verifiers). The specific cases are judgment; only the broad-catch-and-translate fallback is non-negotiable — never leave a method that can `raise` an untranslated SDK exception.


<!-- merged from infra-settings -->

## Infrastructure Settings

Produces one settings class per external integration. The class is the **only** place this codebase reads environment variables — adapters always receive a settings object via DI.

### When to use vs. neighbours

- Adding/extending env-backed configuration for an integration → this skill.
- Wiring the settings into `containers.py` as a Singleton → `infra-di-provider`.
- A frozen-dataclass domain-shaped view of these settings (a tunable knob the domain consults) → the tunable-VO variant in `domain-value-object` (it consumes fields from the settings class).

### File location and naming

- Path: `src/<root>/infrastructure/<subpackage>/settings.py` — always named `settings.py`.
- Class: `<Concept>Settings`. Not `Config`, not `Options`.
- Env prefix: `MYAPP_<DOMAIN>_` (uppercase, short noun 3–8 chars, terminal underscore). Never reuse a prefix across two classes. **The stem (`MYAPP_`) is the application / product, NEVER a bounded context / epic name.** Env vars are an app-level deployment concern: a `DbSettings` declared in the `accounts` epic still serves the whole process, so its prefix is `MM_DB_` (the MeetingMind app), not `ACCOUNTS_DB_`. This matters doubly for shared-substrate settings — under app-mode a `DbSettings` backing the shared `datastore` collapses to one across contexts (`conventions` block F), so a context-named prefix on it is incoherent the moment a second context joins (operators would set `ACCOUNTS_DB_HOST` for a DB both contexts share). When you look at a single epic in isolation, the salient name is the epic — resist it; stem on the app.

### Template — relational database (one integration kind among many)

The class below is a **relational-engine** example. Its connection-pool fields (`port = 5432`, `pool_size`, `max_overflow`, `pool_pre_ping`, `echo`) and the `dsn` are **relational-only** — they mean nothing for an API key, a blob store, a vector store, or an observability backend. For those, use the generic template below; never copy pool/port/echo/dsn into a non-engine settings class.

```python
from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["DbSettings"]

class DbSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYAPP_DB_",
        env_file=".env",
        extra="ignore",
    )

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    name: str

    pool_size: int = 10
    max_overflow: int = 5
    pool_pre_ping: bool = True
    echo: bool = False

    @computed_field
    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
```

### Template — generic integration (API key / blob store / vector store / observability)

Most integrations need a credential plus an endpoint or model name and maybe one or two knobs — no pool, no port, no DSN. This is the shape for everything that is not a relational engine:

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["FooApiSettings"]

class FooApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYAPP_FOO_",
        env_file=".env",
        extra="ignore",
    )

    api_key: SecretStr
    base_url: str = "https://api.foo.example"
    timeout_seconds: int = 30
```

### Rules

#### Required `model_config`

All three keys are mandatory:

- `env_prefix="MYAPP_<DOMAIN>_"`
- `env_file=".env"` — local dev reads `.env`; production injects via real environment (the file simply isn't there).
- `extra="ignore"` — unknown env vars in the namespace are tolerated. Without this, a stray var crashes startup.

#### Field shape

1. **Required fields have no default.** Missing values fail loudly at container instantiation, before any request is served.
2. **Optional fields use inline defaults.** Defaults must be safe values for production-like setups.
3. **Booleans use Python types**, not strings. Pydantic parses env-string forms (`"true"`, `"1"`, `"yes"`) correctly.
4. **Numerics use real types** — `port: int`, never `str`.
5. **Optional is `T | None = None`**, never `T = ""`.

**Engine-pool fields are relational-only.** `port: int = 5432`, `pool_size`, `max_overflow`, `pool_pre_ping`, `echo`, and a `dsn` computed field belong to a relational-database settings class (the first template). A non-engine integration — API key, blob store, vector store, observability — omits them entirely; carrying them is dead config copied from the source app's database.

#### Secrets

6. **`SecretStr` for any value that must not appear in logs, repr, or tracebacks** — passwords, API keys, signing secrets, JWT keys.
7. **Never default a secret.** If a secret env var is missing, the process must crash at startup.
8. **`.get_secret_value()` is called only at point of use** (inside a `@computed_field` like `dsn`, or when constructing an SDK client). Never log, format, or print a `SecretStr`.

#### Composition

9. **Derived values live in `@computed_field @property`.** DSNs, composite URLs, normalized strings. Adapters consume the computed value, not the parts.
10. **Two integrations don't share fields by importing one's settings class from another.** Each settings class is self-contained; copy the field if both genuinely need it.

#### Validators

11. **`@field_validator` for two purposes only:**
    - **Normalization** — accept env-friendly form, store canonical form (e.g. unescaping `\\n` in multi-line keys).
    - **Rejection** — refuse values that would cause silent misbehavior (e.g. allowlist JWT algorithms).
12. **Validation messages should be clear** — they surface at container startup where stack traces get read.

#### Scope and ownership

13. **One settings class per infrastructure subpackage.** Bundling unrelated config under one prefix is forbidden.
14. **Settings live next to the adapter they configure.** No top-level central settings module.
15. **Re-export from the subpackage `__init__.py`** — the settings class is part of the subpackage's public surface.

#### Reading env

16. **Settings are instantiated only in `containers.py`.** Never call `DbSettings()` from a handler, an entrypoint, a test fixture, or another settings class.
17. **Adapters depend on the settings type**, not on `os.environ` or `os.getenv`. No `os.getenv` outside settings classes themselves.

#### Testing

18. **Tests construct settings explicitly with values**, not by mutating env: `DbSettings(host="localhost", user="t", password=SecretStr("t"), name="t")`.
19. **Don't `monkeypatch.setenv`** to drive settings unless testing the env-parsing layer itself.

### Inlined typing / import rules

- `from pydantic import SecretStr, computed_field` — add `field_validator` to this line **only when the class defines one** (rule 11); an unused import is an F401.
- `from pydantic_settings import BaseSettings, SettingsConfigDict`.
- Full annotations on every field and validator.
- No `from __future__ import annotations`.

### Package wiring

Follow `general-python-package` to re-export the settings class from the subpackage `__init__.py`. The DI Singleton wiring is in `infra-di-provider`.

### Hard stops

- Spec asks for env reads outside a settings class → stop, route through a settings field.
- Spec wants two unrelated integrations under the same prefix → stop, split into two classes.
- Spec asks the adapter to take individual fields instead of the settings object → discouraged; pass the whole settings object. Use individual fields only via `.provided.<field>` in the DI wiring when a tunable VO needs a single value.


<!-- merged from infra-di-provider -->

## DI Provider Wiring

`src/<root>/containers.py` is the composition root. Every concrete class is bound to the protocol it satisfies here, and **only** here. Domain and application code never instantiates concrete types — they receive them through DI.

This skill modifies `containers.py`. It does **not** produce settings classes (`infra-settings`), repositories (`infra-sqlalchemy-repository`), domain services or tunable value objects (`domain-service`, `domain-value-object`), or handlers (`application-command` / `application-query`) — those classes must already exist.

### When to use vs. neighbours

- New handler, repository, domain service, tunable value object, settings class, or external adapter → this skill (for the wiring).
- The class itself → its layer-specific skill.
- The lifespan teardown of any long-lived connection (engine / client pool, when the graph wires one) → handled in `restapi/main.py` (`restapi-app-bootstrap`, alongside `restapi-endpoint`); lifespan resource cleanup happens there, not in the container.

### File touched

Only `src/<root>/containers.py`.

### Skeleton (for reference; do not rewrite the whole file)

```python
from dependency_injector import containers, providers

# ...imports for the classes being wired...

__all__ = ["Container"]

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["myapp.restapi"])

    # 1. Settings (Singleton)
    db_settings: providers.Provider[DbSettings] = providers.Singleton(DbSettings)
    storage_settings: providers.Provider[StorageSettings] = providers.Singleton(StorageSettings)

    # 2. Long-lived infrastructure clients (Singleton).
    #    The engine + session_factory pair exists ONLY when a relational
    #    (uses_bootstrap) store backs a repository. A client-style store
    #    (qdrant / redis / …) has no engine — it wires a connection-factory
    #    Singleton instead, e.g.:
    #        vectors_client = providers.Singleton(create_vectors_client, settings=qdrant_settings)
    #    Wire the long-lived clients the graph's datastores actually need, not a fixed Postgres pair.
    engine: providers.Provider[AsyncEngine] = providers.Singleton(create_engine, settings=db_settings)
    session_factory: providers.Provider[async_sessionmaker[AsyncSession]] = providers.Singleton(
        create_session_factory, engine=engine
    )

    # 3. Cross-cutting domain helpers (Singleton when stateless)
    url_canonicalizer: providers.Provider[UrlCanonicalizer] = providers.Singleton(UrlCanonicalizer)

    # 4. Repositories (Factory)
    foo_repository: providers.Provider[IFooRepository] = providers.Factory(
        FooRepository, session_factory=session_factory
    )

    # 5. Tunable value objects (Singleton) + domain services (Factory)
    foo_export_tunable: providers.Provider[FooExportTunable] = providers.Singleton(
        FooExportTunable, max_rows=export_settings.provided.max_rows
    )
    foo_uniqueness_service: providers.Provider[FooUniquenessService] = providers.Factory(
        FooUniquenessService, repo=foo_repository, canonicalizer=url_canonicalizer
    )

    # 6. Handlers (Factory) — grouped by subdomain
    create_foo_handler: providers.Provider[CreateFooHandler] = providers.Factory(
        CreateFooHandler, repo=foo_repository, service=foo_uniqueness_service
    )
    list_foos_handler: providers.Provider[ListFoosHandler] = providers.Factory(
        ListFoosHandler, repo=foo_repository
    )
```

### `Singleton` vs `Factory` decision rule

| Provider | Use for | Examples |
|----------|---------|----------|
| **`Singleton`** | Stateless or expensive-to-construct objects whose lifetime spans the process. | Settings (`*Settings`), `AsyncEngine`, `async_sessionmaker`, JWT verifier, URL canonicalizer, **tunable value objects** (frozen dataclass of tunables sourced from settings). |
| **`Factory`** | Per-resolution instances, constructed quickly, intended to be fresh each request. | All `*Handler`, all `*Repository`, **domain services** that compose other providers, stateful infrastructure adapters bound to per-request state. |

**Default to `Factory` for application/domain artifacts. Reserve `Singleton` for objects that own a connection pool, parse env once, or are pure-data configuration.**

Pitfall: marking a repository `Singleton` looks fine because it's stateless, but it locks the `session_factory` reference at container build time and prevents per-test overrides. **Keep repositories `Factory`.**

### Declaration order (load-bearing)

`DeclarativeContainer` evaluates providers top-to-bottom; a provider can only reference earlier providers in the same class body.

1. **Settings first.** Every other provider may depend on settings.
2. **Long-lived infra (engine, session_factory, verifiers).**
3. **Cross-cutting helpers (canonicalizers, storage adapters) needed by multiple subdomains.**
4. **Per-subdomain block:** repository → policies that use it → handlers that use them.
5. **Cross-subdomain dependencies come first.** If subdomain A's repository is consumed by subdomain B's handlers, declare it before subdomain B's block.

When adding a new provider, **find the right section in `containers.py` and insert it after the latest declaration it depends on.** If you'd have to forward-reference, move the dependency upward.

### Naming and access

- The provider attribute is the snake_case form of the **class** it builds: `FooRepository` → `foo_repository`. The protocol name (`IFooRepository`) informs the type annotation, not the attribute name.
- Type-annotate every provider with `providers.Provider[<Protocol>]` when a protocol exists, otherwise the concrete class.
- Routes call the provider as a method: `request.app.state.container.create_foo_handler()`. The router skill depends on this naming being mechanical — do not deviate.

### Settings lifecycle

- Each `*Settings` is a `Singleton`, instantiated with no args (pydantic reads env on `__init__`).
- Pass settings into other providers via the keyword the consumer expects: `providers.Singleton(create_engine, settings=db_settings)`.
- For tunable value objects that need a single field, use `.provided.<field>`: `providers.Singleton(FooExportTunable, max_rows=export_settings.provided.max_rows)`.

### Adding a UoW factory

When the handler uses a Unit of Work (`pattern-unit-of-work`):

```python
uow_factory: providers.Provider[IUnitOfWork] = providers.Factory(
    SqlAlchemyUnitOfWork, session_factory=session_factory
)
create_foo_handler: providers.Provider[CreateFooHandler] = providers.Factory(
    CreateFooHandler, uow_factory=uow_factory.provider, ...
)
```

`.provider` exposes the zero-arg callable matching `Callable[[], IUnitOfWork]`.

### Package wiring

This skill edits `containers.py` directly and does **not** touch any subpackage `__init__.py` — `containers.py` is a top-level module at the project root, not a package member. The classes the container imports (handlers, repositories, services, settings) are re-exported by their own subpackage `__init__.py` (managed by `general-python-package` in the producing skill). No additional package wiring step here.

**Import each class from the package that DIRECTLY re-exports it — one `from .module import *` hop — never a grandparent** (`general-imports-conventions`). This bites the nested infra layout: a repository class lives in `infrastructure/<store>/repositories/<x>.py`, so import it from the **`repositories` subpackage** — `from myapp.infrastructure.postgres.repositories import MeetingRepository`, `from myapp.infrastructure.qdrant.repositories import MeetingSearchIndex` — **not** from the `<store>` tech package (`from myapp.infrastructure.postgres import MeetingRepository`). The tech-package form resolves at runtime but mypy reports `[attr-defined]` ("Module ... has no attribute MeetingRepository"), because the intermediate `repositories/__init__.py` has a computed `__all__` mypy can't evaluate across the `from .repositories import *` hop. Classes sitting directly under the tech package (the `engine` / `settings` modules, a capability adapter) are one hop away, so importing them from the tech package is correct.

### What never goes in the container

- **No business logic.** The container only wires.
- **No conditionals based on env.** Different environments produce different settings *values*; the wiring stays the same. Hide feature flags behind a settings field inside the implementation, not behind `providers.Selector`.
- **No imports from `restapi/` or other entrypoints.** The container is below the entrypoint layer.
- **No mutable module-level state outside the `Container` class.**
- **No instantiation of concrete domain types** (entities, value objects). The container builds services, not data.
- **No `providers.Resource`** for things that already have a clear lifespan (a long-lived client/engine is disposed in the FastAPI `lifespan`, when one exists).

### Hard stops

- Spec asks to add a provider whose dependency is not yet declared in the container → stop, that dependency's skill must run first.
- Spec asks to wire a repository as `Singleton` → stop, repositories are `Factory`.
- Spec asks for conditional wiring per environment → stop, that's a settings-value problem, not a wiring problem.
- Spec asks to import `restapi/` symbols into `containers.py` → stop, wrong dependency direction.
