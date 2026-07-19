# T01 — Rewrite CLAUDE.md + PRINCIPLES.md (WP1a)

## Goal
Make a fresh session orient on v3, not v2: CLAUDE.md describes the markdown-spec workflow;
PRINCIPLES.md carries the S-series. Until this lands, every session starts with a false map.

## Depends on
None (first task).

## Read first
- `workflow_v3_spec.md` — whole document (§0–§12).
- `notes/15_v3_design_review.md` — the four cross-cutting themes.
- Current `CLAUDE.md` and `PRINCIPLES.md`.

## Deliverables
- `CLAUDE.md` — rewritten.
- `PRINCIPLES.md` — updated.

## Steps
1. Rewrite `CLAUDE.md`:
   - Language rule, "what this repository is" (meta vs target layers) — keep, updated to v3.
   - The three v3 layers (spec §1), the spec store shape (§2, capability files), the three
     commands + `/abandon` (§6), the roles table (§4), enforcement summary (gate.py/accept.py
     as trust anchors, S8/S9 in one breath each).
   - v2 becomes ONE archive paragraph: proven e2e, lives in `main` history (link the tag/
     commit range), design doc `codegen_workflow_spec.md` kept for rationale.
   - Repository map updated (tasks/, .claude/tools/gate.py etc. — as they WILL be; mark
     not-yet-built items as planned with their task id).
   - Common commands: point at `uv run .claude/tools/gate.py` (planned, T04) instead of the
     deleted validator.
2. Update `PRINCIPLES.md`:
   - Replace the whole B-section with the S-series — copy S1–S9 verbatim from spec §11.
   - A2 → "spec files are canonical for intent, code for implementation, verdict for
     conformance"; A1/A3/A4 kept (A4 unchanged); C-section kept (C5 note: enforced via the
     §7.5 coverage surrogate); D1/D3 kept; D4 reformulated (tests vs src, per spec §4);
     F1 kept.
   - Keep the file's own canon: trigger → litmus → why → reference; verdicts here, rationale
     in workflow_v3_spec.md.

## Verification
- `grep -c "S8\|S9" PRINCIPLES.md` ≥ 2; `grep -n "B1 ·\|B2 ·" PRINCIPLES.md` → empty.
- `grep -n "manifest is canonical\|Манифест.*канони" CLAUDE.md PRINCIPLES.md` → empty
  (except the v2 archive paragraph).
- `grep -n "gate.py" CLAUDE.md` → present; `grep -n "/spec\b" CLAUDE.md` → present.
- CLAUDE.md `@`-includes PRINCIPLES.md still (unchanged mechanism).

## Human verification
- Open a fresh session, run `/orient`: the summary must describe v3 and name the next task.

## Out of scope / Escalate if
- Do NOT delete any v2 file (that is T02). Do NOT touch skills. If a spec §11 principle
  seems to contradict a kept principle, escalate — don't resolve silently.
