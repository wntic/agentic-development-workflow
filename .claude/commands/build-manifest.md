---
description: "Phase 2 — Build a manifest: propose the bounded-context boundary, resolve architecture questions, author specs/epics/<NN>-slug/manifest.yaml, validate to green (spec §1, §7)"
argument-hint: "<epic-slug or NN>  |  (empty = ask which epic)"
---

You run the **architect's** from-scratch manifest build (spec §1 phase 2) **interactively, in this main
loop** — *not* a fire-and-forget subagent, because the bounded-context boundary and the architecture
questions are decided with the human in chat. Follow the architect role doc included below, and do the
**build** path only — applying a delta to an existing manifest is the separate `/apply-delta`.

`$ARGUMENTS` is the starting epic (slug or `NN`). If empty and several epics exist, **ask** which.

## Steps

1. **Resolve the epic** to `specs/epics/<NN>-slug/`. It must hold `epic.md` and at least one
   `UC-NN.refined.md` (else the original UC). If the UCs still carry TBDs, stop and point at
   `/refine-usecases`. If a `manifest.yaml` already exists, stop and point at `/apply-delta` (this
   command is the from-scratch path).
2. **Propose the bounded context** (spec §7) — this epic alone, or merged with a neighbour whose
   aggregates change together. Present ~5 lines; the human approves before you model. Read any existing
   manifests first (a merge target may already have one).
3. **Resolve architecture questions** — the ones the analyst parked in each in-scope `epic.md` plus any
   you surface while modeling. Raise them batched, in chat; fold the answers. Product questions are not
   yours — route them back to `/refine-usecases`.
4. **Author the manifest** at `specs/epics/<NN>-slug/manifest.yaml` per the role doc: classify UC
   concepts into nodes via the skills, carry identifiers + edges only, write the three channels
   (`behaviour` verifies, `notes` guides, `sources` traces). Author no table columns, migrations, code,
   or derived names.
5. **Validate to green** — `uv run .claude/tools/validate_manifest.py <manifest>` must report `ok`. Fix
   form/graph errors; resolve loud-degradation warnings. A §16 presence-gap (a `kind` with no skill) is a
   **stop** → human-gated `meta-skill-author`, not improvisation.
6. **Present the review + next step** — the ~5-line semantic summary (nodes, key decisions, open
   cross-epic edges), not the YAML. On approval the manifest is ready for `/scaffold <manifest>`.

@agents/architect.md
