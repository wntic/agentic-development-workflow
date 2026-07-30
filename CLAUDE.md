# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repository is

A Claude Code **marketplace** holding one plugin, `plugins/adw/` — a spec-driven agentic
development workflow for Python backends. It is not an application.

**Status: the workflow is being rebuilt for the fourth time.** Three previous attempts are in git
history under tags; [`HISTORY.md`](HISTORY.md) is the pointer, and it is short. Read it before
proposing any mechanism — most plausible-sounding ideas have already been built and measured once.

The design is settled — [`WORKFLOW.md`](WORKFLOW.md) — and **step 1 of its §10 build order is
closed**: the adapter is written and installed at least once. The plugin now ships
`plugins/adw/skills/` (the house-style catalog), `agents/` (the four roles), `commands/`
(`spec`, `build`, `accept`, `commit`) and `templates/` (the artifacts those commands fill) — and
deliberately no script and no hooks, ever. The build record, task by task, is `plan/`; what the install
actually did is [`plan/INSTALL-REHEARSAL.md`](plan/INSTALL-REHEARSAL.md), and the findings step 1 left
undecided are [`plan/FINDINGS.md`](plan/FINDINGS.md).

**Next is step 2: one real change in a real project** — no second iteration of the workflow before a
feature ships (red line 3). Findings from step 1 are decided at step 4, not while step 2 runs.

**Platform knowledge in this repo was two generations stale**, which is part of why the previous
attempt is gone. Checked against `code.claude.com/docs` on 2026-07-29: subagent frontmatter now
carries `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills` (preloads full
skill content at startup), `mcpServers`, `hooks`, `memory`, `background`, `effort`,
`isolation: worktree`, `color`, `initialPrompt`; plugin subagents ignore `hooks`, `mcpServers` and
`permissionMode`; agent files hot-reload; and custom commands and skills are now one registry.
Before designing any mechanism, **check the docs rather than recalling them** — four mechanisms of
the previous attempt were made redundant by features that already existed.

## Language

**English for everything the workflow ships or produces** — skills, commands, agents, scripts and
their comments, code, commit messages. The dev record (`research/`) and dialogue follow
the user's language, which is Russian. Commands the workflow ships defer to *the consuming
project's* dialogue language.

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
frontmatter `description` + `when_to_use` (≤1536 chars combined, works in subagents too).

Every skill body has the same four sections: *When to use vs. neighbours · Template(s) · Rules ·
Hard stops*. A theme past ~500 lines becomes a thin router `SKILL.md` plus one `<topic>.md` per
artifact — only `SKILL.md` is injected on auto-invocation, so the router's pointers are
instructions the agent acts on, not cross-references. Format details:
`plugins/adw/skills/meta-skill-author/SKILL.md`, with the placeholder vocabulary beside it in
`meta-skill-author/CONVENTIONS.md`. Add a skill with `meta-skill-author`.

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
and written in `plugins/adw/commands/`. It has not yet been run against a real change — that is step 2.
Inside a consuming project everything the plugin ships carries the `adw:` prefix — `/adw:build`,
`adw:test-author`, `adw:conventions`. In this repository the commands and skills load instead from the
`.claude/` symlinks and answer to short names (`/spec`), while the four cycle agents are not symlinked
at all, so they have no subagent type here; `.claude/agents/` holds the three build roles only. Both
observations are measured in `plan/INSTALL-REHEARSAL.md` §6. Do not enable both loads at once.
