# T06 — Enforcement wiring: hooks, ESCALATE, bypass tests (WP3c)

## Goal
The ergonomics tier (fast, explained denials) plus the stop/escalation mechanics — wired to
the real Claude Code hook API, and proven by negative tests that INCLUDE bypass attempts.

## Depends on
T04.

## Read first
- Spec §5.2, §5.3; `notes/15_v3_design_review.md` — F-1..F-8 verdicts (exact field names),
  E-03/08/10.
- Current official hooks docs (re-verify schemas before writing — the F-verdicts are a
  snapshot, docs win).

## Deliverables
- `.claude/hooks/criteria_guard.py` — PreToolUse on Edit|Write matching `**/criteria.md`:
  Edit → old/new comparison if fields present; Write → read file from disk + line-diff;
  allow only state flips (`[ ]`↔`[x]`, human-marked `[m]` passes only outside subagent
  sessions if identifiable, else defer to gate); creation allowed only when no
  `baseline/<context>-NNN` tag exists yet. Paths canonicalized (realpath + casefold).
- `.claude/hooks/bash_guard.py` — PreToolUse on Bash: best-effort deny of write-patterns
  (`sed -i`, `>`/`>>`, `rm`, `mv`, `git checkout --`, `tee`) targeting protected paths
  (tests/**, specs/<context>/*.md, changes/*/criteria.md|change.md, .claude/tools|hooks/**,
  pyproject.toml). Comment at top: THIS IS ERGONOMICS — the trust anchor is gate.py (S8).
- `.claude/hooks/subagent_stop.py` — SubagentStop: runs gate.py on the change branch;
  red → `{"decision":"block","reason":<failed checks>}`; honors `stop_hook_active`; on
  iteration ceiling writes `changes/NNN-<slug>/ESCALATE` (hook-authored, E-08) and allows
  stop with the escalation in the reason.
- `.claude/hooks/session_stop.py` — Stop on the main session during /implement: blocks
  while criteria.md has `[ ]` / verdict.md missing / ESCALATE present without a human turn.
- `.claude/settings.json` — hooks registered with correct matchers.
- `.claude/tools/test_enforcement.py` — the bypass suite.

## Steps
1. FIRST ACTION (spec §10 WP3): re-verify hook payload schemas + glob semantics against
   live docs; record any drift from the F-verdicts in the report.
2. Implement hooks; every denial message says WHY and points at the legal path.
3. Bypass suite (drives hooks as scripts with synthetic payloads + drives gate.py on
   fixture trees): criteria reword via Write-payload → denied AND gate-RED; same via
   simulated shell edit → gate-RED (hook may miss — assert the gate catches it); baseline
   test suppressed via conftest fixture → gate-RED; gate.py self-edit → gate-RED;
   case-variant and `..`-variant paths → denied.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green — bypass cases present and passing.
- Hook scripts are executable, stdlib-only, and each prints a one-line self-description
  with `--describe` (debuggability).

## Out of scope / Escalate if
- Agent frontmatter `disallowedTools` lives with the agents (T09). If the docs contradict
  an F-verdict (schema changed), adapt and RECORD the delta — do not force the spec's
  wording against reality; escalate only if a §5 mechanism becomes impossible.
