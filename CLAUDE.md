# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repository is

A Claude Code **marketplace** holding two plugins. `plugins/adw/` is a spec-driven agentic
development workflow for Python backends — the rest of this document is about it, and the red
lines govern it. `plugins/run-report/` is an observability tool (session transcripts → Markdown
report of how a run went), **deliberately outside the workflow and its red lines**: its script is
legal and does not count against the enforcement budget, whose check is scoped to `plugins/adw`. This repository is
not an application.

**Status: the workflow is being rebuilt for the fourth time.** The three previous attempts live in
git history under two tags — read this block before proposing any mechanism, because most
plausible-sounding ideas have already been built and measured once:

- `v2-archive` — YAML manifest + stdlib validator; attempt 1 (a code generator over a hand-written
  schema) lives inside its history.
- `v3-archive` — living specs + ~17 200 lines of enforcement: **64** build tasks, **0** features.

**Do not rebuild a deleted mechanism from memory.** Recover the real file from its tag
(`git show v3-archive:<path>`) and read what it actually cost. The most expensive lessons are
already distilled in `WORKFLOW.md` §8. The full pointer file this block replaced is itself in git
history: `git log --oneline -- HISTORY.md`, then `git show <sha>:HISTORY.md`.

The design is settled — [`WORKFLOW.md`](WORKFLOW.md). **Steps 1–4 of its §10 build order are closed.**
The adapter is written and installed (step 1); three real changes shipped in the probe project
`adw-probe` — 001 a short-URL service, 002 a read-model exposing a creation timestamp, 003 custom short
codes — each accepted, tagged and defect-logged. The plugin ships `plugins/adw/skills/` (30 house-style
skills), `agents/` (the four roles), `commands/` (`spec`, `build`, `accept`, `commit`) and `templates/`
— and deliberately no script and no hooks, ever.

Since then the skill catalog was restructured: the compressed 13-theme catalog was reverted to the 48
pre-merge skills and re-merged into 30, with the dead generations' vocabulary purged. Decision and
rationale: in git history — `git log --oneline -- plan/R00-skills-restructuring.md`, then
`git show <sha>:plan/R00-skills-restructuring.md`. Status table and the
measured before/after: [`plan/INDEX.md`](plan/INDEX.md).

Change 003 (custom short codes, 8 criteria) shipped on 2026-07-30, and its defect log is the step-3+
section of the retired `plan/FINDINGS.md`, in the registry's git history. That run is the first where the curve bent down — a bigger change cost
63m00s of compute against 002's 84m21s, and the orchestrator's share of output tokens fell from 77% to
59%. **It is not the last shipped change** — `adw-probe` went on to 004, 005 and 006, and a second
probe, `adw-rooms`, shipped 001 and 002; see the toolchain section below for how to count them.

**Step 4 — deciding the findings — was decided on 2026-07-31 and executed on 2026-08-01.** Its rulings
live in the retired `plan/FINDINGS.md` (registry's git history), section «Шаг 4, проход первый»; where that section disagrees with the older
`Решение отложено до` lines above it, **it wins**. It went through 31 entries — the 23 still open, plus
eight that turned out to have closed themselves sidelong. **15 closed with no edit at all**: those
eight, plus seven ruled "did not happen", each with the signal that would reopen it. The other 16 were
decided. The pass produced **exactly one new mechanism**: the implementer lays a skeleton before the
tests, which removes the cause of five entries instead of guarding against them. Everything else was
prose.

**So red line 3 now reads 3 features : 3 passes, and the next action is change 004, not another edit.**
It doubles as the scaffolding's first measurement — one run with a skeleton against three with the
deferred-import workaround.

Two habits worth carrying, both measured rather than asserted: a finding's disposition is the human's
call and arrives as its own commit; and the outcome to prefer is a finding that closes **without a
guard of its own** — F-10 by the restructuring, F-57 by paying it back, F-36 by holding three runs,
each with no mechanism at all; and F-29, F-38, F-40, F-51 and F-55 in this pass, which cost the one
mechanism named above and then closed five entries by removing their cause rather than watching for
it. Five entries for one mechanism is the trade this line is looking for; five mechanisms for five
entries is what killed attempt 3.

Where the record lives: the build record task by task is `plan/`; what the install actually did is
in git history — `git log --oneline -- plan/INSTALL-REHEARSAL.md`, then
`git show <sha>:plan/INSTALL-REHEARSAL.md`; open findings are the files of
`plan/findings/` — `ls plan/findings/` is the open list, and empty is good. The entry format and the
rules live in `plan/ORIENT.md` §5; the frozen `F-` series and everything already decided are in the
registry's git history (`git log -S 'F-NNN' --oneline`, then `git show <sha>:plan/FINDINGS.md`).

**Platform knowledge in this repo was two generations stale**, which is part of why the previous
attempt is gone. [`plan/PLATFORM.md`](plan/PLATFORM.md) is now the authority: nine questions measured
by experiment against `2.1.220`, each with the command and its output. A fact absent from it is **not
measured**, and "I don't know" is the correct answer. What it covers: the accepted forms of a plugin
skill name in `skills:` (and that a wrong form is silently ignored); that `tools:` without
`Write`/`Edit` does not prevent writing when `Bash` is present; what `maxTurns` counts and that hitting
it is silent; that plugin subagents ignore `permissionMode` / `hooks` / `mcpServers`; agent-file
hot-reload between turns **and its new-directory caveat** — the first file in a freshly created
`agents/` directory is *not* picked up without a restart; that `skills:` accepts a block list and
preloads every entry;
**that a subagent auto-invokes a skill by description with no `skills:` field at all, provided `Skill`
is in its `tools:`**; that `paths` does not require the matching file to exist yet; and **that a
subagent's tool set resolves once, when the dispatch launches, and does not change while it runs —
`Skill` is reachable only when named in `tools:` or when `tools:` is omitted entirely, and neither the
width of the list nor a `skills:` field opens it** (question 9).

Question 9 also carries a correction worth reading before trusting any timeline in this repo. It was
raised by an observation that looked like mid-flight re-resolution; the observation was **a timezone
error in its own table** — session times taken as UTC from a transcript, the commit time as local
`+05:00` from `git log`. In one zone the edit landed 4h45m *before* the session started, so nothing
was re-resolved and there was no mystery. The restart claim it was said to contradict is therefore
**unverified, not refuted** — and what happens to a `skills/` directory created *after* a session
starts is one of the file's several items marked НЕ ПРОВЕРЕНО, each carrying the experiment that would
settle it (F-60).

Before designing any mechanism, **check the docs rather than recalling them** — four mechanisms of the
previous attempt were made redundant by features that already existed.

## Language

**English for everything the workflow ships or produces** — skills, commands, agents, code, commit
messages. A ruling of 2026-08-09 widens this from "ships" to the file type: **every agent, skill and
command file is strictly English wherever it lives**, project-scoped dev tooling under `.claude/`
included. Russian appears in such files only as data — quoted identifiers of the dev record (task-file
section names) or output destined for it (the warden verdict form, the `НАХОДКА` draft skeleton). The
dev record (`plan/`, `research/`) and dialogue follow the user's language, which is
Russian. **A commit message is English whatever the commit touches**: a `plan:` commit is a message
about the dev record, so it falls under both sentences, and the first one wins. That seam is the
common case here, not a corner — `plan:` is most of this repository's commits (F-186, where seven
went out in Russian and every one of them was a `plan:`). Commands the workflow ships defer to *the
consuming project's* dialogue language.

## The design

**[`WORKFLOW.md`](WORKFLOW.md) is the design canon — read it before touching anything.** It carries
the spec store, the artifact formats, the four roles, the three commands, the greenfield ruling, and
§8 "what we deliberately do not build", which is the anti-regrowth device. The reasoning behind it —
14 sources, the weighing of alternatives — is in
[`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md).

In one breath: a living spec per capability that compounds; each change arrives as a delta in
OpenSpec's `ADDED`/`MODIFIED`/`REMOVED` + `WHEN … THEN` form and is deleted on acceptance; criteria
are observable behaviour pinned by `@pytest.mark.ac("<criterion-slug>")` tests — the checklist line
carries an ordinal for humans to point at, the marker carries only the slug, because the marker
namespace spans the whole tree and an ordinal answers "is this criterion covered" with a false yes
(measured, F-54); the red phase and the green phase each get a verdict from an agent that
did not author it (four roles, the implementer dispatched twice: **implementer lays the skeleton** →
test-author → test-review → implementer writes the code → evaluator); "green" is `make check` —
**zero scripts of our own**; bypass is caught by reading `git diff`, not by a machine; one branch
per change.

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
produces no file omits `Template(s)`. The template section carries an allowance in two forms, both
stated in `meta-skill-author` rule 1. **A skill covering several artifacts may group its templates
under topical `##` headings instead**, with the templates as `###` inside — legal since the step-4
ruling on F-58, on one condition: the heading must **name an artifact** (`## The Table`), not a subject
of discussion (`## Notes`). **A heading carrying one template may read in the singular or name the form
under it** — `## Template`, `## Template — async, SDK-client form`, `## Skeleton — router file` —
legal since the ruling on F-79 of 2026-08-02, which chose to legalise the headings already in the tree
rather than rename them, there being no measurement that a name variant ever cost anyone a template.
Each form rests on evidence of success rather than a test of failure, so each carries the same
withdrawal condition: if a template is ever missed under such a heading, that form goes.

Counted in the tree rather than from the register, and the count ages — recheck it with the command
rather than trusting this line:

```bash
ls -d plugins/adw/skills/*/ | wc -l                                # skills in total
grep -l '^## Template(s)' plugins/adw/skills/*/SKILL.md | wc -l    # carrying the canonical heading
```

The skills the second command does not list split three ways, and all three are legal: reference skills
that omit the section by rule; skills grouping topically; and skills carrying a singular or named
heading. Read the split out of the tree the same way — the commands are the source, and the shape of
each group is `meta-skill-author` rule 1, not a number here.

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
and written in `plugins/adw/commands/`. `/adw:build` runs eight numbered steps, 0–7; step 1 is the
skeleton, new since step 4, and **it has been exercised** — change 004 was its first run and
`commands/build.md` cites that run as a measurement. The cycle has now been run against **nine**
accepted changes across two probes; count them rather than trusting this line, because it is the line
that went stale once (F-258):

```bash
cd ~/Projects/adw-probe && git tag        # change/NNN
cd ~/Projects/adw-rooms && git tag        # change/NNN
```

Two projects and not three: the count runs over the probes the workflow is carried forward on, and a
one-off greenfield run once for feedback with no continuation is not a consuming project and does not
enter red line 3's count (human ruling, 2026-08-09) — so a `change/NNN` tag in some other project is
not a hole in this list.

The defect logs for the first three are in the retired `plan/FINDINGS.md` — in the registry's git
history — under the step-2, step-3 and step-3+ headings, and the rulings that followed them under
«Шаг 4, проход первый»; everything after that is in the numbered `S0N`/`S10` sections of `plan/INDEX.md`.
Inside a consuming project everything the plugin ships carries the `adw:` prefix — `/adw:build`,
`adw:test-author`, `adw:conventions`. In this repository the skills load instead from the `.claude/skills`
symlink, and the commands from the real directory `.claude/commands` — four per-file symlinks to the
cycle commands (measured in `plan/PLATFORM.md` question 10) plus local dev commands — all answering to
short names (`/spec`), while the four cycle agents are not symlinked
at all, so they have no subagent type here; `.claude/agents/` holds the four repo roles. The short
names and the per-file symlinks are measured in `plan/PLATFORM.md` question 10; the rest of the
install record is in git history — `git log --oneline -- plan/INSTALL-REHEARSAL.md`, then
`git show <sha>:plan/INSTALL-REHEARSAL.md`. Do not enable both loads at once.
