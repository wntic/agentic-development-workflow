---
description: "Phase 2 (brownfield) — Apply a UC change as a delta on an existing manifest: locate the target context(s), author the in-place change, review the blast radius, validate to green, hand off the forward path (spec §1, §4, §8)"
argument-hint: "<UC id or epic-slug>  |  (empty = ask which change)"
---

You run the **architect's** delta path (spec §1 phase 2, §8) **interactively, in this main loop** — *not*
a fire-and-forget subagent, because the bounded-context call, the architecture questions, and the
blast-radius review are decided with the human in chat. Follow the architect role doc included below, and
do the **delta** path only — the from-scratch build is the separate `/build-manifest`.

Brownfield is the primary mode: a new or changed UC is a **delta** on an existing manifest, not a rebuild.
The forward path you hand off to is already brownfield-safe (re-`/scaffold` regenerates declarative/glue
and leaves filled bodies; `/verify` reconciles drift on the `NotImplementedError`/mypy-red trigger), so
your job is to author the delta and review its blast radius.

`$ARGUMENTS` is the change to apply — a UC id (`UC-NN`) or the epic slug it lands in. If empty, **ask**
which change. The UC must be refined (no TBDs); if it still carries TBDs, stop and point at
`/refine-usecases`.

## Steps

1. **Locate the target context(s).** Classify the change relative to the *existing* manifests (spec §7).
   It lands in the bounded context whose aggregates it changes — and may touch **more than one** manifest
   (a downstream consumer that needs an upstream context to expose a new method induces an upstream
   delta). Read every in-scope `manifest.yaml` first. If **no** manifest exists for the target context,
   stop and point at `/build-manifest` (this command is the delta-on-existing path).
2. **Resolve architecture questions** — the ones parked in the in-scope `epic.md`(s) plus any you surface.
   Raise them batched, in chat; fold the answers. Product questions route back to `/refine-usecases`.
3. **Author the delta in place** per the role doc — additive (new node/field/method/scenario), contract
   change (edit in place; record the reviewed `supersedes`/`replaces` where a prior contract is
   replaced), or cross-epic exposure (grow the upstream protocol; the downstream manifest carries the
   `a:IFoo.method` edge). Carry identifiers + edges + the three channels only; earn-its-place still holds.
   Update `sources` on every touched node. Author no table columns, migrations, code, or derived names.
4. **Compute and present the blast radius** — a deterministic graph query (who references the touched
   node). Show the human a ~5-line review (not YAML): nodes added/changed/superseded; which **declarative
   + glue** regenerate for free; which **body-bearing** files will drift red and why; any **table** field
   change that becomes a schema-drift → new Alembic revision. Surface any **orphan / rename** the delta
   implies — that is the unbuilt frontier (spec §4/§14): the graph says *who*, the human declares *how*
   (`replaces`/removal), never an agent guess.
5. **Validate to green** — `uv run .claude/tools/validate_manifest.py <manifest>` must report `ok` (for
   every manifest you touched). Cross-epic edges are warnings, not errors; a §16 presence-gap (a `kind`
   with no skill) is a **stop** → human-gated `meta-skill-author`; resolve loud-degradation warnings.
6. **Hand off the forward path** on approval: `/scaffold <manifest>` (re-runs on the existing tree —
   regenerates declarative/glue, lays down new body scaffolds, leaves filled bodies alone), then `/verify`
   (the runner fills the new scaffolds and reconciles the drifted bodies until the toolchain + canonical
   tests are green). Do **not** re-freeze the scaffold baseline over a filled tree (`scaffold_snapshot.py`
   refuses without `--force` — do not force it).

@agents/architect.md
