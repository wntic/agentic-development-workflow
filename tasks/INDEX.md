# v3 build-out — task index

Decomposition of `workflow_v3_spec.md` §10 (WP1–WP7) into single-session tasks.
Each task is one file in this directory, executed by the `v3-builder` agent via
`/build-task tasks/TNN-<slug>.md`. The spec is the source of truth — task files POINT at
spec sections, they do not restate them; on any conflict the spec wins and the builder
escalates instead of improvising.

## Task file format (all tasks follow it)

- **Goal** — one paragraph.
- **Depends on** — tasks that must be `[x]` first.
- **Read first** — spec §§, notes, existing files the builder must read before writing.
- **Deliverables** — exact paths.
- **Steps** — ordered work items.
- **Verification** — commands the builder RUNS and their expected outcomes; a task is done
  only when these pass. Checks the builder cannot run (interactive commands, human review)
  are listed under "Human verification" and left to the operator.
- **Out of scope / Escalate if** — hard boundaries.

## Status

- [x] T01 — Rewrite CLAUDE.md + PRINCIPLES.md (WP1a)
- [x] T02 — Harvest agent prompts, purge v2 machinery (WP1b)
- [x] T03 — Spec format: templates + criteria lint + /spec (WP2)
- [ ] T04 — gate.py + its test suite (WP3a)
- [ ] T05 — accept.py + its test suite (WP3b)
- [ ] T06 — Enforcement wiring: hooks, ESCALATE, bypass tests (WP3c)
- [ ] T07 — Paid-fixes inventory + test-principles rewrite (WP4a)
- [ ] T08 — Skill catalog merge 44 → ~13 (WP4b)
- [ ] T09 — Cycle agents + /implement + /abandon (WP5)
- [ ] T10 — /accept-change command (WP6)
- [ ] T11 — E2E probe runbook (WP7, human-driven)

## Dependency order

```
T01 ──► T02 ──────────────┐
  └───► T03 ──────────────┤
T02 ──► T04 ──► T05 ──────┼──► T09 ──► T10 ──► T11
          └───► T06 ──────┤
T07 ──► T08 ──────────────┘
```

Parallelizable groups: {T03, T04, T07} after T02 · {T05, T06, T08} after their parents.
Gate before T09: T06's bypass tests MUST be green — spec §10: "без enforcement v3 — это
v2 минус валидатор, то есть хуже v2".

## Rules for whoever drives this

1. One task per `v3-builder` dispatch. Tick the checkbox here only after Verification passed.
2. The builder never edits `workflow_v3_spec.md`, `notes/15_v3_design_review.md`, or task
   files (except this INDEX's checkboxes). Design questions → escalate to the human.
3. Every manual workaround during a task is a finding — recorded in the task report and,
   during T11, in the defect log (the notes/pipeline_dryrun_feedback.md honesty discipline).
4. **Branch base during the build-out:** until `markdown-specs` merges into `main`, it plays
   `main`'s role for S9 — `change/<context>-NNN` branches base on it and `accept.py` merges
   back into it (`main` is still the v2 archive). Revisit after T11.
