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
| **Meta** (the pipeline) | `.claude/` (skills, agents, commands, conventions, the stdlib validator, templates), `specs/`, `examples/`, `*.svg`, `*spec.md` | The skills, agents, commands, conventions, and validator that *drive the agents* which generate code | This is the actual work |
| **Target** (the generated app) | `examples/generated/` (git-ignored, disposable) | The hexagonal backend the **scaffolder + implementer agents** produce from a manifest | Produced from manifests, never hand-edited |

`src/codegen/` is the **retired deterministic generator**, kept only as a read-only **archive** (its
tests still pass; do not extend it). The pipeline no longer renders code — see "the spine" below.

When the user asks to "write a skill / agent / command," they mean the **meta** layer.
The target backend is never committed — it is the *output* of the agents, produced into
`examples/generated/` from a manifest rather than hand-edited.

**How the pipeline is exercised (no committed target app).** There is no checked-in backend. The
deterministic core that exists today — the **stdlib manifest validator** — is exercised on the example
manifests under `.claude/tools/fixtures/` (`helpdesk`, `vector_rag`, `label`):
`uv run .claude/tools/validate_manifest.py <manifest.yaml>`. The agentic forward path
(validate → scaffold → implement → verify) will emit a backend into `examples/generated/<pkg>/`
(disposable, git-ignored) once the scaffolder/implementer agents exist (spec §13 steps 3–5).

## Design principles — read these first

Every cross-cutting decision rule for building and extending this pipeline lives in **`PRINCIPLES.md`**
(`@`-included below), as a checklist in *trigger → litmus → why → `spec §`* form — it is the single home
for those rules, so before a load-bearing choice (adding a manifest field, editing a skill, spawning an
agent) consult the matching rule rather than reasoning from scratch. The spine, in one breath: **three
layers never mix** (knowledge = skills · spec = manifest · orchestration = runner/agents), the
**manifest is canonical for the graph, not the code**, and **determinism lives in verification, not
authoring** (no render-generator; the toolchain + tests + graph validator hold consistency). Full
rationale: `codegen_workflow_spec.md §0`.

@PRINCIPLES.md

## The pipeline stages

Input is a set of BA use cases (PDF), or free text, or "prototype X". The flow (spec §1):

| Stage | Executor | Type | Command |
|---|---|---|---|
| 0. Ingestion → epics + backend filter | analyst agent | agent, interactive | `/ingest-usecases` — built |
| 1. UC refinement (product questions → BA) | analyst agent | agent, file-channel | `/refine-usecases` — built |
| 2. Manifest build / delta (architecture questions → you) | architect agent | agent, interactive chat | `/build-manifest` — built; `/apply-delta` — built (`.claude/commands/apply-delta.md`; delta procedure in `.claude/agents/architect.md`) |
| — Manifest validation | stdlib graph check (no deps) | deterministic, no LLM | `/validate-manifest` *(planned wrapper)* — exists as `.claude/tools/validate_manifest.py` |
| 3. Scaffolding (declarative + glue + body scaffolds + red tests) | scaffolder agent | agent (role) | `/scaffold` — built (`.claude/commands/scaffold.md` + `.claude/agents/scaffolder.md`) |
| 4. Scaffold tail (fill scaffolded bodies behind contracts) | implementer agent | agent, parallel by DAG | `.claude/agents/implementer.md` + `/verify` (dispatch) |
| — Verification loop (mypy / ruff / behavioural tests, TDD mode) | runner + implementer | code + agent in a loop | `/verify` — exists (`.claude/commands/verify.md` + thin runner `.claude/tools/plan_implementation.py` + `.claude/tools/scaffold_snapshot.py` for baseline/diff attribution) |

**Only four agent roles exist** (analyst, architect, scaffolder, implementer) — *not* one persona per
component type. Scaffolders/implementers are differentiated by **context** (which skill is loaded + which
slice of the manifest is fed), not by forking the prompt. Proliferating per-component agent prompts was
the chief mistake of the first prototype; do not reintroduce it.

**The implementer is triggered by the runner, not by you.** Detection is deterministic
(graph marks a node touched → `NotImplementedError` present in a scaffold, or mypy red on a scaffolded
body after contract drift); the fix is the agent's. Parallelism falls out of the manifest DAG for free
— only body-bearing (scaffolded) nodes are parallelized, never declarative/glue code.

### Current state vs. planned

**Done (spec §13 steps 1–2).** The **stdlib manifest validator** (`.claude/tools/validate_manifest.py`,
§6 — zero third-party deps but PyYAML, replaces the old Pydantic schema/validator): form + graph
integrity + behaviour-consistency + loud degradation + the §16 **skill-coverage gate** (`KIND_TO_SKILL`).
The **knowledge layer**: the **skill catalog** (`.claude/skills/`, 44 component-narrow skills) + the
**`conventions` reference skill** (`.claude/skills/conventions/SKILL.md`) — the single home for mechanical
derivation (kind→path/class/suffix, the kind→skill registry, store profiles, the stack substrate as a
*list of libraries without versions*, toolchain commands), absorbing what the generator's
`naming.py`/`store_profiles.py`/constants used to hold. Plus the `uc-extractor` input-prep agent +
`/extract-ucs`, and the manifest shape (the validator's `SCHEMAS` is canonical; `manifest.template.yaml` is
generated from it; `MANIFEST_SCHEMA.md` is stale prose pending rewrite).

**Schema facts the manifest carries** (auth is manifest-declared, not hardcoded): domain
`enums`/`value_objects`/`entities`/`services`/`filters`/`capability_protocols`; infra
`settings`/`datastores`/`repositories`/`capabilities`. Storage is **polyglot** — a `datastore` node
(free-token `kind`) + a `repository.store` edge; the relational **table is a write-once scaffold**
(column types are the implementer's judgment) and **migrations are Alembic-native** (not generated). Infra
groups by **tech** (`infrastructure/<kind|adapter>/` — `postgres`/`qdrant`/`openai`/`jwt`), not a domain
subdomain; capability adapters take an optional agent-noun `role`. `domain.filters` is a first-class
section (read-side filter object + sort enum + pagination). The contract carried to the implementer has
three channels — `behaviour`/`then.with` (verify) · `notes` (guide, node + per-method, domain-semantic vs
infra-tech) · `sources` (provenance); the validator emits loud-degradation warnings. Primary fixture is
**Helpdesk** (`.claude/tools/fixtures/helpdesk_manifest.yaml` — auth + tickets); `vector_rag` is the
non-CRUD/polyglot probe, `label` the small CRUD parse fixture.

**`src/codegen/` is the retired generator (archive only).** Its Pydantic schema, the scaffold-first Jinja
generator, store profiles, and drift check still exist and their tests still pass, but they are no longer
the path and **must not be extended** (removal is deferred to §13's "потом", after the agentic path is
proven on an epic; `main` stays the generator archive — this branch is not merged there).

**Done (spec §13 steps 3–5) — the agentic forward path is proven.** The **scaffolder** agent
(`.claude/agents/scaffolder.md`) + `/scaffold` (`.claude/commands/scaffold.md`); the rewritten
**implementer** agent (`.claude/agents/implementer.md` — body-fill only, file-as-unit, strict §9
anti-collusion) + the verification loop `/verify` (`.claude/commands/verify.md`) driven by the thin
stdlib runner `.claude/tools/plan_implementation.py` (deterministic trigger — both halves of spec §4:
`NotImplementedError`/column-less-table **and** structural contract drift, i.e. a protocol-implementing
body missing a method its protocol declares — + DAG-level worklist, reusing the validator). Step 5 drove
the full path end-to-end on helpdesk + vector_rag into `examples/generated/` — validator → scaffolder →
implementer (by DAG) → verify — mypy/ruff clean, unit tests green, the app constructs with full OpenAPI.

**Done — the upstream bundle + the brownfield delta path.** The **analyst** agent + `/ingest-usecases` +
`/refine-usecases`; the **architect** agent + `/build-manifest` + `/apply-delta`. The forward path is
brownfield-safe (re-`/scaffold` regenerates declarative/glue, leaves filled bodies; `/verify` reconciles
drift via the two-half trigger). The delta path was proven end-to-end on a real delta (`IUserRepository`
grows `get_by_id`, a UC-02 cross-epic exposure on the 01-identity manifest): architect mutate + validate →
brownfield re-scaffold (protocol/fake regenerated, filled bodies untouched) → runner drift trigger →
implementer reconciles → `mypy src tests` + ruff green. See `notes/11_delta_path.txt`.

**Still to build / known frontiers.** The `/validate-manifest` wrapper (the validator itself exists).
**Cross-epic scaffold-time resolution is unbuilt** (the multi-manifest-into-one-package frontier): the
validator warns-and-skips a cross-epic edge (`auth:IFoo.method`), conventions has no cross-epic import
derivation, and the scaffolder has no multi-manifest handling — so a downstream context (e.g. Tickets)
cannot yet be scaffolded into a package alongside the upstream context it depends on (spec §13 «потом» /
§15). Drift detection v1 catches **method-presence** drift; a same-name **signature** change still falls
only to the final whole-tree mypy gate, not the per-node worklist.
Deferred (spec §13 «потом»): the brownfield frontier (orphan GC + rename-with-body-transfer), plugin
packaging + multi-language, and removing the `src/codegen` archive. Open seams: a Docker-backed
integration run (testcontainers), and the §9 review tail (manual-stub assert authorship + adversarial
verifier). See the work order in `codegen_workflow_spec.md` (§13) and `notes/6_build_plan.txt`.

## Repository map

```
codegen_workflow_spec.md          # THE design doc (Russian) — read first
codegen_pipeline_v2_with_ingestion.svg  # the pipeline diagram
.claude/
  skills/                         # the knowledge layer — one artifact-kind per skill
    CONVENTIONS.md                # catalog index + shared vocabulary + the four-section format
    conventions/SKILL.md          # the derivation registry (kind→path/class, kind→skill, store profiles, substrate)
    <prefix>-<name>/SKILL.md      # e.g. domain-entity, application-command, restapi-endpoint
  tools/                          # the stdlib manifest validator (validate_manifest.py — SCHEMAS is the
                                  # CANONICAL manifest shape) + gen_template.py + its tests + fixtures/
  agents/                         # uc-extractor, scaffolder, implementer (done); analyst/architect to build
  commands/                       # slash-commands: extract-ucs, scaffold, verify, brainstorm, commit (upstream pipeline commands to be built)
  templates/
    MANIFEST_SCHEMA.md            # STALE prose, not the contract — pending a thin rewrite (validator wins on conflict)
    manifest.template.yaml        # the manifest shape skeleton — GENERATED from validate_manifest.SCHEMAS (gen_template.py), never hand-edited
src/codegen/                      # RETIRED generator — archive only, do not extend (its tests still pass)
tests/                            # the archived generator's own test suite + fixtures
specs/
  use-cases/UC-NN-*.md            # example BA use cases — the pipeline input
  epics/<NN>-slug/manifest.yaml   # per-epic manifest (architect output, Phase 2; gated on review)
examples/                         # example manifests + generate.py (the archived generator's entrypoint)
```

## How skills work (read before authoring or editing one)

A skill is **knowledge injected into context, not an executor**. It is consumed by *two kinds* of
reader: the **scaffolder/implementer** agents (read `Template(s)` + `Rules` — how to write the
artifact) and the **analyst/architect** agents (read `When to use` / `Hard stops` as classification
rules). Same document, different sections, different consumers.

Every skill is **component-narrow** — produces exactly one kind of artifact — and follows the
four-section body (see `CONVENTIONS.md`): *When to use vs. neighbours · Template(s) · Rules ·
Hard stops*. Use the `meta-skill-author` skill to add one.

The rules that govern skill purity and what the manifest may carry — *a skill must not know what
invokes it* (the human-onboarding test), *the manifest carries identifiers only, everything else is
derived* — live in `PRINCIPLES.md` (sections C and B). The derivation table itself (kind → path / class
/ suffix) lives in the **`conventions` skill**.

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

The project uses **uv** and targets **Python 3.12**.

```bash
# validate a manifest (stdlib validator, self-contained via PEP 723):
uv run .claude/tools/validate_manifest.py .claude/tools/fixtures/helpdesk_manifest.yaml

# the validator's own test suite (lives next to it, outside the default tests/ path):
uv run pytest .claude/tools/test_validate_manifest.py

# the generated target backend uses the verification loop (spec §12), run inside
# examples/generated/<pkg>/: uv run mypy src tests / ruff check src tests / ruff format src tests / pytest
```

The **archived generator** (`src/codegen/`) keeps its own green suite for reference, not part of the
agentic path: `uv run pytest tests/` and `uv run python examples/generate.py <manifest> --package <pkg>`.

`mypy` is part of the *designed* verification loop (spec §12) — type-correctness is load-bearing for
catching contract drift on scaffolded bodies.

Pipeline slash-commands: the full chain is **built** — `/ingest-usecases`, `/refine-usecases`,
`/build-manifest`, `/apply-delta`, `/scaffold`, `/verify` (under `.claude/commands/`, driven by the
analyst/architect/scaffolder/implementer agents + the runner `.claude/tools/plan_implementation.py`). The
only unbuilt command is the `/validate-manifest` wrapper (the validator itself exists). See the stage
table above, `notes/6_build_plan.txt`, and `notes/11_delta_path.txt` (the delta path + the cross-epic
scaffolding frontier).

## Conventions when extending the pipeline

The decision rules for extending the pipeline — earn-its-place and the anticipation litmus before
*any* manifest field, no control-flow/process-state in the manifest, no generate-vs-scaffold field
(derived from node category), cross-refs by identifier, value-object vs primitive vs entity
`__post_init__`, brownfield-first — all live in **`PRINCIPLES.md`** (sections B, E, F). Consult it
before adding a field, editing the schema, or modeling a value; don't reason from scratch.

Two placement facts not covered there: a new skill goes in `.claude/skills/<prefix>-<name>/SKILL.md`
via `meta-skill-author`; a new use case goes in `specs/use-cases/` via `meta-uc-author`.
