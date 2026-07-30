---
name: infra-wiring
description: How configuration enters the process and how classes are bound together — a `pydantic-settings` class per integration (env prefix stemmed on the product, `SecretStr` for secrets, `@computed_field` for derived values), and the single `Container` in `containers.py` with its `Singleton`-versus-`Factory` rule and load-bearing declaration order.
when_to_use: Adding or changing configuration for an external integration, or wiring a handler, repository, service, tunable value object, settings class or adapter into the DI container.
paths: src/**
---

# Infrastructure Wiring

Two halves of one job: getting values in from the environment, and handing objects to whoever needs
them.

- A **settings class** is the only place this codebase reads environment variables. Adapters always
  receive a settings object; nothing calls `os.getenv`.
- **`containers.py`** is the composition root. Every concrete class is bound to the protocol it satisfies
  here and **only** here. Domain and application code never instantiates a concrete type.

The two meet at one rule: a settings class is instantiated **only** by the container.

## When to use vs. neighbours

- Adding or extending env-backed configuration for an integration → the **settings** section.
- Wiring a new class into the container → the **container** section.
- The class being wired — a handler, repository, service, adapter → its own skill. It must already exist.
- A frozen domain-shaped view of settings values the domain consults → the tunable variant in
  `domain-model`; it takes its fields from a settings class via `.provided.<field>`.
- Disposing a long-lived connection at shutdown → `restapi-app`. Lifespan teardown happens there, never
  in the container.

## Settings

### File location and naming

- Path: `src/<root>/infrastructure/<subpackage>/settings.py` — always named `settings.py`.
- Class: `<Concept>Settings`. Not `Config`, not `Options`.
- Env prefix: `MYAPP_<DOMAIN>_` — uppercase, short noun of 3–8 characters, terminal underscore. Never
  reuse a prefix across two classes.

**The stem (`MYAPP_`) is the application or product, NEVER a bounded-context name.** Env vars are an
app-level deployment concern: a `DbSettings` introduced while working on the `accounts` context still
serves the whole process, so its prefix is `MM_DB_` (the MeetingMind app), not `ACCOUNTS_DB_`. This
matters doubly for shared settings — a `DbSettings` backing a datastore shared across contexts collapses
to one (`conventions` block F), so a context-named prefix is incoherent the moment a second context
joins: operators would be setting `ACCOUNTS_DB_HOST` for a database both contexts share. Working inside
one context in isolation, the salient name is that context — resist it, and stem on the app.

### Template — relational database

A **relational-engine** example. Its connection-pool fields (`port = 5432`, `pool_size`,
`max_overflow`, `pool_pre_ping`, `echo`) and the `dsn` are **relational-only** — they mean nothing for an
API key, a blob store, a vector store or an observability backend. Never copy them into a non-engine
settings class.

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

### Template — generic integration (API key, blob store, vector store, observability)

Most integrations need a credential plus an endpoint or model name and maybe a knob or two — no pool, no
port, no DSN. This is the shape for everything that is not a relational engine:

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

### Rules — settings

**All three `model_config` keys are mandatory:** `env_prefix="MYAPP_<DOMAIN>_"`; `env_file=".env"`, so
local dev reads the file while production injects real environment and the file simply is not there; and
`extra="ignore"`, without which a stray env var in the namespace crashes startup.

1. **A required field has no default.** A missing value fails loudly at container instantiation, before
   any request is served.
2. **An optional field has an inline default**, and the default must be safe for a production-like setup.
3. **Booleans are Python types**, not strings — Pydantic parses `"true"`, `"1"`, `"yes"` correctly.
4. **Numerics are real types**: `port: int`, never `str`.
5. **Optional is `T | None = None`**, never `T = ""`.
6. **Engine-pool fields are relational-only.** `port: int = 5432`, `pool_size`, `max_overflow`,
   `pool_pre_ping`, `echo` and a `dsn` computed field belong to the relational template. A non-engine
   integration omits them entirely; carrying them is dead config copied from a database class.
7. **`SecretStr` for any value that must not appear in a log, a repr or a traceback** — passwords, API
   keys, signing secrets, JWT keys.
8. **Never default a secret.** A missing secret env var must crash the process at startup.
9. **`.get_secret_value()` is called only at the point of use** — inside a `@computed_field` like `dsn`,
   or when constructing an SDK client. Never log, format or print a `SecretStr`.
10. **Derived values live in `@computed_field @property`** — DSNs, composite URLs, normalized strings.
    Adapters consume the computed value, not the parts.
11. **Two integrations do not share fields by importing one settings class from another.** Each is
    self-contained; copy the field if both genuinely need it.
12. **`@field_validator` for two purposes only:** normalization, accepting an env-friendly form and
    storing the canonical one (unescaping `\\n` in a multi-line key); and rejection, refusing a value
    that would cause silent misbehaviour (an allowlist of JWT algorithms). Validation messages should be
    clear — they surface at container startup, where stack traces get read.
13. **One settings class per infrastructure subpackage.** Bundling unrelated config under one prefix is
    forbidden.
14. **Settings live next to the adapter they configure.** There is no top-level central settings module.
15. **Settings are instantiated only in `containers.py`.** Never call `DbSettings()` from a handler, an
    entrypoint, a test fixture or another settings class.
16. **Adapters depend on the settings type**, never on `os.environ` or `os.getenv`. No `os.getenv`
    anywhere outside a settings class.
17. **Tests construct settings explicitly with values**, not by mutating env:
    `DbSettings(host="localhost", user="t", password=SecretStr("t"), name="t")`. Do not
    `monkeypatch.setenv` to drive settings unless the env-parsing layer itself is what is under test.

## The container

`src/<root>/containers.py` is the only file this half touches.

### Skeleton (for reference — do not rewrite the whole file)

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
    #    store backs a repository. A client-style store
    #    (qdrant / redis / …) has no engine — it wires a connection-factory
    #    Singleton instead, e.g.:
    #        vectors_client = providers.Singleton(create_vectors_client, settings=qdrant_settings)
    #    Wire the long-lived clients the app's datastores actually need, not a fixed Postgres pair.
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

### `Singleton` vs `Factory`

| Provider | Use for | Examples |
|---|---|---|
| **`Singleton`** | Stateless or expensive-to-construct objects whose lifetime spans the process. | Settings (`*Settings`), `AsyncEngine`, `async_sessionmaker`, a JWT verifier, a URL canonicalizer, **tunable value objects**. |
| **`Factory`** | Per-resolution instances, cheap to construct, meant to be fresh each request. | Every `*Handler`, every `*Repository`, **domain services** that compose other providers, a stateful adapter bound to per-request state. |

**Default to `Factory` for application and domain artifacts. Reserve `Singleton` for objects that own a
connection pool, parse env once, or are pure-data configuration.**

The pitfall: marking a repository `Singleton` looks fine because it is stateless, but it locks the
`session_factory` reference at container build time and prevents per-test overrides. **Repositories stay
`Factory`.**

### Declaration order (load-bearing)

`DeclarativeContainer` evaluates providers top to bottom, and a provider may only reference an earlier one
in the same class body.

1. **Settings first** — everything else may depend on them.
2. **Long-lived infrastructure** — engine, session factory, verifiers.
3. **Cross-cutting helpers** — canonicalizers, storage adapters needed by several subdomains.
4. **Per-subdomain block:** repository → services that use it → handlers that use them.
5. **Cross-subdomain dependencies come first.** If subdomain A's repository is consumed by subdomain B's
   handlers, declare it before B's block.

When adding a provider, find the right section and insert it after the latest declaration it depends on.
If you would have to forward-reference, move the dependency upward.

### Naming and access

- The provider attribute is the snake_case form of the **class** it builds: `FooRepository` →
  `foo_repository`. The protocol name informs the type annotation, not the attribute name.
- Annotate every provider `providers.Provider[<Protocol>]` when a protocol exists, otherwise with the
  concrete class.
- A route calls the provider as a method:
  `request.app.state.container.create_foo_handler()`. `restapi-endpoint` depends on this naming being
  mechanical — do not deviate.

### Settings lifecycle in the container

- Each `*Settings` is a `Singleton` instantiated with no arguments; Pydantic reads env in `__init__`.
- Pass settings into another provider by the keyword the consumer expects:
  `providers.Singleton(create_engine, settings=db_settings)`.
- For a tunable value object needing a single field, use `.provided.<field>`:
  `providers.Singleton(FooExportTunable, max_rows=export_settings.provided.max_rows)`.

### Adding a unit-of-work factory

When the handler uses a unit of work (`patterns`):

```python
uow_factory: providers.Provider[IUnitOfWork] = providers.Factory(
    SqlAlchemyUnitOfWork, session_factory=session_factory
)
create_foo_handler: providers.Provider[CreateFooHandler] = providers.Factory(
    CreateFooHandler, uow_factory=uow_factory.provider, ...
)
```

`.provider` exposes the zero-argument callable matching `Callable[[], IUnitOfWork]`.

### What never goes in the container

- **No business logic.** The container only wires.
- **No conditionals on env.** Different environments produce different settings *values*; the wiring stays
  the same. Hide a feature flag behind a settings field inside the implementation, never behind
  `providers.Selector`.
- **No imports from `restapi/` or another entrypoint.** The container sits below the entrypoint layer.
- **No mutable module-level state outside the `Container` class.**
- **No instantiation of concrete domain types** — entities, value objects. The container builds services,
  not data.
- **No `providers.Resource`** for anything with a clear lifespan; a long-lived client or engine is
  disposed in the FastAPI `lifespan`.

## Inlined typing / import rules

Settings module:

- `from pydantic import SecretStr, computed_field` — add `field_validator` to that line **only when the
  class defines one** (rule 12); an unused import is an F401.
- `from pydantic_settings import BaseSettings, SettingsConfigDict`.
- Full annotations on every field and validator.

Container module:

- **Import each class from the package that DIRECTLY re-exports it — one `from .module import *` hop —
  never a grandparent** (`architecture`). This bites the nested infra layout: a repository class lives in
  `infrastructure/<store>/repositories/<x>.py`, so import it from the **`repositories` subpackage** —
  `from myapp.infrastructure.postgres.repositories import MeetingRepository` — **not** from the `<store>`
  tech package. The tech-package form resolves at runtime but mypy reports `[attr-defined]`, because the
  intermediate `repositories/__init__.py` has a computed `__all__` mypy cannot evaluate across the
  `from .repositories import *` hop. A class sitting directly under the tech package — the `engine` or
  `settings` module, a capability adapter — is one hop away, so importing it from the tech package is
  correct.

Both: no `from __future__ import annotations`.

## Package wiring

A settings class is re-exported from its subpackage `__init__.py` — it is part of that subpackage's
public surface (`architecture`).

`containers.py` needs no package wiring at all: it is a top-level module at the project root, not a
package member. The classes it imports are re-exported by their own subpackages, which their producing
skills handle.

## Hard stops

- Spec asks for an env read outside a settings class → stop, route it through a settings field.
- Spec wants two unrelated integrations under one prefix → stop, split into two classes.
- Spec asks an adapter to take individual fields instead of the settings object → discouraged; pass the
  whole object. Individual fields go through `.provided.<field>` in the wiring, and only when a tunable
  value object needs one.
- Spec asks to add a provider whose dependency is not yet declared → stop, that dependency's own skill
  runs first.
- Spec asks to wire a repository as `Singleton` → stop, repositories are `Factory`.
- Spec asks for conditional wiring per environment → stop, that is a settings-value problem, not a wiring
  problem.
- Spec asks to import a `restapi/` symbol into `containers.py` → stop, wrong dependency direction.
