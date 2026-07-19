# T07 — Paid-fixes inventory + test-principles rewrite (WP4a)

## Goal
Before any skill merging: a machine inventory of every paid-for fix in the current 44-skill
catalog, and a rewritten meta-test that greens it. The guard is built BEFORE the thing it
guards changes (V-07: "лиса сторожит курятник" otherwise).

## Depends on
None (parallel to T03/T04), but MUST complete before T08.

## Read first
- Spec §7.3 (the named minimum), `notes/14_dryrun_fix_plan.md` (P1/P2 fixes + N-01/N-02),
  `notes/15_v3_design_review.md` V-07, current `.claude/skills/` catalog +
  `.claude/skills/test-principles/SKILL.md`.

## Deliverables
- `.claude/tools/test_skill_catalog.py` — pytest: for each inventoried fix, a grep-class
  assertion that the knowledge exists SOMEWHERE in the catalog (path-agnostic — must survive
  the T08 merge unchanged).
- `.claude/skills/test-principles/SKILL.md` — rewritten to describe this meta-test as the
  catalog's guard (skill purity rules C1–C3 respected: no manifest/runner mentions).

## Steps
1. Build the inventory from notes/14 + spec §7.3. Minimum entries (one test each):
   F-013 root-conftest-no-create_app · F-015 failure-state-then-reraise sanctioned ·
   F-016 best_effort-optional · F-018 fake stores/returns copies + `updated` log ·
   F-019 concrete-service-not-structurally-fakeable · F-004 workspace_id/tenant stamping ·
   N-01 import-from-immediate-parent · N-02 getattr-on-FastAPI-internals ·
   assert-strength recipes (7 of them) · two-sub-template idioms (auth-optional,
   relational-optional) · the standing bans (ORM, cursor pagination, inline type-ignore,
   `from __future__`, hardcoded versions/B8 floors rule).
2. Each assertion greps for the CONTENT signature (distinctive phrase/pattern), not the
   file path — merged catalogs must pass without edits to this suite.
3. Rewrite test-principles skill: what the meta-test guards, how to extend it when a new
   paid lesson lands (one entry per closed finding).

## Verification
- `uv run pytest .claude/tools/test_skill_catalog.py` green against the CURRENT (unmerged)
  44-skill catalog — proves the patterns are correct before T08 touches anything.
- Suite has ≥ 15 named entries; each cites its F/N id in the test name.

## Out of scope / Escalate if
- No skill merging here. If a notes/14 fix cannot be located in the current catalog (already
  lost?), that's a FINDING — record it, don't paper over.
