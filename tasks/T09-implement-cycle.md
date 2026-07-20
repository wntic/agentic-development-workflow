# T09 — Cycle agents + /implement + /abandon (WP5)

## Goal
The working loop: three role agents with deterministic tool scoping, the `/implement`
orchestration command with the contract-change protocol and per-class adversarial pass,
plus `/abandon`.

## Depends on
T03, T04, T06, T08.

## Read first
- Spec §4 (roles table incl. disallowedTools cells and the evaluator honesty rule),
  §6 `/implement`+`/abandon`, §5.3; `notes/15` F-2/F-7 (role scoping, sequential dispatch,
  no per-dispatch tool tuning), V-01, E-13, O-02.
- `notes/16_agent_prompt_harvest.md` — the ⚠ TRANSFER rows homed in T09: I1 (review-tail →
  the `[m]`-candidate mapping in the test-author report + the evaluator's per-AC
  PASS/FAIL/MANUAL-candidate verdict format) and the protocol sides of I3/C3. Close them or
  escalate — none silently dropped.
- T04b finding 2: the test-author, when it writes integration tests, follows the
  `testing-integration` Docker-absence rule (env guard is `skipif`, never a raising fixture) —
  otherwise the gate carve-out can't apply. The agent reads that skill; this task only needs
  to ensure the test-author's brief points at it.

## Deliverables
- `.claude/agents/test-author.md` — reads change.md + criteria.md + Interface sketch +
  relevant skills; writes red `ac`-marked tests; removal-class duties; NEVER writes src
  (`disallowedTools`: Edit/Write on src/**, criteria.md, verdict.md).
- `.claude/agents/implementer.md` — fills code until gate GREEN; owns Alembic revisions;
  CONTRACT-CHANGE protocol on Interface-sketch conflicts; (`disallowedTools`: Edit/Write on
  tests/**, specs/**, .claude/**, pyproject.toml).
- `.claude/agents/evaluator.md` — fresh-context verdict per §4 honesty rule
  (`disallowedTools`: Edit/Write on src/**, tests/**; writes only verdict.md + criteria flips).
- `.claude/tools/red_check.py` — script step: runs the new tests, asserts each is RED and
  each AC has ≥1 marked test (green-before-implementation is flagged); tags
  `baseline/<context>-NNN` on the red commit (T04's convention).
- `.claude/commands/implement.md` — the §6 procedure: steps 1–5 verbatim in intent
  (test-author → red_check + baseline commit → implementer (≤3 iterations/red test, ceiling
  → hook-authored ESCALATE) → evaluator (fast-lane for S) → adversarial pass for M/L and
  first-change-of-capability → loop ≤3 → human). One in-flight change per context.
- `.claude/commands/abandon.md` — delete branch, tag `abandoned/<context>-NNN` with reason.

## Steps
1. Agents first (the command references them). Frontmatter tool scoping is THE enforcement
   here — copy the exact `disallowedTools` semantics verified in T06's doc re-check.
2. red_check + its pytest tests. `/implement` **resets the SubagentStop ceiling counter**
   (`.gate/subagent-stop-count`, owned by `subagent_stop.py`, T06) at the start of each
   change — a stale counter from a prior change must not trip an instant false ESCALATE on
   the next. Verify the reset in the smoke.
3. Commands. The adversarial step reuses the assert-strength recipes by pointing the agent
   at `testing-unit` — no duplicated checklist in the command (C7: one home).

## Verification
- `uv run pytest .claude/tools/test_red_check.py` green.
- Frontmatter of the three agents parses (yaml) and contains `disallowedTools` matching §4.
- `grep -n "CONTRACT-CHANGE" .claude/commands/implement.md .claude/agents/implementer.md`
  → both present (the protocol has both ends).

## Human verification
- Scripted smoke on a toy target AT THE REPO ROOT (`src/` — this repo doubles as the
  product repo, spec §1): run `/spec` + `/implement` for a tiny S-change ("add /health
  route", bootstrapping a minimal app skeleton on the way), observe: red baseline → green
  gate → fast-lane verdict → all-[x]. Finish with `/abandon` (smokes it too) so `main`
  stays untouched. This is interactive (slash-commands run in the main session) — the
  builder agent CANNOT do it; it is the T11 entry gate.

## Out of scope / Escalate if
- /accept-change (T10). If disallowedTools cannot express a §4 cell (docs drift), implement
  the closest deny-set, record the delta, and escalate if the gap is load-bearing
  (test-author able to write src = load-bearing).
