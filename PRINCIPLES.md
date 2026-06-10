# Design principles — the decision checklist

The cross-cutting rules that decide *how this pipeline is built and extended*. This file is the
**single home** for those rules; it is `@`-included by `CLAUDE.md`, so it loads into every session.

How the three documents divide labour — keep them in their lanes, never duplicate:

- **`codegen_workflow_spec.md`** is the **why** (rationale, source of truth). Every rule here cites a
  `spec §`; read the section when you need the argument, not the verdict.
- **This file** is the **decision verdict** — *when X is tempting → apply this litmus → do Y*. No prose
  rationale beyond one line; that lives in the spec.
- **Skills** (`.claude/skills/`) are the **how-to-write-a-component** knowledge. House-style for a given
  artifact lives in its skill, not here.

This file follows its own canon: it does not restate the spec, it points to it. If a rule grows a
paragraph of justification, that paragraph belongs in the spec with a `§` back-reference.

Each rule: **Trigger → Litmus / do → why (`§`)**.

---

## A. The three layers never mix (the spine)

**A1 · Layer separation.** *Trigger:* deciding where a fact belongs. *Do:* sort it into exactly one of
*knowledge* (how to write a component → **skills**), *specification* (what the specific component is →
the **manifest**), *orchestration* (who runs what, when → the **runner/agents**). *Why:* most bugs are
one layer leaking into another. `spec §0.1`

**A2 · Manifest is canonical for the graph, not the code.** *Trigger:* asking "where is aggregate X
used / what's the blast radius?" *Do:* answer it as a query against the manifest graph, not from memory
or by grepping code — code is derived and regenerable. *Why:* the manifest is the single source of
truth for the graph; completeness is required of the *graph*, not of generated bodies. `spec §0.2`

**A3 · Determinism lives in verification, not authoring.** *Trigger:* tempted to make some step
"correct by construction" via a code-rendering generator. *Do:* don't — agents write the code (glue and
bodies); correctness is held by deterministic *verifiers* (graph validator + target-language toolchain
compile/type-check/lint + canonical behavioural tests). *Why:* a render-generator has partial coverage
by construction and breaks on the unforeseen manifest; verification catches drift even inside an
already-written body. `spec §0.3`

**A4 · The gate must exercise the real failure mode.** *Trigger:* relying on the toolchain to catch a
class of defect. *Litmus:* does the gate actually *construct / run* the artifact, or only type-check and
lint it? A defect that surfaces only at construct/run time (a missing framework dependency FastAPI
imports at `create_app()`, broken middleware wiring, an unbuildable route schema) passes green until
something exercises it — add that exercise (the app-construction smoke test). Corollary: no silent
no-op — an under-specified body fails loud, it does not pass quietly. *Why:* mypy, ruff, and the unit
tests all stayed green while `create_app()` raised. `spec §0.3, §6`

---

## B. The manifest — what it carries, what it never does

**B1 · Earn-its-place.** *Trigger:* about to add any manifest field. *Litmus:* a field lives only if it
carries a decision that is **(a) NOT derivable** from the graph/signatures/behaviour **AND (b)** one a
human architect must review. Fails either test → derive it or push it into a body, don't store it. *Why:*
as scaffold-first matures the schema should *shrink*, not grow. `spec §5`

**B2 · Anticipation litmus.** *Trigger:* adding a field because the example in front of you needs it.
*Litmus:* "Am I adding X because I know the app I'm building *right now* needs it?" Yes → **do not add
it.** *Why:* shaping the schema around one partial-coverage manifest is the v1 disease — it breaks on the
next unforeseen manifest. *Precedent (removed for failing this):* `body`/`operation`/`sets`,
`guards`/`condition`, `lifecycle`, `archive_flag`, `list_order`, the whole `tables`/`Alembic` block,
`Settings.subpackage`. *Earned it (rare):* `datastore.kind`/`store`, capability `role`,
`requires_packages`, `log_event`, the `domain.filters` shape. `spec §5`

**B3 · Identifiers only; everything else is derived.** *Trigger:* feeling the urge to add `module:`,
`class_name:`, a path, or an import to a node. *Do:* don't — the manifest carries identifiers (entity
name, protocol name, command base-name) and edges; module paths, class-name suffixes
(`Command`/`Handler`/`<Aggregate>Repository`), table pluralization, imports, DI wiring, the infra
subpackage, and `__init__` re-exports are all derived at dispatch time (the derivation registry is the
`conventions` skill). *Why:* a stored derivable creates two sources of truth. *Lone exception:* a
capability's optional `role` agent-noun (non-derivable English morphology, like `log_event`). `spec §5`

**B4 · No control flow or process state in the manifest.** *Trigger:* wanting a `status: draft/approved`,
`auto: true`, `bootstrap`, or an "informational" comment on the manifest. *Do:* drop it — process state
("this delta was reviewed → the scaffolder ran") is a runner *event*, not manifest *data*. *Why:* the
manifest is a state snapshot, not a process log. `spec §5`

**B5 · No generate-vs-scaffold field.** *Trigger:* wanting to mark a node as "generated" vs
"scaffolded/LLM-filled" (a `kind`/`operation`/`body` axis, a thin-vs-thick handler flag). *Do:* don't —
it is **derived from the artifact category** (declarative + glue regenerate; every body + the relational
table are scaffolded once). *Why:* the architect decides nothing here; the old thin/thick-handler pain
dissolved. `spec §3, §5`

**B6 · Cross-references by identifier, never by path or class name.** *Trigger:* writing an edge between
nodes. *Do:* reference the target by identifier; a cross-epic edge needs explicit notation (working
hypothesis `auth:IUserRepository`) and is a validator *warning*, not an error. *Why:* paths/class names
are derived and would re-introduce a second source of truth. `spec §5, §6`

**B7 · Logic is a body, not a field.** *Trigger:* tempted to encode filter application, ordering, a
conditional check, or a timestamp write into the manifest. *Do:* leave it as a body the implementer fills
from `behaviour` + signatures; when in doubt, scaffold + LLM, never grow the schema. *Caveat — object vs
logic:* the read-side filter *object* (filterable fields + sort enum) IS declarative and earns
`domain.filters`; only the WHERE-clause/`order_by` logic that consumes it is a body. *Why:* a logic
mini-language in YAML is a Turing-complete spec-DSL — the thing the redesign exists to avoid. `spec §0.3, §5`

**B8 · Dependencies are derived from the graph, never hardcoded.** *Trigger:* a node needs a third-party
package, or you're writing the dependency manifest. *Do:* pure domain/application carry zero third-party
deps; third-party deps attach only to infra nodes (`requires_packages`) ∪ the stack substrate, and the
dependency manifest (`pyproject.toml`) is derived glue = substrate ∪ graph `requires_packages`, gated on
presence (a `multipart` endpoint pulls `python-multipart`, the way a relational store pulls the Postgres
substrate). Versions are never hardcoded — the package manager pins latest-compatible at scaffold time.
*Why:* hardcoded version pins were the generator's chief rot, and a forgotten graph-derived dep
type-checks green but breaks at app construction. `spec §10`

---

## C. Skills — the knowledge layer

**C1 · A skill is knowledge, not an executor.** *Trigger:* writing or editing a `SKILL.md`. *Litmus:* the
skill must not know what invokes it — no mention of agents, the manifest, use cases, the runner, or
"report to the coordinator". *Why:* a skill is consumed by two different readers (scaffolder/implementer
vs analyst/architect); coupling it to one orchestration leaks a layer. `spec §3`

**C2 · Component-narrow.** *Trigger:* a skill is being stretched to cover an adjacent artifact. *Litmus:*
if its hard-stops fire, the spec asked for the wrong artifact — switch to the right skill, don't stretch
this one. *Why:* one artifact-kind per skill keeps dispatch a deterministic `kind→skill` map. *Exceptions
(deliberate):* `pattern-` (span layers), bootstrap (run-once), reference (always consulted). `CONVENTIONS.md`

**C3 · The human-onboarding purity test.** *Trigger:* any line in a skill. *Litmus:* would a new human
developer read this as onboarding docs? If they'd trip over it (it talks about the manifest, the runner,
what the skill returns), it's a leaked layer — cut it. *Why:* the purity test is what drove removing the
`Inputs the spec must supply` and `Report to the coordinator` sections from every skill. `spec §3`

**C4 · Skills describe artifacts; agents describe processes.** *Trigger:* deciding whether new content is
a skill or an agent. *Do:* artifact-shaped → a skill in `.claude/skills/<prefix>-<name>/` (via
`meta-skill-author`), four-section body, no orchestration/manifest-input sections; process-shaped → an
agent in `.claude/agents/`. *Why:* keeping the lanes apart is what stops per-component prompt
proliferation (see D1). `CONVENTIONS.md`

**C5 · Skill-gap is gated, never self-minted.** *Trigger:* a manifest declares a `kind` with no skill in
the `kind→skill` registry. *Do:* it's a deterministic **presence-gap** → pre-flight stop (like a broken
edge) → `meta-skill-author` drafts → **human accepts** (~5-line review), then scaffolding. A
**coverage-gap** (skill exists but doesn't fit the case) → the agent stops and escalates, never extends
the skill silently. *Why:* a skill is canonical knowledge governing all future generation; silent
self-mint poisons the canon, breeds duplicates, and revives per-component prompts. `spec §16`

**C6 · No scope-overclaim (altitude).** *Trigger:* a skill template or rule bakes in a feature one app
happens to have — auth, a relational store, multipart, multi-tenancy / cross-org, a specific role
ladder, a `realm` / hostname / port literal. *Litmus:* is this feature universal to every app the pack
targets, or contingent on the manifest graph? Contingent → make the template conditional on graph-derived
presence (the two-sub-template idiom), never freeze the source app's choice as universal. *Why:* skills
froze one source app's features as universal — the largest bug class in the catalog (three audit rounds,
80+ findings); the knowledge layer's altitude is the language/stack, not one application. `spec §3`

**C7 · Derivation has one home.** *Trigger:* stating a derived name, path, or mapping in a skill, an
agent, or the catalog index. *Litmus:* the derivation registry (the `conventions` skill) is the single
source — every other document *cites* it, never restates the rule. *Why:* a restated derivation drifts
out of sync (the catalog index naming `auth_mode` after the field was removed; conventions saying
`openai_settings.py` while every consumer uses `settings.py`). This is the no-two-sources-of-truth
meta-rule (this file's header) made enforceable. `spec §0.1`

---

## D. Agents and orchestration

**D1 · Only four agent roles.** *Trigger:* wanting a new agent for a new component type. *Do:* don't —
the four roles (analyst, architect, scaffolder, implementer) are differentiated by **context** (which
skill is loaded + which manifest slice is fed), never by a forked per-component prompt. *Why:*
proliferating per-component personas was the chief mistake of the first prototype. `spec §2`

**D2 · The implementer is triggered by the runner, not by you.** *Trigger:* a scaffolded body needs
filling. *Do:* let the runner detect it deterministically (graph marks a node touched → `NotImplementedError`
present, or mypy red on a scaffolded body after contract drift) and dispatch; you only escalate if a test
won't go green in N iterations. *Why:* detection is deterministic, the fix is the agent's judgment;
parallelism falls out of the DAG for free. `spec §4`

**D3 · Anti-collusion on tests.** *Trigger:* authoring or filling a canonical test. *Do:* the test is
written from the contract, separately and **before** the body, by a different context; the implementer
**never reads or writes** manual-stub asserts. *Why:* co-authoring test and body would let both be
equally wrong about intent; the manifest owns the *list* of scenarios so none is silently dropped.
`spec §9`

**D4 · File ownership is whole-file.** *Trigger:* a re-run touches an existing file. *Litmus:* a file is
**either** declarative/glue (scaffolder owns it, regenerates always) **or** body-bearing (scaffolded once
→ implementer-owned, contract drift → red toolchain → the implementer reconciles). No half-files that get
partially rewritten. The line runs by artifact category, derived from the node. *Why:* whole-file
ownership is what removes the overwrite-the-filled-body hazard. `spec §3, §4`

---

## E. Domain modeling (house-style decisions that drive manifest review)

These few target-app rules live here because they shape *your* review of a manifest; the full how-to is
in the named skills.

**E1 · Value object vs primitive vs entity `__post_init__`.** *Trigger:* deciding how to model a value.
*Litmus:* wrap it in a **value object** only when it carries its own invariant, behavior, or shared/
type-significant meaning (`Email`, `Money`) — *not* mechanically for every primitive (`description: str`
stays primitive). A **single-value** invariant may be a VO *or* an entity `__post_init__` check; a
**cross-field / whole-entity** invariant ("if X then Y") can *only* be an entity `__post_init__`. *Why:*
blanket "VO everywhere" is primitive-obsession inverted — ceremony plus `str ↔ VO` conversion at every
boundary. *(See `domain-value-object` / `domain-entity`.)* `CLAUDE.md`

**E2 · Audit timestamps are not domain fields.** *Trigger:* an entity wants `created_at` / `updated_at`.
*Do:* don't put them on the entity — they're a DB-managed table convention (reserved names the validator
forbids on an entity); a read that must display/filter them returns a **read-model DTO** projected from
the row. *Why:* write model = entity, read model = whatever the API needs. `CLAUDE.md`

**E3 · Polyglot storage; table is a write-once scaffold.** *Trigger:* persistence shows up. *Do:* a
`datastore` node (free-token `kind`) + a `repository.store` edge; the relational `Table` is a write-once
scaffold (column types are the implementer's judgment) and **migrations are Alembic-native, never
generated**. *(Full rules in `infra-sqlalchemy-table` / the `conventions` skill.)* `spec §3`

---

## F. Mode

**F1 · Brownfield is the primary mode.** *Trigger:* designing any pipeline mechanism. *Do:* build it for
**deltas** — a new UC is a delta applied to an existing manifest snapshot; greenfield is the degenerate
case of applying deltas to an empty manifest. *Why:* designing greenfield-first is exactly how the old
generator's glue broke (it added/overwrote but never removed orphans). `spec §8`
