---
name: conventions
description: Reference skill (produces no target-app file) — the Python/FastAPI pack's mechanical derivation registry. Consulted by the scaffolder to place files and name classes, and by the runner/validator for kind→skill dispatch and the §16 coverage gate. Carries kind→path/class/suffix derivation, the kind→skill registry, store profiles, the stack-substrate library list (names, no versions), and the verification-loop toolchain commands. This is the knowledge formerly hardcoded in the deleted generator (naming / store-profiles / substrate constants); other skills own artifact CONTENT, this owns the derivation between manifest identifiers and the file tree.
---

# Conventions (Python / FastAPI pack)

This is the pack's **derivation layer**: the rules that turn the bare identifiers a manifest carries (entity name, protocol name, command base-name, datastore `kind`) into concrete file paths, class names, the producing skill, dependencies, and toolchain invocations. The manifest stays minimal because everything mechanical is derived **here** (spec §3, §5; MANIFEST_SCHEMA.md "Derived, not declared").

Two readers consume it: the **scaffolder** (blocks A, C, D — where to write each file, what to name the class, which client a store gets, what goes in the dependency manifest) and the **runner/validator** (block B — which skill produces a node, and the §16 presence-gap gate). It produces **no file of its own**.

All paths below are relative to the target package root `src/<package>/` (e.g. `src/hdk/domain/auth/user.py`). Worked names use the Helpdesk vocabulary (`auth`/`User`, `support`/`Ticket`, `openai`/`jwt`).

## A. Path & name derivation

**`snake_case`** — PascalCase → snake by inserting `_` before each interior capital, then lowercasing: `ITicketRepository` → `i_ticket_repository`, `OpenaiTextEmbedder` → `openai_text_embedder`. Acronym runs are **not** special-cased yet (revisit if an `OTP`-style identifier needs `o_t_p` avoided).

**`pluralize`** (table names) — `y` after a consonant → `ies`; trailing `s`/`x`/`z`/`ch`/`sh` → `+es`; else `+s`. So `Category` → `categories`, `Box` → `boxes`, `User` → `users`. Table name = `pluralize(snake(aggregate))`.

**Class names** carry only the identifier plus a derived suffix; the manifest never carries a class name (MANIFEST_SCHEMA "deliberately does NOT contain"). Protocol identifiers already include their `I`-prefix / `Repository` suffix.

| Artifact kind | Manifest identifier(s) | Derived class name(s) | Derived file path(s) |
|---|---|---|---|
| `domain.enums[*]` | `name: Role`, `subdomain: auth` | `Role` | `domain/auth/role.py` |
| `domain.value_objects[*]` | `name: Email`, `subdomain: auth` | `Email` | `domain/auth/email.py` |
| `domain.entities[*]` | `name: User`, `subdomain: auth` | `User` | `domain/auth/user.py` |
| `domain.services[*]` | `name: OtpVerifier`, `subdomain: auth` | `OtpVerifier` | `domain/auth/otp_verifier.py` |
| `domain.filters[*]` | `name: TicketFilter`, `subdomain: support` | `TicketFilter` + sort enum | `domain/support/ticket_filter.py` |
| `domain.repository_protocols[*]` | `name: IUserRepository`, `subdomain: auth` | `IUserRepository` | `domain/auth/i_user_repository.py` |
| `domain.capability_protocols[*]` | `name: ICanSendEmail`, `subdomain: auth` | `ICanSendEmail` | `domain/auth/i_can_send_email.py` |
| `domain.exceptions[*]` | `name: NotFoundError` | `NotFoundError` | appended to `domain/exceptions.py` (single catalog) |
| `application.commands[*]` | `name: CreateTicket` (subdomain derived, see below) | `CreateTicketCommand` + `CreateTicketHandler` | `application/support/create_ticket_command.py` + `application/support/create_ticket_handler.py` |
| `application.queries[*]` | `name: ListTickets` | `ListTicketsQuery` + `ListTicketsHandler` + `ListTicketsResult` | `application/support/list_tickets_query.py` + `_handler.py` + `_result.py` |
| `infrastructure.datastores[*]` | `name: vectors`, `kind: qdrant` | — (a configured resource, no class) | `infrastructure/qdrant/connection.py` (scaffolded `create_vectors_client`) |
| `infrastructure.settings[*]` | `name: OpenaiSettings` | `OpenaiSettings` | `infrastructure/openai/settings.py` — subpackage = the consuming tech (see below); the module is always `settings.py` (one settings class per subpackage, as `infra-settings` and every importer expect) |
| `infrastructure.repositories[*]` | `implements: IUserRepository`, `backs: User`, `store: main` | `UserRepository` | `infrastructure/<store-kind>/repositories/user_repository.py` (+ a write-once Table SCAFFOLD at `infrastructure/<store-kind>/tables/users.py` for a relational store) |
| `infrastructure.capabilities[*]` | `implements: ICanEmbedText`, `adapter: openai`, `role: TextEmbedder` | `OpenaiTextEmbedder` | `infrastructure/openai/openai_text_embedder.py` |
| `restapi.schemas[*]` | `name: LoginRequest`, `resource: auth` | `LoginRequest` | grouped into `restapi/schemas/auth.py` |
| `restapi.endpoints[*]` | `method`, `path`, `resource: auth` | endpoint function (name from method+path) | grouped into `restapi/routers/auth.py` |
| `restapi.middlewares[*]` | `name: RequestId`, `config` | `RequestIdMiddleware` | `restapi/middleware/request_id.py` |

**Application subdomain is derived, not declared.** Commands and queries carry no `subdomain` field. The subdomain is the subdomain of the first `handler.dependencies` entry that names a `repository_protocol` (a repository protocol carries its own `subdomain`); when the handler has no repository dependency, fall back to the first domain entity's subdomain. So `CreateTicket` with `handler.dependencies: [ITicketRepository]` (whose protocol is `subdomain: support`) lands in `application/support/`.

**Infrastructure groups by external TECH, never by a domain subdomain and never under a catch-all `db/`** (spec §3; CLAUDE.md "grouped by external tech"). The tech token is:
- a repository's **store kind** — the `kind` of the `datastore` its `store` names; absent `store` ⇒ the implicit single `postgres` store. Relational repos, their write-once table scaffold, and the shared SQLAlchemy engine/`session_factory`/`metadata.py` bootstrap all sit under `infrastructure/postgres/` (`repositories/`, `tables/`).
- a non-bootstrap datastore's **`kind`** — `infrastructure/qdrant/`, `infrastructure/redis/`, holding `connection.py` (the `create_<name>_client` scaffold) and its settings.
- a capability adapter's **`adapter`** token — `infrastructure/openai/`, `infrastructure/jwt/`.
- a settings node's **consuming tech** — the `adapter` of the capability that names it, or the `kind` of the datastore that names it; an orphan settings falls back to its own snake name.

**Capability adapter class** = `<AdapterPascal><Suffix>`, where `Suffix` is the capability's `role` agent-noun when present (`adapter: jwt`, `role: TokenManager` → `JwtTokenManager`) and otherwise the protocol name minus its `ICan` prefix (`adapter: jwt`, `implements: ICanManageTokens`, no role → `JwtManageTokens`). The `role` is carried in the manifest precisely because the agent-noun is not mechanically derivable from the verb (the `log_event` precedent).

**Imports and package mechanics are not restated here** — see block F. Imports are graph edges in Python syntax (a referenced type resolves to its owning module): same-subdomain domain types use a relative `.module` import, cross-subdomain a relative `..subdomain`, cross-layer an absolute `<package>.domain.<subdomain>` import, stdlib its canonical import, builtins none. `general-imports-conventions` owns the rules; `general-python-package` owns `__all__` + the `from .module import *` re-export contract that the collapsed import form depends on.

## B. kind→skill registry

**Producer skills — the deterministic dispatch** (one skill per manifest artifact kind). This table is the source of truth, mirrored as data in the validator's `KIND_TO_SKILL` (which the §16 coverage gate reads — the same way the validator's `SCHEMAS` dict, not the stale `MANIFEST_SCHEMA.md` prose, is the source of truth for the manifest shape). Choosing the skill for a node is a deterministic lookup, **not** an agent judgment (spec §2).

| Artifact kind | Producer skill |
|---|---|
| `domain.enums` | `domain-enum` |
| `domain.value_objects` | `domain-value-object` |
| `domain.entities` | `domain-entity` |
| `domain.services` | `domain-service` (orchestrator vs. pure is DERIVED from the presence of `dependencies`, not a declared field) |
| `domain.filters` | `domain-filter` |
| `domain.repository_protocols` | `domain-repository-protocol` |
| `domain.capability_protocols` | `domain-capability-protocol` |
| `domain.exceptions` | `domain-exception` |
| `application.commands` | `application-command` |
| `application.queries` | `application-query` |
| `infrastructure.repositories` | **store-profile-dispatched** — `infra-sqlalchemy-repository` (relational store) or `infra-store-repository` (any client-style store); see the note below |
| `infrastructure.settings` | `infra-settings` |
| `infrastructure.capabilities` | `infra-capability-adapter` |
| `restapi.schemas` | `restapi-schema` (the `kind: request | response` axis is handled inside the skill) |
| `restapi.endpoints` | `restapi-endpoint` |
| `restapi.middlewares` | `restapi-middleware` |
| `tests.architecture_rules` | `test-architecture-rule` |

- `infrastructure.datastores` has **no producer skill** — a datastore is wired from its **store profile** (block C), not a per-kind skill, and an unknown `kind` degrades gracefully rather than tripping the gate. It is the one artifact kind exempt from the coverage gate.
- **Repositories dispatch by store profile, not vendor.** `infrastructure.repositories` is the one kind whose producer skill depends on a graph **edge** (`repository.store → datastore.kind`), not the kind alone. The choice is made by block C `uses_bootstrap`: a relational (bootstrap) store → `infra-sqlalchemy-repository` (SQLAlchemy Core); **any** client-style store → `infra-store-repository`, a single vendor-agnostic skill covering every vector/cache/document backend (qdrant, redis, chroma, pinecone, mongo, …). A new client-style backend is a **block-C profile row + the node's `requires_packages`** — *never* a new per-vendor skill (the same pattern as one `infra-capability-adapter` serving boto3/httpx/PyJWT/openai). Only a genuinely new *pattern* (not a new vendor) is a §16 gap. The validator mirrors this as `repository_skill(store_kind)`; `KIND_TO_SKILL` carries only the relational default (enough for the presence gate).
- **Library middlewares.** `restapi.middlewares` covers only *custom* middlewares — a body-bearing ASGI class via `restapi-middleware`. A middleware that maps to a library class (e.g. `CORSMiddleware`, a starlette built-in) is **not modelled yet**: a §16 coverage-gap, closed by adding a library-middleware profile when the first one is declared.

**Companion skills** — conditionally applied to a producer's artifact, not separately dispatched (this bucket includes the cross-cutting `pattern-` skills, whose prefix marks that they span layers rather than producing one layer's artifact): `infra-di-provider` (wires each producer's class into `containers.py` — graph-glue applied to every wired class), `infra-sqlalchemy-table` (the write-once `Table` scaffold, triggered by a relational repository — there is no `infrastructure.tables` manifest kind, so it is not a producer dispatch), `pattern-compensating-tx` (a command with an external side-effect before its DB write — its trigger is **derivable** from the handler dependency + `behaviour.then.calls`, so it needs no manifest signal), `pattern-unit-of-work` (≥2 repositories committing atomically — its trigger is **not** derivable from "two dependencies", so it will need a small per-command manifest signal; that signal is **deferred until the first epic that needs it**, §16, and no fixture exercises it today), `restapi-error-responses` (every endpoint advertises its error codes), `restapi-file-transfer` (multipart upload / streaming download), `restapi-auth-dependency` (reference — picks the route's auth dependency).

**Test skills** — derived per artifact (tests are derived, not enumerated; MANIFEST_SCHEMA core principle 3), not from a manifest field: `test-domain-entity` ← entities, `test-domain-enum` ← enums, `test-domain-value-object` ← VOs, `test-domain-service` ← services, `test-application-handler` ← commands/queries, `test-fake-repository` ← per aggregate/capability a handler test needs, `test-repository-contract` ← relational (`uses_bootstrap`) repositories, `test-store-repository-contract` ← client-style store repositories (the same store-profile split as `infra-sqlalchemy-repository` vs `infra-store-repository`), `test-infra-capability-adapter` ← capabilities, `test-restapi-endpoint` ← endpoints.

**Bootstrap skills** — run once, triggered by the working tree (not a manifest node; MANIFEST_SCHEMA core principle 4): `restapi-app-bootstrap`, `domain-exception` (first creation of `domain/exceptions.py`), `test-integration-isolation`, `test-integration-authed-client`, `test-discovery-invariants`.

**Reference / cross-cutting skills** — always consulted, never dispatched per node: `conventions` (this registry itself — the pack's derivation layer), `general-typing-conventions`, `general-imports-conventions`, `general-python-package`, `general-layered-architecture`, `general-logging`, `test-principles`.

> **Coverage is bidirectional (§16).** The forward gate (KIND_TO_SKILL) guarantees every artifact *kind* has a producer skill. The reverse — every skill *directory* is classified into exactly one of the buckets above (producer / companion / test / bootstrap / reference / meta) — is asserted by a meta-test (`test_every_skill_is_classified`), so a producing skill that maps to no manifest kind (an orphan, as `pattern-unit-of-work` once was) cannot hide. The four non-producer buckets are mirrored as data in that test, the way KIND_TO_SKILL mirrors the producer table; keep them in lockstep with this prose.

**Meta skills** — extend the pipeline itself, not the target app: `meta-skill-author` (drafts a new skill when the gate reports a presence-gap — human-reviewed, §16), `meta-uc-author`.

## C. Store profiles

A datastore's `kind` is a free token (not a closed enum — a fixed list is the same disease as a fixed type map). The profile maps a `kind` to the few things the scaffolder needs to wire a repository **without** knowing the backend's SQL/SDK internals (those live in the scaffolded bodies the implementer fills):

| `kind` | resource param / attr | resource type | resource import | method contract | `uses_bootstrap` |
|---|---|---|---|---|---|
| `postgres` | `session_factory` / `sf` | `async_sessionmaker[AsyncSession]` | `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker` | `sql` | **yes** |
| `qdrant` | `client` / `client` | `AsyncQdrantClient` | `from qdrant_client import AsyncQdrantClient` | `collection` | no |
| `redis` | `client` / `client` | `Redis` | `from redis.asyncio import Redis` | `generic` | no |
| *(unknown)* | `client` / `client` | `object` | — | `generic` | no |

- `uses_bootstrap` **also selects the repository producer skill** (registry B): `yes` → `infra-sqlalchemy-repository`; `no` → `infra-store-repository`. So adding a client-style backend is one row here — it routes to the existing vendor-agnostic skill, no new skill.
- `uses_bootstrap: yes` → the repository reuses the shared SQLAlchemy engine + `session_factory` bootstrap under `infrastructure/postgres/` (postgres is the only profile with the flag today), and gets a write-once `Table` scaffold under `infrastructure/postgres/tables/`. `no` → the scaffolder lays a write-once `create_<store>_client(settings)` connection factory in `infrastructure/<kind>/connection.py` that the DI container injects as a `Singleton` into every repository on that store, and there is **no** SQLAlchemy table (the store persists through its own client).
- The `method contract` (`sql` / `collection` / `generic`) only sets the **wording** of the repository scaffold's contract-comment.
- An **unknown** kind degrades to a generic untyped `object` client plus a loud contract comment — the fail-loud-not-crash invariant that the table scaffold also follows. Adding a backend is **one row here**, never a tooling change.

## D. Stack substrate (library NAMES, no versions)

The dependency manifest (`pyproject.toml`) is regenerated glue: the framework substrate ∪ the union of every infra node's `requires_packages` over the graph (spec §10). The scaffolder derives it from the graph; it is never "an agent recalling a package".

- **Framework substrate** (the FastAPI-hexagon stack, always present): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `dependency-injector`, `structlog`.
- **Relational bootstrap** (added only when a `uses_bootstrap` store backs a repository): `sqlalchemy[asyncio]`, `asyncpg`, `alembic`.
- **Multipart form handling** (added **only** when some endpoint declares `request_kind: multipart` — a `Form(...)` / `UploadFile` route): `python-multipart`. FastAPI imports it at app-construct time for any form/multipart route (otherwise `create_app()` raises `RuntimeError: Form data requires "python-multipart"` — which mypy / ruff / unit tests do **not** catch, only constructing the app does), so its presence is graph-derived from a multipart endpoint, exactly like the relational and auth bootstraps. An app with no multipart endpoint must not carry it.
- **Dev** (always present): `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `testcontainers`, `httpx`.
- **Auth test bootstrap** (added **only** when the app declares auth *and* its token scheme is asymmetric — an RSA/EC keypair, e.g. RS256, which is the scheme `test-integration-authed-client` uses today): `cryptography` — that conftest mints RS256 tokens from a generated RSA keypair (sign with the private key, the app verifies with the public one), so building/serializing the keypair needs `cryptography`. The trigger is graph-derived auth-presence (any authenticated endpoint / a token-verifier capability), but the package itself is needed only for the asymmetric path: an app that declares auth yet verifies symmetric (HS256) or opaque tokens generates no keypair and must **not** carry it — a `cryptography` dev dep that nothing imports is the stray-package bug. (RS256/RSA is the catalog's current auth-test scheme, not the only conceivable one.)
- **SDK packages are not listed here** — each rides on the infra node that needs it (`datastore` / `capability` `requires_packages`, e.g. `qdrant-client`, `openai`, `pyjwt`) and is unioned in from the graph.

**No versions.** This list carries names only; `uv add <lib>` pins the latest compatible version at scaffold time, so nothing rots. A pinned `>=` here would reintroduce the generator's chief disease (baked-in `fastapi>=0.115` under eternal manual bump).

**Dev deps live under `[dependency-groups]` (PEP 735).** Emit `[dependency-groups]` with `dev = [...]` — `uv run` / `uv sync` install the `dev` group by default. Do **not** emit the deprecated `[tool.uv.dev-dependencies]` table (uv warns on it and it is slated for removal).

## E. Toolchain commands (the verification loop)

Determinism in the redesign lives in verification, not authoring (spec §0 principle 3, §12). The scaffolder emits bodies as `raise NotImplementedError` that still **compile and type-check**, so a misplaced file or a wrong signature goes red before the implementer runs; the implementer fills bodies until the toolchain and the canonical tests are green.

- type-check: `uv run mypy src/<package>`
- lint / format: `uv run ruff check src tests` · `uv run ruff format src tests`
- **ruff lint config** (emitted into `pyproject.toml`): `[tool.ruff.lint]` `select = ["E", "F", "I", "B904"]`, plus `[tool.ruff.lint.per-file-ignores]` `"**/__init__.py" = ["F403", "F405"]`. `B904` makes a bare `raise X` inside an `except` an error: chain the cause with `raise X(...) from exc`, or deliberately suppress it with `from None` (e.g. translating a lookup-miss to an auth error without leaking the internal cause). The `__init__.py` F403/F405 ignore is the **only** sanctioned ruff suppression — never an inline `# noqa` on a content module.
- tests: `uv run pytest`
- pin a substrate / SDK package at scaffold time: `uv add <lib>` (dev: `uv add --dev <lib>`)
- migrations — **Alembic owns the chain natively; migrations are never generated** (spec §3): `uv run alembic revision --autogenerate -m "<change>"` then `uv run alembic upgrade head`. A schema-drift check (entity fields ↔ table columns) is the deterministic trigger that wakes the implementer to author the next revision.

## F. See also

- `general-imports-conventions` — relative vs absolute reach, the same-package collapse, the `from .module import *` re-export contract.
- `general-python-package` — one class per module, `__all__` placement, subpackage `__init__.py` mechanics.
