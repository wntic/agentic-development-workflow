---
name: conventions
description: The Python/FastAPI house style's derivation registry — turns a bare identifier (entity name, protocol name, command base-name, datastore kind) into a concrete file path and class name. Also carries the store profiles, the library substrate (names, no versions), the Alembic bootstrap, and multi-context resolution. Produces no file of its own.
when_to_use: Deciding where a file goes, what a class is called, which client a datastore gets, which packages the project carries, how the Alembic bootstrap is laid, or how a cross-context reference resolves. Consulted alongside the skill that owns the artifact's content, never instead of it.
---

# Conventions (Python / FastAPI)

This is the **derivation layer**: the rules that turn the bare identifiers a change introduces — an
entity name, a protocol name, a command base-name, a datastore kind — into concrete file paths, class
names and package dependencies. Other skills own what goes *inside* an artifact; this one owns the
mapping between a name and its place in the tree. It produces **no file of its own**.

All paths below are relative to the target package root `src/<package>/` (e.g.
`src/hdk/domain/auth/user.py`). Worked names use a helpdesk vocabulary (`auth`/`User`,
`support`/`Ticket`, `openai`/`jwt`).

## A. Path & name derivation

**`snake_case`** — PascalCase → snake by inserting `_` before each interior capital, then lowercasing:
`ITicketRepository` → `i_ticket_repository`, `OpenaiTextEmbedder` → `openai_text_embedder`. Acronym
runs are **not** special-cased yet (revisit if an `OTP`-style identifier needs `o_t_p` avoided).

**`pluralize`** (table names) — `y` after a consonant → `ies`; trailing `s`/`x`/`z`/`ch`/`sh` → `+es`;
else `+s`. So `Category` → `categories`, `Box` → `boxes`, `User` → `users`. Table name =
`pluralize(snake(aggregate))`.

**Class names** carry only the identifier plus a derived suffix. Protocol identifiers already include
their `I`-prefix / `Repository` suffix.

| Artifact | Given | Derived class name(s) | Derived file path(s) |
|---|---|---|---|
| domain enum | `Role` in subdomain `auth` | `Role` | `domain/auth/role.py` |
| domain value object | `Email` in `auth` | `Email` | `domain/auth/email.py` |
| domain entity | `User` in `auth` | `User` | `domain/auth/user.py` |
| domain service | `OtpVerifier` in `auth` | `OtpVerifier` | `domain/auth/otp_verifier.py` |
| domain filter | `TicketFilter` in `support` | `TicketFilter` + sort enum | `domain/support/ticket_filter.py` |
| repository protocol | `IUserRepository` in `auth` | `IUserRepository` | `domain/auth/i_user_repository.py` |
| capability protocol | `ICanSendEmail` in `auth` | `ICanSendEmail` | `domain/auth/i_can_send_email.py` |
| domain exception | `NotFoundError` | `NotFoundError` | appended to `domain/exceptions.py` (single catalog) |
| application command | `CreateTicket` (subdomain derived, see below) | `CreateTicketCommand` + `CreateTicketHandler` | `application/support/create_ticket_command.py` + `application/support/create_ticket_handler.py` |
| application query | `ListTickets` | `ListTicketsQuery` + `ListTicketsHandler` + `ListTicketsResult` | `application/support/list_tickets_query.py` + `_handler.py` + `_result.py` |
| datastore | named `vectors`, kind `qdrant` | — (a configured resource, no class) | `infrastructure/qdrant/connection.py`, holding `create_vectors_client` |
| settings | `OpenaiSettings` | `OpenaiSettings` | `infrastructure/openai/settings.py` — subpackage = the consuming tech (see below); the module is always `settings.py`, one settings class per subpackage |
| repository adapter | implements `IUserRepository`, backs `User`, on store `main` | `UserRepository` | `infrastructure/<store-kind>/repositories/<repo-stem>.py` (+ a write-once `Table` at `infrastructure/<store-kind>/tables/users.py` for a relational store) |
| capability adapter | implements `ICanEmbedText`, adapter `openai`, role `TextEmbedder` | `OpenaiTextEmbedder` | `infrastructure/openai/openai_text_embedder.py` |
| REST schema | `LoginRequest` for resource `auth` | `LoginRequest` | grouped into `restapi/schemas/auth.py` |
| REST endpoint | method + path, resource `auth` | endpoint function (name from method + path) | grouped into `restapi/routers/auth.py` |
| middleware | `RequestId` | `RequestIdMiddleware` | `restapi/middleware/request_id.py` |

**An application handler's subdomain is derived, not chosen.** It is the subdomain of the first
repository protocol the handler depends on (a repository protocol carries its own subdomain); with no
repository dependency, fall back to the subdomain of the first domain entity it touches. So
`CreateTicket` depending on `ITicketRepository` (subdomain `support`) lands in `application/support/`.

**A value object used as a dependency is a tunable VO, and its wiring follows.** A value object is
normally built inline at its use site. When it is instead *injected* into a handler or a domain
service, it is the **tunable variant** (`domain-model`, the config-knob view of an env
threshold): DI-wired as a `providers.Singleton` constructed field-by-field from a settings class, not
from an inline literal. The stem pairing `<Stem>Tunable` ← `<Stem>Settings` (e.g. `LockoutTunable` ←
`LockoutSettings`) is an **advisory default, not load-bearing** — the real binding is the DI wiring
(`infra-wiring`), which sources the tunable from whichever settings fields match. A stem mismatch
is fine: `LockoutTunable(max_attempts=auth_settings.provided.max_attempts, …)` from a single
`AuthSettings` is correct. Name them to match when a dedicated settings class exists; reuse a broader
one (and let the stems differ) when the knobs naturally live there. The field-by-field construction
`<tunable>(field=<settings>.provided.field, …)` is the invariant. This is how an env-tunable domain
threshold — lockout numbers, quotas, retention — reaches a domain service without the domain importing
`pydantic-settings`.

**Infrastructure groups by external TECH, never by a domain subdomain and never under a catch-all
`db/`.** The tech token is:

- a repository's **store kind** — the kind of the datastore it sits on; with no datastore named, the
  implicit single `postgres` store. Relational repositories, their write-once table, and the shared
  SQLAlchemy engine / `session_factory` / `metadata.py` bootstrap all sit under
  `infrastructure/postgres/` (`repositories/`, `tables/`).
- a non-relational datastore's **kind** — `infrastructure/qdrant/`, `infrastructure/redis/`, holding
  `connection.py` (the `create_<name>_client` factory) and its settings.
- a capability adapter's **adapter** token — `infrastructure/openai/`, `infrastructure/jwt/`.
- a settings class's **consuming tech** — the adapter of the capability that uses it, or the kind of
  the datastore that uses it; a settings class with no consumer falls back to its own snake name.

**Capability adapter class** = `<AdapterPascal><Suffix>`, where `Suffix` is the capability's agent-noun
role when there is one (adapter `jwt`, role `TokenManager` → `JwtTokenManager`) and otherwise the
protocol name minus its `ICan` prefix (adapter `jwt`, implements `ICanManageTokens`, no role →
`JwtManageTokens`). The role is named explicitly precisely because the agent-noun is not mechanically
derivable from the verb.

**Repository file stem — aggregate-derived for a relational store, protocol-derived for a client
store.** The class is always `<Aggregate>Repository` (backs `User` → `UserRepository`), but its **file
stem** depends on the store profile (block C), because polyglot persistence lets two repositories back
ONE aggregate:

- a **relational store** repo → `<snake(aggregate)>_repository.py` (`Meeting` on `main` →
  `meeting_repository.py`).
- a **client-style store** repo → the **protocol-derived** stem: the implemented protocol name minus
  its leading `I`, snaked (`IMeetingSearchIndex` on `vectors` → `meeting_search_index.py`).

So a `Meeting` backed by both a Postgres `IMeetingRepository` and a Qdrant `IMeetingSearchIndex` lands
two distinct files — `postgres/repositories/meeting_repository.py` and
`qdrant/repositories/meeting_search_index.py`. An aggregate-only stem would collide.

**Which repository skill applies is decided by the store profile, not the vendor.** A relational store
→ `infra-persistence` (SQLAlchemy Core). **Any** client-style store →
`infra-store-repository`, one vendor-agnostic skill covering every vector / cache / document backend
(qdrant, redis, chroma, pinecone, mongo, …). A new client-style backend is a **profile row in block C
plus its package**, never a new skill — the same way one `infra-capability-adapter` serves boto3,
httpx, PyJWT and openai.

**Imports and package mechanics are not restated here.** A referenced type resolves to its owning
module: same-subdomain domain types use a relative `.module` import, cross-subdomain a relative
`..subdomain`, cross-layer an absolute `<package>.domain.<subdomain>` import, stdlib its canonical
import, builtins none. `architecture` owns the rules, `__all__`, and the `from .module import *` re-export contract the
collapsed import form depends on.

## C. Store profiles

A datastore's kind is a free token, not a closed enum — a fixed list is the same disease as a fixed
type map. The profile maps a kind to the few things needed to wire a repository **without** knowing the
backend's SQL/SDK internals:

| kind | resource param / attr | resource type | resource import | method contract | relational |
|---|---|---|---|---|---|
| `postgres` | `session_factory` / `sf` | `async_sessionmaker[AsyncSession]` | `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker` | `sql` | **yes** |
| `qdrant` | `client` / `client` | `AsyncQdrantClient` | `from qdrant_client import AsyncQdrantClient` | `collection` | no |
| `redis` | `client` / `client` | `Redis` | `from redis.asyncio import Redis` | `generic` | no |
| *(unknown)* | `client` / `client` | `object` | — | `generic` | no |

- **Relational** also selects the repository skill (block A): yes → `infra-persistence`;
  no → `infra-store-repository`. Adding a client-style backend is one row here.
- **Relational yes** → the repository reuses the shared SQLAlchemy engine + `session_factory` bootstrap
  under `infrastructure/postgres/` (postgres is the only relational profile today), and gets a
  write-once `Table` under `infrastructure/postgres/tables/`. **No** → lay a
  `create_<store>_client(settings)` factory in `infrastructure/<kind>/connection.py` that the DI
  container injects as a `Singleton` into every repository on that store, and there is **no**
  SQLAlchemy table — the store persists through its own client.
- The **method contract** (`sql` / `collection` / `generic`) sets only the *wording* of the
  repository's contract comment.
- An **unknown** kind degrades to a generic untyped `object` client plus a loud contract comment —
  fail loud, do not crash. Adding a backend is **one row here**, never a change to any tool.

**The connection factory is complete glue, not a stub.** For a known profile kind the connection /
engine factory carries zero judgment — it is a fixed function of the settings shape — so write it in
**full**, never as `raise NotImplementedError`. A stub here type-checks and lints clean, then crashes
the DI container at app construct. The canonical complete forms:

```python
# infrastructure/postgres/engine.py  (the relational engine + session factory — complete)
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

The factory name is `create_<datastore-name>_client` — the datastore's *name*, not its kind, so
`create_vectors_client` for a datastore named `vectors`. The resource type and import come from the
profile table. Only a genuinely unknown kind (the degraded `object` row) cannot be written complete;
there alone leave a `NotImplementedError` plus a loud comment.

**Relational migrations bootstrap (Alembic) — complete config plus a write-once baseline.** Laid
**only when a relational store backs a repository**, the same trigger as the Postgres substrate and the
table. Alembic owns the revision chain, but the chain cannot start — and `alembic upgrade head` cannot
run — without two things: the Alembic **config** (pure glue, rewritten freely) and an **initial
baseline revision** (write-once). Without them the integration suite dies at setup: the session-autouse
`_migrated_db` fixture runs `alembic upgrade head` and gets `No 'script_location' key found`. Nothing
in lint, type-check or the unit tier catches that — only a real Docker run does.

The three config files are complete glue at the tree root and `migrations/`:

```ini
# alembic.ini  (tree root)
[alembic]
script_location = migrations
prepend_sys_path = src
```

```python
# migrations/env.py  (async, wired to the project's shared MetaData — online mode only:
# the app is always migrated against a live connection, and `alembic revision --autogenerate`
# also runs online)
import asyncio

from alembic import context

import myapp.infrastructure.postgres.tables  # noqa: F401  — registers every Table on the shared metadata
from myapp.infrastructure.postgres.engine import create_engine
from myapp.infrastructure.postgres.metadata import metadata
from myapp.infrastructure.postgres.settings import DbSettings

target_metadata = metadata


def _run(connection) -> None:  # MigrationContext drives this inside run_sync
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_engine(DbSettings())  # DSN from the *_DB_* env the caller sets (e.g. the testcontainer)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(_run_online())
```

`migrations/script.py.mako` is Alembic's standard revision template (`${message}` / `${up_revision}` /
`${down_revision}` / `upgrade()` / `downgrade()`); write it verbatim so `alembic revision` can author
later deltas.

The **baseline revision** is **write-once** — create `migrations/versions/0001_initial.py` only when
`migrations/versions/` carries no `*.py` yet. Never clobber a chain that already has brownfield deltas:

```python
# migrations/versions/0001_initial.py
"""initial — the users table

Every column, type and constraint is written out here rather than derived from the shared metadata:
`metadata.create_all` reads the metadata as it stands when the revision RUNS, so replaying this
revision later would build whatever the table has become rather than what it was when this was
written. Schema evolution is versioned from this change onward, which means history stays replayable.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        # A check constraint's `name` is the SUFFIX: the metadata convention prepends `ck_users_`; a full name doubles.
        sa.CheckConstraint("char_length(email) > 0", name="email_non_empty"),
    )


def downgrade() -> None:
    op.drop_table("users")
```

The baseline **freezes** the tables as they stood the day it was written — every column, type and
constraint spelled out by hand, nothing read from the live `metadata` at run time. It carries no logic
delta; it exists so the chain can start, and being frozen is what keeps the chain replayable from zero.
The revision does not import the project's `metadata` or its table registrar at all: it needs neither,
and either import would be a false trail back to the derived form. **Every subsequent migration is a
real Alembic revision**
(`uv run alembic revision --autogenerate -m "<change>"`), authored when entity fields and table columns
drift apart. `migrations/` lives at the tree root, outside `src/` and `tests/`, which puts it inside one
of the two surfaces `make check` has and outside the other: `ruff check` and `ruff format --check` run
with **no paths**, so lint and formatting cover the whole tree, `migrations/` included, while
`mypy src tests` names its two directories, so the type surface stops at their edge. The two surfaces
differ by exactly that one directory — which is why a formatter count taken over `src tests` alone is not
the count `make check` produces. Its correctness as a schema chain is exercised by
`alembic upgrade head` in the integration suite.

## D. Stack substrate (library NAMES, no versions)

`pyproject.toml` carries the framework substrate plus whatever each infrastructure adapter needs.

- **Framework substrate** (the FastAPI-hexagon stack, always present): `fastapi`, `uvicorn[standard]`,
  `pydantic`, `pydantic-settings`, `dependency-injector`, `structlog`.
- **Relational bootstrap** (only when a relational store backs a repository): `sqlalchemy[asyncio]`,
  `asyncpg`, `alembic`.
- **Multipart form handling** (only when some endpoint takes a `Form(...)` / `UploadFile`):
  `python-multipart`. FastAPI imports it at app-construct time for any form route, otherwise
  `create_app()` raises `RuntimeError: Form data requires "python-multipart"` — which lint, type-check
  and the unit tier do **not** catch; only constructing the app does. An app with no multipart endpoint
  must not carry it.
- **Dev** (always present): `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `testcontainers`, `httpx`.
- **Auth test bootstrap** (only when the app has auth **and** its token scheme is asymmetric — an
  RSA/EC keypair, e.g. RS256, which is the scheme `testing-integration-setup` uses today):
  `cryptography`. That conftest mints RS256 tokens from a generated RSA keypair, and building the
  keypair needs it. An app that has auth yet verifies symmetric (HS256) or opaque tokens generates no
  keypair and must **not** carry it — a `cryptography` dev dep nothing imports is a stray package.
- **SDK packages are not listed here** — each rides along with the adapter that needs it
  (`qdrant-client`, `openai`, `pyjwt`, …).

**No versions in the substrate.** This list carries names only. `uv lock` / `uv sync` resolve the
latest-compatible versions into `uv.lock`, which is the only home for a concrete pin — so nothing rots.
A pinned `>=` on a substrate library (`fastapi>=0.115` under eternal manual bump) is the disease this
avoids.

**Floors on an SDK — the lone, disciplined exception.** An adapter's SDK *may* carry a `>=` floor, but
only when it marks a **known breaking-version boundary** — an API the code relies on landed or changed
there — with the floor sitting at that boundary, expressed as the major, and the reason in a comment.
It is a *contract* fact ("needs v2, where the API changed"), never a recency guess: do not write a
version you recall as "recent", because that recollection is frozen at a training cutoff, and a floor
padded above the real break (`pyjwt>=2.8` when the break is `2.0`) is exactly that stale memory
masquerading as a constraint. Worked examples: `pyjwt>=2` (PyJWT 2.0 made `encode` return `str`, not
`bytes`); `redis>=4.2` (`redis.asyncio` merged in at 4.2 — before that the async client was the
separate `aioredis`); `argon2-cffi` with **no** floor (the `PasswordHasher` API has been stable for
years, so no justified break and no floor). Symmetry lives in the *rule*, not in pinning every library.

**Dev deps live under `[dependency-groups]` (PEP 735).** Write `[dependency-groups]` with
`dev = [...]` — `uv run` / `uv sync` install the `dev` group by default. Do **not** write the deprecated
`[tool.uv.dev-dependencies]` table; uv warns on it and it is slated for removal.

## E. Toolchain configuration

The commands that define "green" belong to the project, not to this skill. What lives here is the
configuration those commands read, because it is house style and has no other home.

- **Lint and type-check hold `src` and `tests` at parity** — so a defect never hides in whichever
  surface the other skips — **and lint reaches one directory further than the type checker**: `ruff`
  runs with no paths and so covers `migrations/` as well, while `mypy src tests` stops at the edge of
  the two directories it names. What keeps `tests` green is the test skills' rule that every
  fixture and helper is fully annotated: a fixture consuming the app types it `real_app: FastAPI`, a
  yielding fixture annotates `-> AsyncIterator[T]`, a parametrize hook takes `metafunc: pytest.Metafunc`.
- **ruff lint config**: `[tool.ruff.lint]` `select = ["E", "F", "I", "B006", "B904"]`, plus
  `[tool.ruff.lint.per-file-ignores]` `"**/__init__.py" = ["F403", "F405"]`. `B904` makes a bare
  `raise X` inside an `except` an error: chain the cause with `raise X(...) from exc`, or suppress it
  deliberately with `from None` (e.g. translating a lookup miss into an auth error without leaking the
  internal cause). `B006` flags a **mutable default argument** (`def f(x: list = [])`) — a shared-state
  bug; use `x: tuple = ()` or `x: <T> | None = None` and build inside. Both are individual
  `flake8-bugbear` rules, not the whole `B` family — keep the select narrow. The `__init__.py`
  F403/F405 ignore is the **only** sanctioned ruff suppression; never an inline `# noqa` on a content
  module.
- **`line-length` is the project's own parameter, and the number gets written down.** `[tool.ruff]`
  `line-length` defaults to 88; **120 is legal**, and on an established project it is the value to pick
  when signatures and single-line explanatory comments keep colliding with the limit. **Whatever the
  number, write it in `pyproject.toml` explicitly** — a decision that is invisible in the config has not
  been made, and a later reader cannot tell a chosen 88 from ruff's inherited default. The cost of moving
  is measured, not estimated: `line-length` drives the **formatter** as well as `E501`, so raising it
  reformats the tree — on a 67-file project the move from 88 to 120 put **20 files
  under reformat** (`uv run ruff format --check --line-length 120 src tests migrations`). The
  consequence the number carries: this is a **project-setup decision**, settled once when the project is
  laid down, not adjusted mid-change. If an established project does move, the reformat travels as its
  own commit, so it cannot hide a behaviour change inside it. **On a project being laid down, write
  120.** The colliding-with-the-limit signal cannot be read at that moment — there are no signatures and
  no explanatory comments yet — while the reformat cost that argues for staying at 88 is **zero** on an
  empty tree, there being nothing to reformat. Against that zero stand two measured cases where 88 made
  the limit cut the content instead of wrapping it: single-line comments that had to be trimmed with a
  loss of meaning at 89 characters, and a port docstring's contract keys dropped at 93 and 117.
- **mypy config**: `[tool.mypy]` `strict = true`, `python_version = "3.12"`,
  `plugins = ["pydantic.mypy"]`. A third-party package that ships **no type stubs and no `py.typed`
  marker** gets one `[[tool.mypy.overrides]]` block with `ignore_missing_imports = true` — list every
  such package the project carries. Today that set is `dependency_injector.*`, `testcontainers.*` (a
  dev dep the integration suite imports, so it is inside the surface), and any stub-less SDK in use
  (e.g. `argon2.*`). This is the **only** sanctioned way to silence a missing-stub error; never an
  inline `# type: ignore` on a content module.
- Adding a package: `uv add <lib>`, or `uv add --dev <lib>` for a dev dep.
- Starting a project: `uv init --package <name>`. The `--package` flag is what produces the
  `src/<name>/` layout with a `__init__.py` and a build backend — plain `uv init` lays a flat
  single-module project instead, which does not match anything in this house style.

## F. Multi-context apps

A deployable app may hold more than one bounded context in ONE package — contexts as sibling
subpackages keyed by subdomain (`domain/auth/` + `domain/tickets/`, `application/auth/` +
`application/tickets/`, …). A single-context app is the degenerate case. Two rules govern the rest:

**A cross-context reference is a cross-subdomain reference.** Where a name is written
`<subdomain>:<Name>` — a tickets service depending on `auth:IUserRepository`, its body referencing
`auth:Role` — this is **not special**. Strip the `<subdomain>:` prefix and resolve `<Name>` in the
`<subdomain>` subpackage of the appropriate layer, by the ordinary import rules. So
`auth:IUserRepository` injected into a tickets service → `from <package>.domain.auth import
IUserRepository`. The prefix **is** the subpackage, and the DI provider that injects it is wired in the
one shared `containers.py`.

**The shared substrate exists once, as the union of the contexts.** Per-context artifacts — everything
under `domain/<subdomain>/` and `application/<subdomain>/`, a context's repositories and adapters under
their tech subpackage, its routers and per-resource schemas — are per context. These are **one each for
the whole app**, and writing them per context would clobber the other context's contributions:

- `domain/exceptions.py` — the single catalog is the union of every context's exceptions, deduped by
  name; two contexts both declaring `ValidationError` collapse to one.
- `infrastructure/postgres/` bootstrap (engine, `session_factory`, `metadata.py`) and the single
  `DbSettings` — one Postgres substrate; a `DbSettings` or a `main` datastore named in several contexts
  collapses to one, deduped by name and env prefix.
- `restapi/main.py` — one app shell, with `app.include_router(...)` for **every** context's router.
- `restapi/error_handler.py`, `restapi/schemas/errors.py`, `restapi/dependencies.py` — one each. The
  auth dependencies in `dependencies.py` are shared by every context with authenticated endpoints, not
  only the context that introduced auth.
- `containers.py` — ONE `Container`, wiring every context's providers.
- `pyproject.toml` — the substrate plus the union of every context's packages (block D).

Dedup is by identifier: the same name and shape across contexts → one artifact. A genuine **conflict**
— same name, different shape — is never silently merged. Stop and surface it.

## G. See also

- `architecture` — relative vs absolute reach, the same-package collapse, the
  `from .module import *` re-export contract.
- `architecture` — one class per module, `__all__` placement, subpackage `__init__.py`
  mechanics.
