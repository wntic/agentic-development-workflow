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
- This command's drift-check — comparing capability files against the observable surface (OpenAPI
  routes) and listing `main` src-commits not tied to change tags (spec §5.5) — is *planned
  (T05/T10)*: it arrives with `accept.py` and `/adw:accept-change`; until then, skip that step.
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
