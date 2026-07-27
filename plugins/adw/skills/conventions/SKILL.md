---
name: conventions
description: Reference skill (produces no target-app file) — the Python/FastAPI house style's mechanical derivation registry. Carries the derivation from bare identifiers (entity name, protocol name, command base-name, datastore kind) to concrete file paths and class names, the store profiles, the stack-substrate library list (names, no versions), the relational/Alembic bootstrap, and the multi-context resolution rules. Toolchain commands and the "green" definition live in `gate.py`, which this skill cites, never restates (C7). Other skills own artifact CONTENT; this owns the derivation between identifiers and the file tree.
when_to_use: Deciding a file path, a class name, a store profile, which substrate packages an app carries, how the Alembic bootstrap is laid, or how a cross-context reference resolves. Consulted alongside the artifact skill whenever a derived name or path is needed.
---

# Conventions (Python / FastAPI house style)

This is the **derivation layer**: the rules that turn the bare identifiers a change introduces (entity name, protocol name, command base-name, datastore `kind`) into concrete file paths, class names, dependencies, and store wiring. Everything mechanical is derived **here** so the other skills stay about artifact content.

Toolchain commands and the single definition of "green" live in **`gate.py`** (`tools/gate.py`) — this skill cites it, never restates it (C7: derivation has one home, and the toolchain's home is the gate).

All paths below are relative to the target package root `src/<package>/` (e.g. `src/hdk/domain/auth/user.py`). Worked names use the Helpdesk vocabulary (`auth`/`User`, `support`/`Ticket`, `openai`/`jwt`).

## A. Path & name derivation

**`snake_case`** — PascalCase → snake by inserting `_` before each interior capital, then lowercasing: `ITicketRepository` → `i_ticket_repository`, `OpenaiTextEmbedder` → `openai_text_embedder`. Acronym runs are **not** special-cased yet (revisit if an `OTP`-style identifier needs `o_t_p` avoided).

**`pluralize`** (table names) — `y` after a consonant → `ies`; trailing `s`/`x`/`z`/`ch`/`sh` → `+es`; else `+s`. So `Category` → `categories`, `Box` → `boxes`, `User` → `users`. Table name = `pluralize(snake(aggregate))`.

**Class names** carry only the identifier plus a derived suffix. Protocol identifiers already include their `I`-prefix / `Repository` suffix.

| Artifact | Identifier(s) | Derived class name(s) | Derived file path(s) |
|---|---|---|---|
| domain enum | `name: Role`, `subdomain: auth` | `Role` | `domain/auth/role.py` |
| domain value object | `name: Email`, `subdomain: auth` | `Email` | `domain/auth/email.py` |
| domain entity | `name: User`, `subdomain: auth` | `User` | `domain/auth/user.py` |
| domain service | `name: OtpVerifier`, `subdomain: auth` | `OtpVerifier` | `domain/auth/otp_verifier.py` |
| domain filter | `name: TicketFilter`, `subdomain: support` | `TicketFilter` + sort enum | `domain/support/ticket_filter.py` |
| repository protocol | `name: IUserRepository`, `subdomain: auth` | `IUserRepository` | `domain/auth/i_user_repository.py` |
| capability protocol | `name: ICanSendEmail`, `subdomain: auth` | `ICanSendEmail` | `domain/auth/i_can_send_email.py` |
| domain exception | `name: NotFoundError` | `NotFoundError` | appended to `domain/exceptions.py` (single catalog) |
| application command | `name: CreateTicket` (subdomain derived, see below) | `CreateTicketCommand` + `CreateTicketHandler` | `application/support/create_ticket_command.py` + `_handler.py` |
| application query | `name: ListTickets` | `ListTicketsQuery` + `ListTicketsHandler` + `ListTicketsResult` | `application/support/list_tickets_query.py` + `_handler.py` + `_result.py` |
| datastore | `name: vectors`, `kind: qdrant` | — (a configured resource, no class) | `infrastructure/qdrant/connection.py` (`create_vectors_client`) |
| infra settings | `name: OpenaiSettings` | `OpenaiSettings` | `infrastructure/openai/settings.py` — subpackage = the consuming tech; the module is always `settings.py` (one settings class per subpackage) |
| infra repository | `implements: IUserRepository`, `backs: User`, `store: main` | `UserRepository` | `infrastructure/<store-kind>/repositories/<repo-stem>.py` (+ a write-once Table scaffold at `infrastructure/<store-kind>/tables/users.py` for a relational store) |
| infra capability | `implements: ICanEmbedText`, `adapter: openai`, `role: TextEmbedder` | `OpenaiTextEmbedder` | `infrastructure/openai/openai_text_embedder.py` |
| restapi schema | `name: LoginRequest`, `resource: auth` | `LoginRequest` | grouped into `restapi/schemas/auth.py` |
| restapi endpoint | `method`, `path`, `resource: auth` | endpoint function (name from method+path) | grouped into `restapi/routers/auth.py` |
| restapi middleware | `name: RequestId`, `config` | `RequestIdMiddleware` | `restapi/middleware/request_id.py` |

**Application subdomain is derived, not declared.** Commands and queries carry no `subdomain`. The subdomain is that of the first handler dependency that names a repository protocol (a repository protocol carries its own `subdomain`); with no repository dependency, fall back to the first domain entity's subdomain. So `CreateTicket` depending on `ITicketRepository` (`subdomain: support`) lands in `application/support/`.

**A value object in a dependency list is a tunable VO, and its DI is derived.** A value object is normally built inline at its use site, but when its name appears in a handler's or a service's `dependencies`, it is the **tunable variant** (`domain-model`, the config-knob view of an env threshold). It is then DI-wired as a `providers.Singleton` constructed field-by-field from a settings class — not from an inline literal. The stem pairing `<Stem>Tunable` ← `<Stem>Settings` (e.g. `LockoutTunable` ← `LockoutSettings`) is an **advisory default, not load-bearing**: the real binding is the DI wiring (`infra-integration`), which sources the tunable from whichever settings node's fields match — a stem mismatch is fine (`LockoutTunable(max_attempts=auth_settings.provided.max_attempts, …)` from a single `AuthSettings` is correct). The field-by-field construction (`<tunable>(field=<settings>.provided.field, …)`) is the invariant; the stem is just the default guess. This is how an env-tunable domain threshold (lockout numbers, quotas, retention) reaches a domain service without the domain importing `pydantic-settings`. `infra-integration` owns the wiring.

**Infrastructure groups by external TECH, never by a domain subdomain and never under a catch-all `db/`** (CLAUDE.md "grouped by external tech"). The tech token is:
- a repository's **store kind** — the `kind` of the `datastore` its `store` names; absent `store` ⇒ the implicit single `postgres` store. Relational repos, their write-once table scaffold, and the shared SQLAlchemy engine/`session_factory`/`metadata.py` bootstrap all sit under `infrastructure/postgres/` (`repositories/`, `tables/`).
- a non-bootstrap datastore's **`kind`** — `infrastructure/qdrant/`, `infrastructure/redis/`, holding `connection.py` (the `create_<name>_client` factory) and its settings.
- a capability adapter's **`adapter`** token — `infrastructure/openai/`, `infrastructure/jwt/`.
- a settings node's **consuming tech** — the `adapter` of the capability that names it, or the `kind` of the datastore that names it; an orphan settings falls back to its own snake name.

**Capability adapter class** = `<AdapterPascal><Suffix>`, where `Suffix` is the capability's `role` agent-noun when present (`adapter: jwt`, `role: TokenManager` → `JwtTokenManager`) and otherwise the protocol name minus its `ICan` prefix (`adapter: jwt`, `implements: ICanManageTokens`, no role → `JwtManageTokens`). The `role` is stated explicitly precisely because the agent-noun is not mechanically derivable from the verb (the `log_event` precedent).

**Repository file stem — backs-derived for a relational store, protocol-derived for a client store.** The repository class is always `<Aggregate>Repository` (`backs: User` → `UserRepository`), but its **file stem** depends on the store profile (block C), because **polyglot** persistence lets two repositories back ONE aggregate:
- a **relational (bootstrap) store** repo → `<snake(backs)>_repository.py` (`Meeting` on `main` → `meeting_repository.py`).
- a **client-style store** repo → the **protocol-derived** stem: the `implements` name minus its leading `I`, snaked (`IMeetingSearchIndex` on `vectors` → `meeting_search_index.py`).

So a `Meeting` aggregate backed by both a Postgres `IMeetingRepository` and a Qdrant `IMeetingSearchIndex` lands two distinct files (`postgres/repositories/meeting_repository.py` + `qdrant/repositories/meeting_search_index.py`) — a backs-only stem would collide.

**Imports and package mechanics are not restated here** — see block E and `architecture`. Imports are graph edges in Python syntax (a referenced type resolves to its owning module): same-subdomain domain types use a relative `.module` import, cross-subdomain a relative `..subdomain`, cross-layer an absolute `<package>.domain.<subdomain>` import, stdlib its canonical import, builtins none. `architecture` owns the import rules and the `from .module import *` re-export contract that the collapsed import form depends on.

## C. Store profiles

A datastore's `kind` is a free token (not a closed enum — a fixed list is the same disease as a fixed type map). The profile maps a `kind` to the few things needed to wire a repository **without** knowing the backend's SQL/SDK internals (those live in the bodies the implementer fills):

| `kind` | resource param / attr | resource type | resource import | method contract | `uses_bootstrap` |
|---|---|---|---|---|---|
| `postgres` | `session_factory` / `sf` | `async_sessionmaker[AsyncSession]` | `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker` | `sql` | **yes** |
| `qdrant` | `client` / `client` | `AsyncQdrantClient` | `from qdrant_client import AsyncQdrantClient` | `collection` | no |
| `redis` | `client` / `client` | `Redis` | `from redis.asyncio import Redis` | `generic` | no |
| *(unknown)* | `client` / `client` | `object` | — | `generic` | no |

- `uses_bootstrap` **also selects the repository producer skill**: `yes` → `infra-persistence`'s relational (SQLAlchemy Core) form; `no` → its client-style store form. So adding a client-style backend is one row here — it routes to the existing vendor-agnostic form, no new skill.
- `uses_bootstrap: yes` → the repository reuses the shared SQLAlchemy engine + `session_factory` bootstrap under `infrastructure/postgres/` (postgres is the only profile with the flag today), and gets a write-once `Table` scaffold under `infrastructure/postgres/tables/`. `no` → a `create_<store>_client(settings)` connection factory in `infrastructure/<kind>/connection.py` that the DI container injects as a `Singleton` into every repository on that store, and there is **no** SQLAlchemy table (the store persists through its own client).
- The `method contract` (`sql` / `collection` / `generic`) only sets the **wording** of the repository scaffold's contract-comment.
- An **unknown** kind degrades to a generic untyped `object` client plus a loud contract comment — the fail-loud-not-crash invariant the table scaffold also follows. Adding a backend is **one row here**, never a tooling change.

**The connection factory is COMPLETE glue, not a body scaffold.** For a **known** profile kind the connection/engine factory carries zero judgment — it is a fixed function of the settings shape — so it is written in **full** (no `raise NotImplementedError`), exactly like `__init__` re-exports or `containers.py`. Leaving it as a `NotImplementedError` scaffold would crash the DI container at app construct while mypy/ruff/tests stay green (the A4 hazard, `PRINCIPLES.md` §A4). The canonical complete forms:

```python
# infrastructure/postgres/engine.py  (the bootstrap-store engine + session factory — complete)
def create_engine(settings: DbSettings) -> AsyncEngine:
    dsn = (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.name}"
    )
    return create_async_engine(dsn)

def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```
```python
# infrastructure/qdrant/connection.py  (a client-store connection factory — complete; redis is analogous)
def create_vectors_client(settings: QdrantSettings) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
    )
```
The factory name is `create_<datastore-name>_client` (the datastore's `name`, not its kind — `create_vectors_client` for a datastore named `vectors`); the resource type + import come from the profile table above. Only a **genuinely unknown** kind (the degraded `object` row) cannot be rendered complete — there alone a `NotImplementedError` connection factory plus a loud comment is the documented residual.

**Relational migrations bootstrap (Alembic) — complete config + write-once baseline.** Emitted **only when a `uses_bootstrap` store backs a repository** (the same trigger as the Postgres substrate / table scaffold). Alembic owns the revision chain (migrations are never *hand-generated as logic*), but the chain cannot start, and `alembic upgrade head` cannot run, without two things: the Alembic **config** (pure glue) and an **initial baseline revision** (write-once, like a body scaffold). Without these the integration suite dies at setup (`testing-integration`'s session-autouse `_migrated_db` runs `alembic upgrade head`; no `script_location` → `No 'script_location' key found`) — invisible to mypy/ruff/unit/construct, the A4 hazard, surfaced only by a real Docker run.

The config files sit at the tree root + `migrations/`:

```ini
# alembic.ini  (tree root)
[alembic]
script_location = migrations
prepend_sys_path = src
```
```python
# migrations/env.py  (async, wired to the project's shared MetaData — online mode only)
import asyncio
import os

from alembic import context

import myapp.infrastructure.postgres.tables  # noqa: F401  — registers every Table on the shared metadata
from myapp.infrastructure.postgres.engine import create_engine
from myapp.infrastructure.postgres.metadata import metadata
from myapp.infrastructure.postgres.settings import DbSettings

target_metadata = metadata


def _engine():
    # The gate's Docker tier hands the migration DSN in via DATABASE_URL / GATE_DATABASE_URL
    # (see `gate.py`, the docker.alembic tier) — honour it when set, else build from DbSettings.
    dsn = os.environ.get("GATE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        from sqlalchemy.ext.asyncio import create_async_engine
        return create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://", 1))
    return create_engine(DbSettings())


def _run(connection) -> None:  # MigrationContext drives this inside run_sync
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = _engine()
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(_run_online())
```
`migrations/script.py.mako` is Alembic's standard revision template (`${message}` / `${up_revision}` / `${down_revision}` / `upgrade()` / `downgrade()`); emit it verbatim so `alembic revision` can author later deltas.

The **baseline revision** is **write-once** (emit `migrations/versions/0001_initial.py` only when `migrations/versions/` carries no `*.py` yet — never clobber a chain that already has brownfield deltas):

```python
# migrations/versions/0001_initial.py
import myapp.infrastructure.postgres.tables  # noqa: F401  — registers every Table on the shared metadata
from alembic import op
from myapp.infrastructure.postgres.metadata import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
```

The baseline is a derived glue **snapshot** of the just-written tables (≈ `containers.py`), not a hand-authored logic delta — it is the desired-schema snapshot, materialized once so the chain can start. **Every subsequent migration is a real Alembic revision authored in the change cycle** (`uv run alembic revision --autogenerate -m "<change>"`, driven by the schema-drift trigger, block E) — the baseline is the only emitted one. `migrations/` lives at the tree root (outside `src`/`tests`), so it is exercised by `alembic upgrade head` in the integration suite / the gate's Docker tier, not by the `mypy`/`ruff` pass.

## D. Stack substrate (library NAMES, no versions)

`pyproject.toml` is the framework substrate ∪ the union of every infra node's `requires_packages`. It is derived from what the app actually uses, never "an agent recalling a package".

- **Framework substrate** (the FastAPI-hexagon stack, always present): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `dependency-injector`, `structlog`.
- **Relational bootstrap** (added only when a `uses_bootstrap` store backs a repository): `sqlalchemy[asyncio]`, `asyncpg`, `alembic`.
- **Multipart form handling** (added **only** when some endpoint declares a `Form(...)` / `UploadFile` route): `python-multipart`. FastAPI imports it at app-construct time for any form/multipart route (otherwise `create_app()` raises `RuntimeError: Form data requires "python-multipart"` — which mypy / ruff / unit tests do **not** catch, only constructing the app does), so its presence is derived from a multipart endpoint, exactly like the relational and auth bootstraps. An app with no multipart endpoint must not carry it.
- **Dev** (always present): `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `testcontainers`, `httpx`. These are not optional comfort: the gate runs the type-checker, the linter and the test runner (and, when the migration tier runs, `alembic`) **inside the project's own environment** — block E — so a project missing one of them cannot be gated at all.
- **Build system** (always present): the `[build-system]` table that makes the project installable — without it `src/<package>/` is reachable only by whoever puts it on `PYTHONPATH`, so the test run is green while `uv run uvicorn <package>.restapi.main:create_app` dies with `ModuleNotFoundError`. The backend is **`uv_build`**, which is what `uv init --package` writes:
  ```toml
  [build-system]
  requires = ["uv_build>=0.11.6,<0.12.0"]
  build-backend = "uv_build"
  ```
- **Auth test bootstrap** (added **only** when the app declares auth *and* its token scheme is asymmetric — an RSA/EC keypair, e.g. RS256, which is the scheme `testing-integration`'s authed client uses today): `cryptography` — that conftest mints RS256 tokens from a generated RSA keypair, so building/serializing the keypair needs `cryptography`. The trigger is graph-derived auth-presence (any authenticated endpoint / a token-verifier capability), but the package itself is needed only for the asymmetric path: an app that declares auth yet verifies symmetric (HS256) or opaque tokens generates no keypair and must **not** carry it — a `cryptography` dev dep that nothing imports is the stray-package bug. (RS256/RSA is the current auth-test scheme, not the only conceivable one.)
- **SDK packages are not listed here** — each rides on the infra node that needs it (`datastore` / `capability` `requires_packages`, e.g. `qdrant-client`, `openai`, `pyjwt`) and is unioned in.

**`[build-system]` and the package root come as a pair.** With the table present, the build backend expects the package to exist: an absent `src/<package>/__init__.py` makes `uv` hard-fail *every* command (`Expected a Python module at: src/<package>/__init__.py`), not just a build. So the package directory (with its `__init__.py`) exists from the project's very first commit — `uv init --package` creates both together, and block A's paths hang off that root.

**No versions in the substrate.** This list carries names only. `uv lock` / `uv sync` resolves the latest-compatible versions into `uv.lock`, which is the only home for a concrete pin — so nothing rots. A pinned `>=` on a substrate library would reintroduce the old disease (baked-in `fastapi>=0.115` under eternal manual bump). **The `uv_build>=x,<y` bound in `[build-system]` is the one sanctioned version in this list** — not a judgment call but a transcription: `uv init --package` emits that bound itself, and it cannot live in `uv.lock` because the build backend is resolved *before* a lock exists. Copy what uv wrote; never invent or "refresh" the bound (that would be exactly the recency guess B8 below bans). The other exception is B8's, and it lives one level out — on a graph node's `requires_packages`, never on a substrate name.

**Floors on `requires_packages` — the lone, disciplined exception (B8).** A graph node's `requires_packages` SDK *may* carry a `>=` floor, but only when it marks a **known breaking-version boundary** — an API the code relies on landed or changed there — and the floor sits at that boundary, expressed knowledge-stably (the major), with the reason in a comment. It is a *contract* fact ("needs v2, where the API changed"), never a recency guess: an agent must not write a version it recalls as "recent" (its knowledge is frozen at a cutoff), and a floor padded above the real break (`pyjwt>=2.8` when the break is `2.0`) is exactly that stale memory masquerading as a constraint. Worked examples: `pyjwt>=2` (PyJWT 2.0 made `encode` return `str`, not `bytes`); `redis>=4.2` (`redis.asyncio` merged in at 4.2 — before that the async client was the separate `aioredis`); `argon2-cffi` with **no** floor (the `PasswordHasher` hash/verify API has been stable for years — no justified break, so no floor). Symmetry lives in the *rule*, not in pinning every library.

**Dev deps live under `[dependency-groups]` (PEP 735).** Emit `[dependency-groups]` with `dev = [...]` — `uv run` / `uv sync` install the `dev` group by default. Do **not** emit the deprecated `[tool.uv.dev-dependencies]` table (uv warns on it and it is slated for removal).

## E. Toolchain (defined in `gate.py`)

The toolchain commands, the pinned mypy/ruff/pytest config, and the single definition of "green" live in **`gate.py`** — run `uv run "${CLAUDE_PLUGIN_ROOT}/plugins/adw/bin/adw.py" gate` (add `--criteria` to cross-check `criteria.md` flips). This skill does not restate the commands (C7). What follows is only the *house-style knowledge* the config encodes, so an author knows why a rule exists:

- **type-check runs both `src` and `tests`** at parity with lint — so a defect never hides in whichever the other skips. The test skills' "full annotations on every fixture/helper" rule is what keeps `tests` green (a fixture consuming the app types it `real_app: FastAPI`, a yielding fixture annotates `-> AsyncIterator[T]`, a parametrize hook `metafunc: pytest.Metafunc`).
- **`B904`** (a `flake8-bugbear` rule the gate enables) makes a bare `raise X` inside an `except` an error: chain the cause with `raise X(...) from exc`, or deliberately suppress it with `from None` (e.g. translating a lookup-miss to an auth error without leaking the internal cause).
- **`B006`** flags a **mutable default argument** (`def f(x: list = [])`) — a shared-state bug; use `x: tuple = ()` / `x: <T> | None = None` and build inside. (Both are individual bugbear rules, not the whole `B` family — the select stays narrow.)
- **Missing-stub silence has exactly one sanctioned form**: a `[[tool.mypy.overrides]]` block with `ignore_missing_imports = true` for a package that ships no stubs / `py.typed` (today `dependency_injector.*`, `testcontainers.*`, and any stub-less SDK, e.g. `argon2.*`). This is the **only** sanctioned way to silence a missing-stub error — never an inline `# type: ignore` on a content module. The `__init__.py` `F403/F405` ignore is likewise the only sanctioned ruff suppression — never an inline `# noqa` on a content module.
- **migrations** — Alembic owns the chain natively; migrations are never generated as logic. `uv run alembic revision --autogenerate -m "<change>"` then `uv run alembic upgrade head`. A schema-drift check (entity fields ↔ table columns) is the deterministic trigger that wakes the implementer to author the next revision. The gate's Docker tier runs `alembic upgrade head` against a fresh postgres container, handing the DSN in via `DATABASE_URL` / `GATE_DATABASE_URL` (block C `migrations/env.py` honours it).

## F. Multi-context apps (cross-context resolution + shared substrate)

A bounded context is one folder of specs; a deployable **app** is a SET of contexts living in ONE package — contexts as sibling subpackages, keyed by `subdomain` (`domain/auth/` + `domain/tickets/`, `application/auth/` + `application/tickets/`, …). Greenfield (a single context) is the degenerate case. Two derivation rules govern the multi-context case:

**A cross-context ref is a cross-subdomain reference.** A context names a node in another context with the `<subdomain>:<Name>` notation (e.g. a Tickets service depends on `auth:IUserRepository`, and its body references `auth:Role`). Because the contexts share one package, this is **not special** — it is exactly a cross-subdomain reference (block A "imports are graph edges"): strip the `<subdomain>:` prefix and resolve `<Name>` in the `<subdomain>` subpackage of the appropriate layer, via the ordinary import rules. So `auth:IUserRepository` injected into a `tickets` service → `from <package>.domain.auth import IUserRepository`; `auth:Role` in its body → the same. The `<subdomain>:` prefix **is** the subpackage; the name after it is resolved there, and the DI provider that injects it is wired in the one shared `containers.py`.

**The substrate is emitted ONCE, from the union of contexts.** Per-context artifacts (everything under `domain/<subdomain>/`, `application/<subdomain>/`, a context's repositories/adapters under their tech subpackage, its routers + per-resource schemas) belong to that context. The SHARED substrate is written once for the whole app, from the **union** of the contexts — never regenerated per-context (that would clobber the other context's contributions):
- `domain/exceptions.py` — the single catalog is the union of every context's exceptions, dedup by name (two contexts both declaring `ValidationError` collapse to one).
- `infrastructure/postgres/` bootstrap (engine, `session_factory`, `metadata.py`) and the single `DbSettings` — one Postgres substrate; a `DbSettings` / `datastore main` declared in several contexts collapses to one (dedup by name + `env_prefix`).
- `restapi/main.py` — one app shell, with `app.include_router(...)` for **every** context's router.
- `restapi/error_handler.py`, `restapi/schemas/errors.py`, `restapi/dependencies.py` — one each (the auth dependencies in `dependencies.py` are shared by every context whose endpoints are authenticated).
- `containers.py` — ONE `Container`, wiring every context's providers (auth + tickets + …).
- `pyproject.toml` — substrate ∪ the union of all contexts' `requires_packages` (block D) over the whole app.

Dedup is by identifier: same name (and shape) across contexts → one artifact. A genuine **conflict** (same name, different shape) is never silently merged — surface it for the human, like any cross-context ambiguity.

## G. See also

- `architecture` — the four-layer split, relative vs absolute import reach, the same-package collapse, the `from .module import *` re-export contract, one class per module, `__all__` placement, subpackage `__init__.py` mechanics.
- `gate.py` — the toolchain commands, pinned config, and the definition of "green" this skill cites.
