---
name: infra-di-provider
description: Apply when a new handler, repository, domain service, tunable value object, settings class, or external adapter must be wired into `containers.py`. Modifies the single `Container(DeclarativeContainer)` to add one or more providers in the correct declaration order, picking `Singleton` (settings, engines, verifiers, tunable value objects) vs `Factory` (handlers, repositories, domain services, stateful adapters) per the decision rule. Does not produce any of the classes it wires — those are owned by their respective skills.
---

# DI Provider Wiring

`src/<root>/containers.py` is the composition root. Every concrete class is bound to the protocol it satisfies here, and **only** here. Domain and application code never instantiates concrete types — they receive them through DI.

This skill modifies `containers.py`. It does **not** produce settings classes (`infra-settings`), repositories (`infra-sqlalchemy-repository`), domain services or tunable value objects (`domain-service`, `domain-value-object`), or handlers (`application-command` / `application-query`) — those classes must already exist.

## When to use vs. neighbours

- New handler, repository, domain service, tunable value object, settings class, or external adapter → this skill (for the wiring).
- The class itself → its layer-specific skill.
- The lifespan teardown of a connection pool in `restapi/main.py` → `restapi-router-endpoint` covers the entrypoint shape; lifespan resource cleanup happens there, not in the container.

## File touched

Only `src/<root>/containers.py`.

## Skeleton (for reference; do not rewrite the whole file)

```python
from dependency_injector import containers, providers

# ...imports for the classes being wired...

__all__ = ["Container"]

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["myapp.restapi"])

    # 1. Settings (Singleton)
    db_settings: providers.Provider[DbSettings] = providers.Singleton(DbSettings)
    storage_settings: providers.Provider[StorageSettings] = providers.Singleton(StorageSettings)

    # 2. Long-lived infrastructure clients (Singleton)
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

## `Singleton` vs `Factory` decision rule

| Provider | Use for | Examples |
|----------|---------|----------|
| **`Singleton`** | Stateless or expensive-to-construct objects whose lifetime spans the process. | Settings (`*Settings`), `AsyncEngine`, `async_sessionmaker`, JWT verifier, URL canonicalizer, **tunable value objects** (frozen dataclass of tunables sourced from settings). |
| **`Factory`** | Per-resolution instances, constructed quickly, intended to be fresh each request. | All `*Handler`, all `*Repository`, **domain services** that compose other providers, stateful infrastructure adapters bound to per-request state. |

**Default to `Factory` for application/domain artifacts. Reserve `Singleton` for objects that own a connection pool, parse env once, or are pure-data configuration.**

Pitfall: marking a repository `Singleton` looks fine because it's stateless, but it locks the `session_factory` reference at container build time and prevents per-test overrides. **Keep repositories `Factory`.**

## Declaration order (load-bearing)

`DeclarativeContainer` evaluates providers top-to-bottom; a provider can only reference earlier providers in the same class body.

1. **Settings first.** Every other provider may depend on settings.
2. **Long-lived infra (engine, session_factory, verifiers).**
3. **Cross-cutting helpers (canonicalizers, storage adapters) needed by multiple subdomains.**
4. **Per-subdomain block:** repository → policies that use it → handlers that use them.
5. **Cross-subdomain dependencies come first.** If subdomain A's repository is consumed by subdomain B's handlers, declare it before subdomain B's block.

When adding a new provider, **find the right section in `containers.py` and insert it after the latest declaration it depends on.** If you'd have to forward-reference, move the dependency upward.

## Naming and access

- The provider attribute is the snake_case form of the **class** it builds: `FooRepository` → `foo_repository`. The protocol name (`IFooRepository`) informs the type annotation, not the attribute name.
- Type-annotate every provider with `providers.Provider[<Protocol>]` when a protocol exists, otherwise the concrete class.
- Routes call the provider as a method: `request.app.state.container.create_foo_handler()`. The router skill depends on this naming being mechanical — do not deviate.

## Settings lifecycle

- Each `*Settings` is a `Singleton`, instantiated with no args (pydantic reads env on `__init__`).
- Pass settings into other providers via the keyword the consumer expects: `providers.Singleton(create_engine, settings=db_settings)`.
- For tunable value objects that need a single field, use `.provided.<field>`: `providers.Singleton(FooExportTunable, max_rows=export_settings.provided.max_rows)`.

## Adding a UoW factory

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

## Package wiring

This skill edits `containers.py` directly and does **not** touch any subpackage `__init__.py` — `containers.py` is a top-level module at the project root, not a package member. The classes the container imports (handlers, repositories, services, settings) are re-exported by their own subpackage `__init__.py` (managed by `general-python-package` in the producing skill). No additional package wiring step here.

## What never goes in the container

- **No business logic.** The container only wires.
- **No conditionals based on env.** Different environments produce different settings *values*; the wiring stays the same. Hide feature flags behind a settings field inside the implementation, not behind `providers.Selector`.
- **No imports from `restapi/` or other entrypoints.** The container is below the entrypoint layer.
- **No mutable module-level state outside the `Container` class.**
- **No instantiation of concrete domain types** (entities, value objects). The container builds services, not data.
- **No `providers.Resource`** for things that already have a clear lifespan (the engine is disposed in the FastAPI `lifespan`).

## Hard stops

- Spec asks to add a provider whose dependency is not yet declared in the container → stop, that dependency's skill must run first.
- Spec asks to wire a repository as `Singleton` → stop, repositories are `Factory`.
- Spec asks for conditional wiring per environment → stop, that's a settings-value problem, not a wiring problem.
- Spec asks to import `restapi/` symbols into `containers.py` → stop, wrong dependency direction.
