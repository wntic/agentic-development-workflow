---
description: "Stage 0 — Ingest use cases: propose an epic grouping + backend filter for approval, then write specs/epics/<NN>-slug/epic.md (spec §1)"
argument-hint: "(empty = all UCs)  |  <UC-id or epic-slug to (re)ingest as a delta>"
---

You run the **analyst's** stage-0 ingestion (spec §1) **interactively, in this main loop** — *not* as a
fire-and-forget subagent, because the epic grouping is approval-gated: you propose ~5 semantic lines and
the user approves before anything is written. Follow the analyst role doc included below, and do **stage
0 only** — refinement is the separate `/refine-usecases` command.

`$ARGUMENTS` is optional: a UC id or epic slug to (re)ingest as a delta; empty = all UCs under
`specs/use-cases/`.

## Steps

1. **Read existing epics first** (`ls specs/epics/ 2>/dev/null`) — brownfield is the default (spec §8): a
   new UC is a *delta* to an existing epic, not a reason to rebuild.
2. **Read the UCs** under `specs/use-cases/` (skip `*.proposed.md`, `*.partial.md`, `CHANGES.md`).
3. **Apply the backend filter** and **identify the aggregates** each UC touches.
4. **Propose** the grouping as a short review — each epic → member UCs → one-line rationale, plus
   cross-epic edges and any UI-phrased lines you are flagging as ambiguous. **Do not write yet.**
5. **Iterate to approval** (re-cluster / rename / split / merge as the user directs).
6. **On approval, write** `specs/epics/<NN>-slug/epic.md` per the role doc's template. If a folder
   already exists, show the delta and **ask before overwriting** (spec §4).
7. **Report** epics created/updated, UC assignment, cross-epic edges, flagged ambiguities, and the
   product-question seed count; then suggest `/refine-usecases <epic>`.

@agents/analyst.md
