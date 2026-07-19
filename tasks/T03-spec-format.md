# T03 — Spec format: templates + criteria lint + /spec (WP2)

## Goal
The spec-side of the workflow becomes writable: templates for every spec artifact, the
deterministic criteria lint, and the interactive `/spec` command.

## Depends on
T01 (T02 not required).

## Read first
- Spec §2, §2.1, §3 (all of it — classes, depths, criteria states, lint), §6 `/spec`.

## Deliverables
- `.claude/templates/change.md` — with Class/Affects/Companion lines and all §3.1 sections
  as commented placeholders (Interface sketch binding note, Design notes non-binding note).
- `.claude/templates/criteria.md`, `.claude/templates/verdict.md` (per-AC: state, proof
  method, test-id/scenario, git SHA; out-of-scope-diff section; adversarial section slot).
- `.claude/templates/overview.md`, `.claude/templates/capability.md` (invariants carry
  `(verified by: <test-id>)` / `(MANUAL)` provenance).
- `.claude/tools/criteria_lint.py` (stdlib): rejects vague-marker words («корректно»,
  «правильно», "works", "correctly", "as expected"…), requires an observable artifact token
  (HTTP code / field name / state assertion) per AC; exits non-zero with per-line reasons.
- `.claude/tools/test_criteria_lint.py`.
- `.claude/commands/spec.md` — the interview procedure: reads overview + affected
  capabilities; first-change-of-context → proposes the §2.1 cut; proposes class + depth +
  Interface sketch (M/L); allocates `NNN = max(existing ∪ tags) + 1`; creates branch
  `change/<context>-NNN`; writes change.md + criteria.md from templates; exit gate = lint
  green + Verification section answers "how to prove" (live criteria name their env
  provisioning); `--retro` mode per §5.5.

## Steps
1. Templates first (they define the shapes everything else parses).
2. Lint + its tests.
3. The command, pointing at templates and lint — procedure text, no duplicated format rules
   (the templates are the format's single home).

## Verification
- `uv run pytest .claude/tools/test_criteria_lint.py` green; cases: vague word → reject,
  observable criterion → pass, empty criteria → reject, `[m]`/`[x]` states parse.
- Templates contain no manifest-era vocabulary: `grep -rn "manifest\|kind:" .claude/templates` → empty.

## Human verification
- Run `/spec meetings "закрытие action item по UC-16"` end-to-end: one interview produces
  the §9 S-case change on a fresh branch; a deliberately vague criterion is rejected.

## Out of scope / Escalate if
- No gate.py logic here (T04 consumes criteria.md, this task only shapes it). If a template
  needs a field the spec doesn't name — escalate (earn-its-place), don't add.
