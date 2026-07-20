# Skill conventions

Shared vocabulary used by every skill in this directory. When a skill needs a worked example, it draws from this vocabulary so the same names recur and the reader can carry a mental model from one skill to the next.

## How to choose a skill

Each skill is **theme-narrow**: it covers one coherent theme an agent can pick by its `description` / `when_to_use` frontmatter (`domain-model`, `restapi`, `testing-unit`, …). A theme may span several closely-related artifacts, each carried as its own `## …` section that keeps the four-section shape. A single feature usually invokes several skills; which ones auto-load is decided by their `description` / `when_to_use`, not by this index.

If a skill's hard stops fire, it means the task asked for the wrong artifact — switch to the right skill rather than stretching the current one.

Two skills are **reference** skills (consulted, never producing a file): `conventions` (the mechanical derivation registry) and `test-principles` (the catalog's paid-fixes guard). Toolchain commands and the definition of "green" live in `gate.py`, which `conventions` cites.

## Index

### Reference

- `conventions` — the mechanical derivation registry: identifier → file path / class name, store profiles, the stack substrate (names, no versions), the relational/Alembic bootstrap, and multi-context resolution. Cites `gate.py` for the toolchain.
- `test-principles` — the catalog's paid-fixes guard (`.claude/tools/test_skill_catalog.py`) that greps the whole catalog for every hard-won lesson by content signature, and the append-only protocol for extending it.

### Meta

- `meta-skill-author` — produces one new `.claude/skills/<name>/SKILL.md` in the canonical format (`name` + `description` + `when_to_use` frontmatter, four-section body). Use when extending this catalog.
- `meta-uc-author` — produces one new `specs/use-cases/UC-NN-<slug>.md` in the narrative BA-dictated style. Use when hand-authoring a new use case.

### Architecture & style

- `architecture` — the four-layer split (domain / application / infrastructure / entrypoints) and allowed inward dependency direction; Python package mechanics (one class per module, `__all__`, the `from .module import *` re-export contract); and import conventions (relative vs absolute, the collapsed same-package form, importing a re-exported name from its immediate parent, never a grandparent).
- `python-style` — cross-cutting typing (`X | None`, immutable collections in the domain, `Any` only at raw boundaries, the ban on `from __future__ import annotations`) and logging (`structlog` setup, per-layer rules, success-only events in `application/`, never log-and-re-raise).

### Domain

- `domain-model` — entities (mutable `@dataclass`, identity equality, `__post_init__` invariants), value objects (frozen, value equality, tunable-threshold variant), enums (`StrEnum`), filter records (frozen parameter bags), and the single `domain/exceptions.py` catalog.
- `domain-ports` — repository protocols (`IFooRepository`), capability protocols (`ICan<Verb>`), and stateless domain services that orchestrate injected protocols.

### Application

- `application` — command handlers (frozen command DTO + handler returning `UUID | None`, success-only logging), query handlers (query DTO + optional `*Result` DTO), the compensating-transaction pattern (the sanctioned try/except), and the unit-of-work pattern (atomic commit across ≥2 repositories).

### Infrastructure

- `infra-persistence` — relational repositories on SQLAlchemy Core (never the ORM) with an `IntegrityError`-to-domain-exception translator, the write-once `Table` scaffold, client-style store repositories (vector/cache/document), and the implementer-owned Alembic revision discipline.
- `infra-integration` — capability adapters wrapping SDKs (with an SDK-exception-to-domain-exception translator), `pydantic-settings` classes (env prefix stems on the product), and `dependency-injector` container wiring.

### REST API

- `restapi` — the one-shot app bootstrap shell, thin endpoints in routers, Pydantic request/response schemas, the auth-dependency decision (`get_current_user` vs `require_role`), route-level error advertisement, multipart upload / streaming download, and custom middleware ordering.

### Tests

- `testing-unit` — fast no-IO unit tests (domain, application handler with in-memory fakes, the fake-repository pattern, the seven assert-strength recipes, the `@pytest.mark.ac` marker, the grep-firewall architecture rule) plus the unit-tier constitution (pyramid, fixture-vs-builder, AAA, no-mocks, naming).
- `testing-integration` — real-backend tests via testcontainers (repository contract, REST endpoint, discovery invariants, capability adapters) plus the integration-tier constitution (conftest hierarchy, fixture scope, reliability rules) and the Docker-absence skip rule.

## Placeholder aggregates

| Role | Name | snake_case | plural | Use for |

Derived names follow mechanically (the authoritative, exhaustive derivation registry — path/class/suffix, store profiles, the stack substrate — lives in the [`conventions`](conventions/SKILL.md) reference skill; these examples only anchor the shared vocabulary):

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

Every skill has `name` + `description` + `when_to_use` frontmatter — no other custom fields. `description` + `when_to_use` are the two fields the runtime lists for auto-invocation, so they stay ≤1536 characters combined. The body follows the four-section structure so an agent (or reader) knows where to look:

1. **When to use vs. neighbours** — disambiguates the skill from skills that produce adjacent artifacts.
2. **Template(s)** — literal file content with placeholders, not prose.
3. **Rules** — only the rules that apply when *writing this artifact*. Cross-cutting concerns (typing, imports) are referenced, not restated, except for a brief inlined slice when it's load-bearing.
4. **Hard stops** — explicit cases where the agent must stop and switch to a different skill.

A merged theme-skill carries one `## …` section per artifact it covers, each keeping this four-section shape. Two optional helper sections (`Inlined typing / import rules`, `Package wiring`) appear only when load-bearing. A skill carries **no** orchestration section (what it returns, who invokes it) and **no** spec-input table — those layers belong to the agents/commands and the spec format, not to the skill.

## Out of scope (intentionally not in this catalog)

- The agent roles live separately under `.claude/agents/`. Skills describe *artifacts*; agents describe *processes*.
- Process-only skills (e.g. brainstorming, retrospective notes) are not part of this catalog. If reintroduced, they belong in a separate prefix (e.g. `process-brainstorm`).

## Read models — guidance for a future skill

The catalog deliberately does **not** split repositories into write-side and read-side protocols. The CQRS guarantee that matters (commands mutate, queries read) is enforced by the handler split inside `application` (command vs query); partitioning every `IFooRepository` into read/write halves would double the protocol/DI/test surface across all aggregates for a benefit that only materializes with event sourcing, async projections, or a separate read store — none of which apply here today.

Add a new `infra-read-model` skill the first time a query handler genuinely needs a denormalized/join-flattened DTO that is not "an aggregate read" (e.g. "foos with author name + tag count + last_modified_by name" joining three tables). Model it as an additive component (its own protocol, its own adapter, its own flat DTO), not as a partition of the existing repository. Until that use case appears, the unified `IFooRepository` with both reads and writes is the canonical shape.
