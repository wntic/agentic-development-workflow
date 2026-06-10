---
description: "Phase 1 — Refinement: raise the epic's product questions for the BA (questions_for_ba.md), then fold the answers into TBD-free UC-NNN.refined.md (spec §1)"
argument-hint: "(empty = all epics, each in turn)  |  <epic-slug or NN to narrow to one>"
---

You dispatch the **analyst** as a subagent to run phase-1 refinement (spec §1). The unit of work is the
epic, but the command refines *use cases* — like `/ingest-usecases`, a bare invocation covers the whole
corpus and an argument narrows. Unlike ingestion, refinement is **not interactive** — its channel is a
file the BA fills asynchronously — so this is a fire-and-forget subagent, not a main-loop conversation.
The analyst raises only PRODUCT questions (architecture questions stay in `epic.md` for the architect)
and never edits the verbatim source under `specs/use-cases/`.

`$ARGUMENTS` is an **optional scope filter**: a single epic (slug or `NN`). **Empty = every epic**, each
handled in turn — the epic is a narrowing, not the command's identity (this is the symmetry with
`/ingest-usecases`: bare = whole corpus, arg = narrow).

## 1. Resolve scope

Run `ls specs/epics/`. With an argument, resolve it to a single `specs/epics/<NN>-slug/`; **empty → every
epic** under `specs/epics/`. Each must contain `epic.md` — if none exist, stop and point at
`/ingest-usecases`. State the epic(s) in scope.

## 2. Dispatch the analyst — one subagent per epic in scope

For each epic in scope, spawn one **`analyst`** subagent (it loads its own role doc). One subagent
handles exactly one epic; several epics in scope mean several dispatches, run in turn. Each invocation
prompt carries only:

- the epic folder path and the member UCs it covers (from `epic.md`);
- the instruction: **run phase-1 refinement** — read `epic.md` + the member UCs, then per the analyst
  role doc's procedure either **generate** `questions_for_ba.md` (when it is absent or still has
  `_(pending)_` slots) or **fold** the BA's answers into `UC-NNN.refined.md` (when every slot is filled);
- the guardrails: PRODUCT questions only (architecture questions go to `epic.md`, never to the BA file);
  never edit `specs/use-cases/`; never invent an answer.

The state (generate vs fold) is the analyst's to detect from that epic's folder — do not pre-decide it.

## 3. Report + next step

Relay the analyst's report, then point at the next move:

- **generated questions** → the BA answers the `_(pending)_` slots in
  `specs/epics/<NN>-slug/questions_for_ba.md`, then re-run `/refine-usecases <epic>` to fold them;
- **folded answers** → the epic's UCs are TBD-free (`Status: refined`); the next stage is the architect,
  `/build-manifest <epic>` (forthcoming).

## Notes

- One epic per analyst dispatch — a subagent never fans out across epics; the command itself loops
  epics when scope is the whole corpus.
- A red flag worth surfacing: if the analyst finds a question it cannot classify as cleanly product
  *or* architecture, it should raise it rather than guess the channel (spec §1 — the two channels are
  load-bearing).
