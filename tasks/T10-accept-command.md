# T10 — /accept-change command (WP6)

## Goal
The human-facing acceptance flow on top of accept.py: gates → LLM contradiction-hunt →
human review of the merge diff → execute.

## Depends on
T05, T09.

## Read first
- Spec §5.4 (script vs command split — 5.4.5b lives HERE), §6 `/accept-change`, §2
  (merge/tag/delete semantics).

## Deliverables
- `.claude/commands/accept-change.md`: run `accept.py <id>` (check mode) → if gates fail,
  stop with the report → run the contradiction-hunt pass (LLM reads the merge diff + the
  affected context's spec files, lists corpus statements contradicting the delta — output
  appended to the review material) → present merge diff + flags (Affects-intersections,
  spec-lint, fidelity report) to the human → on approval run `accept.py <id> --execute` →
  relay the drift-check report.

## Steps
1. Command procedure text; every deterministic claim delegates to accept.py (no gate
   duplicated as prose — S4).
2. The contradiction-hunt prompt: scoped to the affected context, output format = list of
   (file, quoted statement, why it conflicts) — empty list is a valid result.

## Verification
- `grep -n "accept.py" .claude/commands/accept-change.md` → both check and --execute calls
  present; no gate condition stated as prose-only (review the text against §5.4's six gates:
  each is either "accept.py does it" or explicitly human).

## Human verification
- Full pass on the toy change from T09's smoke: gates green → review → merge to main → tag
  present → change dir gone → drift-check clean.

## Out of scope / Escalate if
- No batch-accept (deferred to post-T11 by the spec). No accept.py changes (that's T05;
  if a gap surfaces, escalate with the failing scenario).
