# Skill conventions

Shared vocabulary used by every skill in this directory. When a skill needs a worked example, it draws
from this vocabulary so the same names recur and a reader can carry one mental model from skill to skill.

## How to choose a skill

Most skills are **narrow** — each covers one artifact, or one set of artifacts that always arrives
together (one endpoint, one repository adapter, the four domain-model kinds). Pick the skill whose
`description` matches what is being written.

Not every skill is that shape. `patterns` spans layers rather than owning one layer's artifact; a few
skills run once per project; and **reference** skills produce no file at all and are consulted alongside
whichever skill owns the artifact. The four shapes and how to tell them apart are in `meta-skill-author`.

If a skill's hard stops fire, the wrong artifact was asked for — switch to the right skill rather than
stretching the current one.

## Index

Thirty skills. A skill covering several artifact kinds says so.

### Reference and meta — produce no target-app file

- `conventions` — the derivation registry: identifier → file path and class name, the store profiles, the
  library substrate, the Alembic bootstrap, multi-context resolution.
- `architecture` — where code lives and how it imports: the four-layer split and its dependency
  direction, package mechanics (one class per module, `__all__`, the `__init__.py` re-export contract),
  and the import conventions that contract underwrites.
- `python-style` — typing conventions and logging rules for every layer.
- `test-principles` — the testing constitution every test skill consults: the pyramid, per-layer speed
  targets, the conftest hierarchy, fixture-vs-builder, the no-mocks contract.
- `meta-skill-author` — adds a new skill to this catalog in the canonical format.
- `meta-uc-author` — adds a use case to `specs/use-cases/` in the narrative BA style.

### Domain

- `domain-model` — the four data shapes: entity (mutable, identity equality), value object (frozen, value
  equality, plus the tunable-threshold variant), enum (`StrEnum`), filter record (frozen parameter bag).
- `domain-ports` — the two protocols infrastructure satisfies structurally: `IFooRepository` for an
  aggregate's data access, `ICan<Verb>` for a single external action.
- `domain-service` — a stateless class for a rule needing cross-aggregate state or a domain capability;
  `assert_*` / `is_*` / verb methods over injected protocols.
- `domain-exception` — the single `domain/exceptions.py` catalog.

### Application

- `application` — the CQRS pair: a command (frozen DTO plus a handler returning `UUID | None`,
  success-only logging) and a query (frozen DTO, handler, and a `*Result` DTO when the read returns more
  than one entity). Also the read-model rule that decides a query's return type.
- `patterns` — the two cross-layer patterns a command may need: the compensating transaction
  (catch → undo → re-raise) and the unit of work (one atomic commit across two or more repositories).
  They nest, compensation outside.

### Infrastructure

- `infra-persistence` — relational persistence on SQLAlchemy Core: the `Table`, the repository adapter
  with its row-to-entity mapper and `IntegrityError` translator, and the Alembic revision that pairs with
  a schema change. The constraint names are one contract across all three.
- `infra-store-repository` — the repository adapter for a client-style store (vector, cache, document —
  qdrant, redis, chroma). One vendor-agnostic skill, with SDK-error translation at the boundary.
- `infra-capability-adapter` — the `ICan<Verb>` implementation wrapping an SDK (boto3, httpx, PyJWT,
  openai), with SDK-exception translation at the boundary.
- `infra-wiring` — how configuration enters and how objects are bound: a `pydantic-settings` class per
  integration, and the single `Container` in `containers.py` with its `Singleton`-vs-`Factory` rule and
  declaration order.

### REST API entrypoint

- `restapi-app` — the app shell (`main.py`, `error_handler.py`, `schemas/errors.py`, and
  `dependencies.py` when the app has auth) plus the raw ASGI middleware classes that wrap it.
- `restapi-endpoint` — one thin HTTP endpoint in `restapi/routers/<resource>.py`.
- `restapi-schema` — the Pydantic request and response models for one resource.
- `restapi-route-contracts` — the two contracts a route declares: which auth dependency it attaches, and
  which error codes it advertises. The second follows from the first.
- `restapi-file-transfer` — multipart upload and streaming download, and the single sanctioned
  route-body `try/except`.

### Tests

- `testing-unit-domain` — the domain layer's unit tests: entity, value object, enum and service. No IO,
  no mocks, no fixtures.
- `test-application-handler` — one handler's unit test: AAA, an in-memory fake, inline `_RaiseXxxRepo`
  subclasses for one-off failure injection.
- `test-fake-repository` — the in-memory `Fake<Aggregate>Repository` under `tests/unit/fakes/`, copying
  the real adapter's exception contract verbatim.
- `test-architecture-rule` — one grep-firewall invariant in `tests/unit/test_architecture.py`.
- `testing-integration-setup` — **one-shot.** Both integration conftests: the containers, the engine and
  the rollback `sf`, plus the `authed_client` factory and its JWT fixtures.
- `testing-contract` — one repository adapter's integration test against the real backend, relational
  (rollback, `context["constraint"]` pinned) or client-style (namespace isolation, SDK-error
  translation).
- `test-infra-capability-adapter` — one capability adapter's test in three flavours: containerized,
  `respx` over real `httpx`, or pure-CPU.
- `test-restapi-endpoint` — one endpoint's integration test over the real app via ASGI.
- `test-discovery-invariants` — **one-shot.** The cross-cutting tests that derive their inputs from the
  running app, so adding an endpoint never edits them.

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
(a command mutates, a query reads); partitioning every `IFooRepository` into read and write
halves would double the protocol, DI and test surface across all aggregates for a benefit that only
materializes with event sourcing, async projections, or a separate read store, none of which apply here
today.

Add a read-model skill the first time a query handler genuinely needs a denormalized, join-flattened DTO
that is not "an aggregate read" — for example foos with author name, tag count and last-modified-by name
joining three tables. Model it as an additive component with its own protocol, adapter and flat DTO, not
as a partition of the existing repository. Until that case appears, the unified `IFooRepository` with
both reads and writes is the canonical shape.
