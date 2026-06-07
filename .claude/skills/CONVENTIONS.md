# Skill conventions

Shared vocabulary used by every skill in this directory. When a skill needs a worked example, it draws from this vocabulary so the same names recur and the reader can carry a mental model from one skill to the next.

## How to choose a skill

**Producer** skills are **component-narrow** — each produces exactly one kind of artifact (one entity file, one repository module, one endpoint, …). Pick the producer whose `description` line matches what the spec asks the agent to produce. A single feature usually invokes several skills in sequence; sequencing is the runner's concern, not the skill's.

Producers are not the only category. **Companion / cross-cutting `pattern-` skills** (which span layers or wrap a producer's work), **bootstrap** skills (run once, triggered by the working tree), and **reference** skills (always consulted, never dispatched) are the deliberate exceptions to component-narrowness — see the full taxonomy in the `conventions` reference skill (registry B). A `pattern-` skill claims no single layer precisely because it touches several.

If a skill's hard-stops fire, it means the spec asked for the wrong artifact — switch to the right skill rather than stretching the current one.

## Index

### Meta

- `meta-skill-author` — produces one new `.claude/skills/<name>/SKILL.md` in the canonical format (frontmatter, four-section body). Use when extending this catalog.
- `meta-uc-author` — produces one new `specs/use-cases/UC-NN-<slug>.md` in the narrative BA-dictated style (title, actor, module, description, main flow(s), alternative flows, business rules, notes). Use when seeding a new use case for the agentic workflow.

### Cross-cutting (apply to every layer)

- `general-typing-conventions` — `X | None`, immutable collections in domain, `Any` only at raw boundaries, prohibition on `from __future__ import annotations`.
- `general-imports-conventions` — relative vs absolute, the collapsed same-package import form, the `from .module import *` re-export contract.
- `general-python-package` — one class per module, `__all__` placement, the subpackage `__init__.py` mechanics every component skill defers to.
- `general-layered-architecture` — the four-layer split (domain / application / infrastructure / entrypoints), allowed dependency direction.
- `general-logging` — `structlog` setup, per-layer logging rules, success-only events in `application/`, never-log-and-re-raise.

### Domain

- `domain-entity` — mutable `@dataclass`, identity equality, `__post_init__` invariants.
- `domain-value-object` — `@dataclass(frozen=True)`, value equality, optional canonical-form escape hatch.
- `domain-enum` — `StrEnum` for closed sets of named values; optional pure-logic methods.
- `domain-filter` — frozen dataclass for repository list/query parameter bags; `frozenset` defaults.
- `domain-exception` — append one class to the single `domain/exceptions.py` source-of-truth file.
- `domain-repository-protocol` — `IFooRepository` protocol module; async CRUD-shaped methods.
- `domain-capability-protocol` — `ICan<Verb>` single-action protocol module.
- `domain-service` — stateless orchestrator (DDD domain service) that takes injected protocols; `assert_*` / `is_*` / verb methods. Use for rules that need cross-aggregate state or a domain capability.
- (Tunable thresholds — `max_rows`, retention days, quotas — are documented as a **variant** of `domain-value-object`, not a separate skill.)

### Application

- `application-command` — frozen command DTO + handler returning `UUID | None`, success-only logging.
- `application-query` — frozen query DTO + handler + optional `*Result` DTO.

### Patterns (cross-cutting)

The `pattern-` prefix marks a skill that **spans layers** (a domain port + an infra adapter + an application usage) rather than producing one layer's artifact.

- `pattern-compensating-tx` — the only sanctioned `try/except` in `application/`: catch → undo → re-raise, shaping a command handler's body when an external side-effect precedes the DB write.
- `pattern-unit-of-work` — `IUnitOfWork` protocol (domain) + SQLAlchemy implementation (infra) + the handler form that uses it (application), when ≥2 repositories must commit atomically.

(How each pattern is keyed to a producer's work — and the deferred unit-of-work manifest signal — lives in the `conventions` reference skill's registry B, not here.)

### Infrastructure

- `infra-sqlalchemy-table` — the write-once SQLAlchemy Core `Table` scaffold (the Alembic revision is authored separately via `alembic revision`, not generated); constraint-naming convention.
- `infra-sqlalchemy-repository` — repository adapter satisfying a domain protocol; `IntegrityError`-to-domain-exception translator.
- `infra-capability-adapter` — adapter satisfying a domain `ICan<Verb>` capability protocol (object storage, HTTP gateway, token verifier, renderer); SDK-exception-to-domain-exception translator at the boundary.
- `infra-settings` — one `pydantic-settings.BaseSettings` per integration.
- `infra-di-provider` — wires a class into `containers.py` with the right `Singleton`/`Factory` choice and declaration order.

### REST API entrypoint

- `restapi-app-bootstrap` — **one-shot per project.** Creates `main.py`, `error_handler.py`, `dependencies.py`, `schemas/errors.py`. Attaches the DI container, lifespan, CORS, max-request-size middleware, and the central `DomainError` handler. The catalog of allowed error statuses derives dynamically from `domain.exceptions.__all__` — no `domain/error_catalog.py` is created or maintained.
- `restapi-endpoint` — one HTTP endpoint in a `restapi/routers/<resource>.py` file. Consumes `auth_mode` and `error_codes` decisions; does not own them.
- `restapi-schema` — Pydantic Request/Response models for one resource.
- `restapi-auth-dependency` — decision rule for `get_current_user` vs `require_role(Role.X)` and the `_` vs `user` binding. Owns the auth choice; `restapi-endpoint` consumes it.
- `restapi-error-responses` — route-level `responses=error_responses(...)` advertisement and the rare middleware-code registration. Adding a `DomainError` subclass needs no registry append — the catalog is dynamic.
- `restapi-file-transfer` — multipart upload and streaming download patterns; the single sanctioned route-body `try/except`. Specialized variant of `restapi-endpoint`.

### Tests

- `test-principles` — **reference skill** every other `test-*` skill consults. Documents the testing pyramid + per-layer speed targets, the conftest hierarchy (which fixtures live where), the fixture-vs-builder rule, when to parametrize, AAA structure, the no-mocks contract, naming conventions, and the reliability rules that produce local-vs-CI parity.
- `test-integration-isolation` — **one-shot per project.** Produces `tests/integration/conftest.py` with session-scoped containers + engine, function-scoped outer transaction, `sf`, and `real_app` (with DI overrides for `session_factory`, `db_settings`, `storage_settings`, `jwt_settings`). Rollback at teardown drops everything the test wrote. Load-bearing — every integration test depends on it.
- `test-integration-authed-client` — **one-shot per project.** Produces `tests/integration/api/conftest.py` with the `authed_client` factory plus `rsa_keypair` + `jwt_settings` session fixtures (the latter consumed by `real_app`) and the `tests/helpers/jwt.py` `sign_token(...)` helper.
- `test-discovery-invariants` — **one-shot per project.** Five test files under `tests/integration/api/` that iterate `app.routes` and `app.openapi()` to assert global properties. Adding an endpoint never requires editing these.
- `test-fake-repository` — pairs with `infra-sqlalchemy-repository` (and with `domain-repository-protocol` / `domain-capability-protocol`). Produces one in-memory `Fake<Aggregate>Repository` under `tests/unit/fakes/`, copying the real adapter's exception contract verbatim. No flags; one-off failures come from inline subclasses at the handler-test site.
- `test-application-handler` — pairs with `application-command` / `application-query` / `pattern-compensating-tx`. One file per handler under `tests/unit/application/`. AAA + fakes + inline `_RaiseXxxRepo` subclasses for one-off failure injection, including the compensating-tx "DB-fails-after-upload" assertion.
- `test-domain-entity` — pairs with `domain-entity`. Identity-equality block, `_make_<entity>(**overrides)` builder, one `test_*` per `__post_init__` invariant.
- `test-domain-value-object` — pairs with `domain-value-object`. Canonical-equality + invariant tests; skip the file entirely when the VO has no `__post_init__` and no custom `__eq__`.
- `test-domain-enum` — pairs with `domain-enum`. Pins every member's value, asserts unknown-value rejection, covers pure-logic methods.
- `test-domain-service` — pairs with `domain-service`. Orchestrator flavor uses a minimal inline-class protocol stub; pure-logic flavor constructs once at module scope and requires `test_idempotent` for canonicalizers.
- `test-repository-contract` — pairs with `infra-sqlalchemy-repository`. One file per repository under `tests/integration/postgres/`; consumes `sf`. CRUD round-trip, every UNIQUE on insert AND update with `context["constraint"]` assertions, `updated_at` advance, cascades, `get_by_*` found/not-found, pagination + sort.
- `test-infra-capability-adapter` — pairs with `infra-capability-adapter`. One file per adapter; three flavors — containerized (S3/MinIO/Redis under `tests/integration/<adapter>/`), `respx` over real `httpx` for HTTP gateways (also integration), pure-CPU verifier/renderer (`tests/unit/infrastructure/<adapter>/`). Asserts `context` keys on every translated `DomainError` to pin the SDK-exception map row-by-row.
- `test-restapi-endpoint` — pairs with `restapi-endpoint`. One self-contained file per endpoint under `tests/integration/api/<resource>/`; consumes `real_app` + `authed_client`. Pydantic-validated 2xx bodies, exact counts (rollback isolation), cross-org returns 404 (not 403), per-resource fixtures live in the sibling `conftest.py`.
- `test-architecture-rule` — adds one grep-firewall function to `tests/unit/test_architecture.py`.

## Placeholder aggregates

| Role | Name | snake_case | plural | Use for |

Derived names follow mechanically (the authoritative, exhaustive derivation registry — kind→path/class/suffix, store profiles, the kind→skill map, the stack substrate — lives in the [`conventions`](conventions/SKILL.md) reference skill; these examples only anchor the shared vocabulary):

- Module: `foo.py`, `bar.py`
- Subdomain package: `domain/foos/`, `application/foos/`, `infrastructure/postgres/repositories/foo_repository.py` (infra groups by tech)
- Table: `foos_table`, file `infrastructure/postgres/tables/foos.py`
- Protocol: `IFooRepository` in `i_foo_repository.py`; capability `ICan<Verb>` in `i_can_<verb>.py`
- Commands / queries: `CreateFooCommand`, `ListFoosQuery`, `CreateFooHandler`, `ListFoosResult`
- REST schemas: `FooResponse`, `FooListResponse`, `FooCreateRequest`, `FooUpdateRequest`
- REST router: `restapi/routers/foos.py`, prefix `/foos`

## Project root package

Examples use `myapp` as the project's root Python package (e.g. `from myapp.domain.foos import IFooRepository`). Substitute your real root package name when adopting these skills in a new project.

## Skill format

Every skill has the standard `name:` + `description:` frontmatter only — no custom fields. The body follows the same four-section structure so an agent (or reader) knows where to look:

1. **When to use vs. neighbours** — disambiguates the skill from skills that produce adjacent artifacts.
2. **Template(s)** — literal file content with placeholders, not prose.
3. **Rules** — only the rules that apply when *writing this artifact*. Cross-cutting concerns (typing, imports) are referenced, not restated, except for a brief inlined slice when it's load-bearing.
4. **Hard stops** — explicit cases where the agent must stop and switch to a different skill.

Two optional helper sections (`Inlined typing / import rules`, `Package wiring`) appear only when load-bearing. A skill carries **no** orchestration section (what it returns, who invokes it) and **no** manifest-input table — those layers belong to the runner and the manifest schema, not to the skill.

## Out of scope (intentionally not in this catalog)

- The agent roles (analyst, architect, implementer) live separately under `.claude/agents/`. Skills describe *artifacts*; agents describe *processes*.
- Process-only skills (e.g. brainstorming, retrospective notes) are not part of this catalog. If reintroduced, they belong in a separate prefix (e.g. `process-brainstorm`).

## Read models — guidance for a future skill

The catalog deliberately does **not** split repositories into write-side and read-side protocols. The CQRS guarantee that matters (commands mutate, queries read) is enforced by the handler split (`application-command` vs `application-query`); partitioning every `IFooRepository` into read/write halves would double the protocol/DI/test surface across all aggregates for a benefit that only materializes with event sourcing, async projections, or a separate read store — none of which apply here today.

Add a new `infra-read-model` skill the first time a query handler genuinely needs a denormalized/join-flattened DTO that is not "an aggregate read" (e.g. "foos with author name + tag count + last_modified_by name" joining three tables). Model it as an additive component (its own protocol, its own adapter, its own flat DTO), not as a partition of the existing repository. Until that use case appears, the unified `IFooRepository` with both reads and writes is the canonical shape.
