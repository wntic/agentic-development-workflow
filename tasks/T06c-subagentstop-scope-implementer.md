# T06c — Scope the stop hooks to their intended context

## Goal
Fix two same-class over-firing bugs surfaced by the greenfield probe: both stop hooks fire
outside the context they were designed for.

**F1 — `.claude/hooks/subagent_stop.py` re-runs gate.py on EVERY subagent stop**, so it
blocked the **test-author** (whose deliverable IS a red gate) three times and wrote a false
ESCALATE ("gate red after 3 implementer passes") when no implementer had run. Only the
implementer should be held-and-counted while the gate is red.

**F1b — `.claude/hooks/session_stop.py` blocks EVERY main-session turn while an ESCALATE (or
a `[ ]` criterion) exists anywhere in the tree**, not just during an active `/implement`
cycle. A stale ESCALATE floating as an untracked file on the build branch (`markdown-specs`)
blocked an ordinary design turn — and would block every turn until a human removes the file.
§5.3 scopes this hook to "Stop на главной сессии **в /implement**"; the implementation lost
the scope. It must only fire when the session is actually mid-cycle — the clean deterministic
proxy is **the current branch is a `change/<context>-NNN` branch**; on the base/build branch
it never fires.

## Depends on
T06, T09 (the agents whose names the hook must recognise exist).

## Read first
- `.claude/hooks/subagent_stop.py` — `main()` reads the payload but never checks which agent stopped.
- `notes/15_v3_design_review.md` F-2 (SubagentStop payload DOES carry `agent_type` — unlike
  PreToolUse); `notes/greenfield-first-change-blockers.md` F1.
- `.claude/agents/implementer.md` (the exact agent name/type to match).

## Deliverables
- `.claude/hooks/subagent_stop.py` — read `agent_type` from the payload; run the
  gate-hold + counter + ESCALATE logic ONLY when the stopping agent is the implementer.
  Any other agent's stop (test-author, evaluator) passes through untouched (exit 0, no gate
  run, no counter increment).
- `.claude/hooks/session_stop.py` — fire ONLY when the current git branch matches
  `change/<context>-NNN` (an active cycle); on the base/build branch, pass through (exit 0).
  A stale ESCALATE floating on the build branch must not block ordinary turns.
- `.claude/tools/test_enforcement.py` (or the hooks' own tests) — cases: implementer stop +
  red gate → block + count; test-author stop + red gate → pass through (NOT blocked, counter
  untouched); implementer stop at ceiling → ESCALATE written; session_stop on a `change/*`
  branch with ESCALATE → block; session_stop on `markdown-specs`/base with a floating
  ESCALATE → pass through.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green with the new cases.
- Simulated test-author SubagentStop payload against a red tree → exit 0, no ESCALATE, no
  counter change; implementer payload against the same tree → block with reason.

## Out of scope / Escalate if
- Do not change what the gate checks (T04) or the ceiling value (WORKFLOW_STOP_CEILING). If
  the payload field name differs from `agent_type` in the live docs, use the real field and
  record the delta (docs win).
