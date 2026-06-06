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
| `infrastructure.settings[*]` | `name: OpenaiSettings` | `OpenaiSettings` | `infrastructure/openai/openai_settings.py` — subpackage = the consuming tech (see below); one class per module |
| `infrastructure.repositories[*]` | `implements: IUserRepository`, `backs: User`, `store: main` | `UserRepository` | `infrastructure/<store-kind>/repositories/user_repository.py` (+ a write-once Table SCAFFOLD at `infrastructure/<store-kind>/tables/users.py` for a relational store) |
| `infrastructure.capabilities[*]` | `implements: ICanEmbedText`, `adapter: openai`, `role: TextEmbedder` | `OpenaiTextEmbedder` | `infrastructure/openai/openai_text_embedder.py` |
| `restapi.schemas[*]` | `name: LoginRequest`, `resource: auth` | `LoginRequest` | grouped into `restapi/schemas/auth.py` |
| `restapi.endpoints[*]` | `method`, `path`, `resource: auth` | endpoint function (name from method+path) | grouped into `restapi/routers/auth.py` |

**Application subdomain is derived, not declared.** Commands and queries carry no `subdomain` field. The subdomain is the subdomain of the first `handler.dependencies` entry that names a `repository_protocol` (a repository protocol carries its own `subdomain`); when the handler has no repository dependency, fall back to the first domain entity's subdomain. So `CreateTicket` with `handler.dependencies: [ITicketRepository]` (whose protocol is `subdomain: support`) lands in `application/support/`.

**Infrastructure groups by external TECH, never by a domain subdomain and never under a catch-all `db/`** (spec §3; CLAUDE.md "grouped by external tech"). The tech token is:
- a repository's **store kind** — the `kind` of the `datastore` its `store` names; absent `store` ⇒ the implicit single `postgres` store. Relational repos, their write-once table scaffold, and the shared SQLAlchemy engine/`session_factory`/`metadata.py` bootstrap all sit under `infrastructure/postgres/` (`repositories/`, `tables/`).
- a non-bootstrap datastore's **`kind`** — `infrastructure/qdrant/`, `infrastructure/redis/`, holding `connection.py` (the `create_<name>_client` scaffold) and its settings.
- a capability adapter's **`adapter`** token — `infrastructure/openai/`, `infrastructure/jwt/`.
- a settings node's **consuming tech** — the `adapter` of the capability that names it, or the `kind` of the datastore that names it; an orphan settings falls back to its own snake name.

**Capability adapter class** = `<AdapterPascal><Suffix>`, where `Suffix` is the capability's `role` agent-noun when present (`adapter: jwt`, `role: TokenManager` → `JwtTokenManager`) and otherwise the protocol name minus its `ICan` prefix (`adapter: jwt`, `implements: ICanManageTokens`, no role → `JwtManageTokens`). The `role` is carried in the manifest precisely because the agent-noun is not mechanically derivable from the verb (the `log_event` precedent).

**Imports and package mechanics are not restated here** — see block F. Imports are graph edges in Python syntax (a referenced type resolves to its owning module): same-subdomain domain types use a relative `.module` import, cross-subdomain a relative `..subdomain`, cross-layer an absolute `<package>.domain.<subdomain>` import, stdlib its canonical import, builtins none. `general-imports-conventions` owns the rules; `general-python-package` owns `__all__` + the `from .module import *` re-export contract that the collapsed import form depends on.

## B. kind→skill registry

**Producer skills — the deterministic dispatch** (one skill per manifest artifact kind). This table is mirrored as data in the validator's `KIND_TO_SKILL` (the way `SCHEMAS` mirrors MANIFEST_SCHEMA.md) and is the source the §16 coverage gate reads. Choosing the skill for a node is a deterministic lookup, **not** an agent judgment (spec §2).

| Artifact kind | Producer skill |
|---|---|
| `domain.enums` | `domain-enum` |
| `domain.value_objects` | `domain-value-object` |
| `domain.entities` | `domain-entity` |
| `domain.services` | `domain-service` (the `kind: orchestrator | pure` axis is handled inside the skill) |
| `domain.filters` | `domain-filter` |
| `domain.repository_protocols` | `domain-repository-protocol` |
| `domain.capability_protocols` | `domain-capability-protocol` |
| `domain.exceptions` | `domain-exception` |
| `application.commands` | `application-command` |
| `application.queries` | `application-query` |
| `infrastructure.repositories` | `infra-sqlalchemy-repository` (relational) — see the non-relational note below |
| `infrastructure.settings` | `infra-settings` |
| `infrastructure.capabilities` | `infra-capability-adapter` |
| `restapi.schemas` | `restapi-schema` (the `kind: request | response` axis is handled inside the skill) |
| `restapi.endpoints` | `restapi-endpoint` |
| `tests.architecture_rules` | `test-architecture-rule` |

- `infrastructure.datastores` has **no producer skill** — a datastore is wired from its **store profile** (block C), not a per-kind skill, and an unknown `kind` degrades gracefully rather than tripping the gate. It is the one artifact kind exempt from the coverage gate.
- **Non-relational repositories.** The producer table maps `infrastructure.repositories` to `infra-sqlalchemy-repository` (SQLAlchemy Core) — correct for a relational store. A repository on a non-bootstrap store (qdrant/redis) is a store-profile-driven scaffold with **no dedicated skill yet**; the first one built is a §16 coverage-gap to close by authoring the missing `infra-<kind>-repository` skill, at which point this dispatch becomes store-kind-aware.

**Companion skills** — conditionally applied to a producer's artifact, not separately dispatched: `application-compensating-tx` (a command with an external side-effect before its DB write), `restapi-error-responses` (every endpoint advertises its error codes), `restapi-file-transfer` (multipart upload / streaming download), `restapi-auth-dependency` (reference — picks the route's auth dependency).

**Test skills** — derived per artifact (tests are derived, not enumerated; MANIFEST_SCHEMA core principle 3), not from a manifest field: `test-domain-entity` ← entities, `test-domain-enum` ← enums, `test-domain-value-object` ← VOs, `test-domain-service` ← services, `test-application-handler` ← commands/queries, `test-fake-repository` ← per aggregate/capability a handler test needs, `test-repository-contract` ← repositories, `test-infra-capability-adapter` ← capabilities, `test-restapi-endpoint` ← endpoints.

**Bootstrap skills** — run once, triggered by the working tree (not a manifest node; MANIFEST_SCHEMA core principle 4): `restapi-app-bootstrap`, `domain-exception` (first creation of `domain/exceptions.py`), `test-integration-isolation`, `test-integration-authed-client`, `test-discovery-invariants`.

**Reference / cross-cutting skills** — always consulted, never dispatched per node: `general-typing-conventions`, `general-imports-conventions`, `general-python-package`, `general-layered-architecture`, `general-logging`, `test-principles`.

**Meta skills** — extend the pipeline itself, not the target app: `meta-skill-author` (drafts a new skill when the gate reports a presence-gap — human-reviewed, §16), `meta-uc-author`.

## C. Store profiles

A datastore's `kind` is a free token (not a closed enum — a fixed list is the same disease as a fixed type map). The profile maps a `kind` to the few things the scaffolder needs to wire a repository **without** knowing the backend's SQL/SDK internals (those live in the scaffolded bodies the implementer fills):

| `kind` | resource param / attr | resource type | resource import | method contract | `uses_bootstrap` |
|---|---|---|---|---|---|
| `postgres` | `session_factory` / `sf` | `async_sessionmaker[AsyncSession]` | `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker` | `sql` | **yes** |
| `qdrant` | `client` / `client` | `QdrantClient` | `from qdrant_client import QdrantClient` | `collection` | no |
| `redis` | `client` / `client` | `Redis` | `from redis.asyncio import Redis` | `generic` | no |
| *(unknown)* | `client` / `client` | `object` | — | `generic` | no |

- `uses_bootstrap: yes` → the repository reuses the shared SQLAlchemy engine + `session_factory` bootstrap under `infrastructure/postgres/` (postgres is the only profile with the flag today). `no` → the scaffolder lays a write-once `create_<store>_client(settings)` connection factory in `infrastructure/<kind>/connection.py` that the DI container injects as a `Singleton` into every repository on that store.
- The `method contract` (`sql` / `collection` / `generic`) only sets the **wording** of the repository scaffold's contract-comment.
- An **unknown** kind degrades to a generic untyped `object` client plus a loud contract comment — the fail-loud-not-crash invariant that the table scaffold also follows. Adding a backend is **one row here**, never a tooling change.

## D. Stack substrate (library NAMES, no versions)

The dependency manifest (`pyproject.toml`) is regenerated glue: the framework substrate ∪ the union of every infra node's `requires_packages` over the graph (spec §10). The scaffolder derives it from the graph; it is never "an agent recalling a package".

- **Framework substrate** (the FastAPI-hexagon stack, always present): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `dependency-injector`, `structlog`.
- **Relational bootstrap** (added only when a `uses_bootstrap` store backs a repository): `sqlalchemy[asyncio]`, `asyncpg`, `alembic`.
- **Dev**: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `testcontainers`, `httpx`.
- **SDK packages are not listed here** — each rides on the infra node that needs it (`datastore` / `capability` `requires_packages`, e.g. `qdrant-client`, `openai`, `pyjwt`) and is unioned in from the graph.

**No versions.** This list carries names only; `uv add <lib>` pins the latest compatible version at scaffold time, so nothing rots. A pinned `>=` here would reintroduce the generator's chief disease (baked-in `fastapi>=0.115` under eternal manual bump).

## E. Toolchain commands (the verification loop)

Determinism in the redesign lives in verification, not authoring (spec §0 principle 3, §12). The scaffolder emits bodies as `raise NotImplementedError` that still **compile and type-check**, so a misplaced file or a wrong signature goes red before the implementer runs; the implementer fills bodies until the toolchain and the canonical tests are green.

- type-check: `uv run mypy src/<package>`
- lint / format: `uv run ruff check src tests` · `uv run ruff format src tests`
- tests: `uv run pytest`
- pin a substrate / SDK package at scaffold time: `uv add <lib>` (dev: `uv add --dev <lib>`)
- migrations — **Alembic owns the chain natively; migrations are never generated** (spec §3): `uv run alembic revision --autogenerate -m "<change>"` then `uv run alembic upgrade head`. A schema-drift check (entity fields ↔ table columns) is the deterministic trigger that wakes the implementer to author the next revision.

## F. See also

- `general-imports-conventions` — relative vs absolute reach, the same-package collapse, the `from .module import *` re-export contract.
- `general-python-package` — one class per module, `__all__` placement, subpackage `__init__.py` mechanics.
