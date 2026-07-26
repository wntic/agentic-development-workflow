# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**English is the working language of everything the workflow ships and produces** — skills,
agents, commands, templates, `.claude/` tools and their comments, code, commit messages. The
workflow itself imposes no human language: its commands defer to *the project's* dialogue language
(a consumer project sets its own; English if unset).

## What this repository is

This is **not** a normal application. It is the **tooling for a spec-driven agentic development
workflow (v3)**: living Markdown specs per bounded context, a change cycle
(red tests → code → run → criteria check → iterate), and deterministic gates that hold the trust.
Read **`workflow_v3_spec.md`** (Russian) first — it is the source of truth for v3 and is written
as a build order; `notes/15_v3_design_review.md` is the adversarial-review register behind its
hardening (S8/S9). Both are design canon — never edited by agents.

Two layers, not to be confused:

| Layer | Where | What it is |
|---|---|---|
| **Meta** (the workflow) | `.claude/` (skills, agents, commands, `gate.py`/`accept.py`, hooks, templates), `tasks/`, the design docs | The knowledge + enforcement + orchestration that drive the agents |
| **Target** (the app) | `src/`, `tests/`, `specs/<context>/` | The hexagonal Python backend built and maintained **in this repo** through the change cycle — one change = one branch, `main` always green |

The v2→v3 shift in one line: v2 emitted a disposable app from a YAML manifest into a git-ignored
directory; v3 maintains the app in-repo under branch-per-change, and the spec compounds into living
documentation instead of being rendered from a schema.

**What ships, in one rule: `.claude/` IS the Claude Code plugin (`adw`), and a file ships iff it
lives under it** (T15). So `tasks/`, `notes/`, both design docs, this file and any trial app are dev
artifacts a consumer never sees — which is why they keep the bare command names while everything
inside `.claude/**` refers to commands as `/adw:<name>` (a bare `/spec` is *Unknown command* in a
consumer). Packaging reference, release procedure and the measured platform facts:
**`notes/21_plugin_packaging.md`**. Do not enable both loads at once — checked out *and* installed
fires every hook twice.

**Status: v3 is being built.** The build-out is decomposed into `tasks/` (T01–T11, status in
`tasks/INDEX.md`), executed one task per `v3-builder` dispatch via `/build-task`. Anything marked
*planned (TNN)* below does not exist yet — check the INDEX before assuming a tool is available.

## The three layers of v3 (spec §1)

| Layer | What it is | Where it lives |
|---|---|---|
| **Knowledge** | how to write an artifact (house style) | `.claude/skills/` (44 skills now → ~13 after T08) |
| **Specification** | what to do and how to verify it | `specs/` — sectioned free Markdown |
| **Enforcement + orchestration** | who does what, what is forbidden, when it is "done" | `.claude/agents/`, `.claude/commands/`, `gate.py`/`accept.py` + hooks |

A fact lives in exactly one layer. The enforcement layer is **first of all two scripts** —
`gate.py` ("is it green") and `accept.py` ("may it merge") — and only secondarily hook ergonomics.
There is deliberately **no machine-readable index**: blast-radius questions are answered by
grep/agent over specs and code (earn-its-place if that ever hurts). Directory placement is pinned:
`.claude/skills/` = knowledge (auto-invocation by `description`/`when_to_use` is fine),
`.claude/commands/` = orchestration (explicit human launch only) — never merge them.

## Design principles — read these first

Every cross-cutting decision rule lives in **`PRINCIPLES.md`** (`@`-included below) as a checklist
in *trigger → litmus → why → `§`* form — consult the matching rule before a load-bearing choice
instead of reasoning from scratch. The spine, in one breath: **the spec is free Markdown for the
human and for agent orientation; acceptance criteria are a checklist agents can only tick with
machine-checkable proof; every must-hold rule is a deterministic gate, and trust is held by
`gate.py` checking the result against the git baseline (S8); one change = one branch, `main` is
always green (S9)**. Full rationale: `workflow_v3_spec.md §0`.

@PRINCIPLES.md

## The spec store (spec §2)

```
specs/
  <context>/                      # bounded context = folder (ownership boundary, mirrors a code subpackage)
    overview.md                   # context map: purpose, capability list, cross-cutting invariants, integrations
    <capability>.md               # LIVING spec of one capability, 50–300 lines — compounds over time;
                                  #   invariants carry provenance: (verified by: <test-id>) / (MANUAL)
    changes/
      NNN-<slug>/                 # one change = one delta spec, living on ITS OWN branch change/<context>-NNN
        change.md                 # Class / Context / Task / Interface sketch / Acceptance criteria / Verification
        criteria.md               # the checklist agents can only flip with junit-backed proof (§3.3)
        verdict.md                # the evaluator's report (written by the cycle)
  use-cases/                      # BA sources — verbatim, input material for /spec
```

- A change's lifecycle (`draft → in-progress → done → merged | abandoned`) is the branch position +
  the state of `criteria.md`; there is **no status field** (no process state in the spec).
- **Acceptance** merges the criteria into capability files as invariants and **deletes** the change
  directory — the archive is git history + the tag `change/<context>-NNN`. There is no `archive/`.
- Cutting rules (spec §2.1): context = "doesn't change together"; capability = cohesion-of-change;
  a file past ~300 lines gets cut; re-cutting is a `/spec` right and rewrites in-flight `Affects:`.
- Cross-context deltas are paired changes linked by `Companion:` — `accept.py` takes both or neither.

## The change cycle (spec §6)

Three commands plus `/abandon` — all *planned*, see `tasks/INDEX.md`:

| Command | What it does | Status |
|---|---|---|
| `/spec` | interview with the human → `change.md` + `criteria.md` (+ Interface sketch for M/L), criteria lint, branch `change/<context>-NNN`; `--retro` for hotfix legalisation | planned (T03) |
| `/implement <context>/NNN` | the cycle on the change branch: test-author (red tests, baseline commit) → implementer (to green `gate.py`) → fresh evaluator (flips criteria, writes `verdict.md`) → adversarial pass (M/L + first change of a capability); 3 full passes → `ESCALATE` file | planned (T09) |
| `/accept-change <context>/NNN` | wrapper over `accept.py`: gates → human reviews the merge diff → merge to `main` + tag + delete change dir | planned (T10) |
| `/abandon <context>/NNN` | delete the change branch (red tests never touched `main`), reason in tag `abandoned/<context>-NNN` | planned (T09) |

Change **classes**: `behavioral` (default; the removal flavour — marked `REMOVED` on the `Class:`
line, with a `## Removed` section listing the symbols and obsolete node-ids — makes the test-author
owner of obsolete tests), `bugfix` (code diverged from a recorded invariant), `invisible` (refactor/deps/perf — proof
is a green gate + empty OpenAPI diff). Change **depths**: S (Task + 1–3 AC, evaluator fast-lane) ·
M (+ Context, Out of scope, Interface sketch, Verification) · L (+ non-binding Design notes). A new
context's first change is a **vertical slice** — one end-to-end observable AC. There is no scaffold
template: a new project is a plain `uv init` + the installed plugin, and the substrate is
**agent-owned per change** — the test-author declares the change's dependencies in a pre-baseline
commit (from the Interface sketch), and the implementer writes the behaviorless app shell as ordinary
`src/**` work on the first change. The workflow generates no code (D1/A3). At most one change per
context is in `/implement` at a time.

## Roles (spec §4) — few, differentiated by context

| Role | Who | Does | Cannot (enforced via `disallowedTools`) |
|---|---|---|---|
| **spec-author** | human + main session (`/spec`) | interview → change.md + criteria.md + Interface sketch; capability (re-)cutting | write code or tests |
| **test-author** | subagent, own context | red tests with `@pytest.mark.ac("AC-n")` markers from spec + Interface sketch; removes obsolete tests in removal changes; redness confirmed by script; red commit = baseline | write `src/**`, criteria.md, verdict.md |
| **implementer** | subagent | code to a green `gate.py`; owns the Alembic revision; blocked contract → **contract-change protocol** (back to test-author), never a silent workaround | write `tests/**`, `specs/**`, `.claude/**`, `pyproject.toml`; SubagentStop holds it while the gate is red |
| **evaluator** | subagent, **fresh context** | full `gate.py` + live checks where Verification provisioned an environment; flips `[ ]`↔`[x]` both ways; writes verdict.md | write `src/**`, `tests/**` |

The Interface sketch (change.md, M/L) is the one published contract test-author and implementer
share — it kills the "who owns the names" seam. Agent definitions for these roles are planned (T09).

## Enforcement (spec §5) — gate.py and accept.py are the trust anchors

**`gate.py`** *(planned, T04)* — the single point of truth for "green", stdlib-only, machine-readable
verdict + junit-xml + git SHA. Inventory (§5.1, every check traces to a paid-for finding): toolchain
(mypy / ruff / pytest with **pinned config living inside gate.py**); grep-gates (`# type: ignore`,
`from __future__ import annotations`, `# noqa: F401`, `raise NotImplementedError` in `src/**`);
construct-smoke (`create_app()` + `app.openapi()`, table-metadata import); Docker tier
(testcontainers + `alembic upgrade head`, loud `DOCKER SKIPPED` otherwise); `--criteria` (every
`[x]` must be backed by a **passed** `ac`-marked test in this run's junit); and **integrity against
the red-commit baseline** — protected-tree diff (criteria.md legal flips only, change.md hash,
`.claude/tools|hooks`, settings, `pyproject.toml`), test inventory ⊇ baseline (a missing/skipped/
xfailed baseline test is RED), self-hash of the **whole enforcement layer** (T18: every tool, hook
and manifest under the plugin root — `tools/*.py`, `hooks/*.py|json`, `bin/*.py`, `plugin.json`,
`settings.json` — must match git HEAD of the repo the plugin lives in, which is the *only* protection
the plugin's own files have once installed: `bash_guard` is anchored to the consumer's root and the
protected-tree diff is vacuous there), and `escalate-intact`
(an `ESCALATE` the branch's history knows — carried by the baseline commit *or* committed by the hook
since it — must still be in the work tree; its *removal* is RED, its *presence* is not, since a
standing lock is `accept.py`'s business. Clearing it is a recorded act: commit the deletion, then
`red_check.py --change <ctx>/NNN --clear-escalate` moves the baseline over it — T06h). **S8 in one breath: hooks
are ergonomics — trust is the post-hoc check against the git baseline; bypassing a hook only gets
your result invalidated at the gate.**

**`accept.py`** *(planned, T05)* — acceptance preconditions as a script, not command prose: all
criteria `[x]`/`[m]` and junit-backed at the verdict's SHA; gate GREEN; no `ESCALATE` file;
`Companion:` accepted together; Affects-intersection flags for in-flight changes; merge-fidelity
pre-check (every AC findable in the capability-file diff); spec-lint; orphan sweep for removals.
Then: criteria → invariants with provenance, merge to `main`, tag, delete the change dir. **S9 in
one breath: one change = one branch — red tests, code and verdict live on the change branch, and
`main` only ever receives green merges through `accept.py`.**

Hook ergonomics + stop-gates *(planned, T06)*: criteria-guard (disk-diff on Write), bash-guard,
path canonicalisation, SubagentStop blocking the implementer while the gate is red, and a
**hook-written and hook-committed** `ESCALATE` file at the iteration ceiling (`accept.py` denies
while it exists *and* after a committed one disappears; only the human clears it, through
`red_check --clear-escalate`). Hotfixes past the workflow are legal but not silent: `/spec --retro`
+ the drift-check `drift.py` runs for `/orient`, whose hotfix half `accept.py` prints after every
`--execute` (§5.5). It **surfaces** and never denies — the one deterministic check in this workflow
that is deliberately not a gate.

## v2 — archived

v2 (YAML manifest + stdlib validator + scaffolder/implementer over the manifest DAG) was **proven
end-to-end** — full forward path, brownfield delta, cross-context scaffolding, Docker integration
tier, the §9 trust tail — and is archived in the git history of **`main`** (tag **`v2-archive`** =
commit `6824289`, the tip at this branch's fork point; no separate archive directory). Its design doc
`codegen_workflow_spec.md` is kept for rationale, and `notes/` keep the decision history
(`notes/pipeline_dryrun_feedback.md` is the honesty benchmark for defect logs). The v2 files that
lived on this branch — the generator, the validator/runner under `.claude/tools/`, the v2
agents/commands, `examples/` — were **harvested (`notes/16_agent_prompt_harvest.md`) then purged
in T02**; recover any of them from git history, never by rewriting.

## Repository map (as it will be — planned items marked)

```
workflow_v3_spec.md               # THE v3 design doc (Russian) — read first; design canon
notes/15_v3_design_review.md      # the 5-probe adversarial review register — design canon
codegen_workflow_spec.md          # v2 rationale — archive, kept for the "why" of what survived
tasks/                            # v3 build-out: INDEX.md (status) + one file per task (T01–T11)
notes/21_plugin_packaging.md      # what ships, the release procedure, the measured platform facts
.claude/                          # THE PLUGIN ROOT (`adw`) — everything here ships, nothing else does
  .claude-plugin/plugin.json      # the manifest
  bin/adw.py                      # the one invocation form: `${CLAUDE_PLUGIN_ROOT}/bin/adw.py <tool>`
  skills/                         # knowledge layer — 44 skills now, merged to ~13 (T08) after the
                                  #   paid-fixes inventory + test-principles rewrite (T07)
  tools/
    gate.py                       # "is it green" — the trust anchor            (planned, T04)
    accept.py                     # "may it merge" — acceptance preconditions   (planned, T05)
    drift.py                      # "has anything drifted" — §5.5, surfaces, never denies (T17);
                                  #   run by /orient, its hotfix half is accept.py's own
  hooks/                          # criteria-guard, bash-guard, stop-gates      (planned, T06)
    hooks.json                    #   the same wiring for an INSTALLED load; settings.json is the
                                  #   checked-out twin (a plugin cannot ship hooks in settings.json)
  agents/                         # v3-builder (build-out executor); test-author / implementer /
                                  #   evaluator (planned, T09); v2 agents purged in T02
  commands/                       # orient, commit, brainstorm, build-task; /spec (T03),
                                  #   /implement + /abandon (T09), /accept-change (T10);
                                  #   v2 commands purged in T02
  templates/                      # change.md / criteria.md / verdict.md / overview / capability
                                  #   skeletons (planned, T03); v2 manifest templates purged in T02
specs/
  use-cases/UC-NN-*.md            # BA corpus, verbatim — the input material for /spec
  <context>/                      # living spec of one bounded context (created by /spec)
src/ tests/                       # the target app, maintained through the change cycle
                                  #   (absent until the first change creates them — T02 purged v2's)
```

## How skills work (read before authoring or editing one)

A skill is **knowledge injected into context, not an executor**. Skills auto-invoke via frontmatter
`description` + `when_to_use` (1536-char listing cap; auto-invocation works in subagents too) — the
test-author/implementer read `Template(s)` + `Rules`, the `/spec` session reads `When to use` /
`Hard stops` as classification rules. Same document, different sections, different consumers.

Every skill follows the four-section body (see `.claude/skills/CONVENTIONS.md`): *When to use vs.
neighbours · Template(s) · Rules · Hard stops*. Use `meta-skill-author` to add one. Purity rules
(a skill must not know what invokes it; every must-hold rule needs a gate, not prose) live in
`PRINCIPLES.md` sections C and S4. Mechanical derivation (paths, naming, store profiles, substrate)
has one home: the `conventions` skill — toolchain commands live in `gate.py`, which `conventions`
cites, never restates.

## The target app's architecture (what the workflow produces)

A strict **hexagonal / four-layer** Python backend; the skills encode this house style:

- `domain/` — pure Python, zero third-party deps. Entities (mutable `@dataclass`, identity
  equality), value objects (`frozen`, value equality), enums (`StrEnum`), repository **protocols**
  (`IFooRepository`), capability **protocols** (`ICan<Verb>`), a single `exceptions.py` catalog.
  Audit timestamps are a DB-managed table convention, never domain fields — reads that need them
  return a read-model DTO projected from the row.
- `application/` — CQRS: thin command/query handlers over frozen DTOs; success-only structured
  logging; the only sanctioned `try/except` is the compensating-transaction pattern.
- `infrastructure/` — grouped by external **tech** (`postgres`/`qdrant`/`openai`/`jwt`), not by
  domain subdomain. Relational repositories use SQLAlchemy **Core** (never ORM); other stores use
  their own client (store profiles live in the `conventions` skill). Capability adapters wrap SDKs,
  `pydantic-settings`, the `dependency-injector` container in `containers.py`. Persistence is
  **polyglot**; the table schema is written once, migrations are Alembic-native and owned by the
  implementer.
- `restapi/` — FastAPI; thin routers, Pydantic schemas, a central `DomainError` handler. No
  business logic in routes.

Dependency direction points **inward** to the domain; ports live in the domain, adapters in
infrastructure — the architecture skills + the architecture-rule test firewall enforce this. Tests
follow a no-mocks pyramid: unit tests use in-memory fakes, integration tests run real backends via
testcontainers; every acceptance criterion is pinned by an `@pytest.mark.ac("AC-n")`-marked test.

## Common commands

The project uses **uv** and targets **Python 3.12**.

Every tool is reached through one shim, `bin/adw.py` (T15). At a plain terminal name it by path;
inside a session, shipped files use `"${CLAUDE_PLUGIN_ROOT}/bin/adw.py"`, which resolves in both
layouts (see `notes/21`) — the two are the same file.

```bash
# the single point of truth for "green"
uv run .claude/bin/adw.py gate                      # --criteria to cross-check criteria.md flips

# acceptance preconditions
uv run .claude/bin/adw.py accept <context>/NNN

# the red baseline, and the criteria lint
uv run .claude/bin/adw.py red-check --change <context>/NNN
uv run .claude/bin/adw.py criteria-lint <path-to-criteria.md>

# the meta layer's own suite (must pass with no src/ in the tree — T15's acceptance test)
uv run pytest .claude/tools

# the build-out itself: execute ONE task with the v3-builder agent
/build-task tasks/TNN-<slug>.md         # tick tasks/INDEX.md only on green verification
```

`mypy` stays load-bearing (contract drift shows up as type errors), but the command you run is
`gate.py` — the toolchain config lives inside it, so there is exactly one definition of "green".

## Conventions when extending the workflow

Consult `PRINCIPLES.md` before a load-bearing choice — notably: S1 (behaviour, not construction, in
specs), S3 (criteria are observable behaviour; append-only for agents), S4 (a must-hold rule lives
in a gate, not prose), S8 (hooks are ergonomics; trust is the baseline check), S9 (branch per
change), C-section for skills, D-section for roles and file ownership (tests vs src).

Placement facts: a new skill goes in `.claude/skills/` via `meta-skill-author`; a new use case goes
in `specs/use-cases/` via `meta-uc-author`; a new must-hold rule goes into `gate.py`/`accept.py`
with a test, or is consciously demoted to advice.
