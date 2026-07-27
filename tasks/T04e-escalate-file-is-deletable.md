# T04e — `ESCALATE` is deletable by an agent; §5.3 says only the human may remove it

## Goal
Spec §5.3 makes the `ESCALATE` file a human-only lock: the iteration ceiling writes it, `accept.py`
denies while it exists, and **only the human removes it**. Nothing enforces that. Found by the T10f
audit (`notes/19_accept_gate_audit.md`, finding 10) and correctly ruled out of its scope.

The hole is one line of inventory: the change directory is **not** in `gate.py`'s `PROTECTED_PATHS`
(`.claude/tools`, `.claude/hooks`, `.claude/settings.json`, `pyproject.toml`). So an agent that
deletes `ESCALATE` is invisible to *both* scripts — `gate.py`'s protected-tree diff never looks
there, and `accept.py` only checks whether the file exists *now*. The agent that hit its ceiling can
unlock itself and proceed to acceptance.

This is a textbook **S8** case, and the litmus answers badly: *what does `gate.py` see if an agent
bypasses the rule?* Nothing. So under S4 the rule does not currently exist — it is prose.

## Depends on
T04 (`gate.py` + its integrity inventory), T06 (the hook that writes `ESCALATE`), T10f (the audit
that found it — read its register first).

## Read first
- `notes/19_accept_gate_audit.md` finding 10 — the finding and its reasoning.
- `.claude/tools/gate.py` — `PROTECTED_PATHS` and the `integrity.protected-trees` check: how a tree
  is diffed against the baseline commit, and why the change dir was left out.
- `.claude/tools/accept.py` — the `escalate` gate (presence-only check).
- `workflow_v3_spec.md §5.3` — the human-only removal rule this must make real.
- `PRINCIPLES.md` S4, S8.

## Deliverables
- `.claude/tools/gate.py` — make the disappearance of `ESCALATE` **detectable against the baseline**,
  the same way every other protected-tree edit is. The obvious shape: if `ESCALATE` is present at the
  baseline commit and absent at HEAD, that is a FAIL, not a silent pass. Prefer this over adding the
  whole change dir to `PROTECTED_PATHS` — `criteria.md` and `verdict.md` live there and are *supposed*
  to change during the cycle, so a blanket protection would deadlock the cycle it is meant to guard.
- `.claude/tools/test_gate.py` — the baseline-has-it / HEAD-lacks-it case FAILs; a change that never
  had an `ESCALATE` still passes; a human removal followed by a re-baseline is not punished (see the
  escalate-if below if that turns out to be unrepresentable).

## Verification
- `uv run pytest .claude/tools/test_gate.py` green with the new cases.
- The new case demonstrably FAILs against the pre-fix `gate.py`.
- `uv run pytest .claude/tools` — whole meta suite still green.

## Out of scope / Escalate if
- Do NOT add the change dir wholesale to `PROTECTED_PATHS`. `criteria.md` flips and `verdict.md`
  writes are legal cycle traffic; freezing the directory would deadlock the cycle.
- Do NOT try to identify *who* removed the file. The workflow cannot distinguish a human from an
  agent at the filesystem (that is exactly why `criteria_guard` cannot either) — the goal is to make
  the removal **visible and gate-failing**, so a human removal is a deliberate, recorded act.
- **Escalate if** the legitimate human-removal path cannot be expressed without a re-baseline: that
  would mean "the human clears an ESCALATE" is a workflow step needing a command (a `/escalate-clear`
  or a `red_check` flag), which is a canon decision, not a builder's call.
