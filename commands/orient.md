---
description: "Session bootstrap — orient on the v3 workflow: read the design canon + task index, then summarize state and the next task"
---

> Invoked as `/adw:orient` when the workflow is installed as a plugin, `/orient` when it is
> loaded from a project's own `.claude/` — as in the workflow's own repo. The two forms name
> this same file; other commands are referred to below in the `/adw:` form.

You are joining work on **workflow v3** — a spec-driven agentic development cycle: living Markdown
specs per bounded context, a change cycle (red tests → code → run → criteria check → iterate), and
deterministic gates that hold the trust. The target application lives **in this repository**
(`src/`, `tests/`, `specs/<context>/`) and is maintained through the change cycle: one change =
one branch, `main` always green.

Before proposing or writing anything, **read and assemble the current picture** (in this order):

1. `workflow_v3_spec.md` — THE design doc and source of truth for v3, written as a build order.
   Read it **in full**. (`notes/15_v3_design_review.md` is the adversarial-review register behind
   its S8/S9 hardening; both are design canon — never edited by agents.)
2. `PRINCIPLES.md` — the decision checklist (*trigger → litmus → why → §*); it is already in
   context via `CLAUDE.md`, but confirm you hold the S-series (S1–S9).
3. `tasks/INDEX.md` — **the source of truth for build-out state**: which of T01–T11 are checked
   `[x]`, which are open, and the dependency order. Nothing marked *planned (TNN)* exists until
   its checkbox is ticked. Cross-check with `git status` / `git log` on the current branch.

Keep in mind:

- **Status: v3 is being built.** The build-out is decomposed into `tasks/` and executed one task
  per `v3-builder` dispatch via `/adw:build-task tasks/TNN-<slug>.md`.
- The trust anchors are two scripts: `gate.py` ("is it green", T04) and `accept.py` ("may it
  merge", T05); hooks are ergonomics — trust is the post-hoc check against the git baseline (S8).
- This command's §5.5 drift-check is **live** — run it and relay it, per the last section below.
- v2 is archived in the git history of `main` (tag `v2-archive`); its files were purged in T02 —
  recover them only from git history, never by rewriting. `codegen_workflow_spec.md` is kept for
  the rationale of what survived.

After reading:

- **Briefly (3–5 lines)** summarize the current build-out state and name **the next task per
  `tasks/INDEX.md`** (respecting the dependency order) — so the human sees you are up to date.
- **Do not touch code or propose edits until the direction is confirmed.** Discuss first, act
  second.
- Dialogue with the human follows the project's convention (see its `CLAUDE.md`; English if it
  sets none); everything that lands in the repo is in **English** (exceptions per `CLAUDE.md`:
  verbatim use cases, the living spec corpus under `specs/<context>/`, the design docs).

## The §5.5 drift-check — run it, relay it, judge nothing

One command answers both halves — the base's src commits tied to no `change/*` tag, and the
constructed app's OpenAPI routes against the capability files, in both directions:

```
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" drift
```

Print its report to the human **verbatim** and add nothing to its verdict. What each finding means
is in the report; what the check is *for* is spec §5.5 — a hotfix past the workflow is legal, it is
only not silent, and `/adw:spec --retro` legalises it after the fact. **It is not a gate**: it
surfaces, it never denies, so nothing here is yours to approve or refuse.

Two things the script deliberately leaves to you as its reader:

- a route reported as **not described** may still be described in prose that names neither its path
  nor its method — read the capability file the report names before concluding anything;
- an **UNDETERMINED** half means the comparison did not run (an app that will not construct, a base
  that will not resolve). That is not "clean" — say so plainly rather than reporting silence.

`--base <branch>` names the S9 base explicitly; omitted, it is the branch at HEAD, or — on a
`change/*` branch — derived the way `accept.py` derives it. The hotfix half **is** `accept.py`'s own
(it prints it after every `--execute`), so the two can never disagree.
