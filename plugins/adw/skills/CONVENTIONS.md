# Skill conventions

Shared vocabulary used by every skill in this directory. When a skill needs a worked example, it draws
from this vocabulary so the same names recur and a reader can carry one mental model from skill to skill.

## How to choose a skill

Most skills are **narrow** — each covers one artifact, or one set of artifacts that always arrives
together (one entity, one repository adapter, one endpoint, the four domain-model kinds). Pick the skill
whose `description` matches what is being written.

Not every skill is that shape. **Cross-cutting `pattern-` skills** span layers rather than owning one
layer's artifact; **bootstrap** skills run once per project; **reference** skills produce no file and are
consulted alongside whichever skill owns the artifact. The four shapes and how to tell them apart are in
`meta-skill-author`.

If a skill's hard stops fire, the wrong artifact was asked for — switch to the right skill rather than
stretching the current one.

## Index

### Meta

- `meta-skill-author` — produces one new `skills/<name>/SKILL.md` in the canonical format (frontmatter,
  four-section body). Use when extending this catalog.
- `meta-uc-author` — produces one new `specs/use-cases/UC-NN-<slug>.md` in the narrative BA-dictated
  style (title, actor, module, description, main flow(s), alternative flows, business rules, notes).

### Cross-cutting (apply to every layer)

- `general-typing-conventions` — `X | None`, immutable collections in domain, `Any` only at raw
  boundaries, prohibition on `from __future__ import annotations`.
- `general-imports-conventions` — relative vs absolute, the collapsed same-package import form, the
  `from .module import *` re-export contract.
- `general-python-package` — one class per module, `__all__` placement, the subpackage `__init__.py`
  mechanics every component skill defers to.
- `general-layered-architecture` — the four-layer split (domain / application / infrastructure /
  entrypoints), allowed dependency direction.
- `general-logging` — `structlog` setup, per-layer logging rules, success-only events in `application/`,
  never-log-and-re-raise.

### Domain

- `domain-entity` — mutable `@dataclass`, identity equality, `__post_init__` invariants.
- `domain-value-object` — `@dataclass(frozen=True)`, value equality, optional canonical-form escape
  hatch.
- `domain-enum` — `StrEnum` for closed sets of named values; optional pure-logic methods.
- `domain-filter` — frozen dataclass for repository list/query parameter bags; `frozenset` defaults.
- `domain-exception` — the single `domain/exceptions.py` catalog.
- `domain-repository-protocol` — `IFooRepository` protocol module; async CRUD-shaped methods.
- `domain-capability-protocol` — `ICan<Verb>` single-action protocol module.
- `domain-service` — stateless orchestrator that takes injected protocols; `assert_*` / `is_*` / verb
  methods. For rules needing cross-aggregate state or a domain capability.
- (Tunable thresholds — `max_rows`, retention days, quotas — are a **variant** of `domain-value-object`,
  not a separate skill.)

### Application

- `application-command` — frozen command DTO + handler returning `UUID | None`, success-only logging.
- `application-query` — frozen query DTO + handler + optional `*Result` DTO.

### Patterns (cross-cutting)

The `pattern-` prefix marks a skill that **spans layers** (a domain port + an infra adapter + an
application usage) rather than owning one layer's artifact.

- `pattern-compensating-tx` — the only sanctioned `try/except` in `application/`: catch → undo →
  re-raise, shaping a command handler's body when an external side-effect precedes the DB write.
- `pattern-unit-of-work` — `IUnitOfWork` protocol (domain) + SQLAlchemy implementation (infra) + the
  handler form that uses it (application), when ≥2 repositories must commit atomically.

### Infrastructure

- `infra-sqlalchemy-table` — the write-once SQLAlchemy Core `Table` (the Alembic revision is authored
  separately via `alembic revision`, never generated); constraint-naming convention.
- `infra-sqlalchemy-repository` — repository adapter satisfying a domain protocol on a **relational**
  store; `IntegrityError`-to-domain-exception translator.
- `infra-store-repository` — repository adapter for an aggregate on a **client-style** store
  (vector/cache/document: qdrant, redis, chroma, …); one vendor-agnostic skill for all of them.
  SDK-error-to-domain-exception translator at the boundary.
- `infra-capability-adapter` — adapter satisfying a domain `ICan<Verb>` capability protocol (object
  storage, HTTP gateway, token verifier, renderer); SDK-exception-to-domain-exception translator at the
  boundary.
- `infra-settings` — one `pydantic-settings.BaseSettings` per integration.
- `infra-di-provider` — wires a class into `containers.py` with the right `Singleton`/`Factory` choice
  and declaration order.

### REST API entrypoint

- `restapi-app-bootstrap` — **one-shot per project.** Creates `main.py`, `error_handler.py`,
  `dependencies.py`, `schemas/errors.py`. Attaches the DI container, lifespan, CORS and the central
  `DomainError` handler. The catalog of allowed error statuses derives from `domain.exceptions.__all__`
  — no `domain/error_catalog.py` is created or maintained.
- `restapi-endpoint` — one HTTP endpoint in a `restapi/routers/<resource>.py` file. Consumes the route's
  auth decision (`restapi-auth-dependency`) and the error codes it advertises
  (`restapi-error-responses`); owns neither.
- `restapi-schema` — Pydantic request/response models for one resource.
- `restapi-auth-dependency` — the decision rule for `get_current_user` vs `require_role(Role.X)` and the
  `_` vs `user` binding. Owns the auth choice; `restapi-endpoint` consumes it.
- `restapi-error-responses` — route-level `responses=error_responses(...)` advertisement and the rare
  middleware-code registration. Adding a `DomainError` subclass needs no registry append.
- `restapi-middleware` — one custom ASGI middleware class wrapping every route (request id, body-size
  cap, timing), wired once via `app.add_middleware(...)`.
- `restapi-file-transfer` — multipart upload and streaming download; the single sanctioned route-body
  `try/except`. A specialized variant of `restapi-endpoint`.

### Tests

- `test-principles` — **reference skill** every other `test-*` skill consults. The testing pyramid and
  per-layer speed targets, the conftest hierarchy, the fixture-vs-builder rule, when to parametrize, AAA
  structure, the no-mocks contract, naming, and the rules that keep local and CI in parity.
- `test-integration-isolation` — **one-shot per project.** `tests/integration/conftest.py` with
  session-scoped containers + engine, a function-scoped outer transaction, `sf`, and `real_app`.
  Rollback at teardown drops everything a test wrote. Every integration test depends on it.
- `test-integration-authed-client` — **one-shot per project.** `tests/integration/api/conftest.py` with
  the `authed_client` factory plus `rsa_keypair` + `jwt_settings` session fixtures, and the
  `tests/helpers/jwt.py` `sign_token(...)` helper.
- `test-discovery-invariants` — **one-shot per project.** Test files under `tests/integration/api/` that
  iterate `app.routes` and `app.openapi()` to assert global properties. Adding an endpoint never
  requires editing them.
- `test-fake-repository` — pairs with the repository adapters and the domain protocols. One in-memory
  `Fake<Aggregate>Repository` under `tests/unit/fakes/`, copying the real adapter's exception contract
  verbatim. No flags; one-off failures come from inline subclasses at the handler-test site.
- `test-application-handler` — pairs with `application-command` / `application-query` /
  `pattern-compensating-tx`. One file per handler under `tests/unit/application/`. AAA + fakes + inline
  `_RaiseXxxRepo` subclasses for one-off failure injection.
- `test-domain-entity` — pairs with `domain-entity`. Identity-equality block,
  `_make_<entity>(**overrides)` builder, one `test_*` per `__post_init__` invariant.
- `test-domain-value-object` — pairs with `domain-value-object`. Canonical-equality and invariant tests;
  skip the file entirely when the VO has no `__post_init__` and no custom `__eq__`.
- `test-domain-enum` — pairs with `domain-enum`. Pins every member's value, asserts unknown-value
  rejection, covers pure-logic methods.
- `test-domain-service` — pairs with `domain-service`. The orchestrator flavour uses a minimal inline
  protocol stub; the pure-logic flavour constructs once at module scope and requires `test_idempotent`
  for canonicalizers.
- `test-repository-contract` — pairs with `infra-sqlalchemy-repository`. One file per repository under
  `tests/integration/postgres/`; consumes `sf`. CRUD round-trip, every UNIQUE on insert AND update with
  `context["constraint"]` assertions, `updated_at` advance, cascades, `get_by_*` found and not-found,
  pagination and sort.
- `test-store-repository-contract` — pairs with `infra-store-repository`. One file per repository under
  `tests/integration/<store-kind>/`; a real store via testcontainers, isolated by a per-test namespace
  (collection or key prefix) rather than transaction rollback. CRUD plus the store's non-CRUD verbs,
  entity↔record mapping round-trip, and SDK-error → `UpstreamError`/`NotFoundError` translation.
- `test-infra-capability-adapter` — pairs with `infra-capability-adapter`. One file per adapter; three
  flavours — containerized (S3/MinIO/Redis), `respx` over real `httpx` for HTTP gateways, and pure-CPU
  verifier/renderer under `tests/unit/`. Asserts `context` keys on every translated `DomainError` to pin
  the SDK-exception map row by row.
- `test-restapi-endpoint` — pairs with `restapi-endpoint`. One self-contained file per endpoint under
  `tests/integration/api/<resource>/`; consumes `real_app` + `authed_client`. Pydantic-validated 2xx
  bodies, exact counts, cross-org returns 404 rather than 403, per-resource fixtures in the sibling
  `conftest.py`.
- `test-architecture-rule` — adds one grep-firewall function to `tests/unit/test_architecture.py`.

## Placeholder vocabulary

`Foo` is the primary aggregate, `Bar` the secondary. Derived names follow mechanically — the exhaustive
derivation registry (path and class derivation, store profiles, the library substrate) lives in the
[`conventions`](conventions/SKILL.md) reference skill; the examples here only anchor the shared
vocabulary:

- Module: `foo.py`, `bar.py`
- Subdomain package: `domain/foos/`, `application/foos/`,
  `infrastructure/postgres/repositories/foo_repository.py` (infrastructure groups by tech)
- Table: `foos_table`, file `infrastructure/postgres/tables/foos.py`
- Protocol: `IFooRepository` in `i_foo_repository.py`; capability `ICan<Verb>` in `i_can_<verb>.py`
- Commands / queries: `CreateFooCommand`, `ListFoosQuery`, `CreateFooHandler`, `ListFoosResult`
- REST schemas: `FooResponse`, `FooListResponse`, `FooCreateRequest`, `FooUpdateRequest`
- REST router: `restapi/routers/foos.py`, prefix `/foos`

## Project root package

Examples use `myapp` as the project's root Python package (e.g.
`from myapp.domain.foos import IFooRepository`). Substitute the real root package name when adopting
these skills in a project.

## Skill format

The authoritative format — frontmatter fields, their budget, the four-section body, and the four skill
shapes — lives in `meta-skill-author`. In one breath: `name` + `description` (+ `when_to_use`, +
`paths` when the skill is scoped to part of the tree), then a body of

1. **When to use vs. neighbours** — disambiguates this skill from those covering adjacent artifacts, and
   carries the negative routing the description deliberately leaves out.
2. **Template(s)** — literal file content with placeholders, not prose.
3. **Rules** — only what applies when writing *this* artifact. Cross-cutting concerns are referenced,
   not restated, except for a brief inlined slice when load-bearing.
4. **Hard stops** — explicit cases where the reader must stop and switch skills.

Two optional helper sections (`Inlined typing / import rules`, `Package wiring`) appear only when
load-bearing. A skill carries **no** section describing who invokes it or what it hands back — that is a
layer outside the skill.

## Out of scope (intentionally not in this catalog)

- Process-only skills (brainstorming, retrospective notes). If reintroduced they belong under a separate
  prefix, e.g. `process-brainstorm`.

## Read models — guidance for a future skill

The catalog deliberately does **not** split repositories into write-side and read-side protocols. The
CQRS guarantee that matters — commands mutate, queries read — is carried by the handler split
(`application-command` vs `application-query`); partitioning every `IFooRepository` into read and write
halves would double the protocol, DI and test surface across all aggregates for a benefit that only
materializes with event sourcing, async projections, or a separate read store, none of which apply here
today.

Add a read-model skill the first time a query handler genuinely needs a denormalized, join-flattened DTO
that is not "an aggregate read" — for example foos with author name, tag count and last-modified-by name
joining three tables. Model it as an additive component with its own protocol, adapter and flat DTO, not
as a partition of the existing repository. Until that case appears, the unified `IFooRepository` with
both reads and writes is the canonical shape.
