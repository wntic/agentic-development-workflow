# T04f — `gate.py`'s `_baseline_paths()` swallows the git return code

## Goal
`notes/19` credits `gate.py` with the reflex `accept.py` lacked: *"guards every integrity `_git`
call with `if rc != 0: FAIL`"*. Building T04e showed that is **not true of `_baseline_paths()`**,
which does `return [...] if rc == 0 else []` — an unanswerable git call is indistinguishable from
"the baseline commit touched no files".

Two current callers, `check_criteria_flips` and `check_change_frozen`. Both happen to fail *closed*
today (the per-file `_baseline_blob` also fails, producing "created after the baseline commit" →
FAIL), so nothing is broken right now. That is luck, not design: the helper is shared, and the next
caller inherits the fail-open. This is the F-01 family (T10f) with the fuse not yet lit.

Small task, filed because the register states the opposite as fact and a future reader will trust it.

## Depends on
T04, T04e (which found it), T10f (the undetermined-input rule this should be consistent with).

## Read first
- `.claude/tools/gate.py` — `_baseline_paths()`, its two callers, and `_baseline_blob()` (the
  accidental backstop). Also `check_self_hash`, which *does* guard its `_run` — the contrast.
- `notes/19_accept_gate_audit.md` — the claim about `gate.py`'s guard reflex, and the F-01 finding
  whose shape this shares. Correct that claim while you are there.
- `.claude/tools/accept.py` — how T10f made "input could not be determined" a representable value
  rather than an empty container. Mirror the idea; do not import the machinery.

## Deliverables
- `.claude/tools/gate.py` — `_baseline_paths()` distinguishes "git could not answer" from "no
  paths", and every caller treats the former as a **FAIL** naming the git failure. Keep it small: a
  sentinel or an exception, not a new abstraction layer.
- **Sweep the rest of `gate.py` for the same pattern** while you are in there — any `_run` / `_git`
  in an integrity check whose return code is discarded. Report what you find even if you fix
  nothing; the point of this task is that the register's blanket claim was wrong, so the inventory
  matters as much as the fix.
- `notes/19_accept_gate_audit.md` — correct the sentence crediting `gate.py` with guarding every
  integrity git call, with a dated note (the file already carries one such correction; match it).
- `.claude/tools/test_gate.py` — a case where the baseline commit cannot be resolved: the affected
  checks FAIL naming git, never PASS and never silently empty.

## Verification
- `uv run pytest .claude/tools/test_gate.py` green; the new case demonstrably fails against pre-fix
  `gate.py` (today it passes through the `_baseline_blob` backstop with a *misleading* message —
  "created after the baseline commit" — so assert on the message, not just the status).
- `uv run pytest .claude/tools` — whole meta suite green.
- `uv run .claude/tools/gate.py` on this repo still GREEN, and on the `users/002` worktree unchanged.

## Out of scope / Escalate if
- Do NOT port T10f's `GATES` registry / validated-input layer into `gate.py`. Same *idea*, different
  script, and `gate.py`'s check list has a different shape. A registry for `gate.py` would be its own
  task with its own argument.
- Do NOT touch the `PYTHONPATH` injections (T12b) or `check_self_hash`.
- **Escalate if** the sweep finds more than ~3 further unguarded sites — that would mean `gate.py`
  needs the same structural answer `accept.py` got in T10f, which is a bigger task than this one and
  deserves to be argued, not slipped in.
