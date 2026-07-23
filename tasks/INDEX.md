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
- [x] T04 — gate.py + its test suite (WP3a)
- [x] T04b — Docker-skip carve-out in gate's inventory check (design ruling on T04 finding 2)
- [x] T05 — accept.py + its test suite (WP3b)
- [x] T06 — Enforcement wiring: hooks, ESCALATE, bypass tests (WP3c)
- [x] T06b — Tighten bash_guard toward precision (T06 finding 3 false positives)
- [x] T07 — Paid-fixes inventory + test-principles rewrite (WP4a)
- [x] T08 — Skill catalog merge 44 → ~13 (WP4b)
- [x] T04c — no-ORM + no-mocks grep-gates in gate.py (T08 finding 5; do BEFORE T09)
- [x] T04d — narrow no-mocks off monkeypatch (T04c finding 5 false positive; do BEFORE T09)
- [x] T09 — Cycle agents + /implement + /abandon (WP5)
- [x] T09b — red-baseline commit must be tests-only (T09 finding 2 anti-collusion)
- [x] T10 — /accept-change command (WP6)
- [x] T10b — accept.py honours a multi-target placement map (T10 finding 2; before T11 IFF the probe goes multi-target)
- [x] T06c — SubagentStop must hold only the implementer (greenfield-probe F1 bug; blocks a clean re-run)
- [x] T09c — greenfield bootstrap (bootstrap.py) — **REVERTED 2026-07-22.** bootstrap.py was a
  v1/v2 codegen regression (a script emitting the app shell; D1/A3). Replaced by **approach A**:
  the substrate is an external-template precondition and the workflow is brownfield-only. Spec §9
  rewritten, `bootstrap.py` + `test_bootstrap.py` removed, `/implement` §0.5 dropped.
- [x] T09d — evolving/conditional substrate ownership — **RESOLVED by T12.** Conditional deps
  (relational / auth / multipart) are the **test-author's** pre-baseline concern, per change, declared
  from the Interface sketch — never predicted into a template or a script.
- [ ] SKILL-GATE — architecture/restapi skill templates must be gate-clean under RUFF_SELECT (still
  live, and now a T12 dependency: the implementer writes the app shell from these skills, so the
  emitted code must pass the gate's ruff select). Core tension: the architecture re-export contract
  mandates `from .module import *` → F403/F405. See `tasks/SKILL-GATE-templates-gate-clean.md`.
- [x] TEMPLATE — external project scaffold — **DROPPED (superseded by T12).** A scaffold template that
  ships fastapi/a shell re-encodes the prediction the workflow must not do; agents own deps + shell,
  and new-project setup is plain `uv init` + the installed plugin.
- [ ] T12 — agents own dependencies and the app shell (dissolve bootstrap AND the template):
  test-author lands the change's deps in a pre-baseline commit (from the Interface sketch);
  implementer writes the behaviorless shell from the skills; `red_check` gains a greenfield
  collection-error fallback (static AST marker scan). `gate.py` untouched. See `tasks/T12-*.md`.
- [ ] T11 — E2E probe runbook (WP7, human-driven). Greenfield e2e runs after T12: `uv init` project →
  `/spec` → `/implement` reaches green with no bootstrap and no template; thereafter brownfield.

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
