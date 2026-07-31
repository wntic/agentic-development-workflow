# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repository is

A Claude Code **marketplace** holding one plugin, `plugins/adw/` — a spec-driven agentic
development workflow for Python backends. It is not an application.

**Status: the workflow is being rebuilt for the fourth time.** Three previous attempts are in git
history under tags; [`HISTORY.md`](HISTORY.md) is the pointer, and it is short. Read it before
proposing any mechanism — most plausible-sounding ideas have already been built and measured once.

The design is settled — [`WORKFLOW.md`](WORKFLOW.md). **Steps 1–3 of its §10 build order are closed.**
The adapter is written and installed (step 1); three real changes shipped in the probe project
`adw-probe` — 001 a short-URL service, 002 a read-model exposing a creation timestamp, 003 custom short
codes — each accepted, tagged and defect-logged. The plugin ships `plugins/adw/skills/` (30 house-style
skills), `agents/` (the four roles), `commands/` (`spec`, `build`, `accept`, `commit`) and `templates/`
— and deliberately no script and no hooks, ever.

Since then the skill catalog was restructured: the compressed 13-theme catalog was reverted to the 48
pre-merge skills and re-merged into 30, with the dead generations' vocabulary purged. Decision and
rationale: [`plan/R00-skills-restructuring.md`](plan/R00-skills-restructuring.md). Status table and the
measured before/after: [`plan/INDEX.md`](plan/INDEX.md).

**Red line 3 is satisfied for the first time: three shipped features against two completed passes of
workflow edits.** Change 003 (custom short codes, 8 criteria) shipped on 2026-07-30, and its defect log
is the step-3+ section of `plan/FINDINGS.md`. That run is also the first where the curve bent down —
a bigger change cost 63m00s of compute against 002's 84m21s, and the orchestrator's share of output
tokens fell from 77% to 59%.

So **step 4 — deciding the findings — is now legitimate**, where it was forbidden before. Two things to
carry into it: a finding's disposition is the human's call and arrives as its own commit, and three
findings closed themselves without a mechanism (F-10 by the restructuring, F-57 by paying it back,
F-36 by holding three runs in a row), which is the outcome to prefer over building a guard.

Where the record lives: the build record task by task is `plan/`; what the install actually did is
[`plan/INSTALL-REHEARSAL.md`](plan/INSTALL-REHEARSAL.md); open questions are
[`plan/FINDINGS.md`](plan/FINDINGS.md), read by header (`grep '^## F-'`) and never whole.

**Platform knowledge in this repo was two generations stale**, which is part of why the previous
attempt is gone. [`plan/PLATFORM.md`](plan/PLATFORM.md) is now the authority: eight questions measured
by experiment against `2.1.220`, each with the command and its output, plus one open question marked
НЕ ПРОВЕРЕНО with the experiment that would settle it. A fact absent from it is **not
measured**, and "I don't know" is the correct answer. What it covers: the accepted forms of a plugin
skill name in `skills:` (and that a wrong form is silently ignored); that `tools:` without
`Write`/`Edit` does not prevent writing when `Bash` is present; what `maxTurns` counts and that hitting
it is silent; that plugin subagents ignore `permissionMode` / `hooks` / `mcpServers`; agent-file
hot-reload and its new-directory caveat; that `skills:` accepts a block list and preloads every entry;
**that a subagent auto-invokes a skill by description with no `skills:` field at all, provided `Skill`
is in its `tools:`**; and that `paths` does not require the matching file to exist yet. The open one
(question 9) is whether a running dispatch's `tools:` is re-resolved mid-flight — raised by an
observation that contradicts a restart claim this repo previously asserted as fact (F-60).

Before designing any mechanism, **check the docs rather than recalling them** — four mechanisms of the
previous attempt were made redundant by features that already existed.

## Language

**English for everything the workflow ships or produces** — skills, commands, agents, code, commit
messages. The dev record (`plan/`, `research/`) and dialogue follow the user's language, which is
Russian. Commands the workflow ships defer to *the consuming project's* dialogue language.

## The design

**[`WORKFLOW.md`](WORKFLOW.md) is the design canon — read it before touching anything.** It carries
the spec store, the artifact formats, the four roles, the three commands, the greenfield ruling, and
§8 "what we deliberately do not build", which is the anti-regrowth device. The reasoning behind it —
14 sources, the weighing of alternatives — is in
[`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md).

In one breath: a living spec per capability that compounds; each change arrives as a delta in
OpenSpec's `ADDED`/`MODIFIED`/`REMOVED` + `WHEN … THEN` form and is deleted on acceptance; criteria
are observable behaviour pinned by `@pytest.mark.ac("AC-n")` tests; the red phase and the green
phase each get a verdict from an agent that did not author it (four roles: test-author →
test-review → implementer → evaluator); "green" is `make check` — **zero scripts of our own**;
bypass is caught by reading `git diff`, not by a machine; one branch per change.

## The two layers — core and adapter

Every file belongs to exactly one, and the split decides how much is thrown away at the next
platform change (`WORKFLOW.md` §1):

- **Core, 100% portable** — `specs/` entirely, skill bodies, `make check`, the branch+tag
  convention, the prose bodies of agent prompts. Markdown, git, make.
- **Adapter, Claude Code** — agent frontmatter (`tools`, `skills`, `model`, `maxTurns`,
  `isolation`), `commands/*.md`, the manifests. 4–7 small files, rewritable in an evening.
- **Zero** — hooks, logic in `settings.json`, any script against platform JSON payloads, any
  integrity check. These do not port, so they do not get written.

Commands live in `commands/`, knowledge in `skills/`. The platform merged the two registries, so the
old reason for keeping the directories apart is gone — but the split still says what each file is,
and `disable-model-invocation: true` / `user-invocable: false` now express the difference where it
matters.

## The seven red lines

Each names a measured failure, not a taste. Full form in `WORKFLOW.md` §9.

1. **No mechanism without a measured failure it fixes.** Not an imaginable one — a recorded case
   with a date. Attempt 3 was designed against 55 *imaginable* failures found by an adversarial
   review held before implementation. That review is the origin of the 17 000 lines.
2. **The enforcement budget is a number, not an intention.** Today the number is **zero**:
   `ruff` + `mypy` + `pytest` behind `make check`. A rule that does not fit is consciously demoted to
   advice in a skill. A demotion is a decision, not a defeat.
3. **The workflow may not spend longer building itself than it spends building applications.** Ship
   a feature of a target app before iterating on the workflow a second time. The score at
   `v3-archive` — 0 features against 64 build tasks — is what this line forbids.
4. **Defend against the honest mistake, not the adversarial agent.** An agent that faithfully built
   the wrong thing is measured and common; an agent that routes around a hook to cheat a gate is
   neither. Everything that guards against bypass waits for a real bypass.
5. **Every harness component is a hypothesis about a model limitation, and carries a review date.**
   Anthropic measured a construct that was load-bearing on Opus 4.5 and pure overhead on 4.6. Write
   down which limitation each mechanism compensates for, so it can be switched off when the
   limitation goes away.
6. **The portability budget.** The value lives in the core — Markdown, git, make. Keep the
   Claude-Code-specific part small enough to rewrite in an evening. *Test:* could this workflow be
   described to another agent through one `AGENTS.md` plus the same `specs/` tree? If a mechanism
   can't, it is an adapter detail and must stay small. Four mechanisms of the previous attempt were
   made **redundant** by the platform without anything breaking — you cannot defend against that
   with reliability, only with volume.
7. **The soft-degradation litmus.** Adopt a platform feature only if its disappearance degrades
   gracefully. `maxTurns` gone → the human notices the agent looping. `isolation: worktree` gone →
   `git worktree add` by hand. A broken hook → the session deadlocks outright (measured here on
   2026-07-29). That is failure, not degradation — so there are no hooks.

## How skills work

A skill is **knowledge injected into context, not an executor**. Skills auto-invoke on their
frontmatter `description` + `when_to_use` — capped at 1536 chars combined, and measured to work in a
subagent with no `skills:` field when `Skill` is in its `tools:` (`plan/PLATFORM.md` question 7). All
30 carry `description` + `when_to_use`; 24 also carry `paths`, the six without it being the
cross-cutting ones where a glob would exclude nothing.

The canonical body is four sections — *When to use vs. neighbours · Template(s) · Rules · Hard stops* —
with two optional helpers (*Inlined typing / import rules*, *Package wiring*). A reference skill that
produces no file omits `Template(s)`. **Five skills deviate**: they carry templates outside a
`## Template(s)` section because a merged skill covering several artifacts organizes by topic instead.
That is recorded, not endorsed — F-58.

**There are no router skills and no topic files.** A theme past ~500 lines was the documented signal to
split into a thin `SKILL.md` plus `<topic>.md` siblings; that shape is deliberately not used here,
because only `SKILL.md` is preloaded, so a pointer to a sibling is a read the agent must perform and may
not (F-10). The one non-`SKILL.md` file in the catalog is
`plugins/adw/skills/meta-skill-author/CONVENTIONS.md` — the shared placeholder vocabulary, the catalog
index and the format canon, a supporting file of the one skill that reads it. Add a skill with
`meta-skill-author`.

Two standing rules:

- **A skill must not know what invokes it.** No mention of agents, the change cycle, criteria
  files, or "report back". The test: would a new human developer read this line as onboarding
  docs? If they would trip over it, it is a leaked layer — cut it.
- **Derivation has one home.** Paths, naming, store profiles and substrate live in the
  `conventions` skill; toolchain commands live in the project's toolchain config, which
  `conventions` cites and never restates.

## The target app's architecture (what the skills encode)

A strict **hexagonal / four-layer** Python backend, `uv` and Python 3.12:

- `domain/` — pure Python, zero third-party deps. Entities (mutable `@dataclass`, identity
  equality), value objects (frozen, value equality), enums (`StrEnum`), repository protocols
  (`IFooRepository`), capability protocols (`ICan<Verb>`), one `exceptions.py` catalog. Audit
  timestamps are a DB-managed table convention, never domain fields — a read that needs them
  returns a read-model DTO projected from the row.
- `application/` — CQRS: thin command/query handlers over frozen DTOs, success-only structured
  logging. The only sanctioned `try/except` is the compensating-transaction pattern.
- `infrastructure/` — grouped by external **tech** (`postgres`/`qdrant`/`openai`/`jwt`), never by
  domain subdomain. Relational repositories use SQLAlchemy **Core**, never the ORM. Persistence is
  polyglot; migrations are Alembic-native.
- `restapi/` — FastAPI: thin routers, Pydantic schemas, one central `DomainError` handler. No
  business logic in routes.

Dependencies point **inward**. Tests follow a no-mocks pyramid: unit tests use in-memory fakes,
integration tests run real backends via testcontainers.

## Commands

This repo carries no application, so its own toolchain is two lines:

```bash
uv run ruff check
uv run pre-commit run --all-files
```

A *consuming* project's definition of "green" is its own `make check` — `ruff` + `mypy` + `pytest`,
and nothing of ours. Adding a script back is a decision governed by red lines 2, 6 and 7.

The workflow's own cycle is `/adw:spec` → `/adw:build` → `/adw:accept`, specified in `WORKFLOW.md` §6
and written in `plugins/adw/commands/`. It has been run against three real changes in `adw-probe`, all
accepted; the defect logs are in `plan/FINDINGS.md` under the step-2, step-3 and step-3+ headings.
Inside a consuming project everything the plugin ships carries the `adw:` prefix — `/adw:build`,
`adw:test-author`, `adw:conventions`. In this repository the commands and skills load instead from the
`.claude/` symlinks and answer to short names (`/spec`), while the four cycle agents are not symlinked
at all, so they have no subagent type here; `.claude/agents/` holds the three build roles only. Both
observations are measured in `plan/INSTALL-REHEARSAL.md` §6. Do not enable both loads at once.
