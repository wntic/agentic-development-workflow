# Manifest Schema

> **⚠️ STALE — not maintained. Do not treat this prose as the contract.**
> The canonical manifest **shape** is the validator's `SCHEMAS` dict
> (`.claude/tools/validate_manifest.py`) + the generated skeleton
> (`manifest.template.yaml`, emitted by `gen_template.py`) + the validated fixtures under
> `.claude/tools/fixtures/`. This document drifted from those (it predates the storage redesign and
> the `conventions` knowledge layer — e.g. it still describes `tables:`/`subpackage:`/`alembic:`/
> `Service.kind`, none of which the validator accepts) and is scheduled for a thin, pointer-only
> rewrite. **When this prose disagrees with the validator, the validator wins.** Field semantics
> live in `codegen_workflow_spec.md` §5 and the `conventions` skill; the read/write (read-model)
> split now lives in the `application-query` skill.

This document defines the YAML schema for an **epic manifest** — the intermediate representation between BA-authored use cases and the agent pipeline (a scaffolder lays down files, an implementer fills bodies; see `codegen_workflow_spec.md`).

## Where manifests live

```
specs/
  use-cases.pdf                       # BA-authored source of truth (Confluence export)
  use-cases/<UC-NNN>.md               # the BA use cases (pipeline input)
  epics/
    index.md                          # epic→UC grouping (ingestion output, Шаг 0)
    <NN-epic-slug>/
      questions_for_ba.md             # product questions (Фаза 1 refinement)
      manifest.yaml                   # epic manifest (architect, Фаза 2; gated on review)
```

**Versioning.** The BA does not edit existing UCs; revisions appear as new UCs (e.g. UC-018 supersedes UC-005). Manifests are append-only too — each epic produces one manifest, never edited after it is approved (approval is a runner event, not a manifest field; see "The earn-its-place rule"). When a new UC supersedes a prior one, the reviewer flags it during manifest review and the new manifest:

- Lists the prior UC IDs in `meta.supersedes:` (already in the schema).
- Lists every prior **artifact** being regenerated in `meta.replaces:` (see below).
- Carries a **full re-declaration** of each replaced artifact with its post-change shape.

The prior manifest is left untouched as historical record. The scaffolder regenerates the on-disk files for every artifact in `meta.replaces:` (declarative/glue rewritten in full; a body-bearing file's contract is rewritten and the implementer reconciles the body against it).

**Modification scope (`meta.replaces:`).** This field is a list of artifact names (NOT UC IDs — those live in `meta.supersedes:`). Each name must resolve to an artifact in a prior approved manifest. The architect is responsible for impact analysis: when the BA's superseding UC changes artifact X, the architect walks the typed cross-reference graph (see "Cross-references" below) to find every downstream artifact whose shape depends on X, and includes those in `meta.replaces:` as well. The reviewer sees the full blast radius during delta review before approving.

Example — UC-018 renames `Material.title → name`:

```yaml
meta:
  epic: 06-material-rename
  sources: [UC-018]
  supersedes: [UC-005]
  replaces:
    - Material
    - MaterialRepository
    - CreateMaterialHandler
    - UpdateMaterialHandler
    - GetMaterialHandler
    - ListMaterialsHandler
    - MaterialResponse
    - MaterialCreateRequest
    - MaterialUpdateRequest
```

Each name re-appears as a full declaration in its respective top-level section (`domain.entities`, `application.commands`, `restapi.schemas`, …). There is no `tables` artifact to list — re-declaring the `Material` entity changes its fields; the table SCAFFOLD is write-once (not rewritten), so a field change surfaces as schema drift and the implementer authors a **new** Alembic migration (column rename / drop), never a rewrite of a prior migration file.

**Business rules.** The BA does not maintain a numbered BR registry — rules appear as an unnumbered bullet list under «Бизнес-правила» inside each UC. The architect reads those bullets and attaches the relevant rule **text** to affected artifacts as inline `invariants:` entries; the artifact carries the rule, not a pointer to one.

**Entity invariants → a scaffolded `__post_init__`.** An entity `invariants:` entry is `{rule, field, source}` and must be an **enforceable runtime rule on the entity's own state** (e.g. "name length 3–100"). It is a *contract declaration*, never executable code (no `condition:` DSL). An entity that declares invariants gets a **scaffolded `__post_init__`** (the scaffolder emits the shell + a contract-comment listing the rules + `raise NotImplementedError`; the implementer fills the checks, raising `ValidationError(message, {"field": <field>})`), and the entity file becomes body-bearing (scaffolded once, not regenerated). Each invariant also yields a canonical entity test (write-once manual stub — a bound needs example inputs). A **design note** that is not a runtime check (e.g. "the `is_pinned` flag is presentation, a sort hint, not a lifecycle rule") is **not** an invariant — it is a YAML comment or belongs to a read-side concern, not `__post_init__`.

## Scope

The pipeline generates a **backend**. Use cases often describe end-to-end behaviour including frontend rendering and client apps, but only artifacts that belong to the backend are extracted (HTTP endpoints, application handlers, domain model, persistence, blob storage). Steps about modal dialogs, field highlighting, table refreshes, button clicks, and other UI mechanics are out of scope unless they imply an API contract (request shape, response shape, error code).

The application handlers are the backend's **public API**; `restapi` is the first **entrypoint** — a driving adapter over that API. Other entrypoints (CLI, gRPC, …) would be additive sections that reuse the same `application` handlers, not a change to the domain/application core (see `codegen_workflow_spec.md` §4).

## Core principles

1. **Derived, not declared.** The manifest carries the minimum the BA + architect cannot reasonably derive. Module paths, class-name suffixes, table-name pluralization, file layout — all of these are properties of the knowledge layer (skills + conventions) and are derived by the scaffolder at scaffold time. See "Path and naming derivation" below for the full mapping.
2. **One source of truth per fact.** An entity's `fields:` are declared once; the table, repository, schemas all reference them.
3. **Tests are derived from artifacts, not enumerated.** Every Producer `test-*` skill reads the matching artifact entry and produces its file. The `tests:` block only carries cross-cutting rules that don't derive from an artifact.
4. **Bootstrap is derived, not declared.** Bootstrap-mode skills (the FastAPI app, the test harness, the first `domain/exceptions.py`) are not listed in the manifest. Whether they still need to run is a property of the working tree — the scaffolder inspects it directly. A `bootstrap:` flag would be derivable state that does not earn its place (see "The earn-its-place rule").
5. **Every artifact carries `sources:`** — UC IDs that motivated it. The only back-reference from code to the BA's source of truth. Business rules are embedded inline as `invariants:` text, not referenced by ID.

## Path and naming derivation

The manifest carries identifiers (entity name, protocol name, command base-name); the knowledge layer derives everything else — module paths, class-name suffixes, the infrastructure subpackage, table pluralization. That derivation is **Python-pack-specific** (a different language pack derives differently), so it does **not** live in this neutral contract. It is the single authoritative table in the **`conventions` skill** (`.claude/skills/conventions/SKILL.md`, block A "Path & name derivation"); the validator's `KIND_TO_SKILL` mirrors its kind→skill registry, and the scaffolder reads it to place every file.

If you ever feel the urge to add a `module:` or `class_name:` field, push back — the `conventions` skill already encodes that derivation and adding it to the manifest creates two sources of truth.

## Cross-references

Artifacts link by **identifier**, not by file path or class name.

- Command/query `handler.dependencies:` → names of `domain.repository_protocols` / `domain.capability_protocols` / `domain.services`.
- Infrastructure `repositories[*].implements:` → name of a `domain.repository_protocols` entry.
- Infrastructure `repositories[*].backs:` → name of a `domain.entities` entry (the aggregate this repo manages).
- Infrastructure `repositories[*].store:` → name of an `infrastructure.datastores` entry (the backend this repo persists to; the store's `kind` picks the profile). Optional — absent ⇒ the implicit single-Postgres store.
- Infrastructure `capabilities[*].implements:` → name of a `domain.capability_protocols` entry.
- Infrastructure `capabilities[*].settings:` / `datastores[*].settings:` → name of an `infrastructure.settings` entry.

**Polyglot persistence — `datastores` + `store` (NO `tables` block).** Storage is **not** assumed to be one Postgres DB. A `datastore` node declares a backend by a free-token `kind` (`postgres`/`qdrant`/`redis`/…, never a `Literal` — a closed enum is the same disease as a fixed type map); each repository names its `store`. The knowledge layer maps `kind` → a **store profile** (a small open registry in conventions): which client the repo is injected with, the connection-factory scaffold, the DI wiring, the contract-comment style. An unknown kind degrades to a generic client, never a crash. There is **no `infrastructure.tables` block** — a relational table's schema (column **types**, indexes, constraints — jsonb/pgvector) is **judgment, not transcription**, so the scaffolder emits a **write-once Table SCAFFOLD** (the `Table("…", metadata, …)` skeleton + a field contract-comment) the implementer fills; a non-relational store gets no SQLAlchemy table. **Migrations are not generated at all** — Alembic owns the revision chain natively (`alembic revision` assigns the id + `down_revision` from the current head); the manifest is a desired-schema **snapshot**, never a revision journal.

**Audit timestamps** (`created_at`/`updated_at`) remain a DB-managed convention the implementer adds to a relational table (`server_default=now()`; `updated_at` also `onupdate=now()`) — they are **not** domain entity fields. The names are **reserved**: the graph validator rejects an entity that declares them. A read that must **display or filter** a timestamp does so on the **read side** — see the read/write split below.

**Reads can return read-models, not just domain entities (CQRS read/write split).** The domain entity is the **write** model (commands load/mutate it; it carries invariants). A **read** that needs more than the entity exposes — audit timestamps, denormalized or computed fields, date-range filtering — returns a **read-model DTO** that the repository projects directly from the row, bypassing the domain entity (the existing `query.result_fields:` → `*Result` DTO is this mechanism). So "the app shows a creation date" or "filter by updated_at" is satisfied by a read-model + a repository filter, never by pulling the timestamp onto the domain aggregate. A query whose output the API exposes should return a read-model rather than the bare entity when the response needs fields the entity does not (and should not) carry.
- Endpoint `handler:` → name of an `application.commands` or `application.queries` entry.
- Endpoint `request:` / `response:` → name of a `restapi.schemas` entry.
- Endpoint **errors are derived, not declared**: the advertised codes = the handler's `raises:` (mapped to HTTP) ∪ the auth dependency's (`role:` → 401/403, `authenticated` → 401). There is no `errors:` field — declaring it duplicated the handler contract, and the route advertises exactly what its handler can raise.
- Endpoint `status_code:` is an **optional override**: unset → derived from the method (POST → 201, DELETE → 204, else 200); set only for a non-standard code (e.g. a POST that returns no body → 204).

## Regenerated vs. scaffolded: ownership derived from node category, never declared

There is **no `body:` field** (and no `operation:`/`sets:` body-shape axis) in the manifest. All code is authored by agents; the node's artifact category decides **file ownership** — whether the **scaffolder regenerates** the file from the manifest on every run, or lays it down **once** so an **implementer** then owns the body (spec §0 principle 3, §3, §5):

- **Regenerated by the scaffolder** — declarative artifacts (`enums`, `value_objects`, `entities`' field shells, `repository_protocols`, `capability_protocols`, `filters`, `exceptions`, plain settings classes — fields only, REST schemas, DTOs) and graph-glue (DI/containers, `__init__` re-exports, route registration, contract-type imports, the **dependency manifest** as a graph union of the framework substrate ∪ each infra node's `requires_packages` — library names only, versions pinned by the package manager at scaffold time, spec §10). These are a transcription of the graph, so the scaffolder owns them and **always regenerates** them. The SQLAlchemy engine bootstrap (`create_engine`/`create_session_factory`) is graph-glue too — the scaffolder wires it from the relational datastore's declared settings node (the DB connection settings are an **ordinary settings node**, not a hardcoded scaffold; the postgres DSN grammar is substrate knowledge in the Python pack).
- **Scaffolded once, then implementer-owned** — *every method body* **and the relational table schema**: `application.commands`/`application.queries` handlers, `domain.services` methods, a settings class's `methods` (a derived value like a DSN — fields stay declarative, the method body is the implementer's), `infrastructure.capabilities` adapter bodies, a datastore's connection factory (`create_<store>_client`), the write-once **Table** skeleton (column types/indexes the implementer fills), an entity's or VO's `__post_init__` invariants, endpoint functions, and future entrypoint/RAG nodes. The scaffolder lays the scaffold (`class + __init__ + signature + contract-comment + NotImplementedError`) **once**; the body file is then implementer-owned (contract drift → red toolchain → the implementer reconciles). Migrations are not emitted here at all — Alembic authors them; a deterministic schema-drift check (entity fields ↔ table columns) is the trigger that wakes the implementer.

The dividing line runs **by artifact category, derived from the node** — not by a manifest flag. The thin-vs-thick distinction (a `DeleteLabel` delete check vs. a token-orchestration handler) is captured by the node's `behaviour` block and the scaffold's contract-comment, **not** by a `regenerated`/`handwritten`/`unsure` axis. **When in doubt, scaffold + implementer.** Do not reintroduce a `body`/`operation`/`sets`/`kind: generated|handwritten` axis to the manifest.

(`domain.services[*].kind: orchestrator | pure` is a separate, *structural* axis — does the service take injected protocols? — and is unrelated to regenerate-vs-scaffold, which is derived for the service body just as for every other body.)

## The earn-its-place rule (the schema shrinks, not grows)

A field lives in the manifest **only if both** hold:

1. It carries a **decision that is not derivable from the graph** — module paths, class-name suffixes, table pluralization, imports, DI wiring, `__init__` re-exports, container provider lines, and the regenerate-vs-scaffold choice are all *derived* and must never appear (see "Path and naming derivation" and "deliberately does NOT contain"); **and**
2. A **human architect must review** that decision (it is a genuine design choice, not mechanical bookkeeping).

Process state ("draft/approved", "this delta was reviewed", "bootstrap done") is a **runner event, not manifest data** (spec §4) and fails this test — hence no `status:`, no `bootstrap:`, no `auto:` flags. As scaffold-first matures, the deterministic leg gets thinner and the schema **shrinks subtractively** — when unsure whether to add a field, the default is *don't* (scaffold + LLM absorbs the novelty instead). A field that merely restates something the graph already implies is two sources of truth and must be removed.

Before adding any field, apply the **anticipation litmus test** (CLAUDE.md): if you are reaching for a field *because the example you happen to be implementing right now needs it*, do not add it. That is how the v1 schema bloated; the "deliberately does NOT contain" list below catalogs the fields removed for failing this test.

## Behavioural specification: the `behaviour` block

The `behaviour:` block is the **canonical** declaration of what a node does, attached next to its contract. It is the single source from which acceptance tests are derived — so the test can never drift from intent, and an implementer cannot satisfy the type-checker while ignoring the behaviour (§13). It lives on the body-bearing node kinds (commands, queries, services, capabilities).

Each entry is a given/when/then scenario:

```yaml
behaviour:
  - given: "label in use (usage_count > 0)"  # PROSE precondition, realized against named fixtures
    when: execute                            # the node method under test (closed vocab)
    then: {raises: ConflictError}            # outcome (closed vocab)
    source: UC-14                            # the UC the scenario comes from
```

**Form (hybrid).** `when` / `then` use a closed vocabulary that maps mechanically to the canonical test (the scaffolder renders it); `given` is prose, realized against named fixtures (the part that needs judgment):

- `when:` — a method name. For a handler, always `execute`. For a service, the method (`verify`, …).
- `then:` — one or more of a closed verb set:
  - `{raises: <ExceptionName>}` — must be a name in the node's `raises:`.
  - `{returns: <Type or literal>}` — the success result.
  - `{persists: <Entity>}` / `{deletes: <Entity>}` — a repository mutation.
  - `{logs: <event>}` — must equal the node's `log_event:`.
  - `{calls: "<Dependency>.<method>"}` — an interaction with an injected dependency.

**The behaviour block drives a red test, always.** Because every body is scaffolded (the scaffolder emits the contract + `NotImplementedError`, never the body), the scaffolder renders the canonical scenarios into a **red** test that exists *before* the body. The implementer writes the body until it goes green — the red test is born from the manifest, so the implementer cannot satisfy the type-checker while ignoring intent and cannot cheat past it (spec §9). A domain rule like `DeleteLabel`'s in-use/archived check is **not** an executable `condition` in the manifest (§5) — it rides entirely on the node's `behaviour:` scenarios, and the implementer reconstructs the check in the scaffolded body. The entity stays a pure declarative shell (fields + identity).

Worked example — `DeleteLabel` (epic Labels / UC-03), the in-use / archived delete rule carried by behaviour:

```yaml
commands:
  - name: DeleteLabel
    input: [{name: label_id, type: UUID}]
    output: "None"
    handler: {dependencies: [ILabelRepository]}
    log_event: label_deleted
    raises: [NotFoundError, ConflictError]
    behaviour:
      - {given: "label with usage_count > 0",             when: execute, then: {raises: ConflictError}, source: UC-03}
      - {given: "an archived label",                      when: execute, then: {raises: ConflictError}, source: UC-03}
      - {given: "a live, unused label (usage_count = 0)", when: execute, then: {deletes: Label},          source: UC-03}
    sources: [UC-03]
```

## Annotated reference

The canonical, machine-parseable shape of a manifest lives in a sibling YAML file:

**[`.claude/templates/manifest.template.yaml`](manifest.template.yaml)**

That file IS YAML — comments annotate the fields. A real `manifest.yaml` produced by the architect follows the same top-level keys, the same per-artifact field names, and the same value forms; comments are dropped. Read the template alongside this document: the prose here is the *contract* (principles, derivation, cross-references, validation); the template is the *shape*.

## Validation rules (the stdlib validator runs these before scaffolding)

1. **Every required field for every artifact is present.** The validator checks each artifact against the manifest schema using stdlib only (no third-party deps — it ships bare in the plugin). Missing required fields → flagged for review, not a silent default. Language-specific correctness (types, signature grammar) is NOT checked here — that is the toolchain's job (spec §6).
2. **Every cross-reference resolves.** Protocol names, handler names, schema names, exception names, repository-`backs:` aggregate names, repository-`implements:` protocol names, repository-`store:` datastore names, capability/datastore-`settings:` names — all must point to an entry in this manifest or a prior approved one.
3. **Every `sources:` entry resolves** to a UC file in `specs/use-cases/`. (Business rules are inline text, not validated by ID.)
4. **No artifact name collides** with an artifact of the same kind in a prior approved manifest.
5. **Bootstrap is derived from the working tree, not declared.** There is no `bootstrap:` list to validate — the scaffolder inspects the working tree to decide which bootstrap-mode skills still need to run.
6. **Every name in `meta.replaces:` resolves** to an artifact in a prior approved manifest. Unknown names → blocker; the reviewer must either drop the entry or pin the canonical name.
7. **Every name in `meta.replaces:` has a matching full re-declaration** in the relevant top-level section of THIS manifest. A name listed in `replaces:` without a matching re-declaration is a blocker — the scaffolder wouldn't know what to write.
8. **Impact-analysis completeness check (warning, not blocker).** For every name in `meta.replaces:`, the validator walks downstream cross-references in prior approved manifests. If any consumer of a replaced artifact is NOT itself listed in `meta.replaces:` and is NOT explicitly justified in `meta.notes:` as unaffected, the validator emits a question rather than failing — the reviewer decides whether the omission is intentional.
9. **Every `behaviour` scenario type-checks against its node.** `then.raises` resolves to a name in the node's `raises:`; `then.logs` equals the node's `log_event:`; `then.calls` names a method on a declared `handler.dependencies:` (or service dependency); `when` names a real method of the node. `given` is prose and is not structurally validated.

## What the manifest deliberately does NOT contain

- **Module paths or file paths.** Derived per the table above.
- **Class names beyond identifiers.** Skill applies suffixes (`Command`, `Query`, `Handler`, `Result`, `SqlAlchemy*`, etc.).
- **Plural-ization of table names.** Skill derives.
- **The relational table schema and an `infrastructure.tables` block.** No `tables:` section, no columns/types/indexes/constraints — a table is a write-once SCAFFOLD the implementer fills (column types are judgment, not transcription). Which entity is persisted, and where, is carried by `repositories[*].backs` + `store`.
- **Alembic migrations and the revision/down-revision chain.** Not generated — Alembic owns the chain in `versions/` (`alembic revision`); the manifest is a desired-schema snapshot, not a journal. No `alembic:` field.
- **A settings `subpackage`.** Derived from the consuming tech (capability `adapter` / datastore `kind`); infra groups by integration, not domain subdomain.
- **An open freeform map per artifact.** No artifact carries an arbitrary key/value escape hatch — it bypassed the schema. Human-readable context uses the typed `notes:` field where modelled.
- **A command's external-effect flag.** External effects are captured by the handler's dependency + `behaviour.then.calls` (+ the `pattern-compensating-tx` skill), not a declared list.
- **A repository's standalone/uow mode.** Unit-of-work is an operation-level decision (see `application.unit_of_work`), not a per-repo flag.
- **An endpoint's upload/download flag.** Not modelled.
- **Test cases or test file paths.** Derived by each `test-*` skill from the artifact entry.
- **Container provider lines.** Pure graph-glue, derived from artifacts unconditionally — no `di_providers` block, no `auto:` flag.
- **The regenerate-vs-scaffold choice.** Derived from node category (see "Regenerated vs. scaffolded"). No `body:`/`operation:`/`sets:` axis.
- **Process state.** No `status:` (draft/approved), no review/bootstrap-done flags — that is a runner event (spec §4).
- **`__init__.py` re-exports.** Derived by `general-python-package`.
- **Import statements.** Derived by `general-imports-conventions`.
- **Alembic revision IDs.** Read from the working tree at run time.
- **Reference-skill content** (typing, imports, layering, logging, test principles). Consulted on demand; never enumerated.

## Open extension points

- **`notes:` per artifact** — freeform context for human reviewers (where the schema models a `notes:` field). This is the only sanctioned escape hatch for human-readable notes; there is no open freeform map, since arbitrary keys would bypass the schema (see "The earn-its-place rule").
- **Manifest-level `notes:`** — epic-wide context.
