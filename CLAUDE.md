# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repository is

A Claude Code **marketplace** holding one plugin, `plugins/adw/` — a spec-driven agentic
development workflow for Python backends. It is not an application.

**Status: the workflow is being rebuilt for the fourth time.** Three previous attempts are in git
history under tags; [`HISTORY.md`](HISTORY.md) is the pointer, and it is short. Read it before
proposing any mechanism — most plausible-sounding ideas have already been built and measured once.

Right now the plugin ships **the knowledge layer only**: `plugins/adw/skills/` (the house-style
catalog) plus `plugins/adw/commands/commit.md`. There is no change cycle, no gate script, no hooks.
That is the intended starting state, not an unfinished migration.

## Language

**English for everything the workflow ships or produces** — skills, commands, agents, scripts and
their comments, code, commit messages. The dev record (`research/`) and dialogue follow
the user's language, which is Russian. Commands the workflow ships defer to *the consuming
project's* dialogue language.

## The direction that was chosen

From [`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md) — read §7 for the
weighing and §8 for the red lines. The chosen architecture (variant C):

- **Living spec per capability + a delta per change.** The delta format is OpenSpec's, taken
  verbatim rather than reinvented: `ADDED` / `MODIFIED` / `REMOVED Requirements`, scenarios as
  `WHEN … THEN`. On acceptance the delta merges into the living spec and is deleted.
- **Every acceptance criterion is pinned by a test** carrying `@pytest.mark.ac("AC-n")`. A
  criterion may be ticked only against a **passed** marked test in the run's junit report.
- **One check script, ≤300 lines.** It runs `ruff` + `mypy` + `pytest --junit` and cross-checks the
  criteria checklist against the junit. That is the whole enforcement layer.
- **A fresh-context evaluator subagent** renders the verdict — the one role the research backs with
  a measurement (agents reliably over-grade their own work).
- **A branch per change; the base branch stays green.** This costs zero lines: it is git.
- **Bypass is handled by human review of the merge diff**, not by a gate. The industry does it this
  way; the previous attempt spent ~17 000 lines not doing it this way.

## The five red lines

These exist because each one names a measured failure of attempt 3, not a taste.

1. **No mechanism without a measured failure it fixes.** Not an imaginable one — a recorded case
   with a date. Attempt 3 was designed against 55 *imaginable* failures found by an adversarial
   review held before implementation. That review is the origin of the 17 000 lines.
2. **The enforcement budget is a number, not an intention.** If a rule does not fit inside
   `ruff` + `mypy` + `pytest` + ≤300 lines of glue, it is consciously demoted to advice in a skill.
   A demoted rule is a decision, not a defeat.
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

## How skills work

A skill is **knowledge injected into context, not an executor**. Skills auto-invoke on their
frontmatter `description` + `when_to_use` (≤1536 chars combined, works in subagents too).

Every skill body has the same four sections: *When to use vs. neighbours · Template(s) · Rules ·
Hard stops*. A theme past ~500 lines becomes a thin router `SKILL.md` plus one `<topic>.md` per
artifact — only `SKILL.md` is injected on auto-invocation, so the router's pointers are
instructions the agent acts on, not cross-references. Format details:
`plugins/adw/skills/CONVENTIONS.md`. Add a skill with `meta-skill-author`.

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

```bash
uv run ruff check                 # the whole toolchain this repo currently has
uv run pre-commit run --all-files
```

There is no `gate` command any more, and adding one back is a decision governed by red line 2.
