# T10f — Adversarial pass over accept.py's own gates

## Goal
`accept.py` has now shipped three defects found by *using* it, not by its tests:

1. **A silent false-accept in the freshness gate, shipped since T05** — an unresolvable pin produced
   an empty diff, which read as PASS. Exposed and closed incidentally by T10d.
2. **T10c** — a red deny on pure verdict formatting (backticked SHA, `## Adversarial pass` vs
   `review`).
3. **T10e** — `_orphan_sweep` classifying a `Class: behavioral` change as a removal and harvesting
   19 generic identifiers out of the Interface sketch.

Defect 1 is the alarming one: it fails **open**. The other two fail closed (annoying, visible, and a
human notices). A gate that silently passes is worse than no gate, because the whole trust model
(S8: the gate is the backstop for every bypassable hook) rests on it. Two independent defects
surfacing from a single change (`users/002`) is a signal about this script's test coverage.

The T10d builder flagged this pass as worth doing. This is that task.

## Depends on
T05, T10, T10b, T10c, T10d, T10e (do this *after* T10e so the classifier fix is in scope).

## Read first
- `.claude/tools/accept.py` — the whole gate inventory, and every early-return / empty-input path.
- `.claude/tools/test_accept.py` — what is currently covered, and more importantly what shape of
  case is *absent* (the pattern in all three defects is degenerate/empty input, not wrong logic).
- `workflow_v3_spec.md §5.3`, `§5.4` — the acceptance preconditions and the freshness rule these
  gates are supposed to implement.
- `PRINCIPLES.md` S4, S5, S8, S9.
- `tasks/INDEX.md` — the T10d sign-off note recording defect 1.

## Deliverables
- A written finding register (append to `notes/`, following the
  `notes/pipeline_dryrun_feedback.md` honesty standard) covering, for **every** gate in `accept.py`:
  - **Does it fail open on degenerate input?** Empty diff, missing file, unresolvable SHA, empty
    criteria list, absent verdict section, zero AC, absent `src/`, absent companion branch. For each,
    state whether the outcome is PASS/FAIL/SKIP and whether that is the intended direction.
  - **Is its regex/parse anchored structurally**, or does it grep prose? (T10e's defect class — the
    classifier that read a wrapped sentence as a heading.)
  - **Can an agent make it pass without doing the work?** The S8 question, applied to acceptance
    rather than to the gate.
- `.claude/tools/test_accept.py` — a degenerate-input case per gate, asserting the **direction** of
  the failure: an unresolvable / empty / missing input must never yield PASS. Prefer a shared
  parametrised "every gate refuses to pass on empty input" test over one-off cases, so a *future*
  gate is covered by construction.
- `.claude/tools/accept.py` — fix whatever the register finds failing open.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green.
- For each fail-open defect found: demonstrate the old behaviour (test fails against the pre-fix
  function) before fixing it. A finding with no failing test is a claim, not a finding.
- `uv run .claude/tools/accept.py users/002` still reaches the same verdict as before the pass —
  this task must not change the answer for a legitimate change, only for degenerate input.

## Out of scope / Escalate if
- Do NOT redesign the acceptance preconditions. This audits the implementation of `§5.3`/`§5.4`
  against its own spec; a *disagreement* with the spec is an escalation, not a fix.
- Do NOT fold in `gate.py`. Same defect class probably lives there too, but that is its own task —
  scoping both into one dispatch is how audits get shallow.
- If the register finds more than ~3 fail-open paths, stop and escalate before fixing: that many
  would mean the acceptance script needs a structural answer (a single validated-input layer), not
  a patch per gate.
