# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

Dialogue with the user is in **Russian** (English technical terms are fine and expected).
Everything that lands in the repo — skills, agents, commands, templates, code, comments,
commit messages — is written in **English**. The one exception is the BA's source material:
use cases under `specs/use-cases/` stay in their original language verbatim — never translate them.

## What this repository is

This is **not** a normal application. It is the **tooling for an agentic code-generation
pipeline**: a system of AI agents that turn business analyst (BA) use cases into a Python
backend and then maintain it through change. Read `codegen_workflow_spec.md` (Russian) for the
full design rationale — it is the source of truth for *why* the pipeline is shaped the way it
is, and `codegen_pipeline_v2_with_ingestion.svg` for the diagram.

There are two layers, and they must not be confused:

| Layer | Where | What it is | Status |
|---|---|---|---|
| **Meta** (the pipeline) | `.claude/`, `src/codegen/`, `specs/`, `examples/`, `*.svg`, `*spec.md` | The generator plus the skills, agents, commands, and templates that *generate* code | This is the actual work |
| **Target** (the generated app) | `examples/generated/` (git-ignored, disposable) | The hexagonal backend the generator produces from a manifest | Regenerated from manifests, never hand-edited |

When the user asks to "write a skill / agent / command," they mean the **meta** layer.
The target backend is never committed — it is the *output* of the generator, regenerated into
`examples/generated/` from a manifest rather than hand-edited.

**How the generator is exercised (no committed target app).** There is no checked-in backend to
test against anymore. The generator is validated by running it on
the **example manifests in `examples/`** (`helpdesk_manifest.yaml`, `vector_rag_manifest.yaml`, etc.) and
asserting on the produced tree: `uv run python examples/generate.py <manifest> --package <pkg>` emits
into `examples/generated/<pkg>/` (disposable, git-ignored), and the test suite in `tests/` generates
from those same manifests into a temp dir and asserts file shape, imports, and reference integrity.
So "see how the generator behaves" = run it on an `examples/` manifest and inspect `examples/generated/`,
not open a hand-written app.

## The three-layer principle (the spine of everything)

Every design decision derives from three principles in `codegen_workflow_spec.md §0`. Keep them
straight — most bugs are one layer leaking into another:

1. **Three layers never mix.** *Knowledge* (how to write a component — **skills**), *specification*
   (what the specific component is — the **manifest**), *orchestration* (who runs what, when — the
   **runner/agents**). A skill must not know what invokes it; a manifest must not carry control flow.
2. **The manifest is canonical for the graph, not the code.** The manifest is the source of truth;
   code is derived and regenerable. "Where is aggregate X used?" is a query against the manifest
   graph, not something held in your head.
3. **Determinism only where the output is a transcription of the input (scaffold-first).** Declarative
   artifacts (enums, exceptions, protocols, plain VOs, entity/DTO field shells) and graph-glue
   (DI/containers, `__init__`, pyproject, tables/migrations, route registration, contract imports) →
   Jinja2 template, no LLM. *Every method body* (handlers, adapters, endpoint functions, invariant
   `__post_init__`) → a **scaffold** (signature + contract-comment + `NotImplementedError`) the
   implementer LLM fills behind a contract. The dividing line runs by **artifact category**
   (declarative/glue vs body), *derived from the node* — not declared via a manifest field.

## The pipeline stages

Input is a set of BA use cases (PDF), or free text, or "prototype X". The flow (spec §1):

| Stage | Executor | Type | Command |
|---|---|---|---|
| 0. Ingestion → epics + backend filter | analyst agent | agent, interactive | `/ingest-usecases` *(planned)* |
| 1. UC refinement (product questions → BA) | analyst agent | agent, file-channel | `/refine-usecases` *(planned)* |
| 2. Manifest build / delta (architecture questions → you) | architect agent | agent, interactive chat | `/build-manifest`, `/apply-delta` *(planned)* |
| — Manifest validation | Pydantic + graph check | deterministic, no LLM | `/validate-manifest` *(planned)* |
| 3. Forward generation (declarative domain + graph-glue; scaffolds for bodies) | generator + Jinja2 | deterministic, no LLM | `/generate` *(planned)* |
| 4. Scaffold tail (fill scaffolded bodies behind contracts) | implementer agent | agent, parallel by DAG | `implement-node` (runner-internal) |
| — Verification loop (mypy / ruff / behavioural tests, TDD mode) | runner + implementer | code + agent in a loop | `/verify` *(planned)* |

**Only three agent roles exist** (analyst, architect, implementer) — *not* one persona per
component type. Implementers are differentiated by **context** (which skill is loaded + which slice
of the manifest is fed), not by forking the prompt. Proliferating per-component agent prompts was
the chief mistake of the first prototype; do not reintroduce it.

**The implementer is triggered by the runner, not by you.** Detection is deterministic
(graph marks a node touched → `NotImplementedError` present in a scaffold, or mypy red on a scaffolded
body after contract drift); the fix is the agent's. Parallelism falls out of the manifest DAG for free
— only body-bearing (scaffolded) nodes are parallelized, never declarative/glue code.

### Current state vs. planned

What exists today: the **skill catalog** (`.claude/skills/`, 45+ skills — already refactored per
spec §3, two sections stripped), the **manifest schema** (`.claude/templates/`), and the `uc-extractor` input-prep agent + `/extract-ucs`. The
manifest Pydantic schema + graph validator (`src/codegen/manifest/`) and the **scaffold-first generator**
(`src/codegen/generator/`) exist and are green end-to-end on the example manifests. The schema has grown the **auth slice**
(domain `enums`/`value_objects`/`services`/`capability_protocols`; infra `settings`/`capabilities`) so that
**auth is manifest-declared, not hardcoded** in the generator; multi-dependency handlers and a derived
`restapi/dependencies.py` came with it. The generator's **primary fixture is Helpdesk**
(`examples/helpdesk_manifest.yaml` — auth + tickets); a small Label CRUD fixture
(`tests/fixtures/label_manifest.yaml`) backs the schema/validator parse tests. **Storage is polyglot, not Postgres-hardcoded** (driven by
a non-CRUD probe, `examples/vector_rag_manifest.yaml`): a `datastore` node (free-token `kind`) + a
`repository.store` edge; the relational **table is a write-once scaffold** (the `_SQL_CORE` Python→SQL map is
gone — column types are the implementer's judgment) and **migrations are Alembic-native** (not generated);
**store profiles** (`src/codegen/generator/store_profiles.py`, postgres/qdrant/redis + graceful unknown) make the
repo/connection/DI store-aware; a **schema-drift** check (`src/codegen/generator/drift.py`) is the deterministic
implementer trigger; **`pyproject.toml` is generated** from the graph (framework substrate ∪ infra-node
`requires_packages`). Infra groups by **tech** (`infrastructure/<kind|adapter>/` — `postgres`/`qdrant`/`openai`/
`jwt`), not a domain subdomain; capability adapters take an agent-noun `role` (`OpenaiTextEmbedder`). Multi-repo
handlers are unlocked. The contract carried to the implementer has three channels —
`behaviour`/`then.with` (verify) · `notes` (guide, node + per-method, domain-semantic vs infra-tech) ·
`sources` (provenance) — and the validator emits loud-degradation warnings (spec §6). Still to build: the
**analyst / architect / implementer agents and every pipeline slash-command** — see the work order in
`codegen_workflow_spec.md` (§13). The next decisive test is a thick, non-CRUD node.

## Repository map

```
codegen_workflow_spec.md          # THE design doc (Russian) — read first
codegen_pipeline_v2_with_ingestion.svg  # the pipeline diagram
.claude/
  skills/                         # the knowledge layer — one artifact-kind per skill
    CONVENTIONS.md                # shared vocabulary + skill index + the four-section format
    <prefix>-<name>/SKILL.md      # e.g. domain-entity, application-command, restapi-endpoint
  agents/uc-extractor.md          # input-prep: PDF → verbatim UC files (analyst/architect/implementer to be built)
  commands/                       # slash-commands: extract-ucs, brainstorm, commit (pipeline commands to be built)
  templates/
    MANIFEST_SCHEMA.md            # the manifest contract (principles, derivation, validation)
    manifest.template.yaml        # the canonical machine-parseable manifest shape
src/codegen/                      # the generator (Python package)
  manifest/                       # Pydantic schema + graph validator
  generator/                      # the scaffold-first forward generator
  templates/                      # Jinja2 templates (declarative + glue)
  scaffold/                       # package-agnostic reference files copied verbatim
tests/                            # the generator's own test suite + fixtures
specs/
  use-cases/UC-NN-*.md            # example BA use cases — the pipeline input
  epics/<NN>-slug/manifest.yaml   # per-epic manifest (architect output, Phase 2; gated on review)
examples/                         # example manifests + generate.py (output → examples/generated/, git-ignored)
```

## How skills work (read before authoring or editing one)

A skill is **knowledge injected into context, not an executor**. It is consumed by *two* readers:
the deterministic generator (reads the `Template(s)` section) and the analyst/architect agents
(read `When to use` / `Hard stops` as classification rules). Same document, different sections,
different consumers.

Every skill is **component-narrow** — produces exactly one kind of artifact — and follows the
four-section body (see `CONVENTIONS.md`): *When to use vs. neighbours · Template(s) · Rules ·
Hard stops*. Use the `meta-skill-author` skill to add one.

Per spec §3, two sections were removed from every skill: `Inputs the spec must supply` (migrates
into the manifest Pydantic schema) and `Report to the coordinator` (orchestration — belongs to the
runner, not the skill). The purity test that drove it: *would a new human developer read this as
onboarding docs?* If they'd trip over a line, that line is a leaked layer — cut it.

The manifest carries **identifiers only** (entity name, protocol name, command base-name).
Module paths, class-name suffixes (`Command`/`Handler`/`<Aggregate>Repository`), table pluralization, imports,
DI wiring, the infra subpackage (derived from a store's `kind` / adapter tech), and `__init__.py` re-exports are
all **derived** by skills at dispatch time. If you feel the urge to add a `module:` or `class_name:` field to the
manifest, push back — that creates two sources of truth. (The one carried *name* fragment is a capability's
optional `role` agent-noun — non-derivable English morphology, like `log_event`; the class is still composed
`<Adapter><role>`.) See the derivation table in `MANIFEST_SCHEMA.md`.

## The target app's architecture (what the pipeline produces)

The generated backend is a strict **hexagonal / four-layer** Python backend; the skills encode this house style:

- `domain/` — pure Python, zero third-party deps. Entities (mutable `@dataclass`, identity equality),
  value objects (`frozen`, value equality), enums (`StrEnum`), repository **protocols**
  (`IFooRepository`), capability **protocols** (`ICan<Verb>`), a single `exceptions.py` error catalog.
  Domain entities carry **domain state only** — audit timestamps (`created_at`/`updated_at`) are a
  DB-managed table convention (added to every aggregate table; reserved names the validator forbids on an
  entity), never domain fields. A read that must display/filter them returns a **read-model DTO** projected
  from the row (write model = entity; read model = whatever the API needs), not the aggregate.
- `application/` — CQRS: thin command/query handlers over frozen DTOs; success-only structured logging;
  the only sanctioned `try/except` is the compensating-transaction pattern.
- `infrastructure/` — grouped by external **tech** (`infrastructure/<kind|adapter>/`: `postgres`/`qdrant`/
  `openai`/`jwt`), not by domain subdomain. Relational repositories use SQLAlchemy **Core** (never ORM); other
  stores use their own client (a `datastore`'s `kind` picks the profile). Capability adapters wrap SDKs
  (boto3/httpx/PyJWT), `pydantic-settings` (one class per module, no `subpackage` field), the
  `dependency-injector` container in `containers.py`. Persistence is **polyglot** — a manifest can target
  Postgres + Qdrant + Redis at once; the table schema is a write-once scaffold, migrations are Alembic-native.
- `restapi/` — FastAPI; thin routers, Pydantic schemas, a central `DomainError` handler. No business
  logic in routes.

Dependency direction points **inward** to the domain; ports live in the domain, adapters in
infrastructure. `general-layered-architecture` and the `test-architecture-rule` grep-firewall enforce
this. Tests follow a no-mocks pyramid: unit tests use in-memory fakes; integration tests run real
Postgres/MinIO via testcontainers with per-test transaction rollback.

## Common commands

The project uses **uv** and targets **Python 3.12**. Run tooling for the *generator* package:

```bash
uv sync                              # install the generator + its test deps
uv run ruff check src tests examples   # lint
uv run ruff format src tests examples  # format
uv run pytest                        # the generator's whole test suite (tests/)
uv run pytest tests/test_generator.py                 # one file
uv run pytest -k "test_label_manifest_graph_is_clean" # one test by name

# generate a target backend from a manifest (output → examples/generated/, git-ignored):
uv run python examples/generate.py examples/helpdesk_manifest.yaml --package hdk
```

`mypy` is part of the *designed* verification loop (spec §17) — type-correctness is load-bearing
for catching contract drift on scaffolded bodies — but it is not yet wired into deps/CI.

Pipeline slash-commands (`/ingest-usecases`, `/refine-usecases`, `/build-manifest`, `/apply-delta`,
`/validate-manifest`, `/generate`, `/verify`) are **not built yet** — see the stage table above.
Building them, in workflow-diagram order, is the current work.

## Conventions when extending the pipeline

- **Skills** describe *artifacts*; **agents** describe *processes*. Keep them in their lanes
  (`CONVENTIONS.md` "Out of scope"). A new skill goes in `.claude/skills/<prefix>-<name>/SKILL.md`
  via `meta-skill-author`; a new use case goes in `specs/use-cases/` via `meta-uc-author`.
- **The manifest never carries control flow or process state.** No `status: draft/approved` on the
  manifest itself, no dead `auto: true` flags, no "informational" comments. State ("this delta was
  reviewed → generator ran") is a runner event, not manifest data (spec §4).
- **There is no generate-vs-scaffold field in the manifest.** Whether a node is generated (declarative/
  glue) or scaffolded (a body the implementer LLM fills) is *derived from the node category*, never
  declared — every handler body, capability adapter, datastore connection factory, and **the relational
  table schema** is a scaffold; the domain's declarative artifacts, DTOs, REST schemas, settings, and all
  graph-glue (DI, imports, `__init__`, `pyproject.toml`) are generated; **migrations are not generated at all**
  (Alembic owns them) (spec §3, §5). Do not reintroduce a `kind`/`operation`/`body` axis; when unsure,
  scaffold + LLM.
- **The anticipation litmus test (apply before adding ANY manifest field).** Ask: *"Am I adding field X
  because I know the example I'm implementing right now needs it?"* If yes — **do not add it.** That is
  the v1 disease: shaping the schema/generator around the manifest you happen to be building, which only
  has partial coverage and breaks on the next unforeseen manifest. A field earns its place only if it
  carries a decision that is (a) NOT derivable from the graph/signatures/behaviour AND (b) one a human
  architect must review (spec §5 earn-its-place). Behaviour/logic (filters, ordering, checks, timestamp
  writes) is NOT a field — it is a body the implementer LLM fills from `behaviour` + signatures; when in
  doubt, scaffold + LLM, never grow the schema. Precedent: `body`/`operation`/`sets`, `guards`/`condition`,
  `lifecycle`, `archive_flag`, `list_order`, the whole `tables`/`Table`/`Alembic` block (table schema is a
  scaffold; `_SQL_CORE` deleted), and `Settings.subpackage` (derived from tech) were all removed for failing
  this test. The countervailing move — a field that EARNS its place because it is genuinely not derivable AND
  human-reviewed — is rarer: `datastore.kind`/`store`, capability `role`, `requires_packages`, `log_event`.
- **Value object vs. primitive vs. entity `__post_init__` (domain modeling).** Wrap a value in a
  **value object** (`domain-value-object`) only when it carries its own **invariant, behavior, or shared/
  type-significant meaning** (e.g. `Email` normalize+validate+reused, `Money`) — *not* mechanically for
  every primitive. A plain field with no rule (`description: str`, a `bool`, a count) stays a primitive;
  blanket "VO everywhere" is primitive-obsession inverted — ceremony plus a `str ↔ VO` conversion at every
  boundary (table column stays primitive, REST/DTO use the primitive). A **single-value** invariant
  (`name` 3–100) may be a VO **or** an entity `__post_init__` check; a **cross-field / whole-entity**
  invariant ("if X then Y") can only be an entity `__post_init__` — a VO sees only its own value. So the
  two mechanisms are complementary, never "VO for everything." (VO-threading through table/DTO/schema is
  not yet wired in the generator — introduce it at the first value that genuinely earns it, likely `Email`,
  not preemptively.)
- **Cross-references are by identifier, never by file path or class name** (`MANIFEST_SCHEMA.md`).
  Cross-epic edges need explicit notation (working hypothesis `auth:IUserRepository`).
- **Brownfield is the primary mode.** A new UC is a *delta* applied to an existing manifest snapshot;
  greenfield is the degenerate case of applying deltas to an empty manifest. Build for deltas from
  the start (spec §7).
