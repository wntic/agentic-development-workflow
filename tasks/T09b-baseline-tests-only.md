# T09b — red-baseline commit must be tests-only (anti-collusion)

## Goal
Close the T09 finding-2 hole deterministically. test-author's `disallowedTools` denies
Edit/Write on `src/**`, but a Bash write (`echo > src/foo.py`) bypasses it (bash_guard can't
role-scope — F-2). The builder claimed red_check catches it; it only catches the case where
the seeded src makes tests pass (green-before-implementation). A test-author that seeds
*partial* src — tests still red — passes red_check and the collusion lands in the baseline.
Catch the artifact, not the actor (S8): the red-baseline commit must touch `tests/**` only.

## Depends on
T09.

## Read first
- `.claude/tools/red_check.py` — where it tags `baseline/<context>-NNN`.
- Spec §4 (D3 anti-collusion), S8; T09 finding 2.

## Deliverables
- `.claude/tools/red_check.py` — before tagging the baseline, assert the baseline commit's
  diff touches only `tests/**` (a removal-class change may also delete tests — still `tests/**`).
  Any `src/**` path in the baseline commit → refuse to tag, exit non-zero with the offending
  paths ("the red-tests commit wrote code — anti-collusion, §4/D3"). specs/change-dir files
  created by /spec are in an earlier commit, not the baseline commit, so they don't trip it —
  verify that assumption against how /implement sequences the commits.
- `.claude/tools/test_red_check.py` — cases: baseline commit with only tests/ → tags;
  baseline commit containing a src/ file → refused with the path named.

## Verification
- `uv run pytest .claude/tools/test_red_check.py` green with the two new cases.
- A hand-built fixture repo whose "red commit" includes `src/x.py` → red_check refuses to tag.

## Out of scope / Escalate if
- This does not try to prevent the Bash write (bash_guard can't role-scope); it invalidates
  the result, which is the S8 posture. If /implement's commit sequencing puts change-dir or
  other legitimate non-test files in the same commit as the red tests, widen the allowed set
  to exactly those and record why — do not weaken it to "anything but src".
