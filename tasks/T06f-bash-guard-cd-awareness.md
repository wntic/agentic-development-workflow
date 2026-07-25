# T06f — bash_guard must resolve relative write targets against the command's effective cwd

## Goal
`bash_guard` denies legitimate writes into scratch directories outside the repo whenever the
command reaches them by `cd`-ing first. It twice blocked the `users/002` adversarial evaluator on
`cd /private/tmp/.../scratchpad/mut && cat > tests/integration/.../test_probe.py` — a write into a
throwaway mutation copy of the tree, nowhere near the repo.

This is **not** the bug T06e closed. T06e anchored the match to the repo root for *absolute*
targets. The remaining hole is relative targets: `offending()` does resolve them against `cwd`
(`bash_guard.py:199-201`), but the `cwd` in the PreToolUse payload is the **session** cwd, and
`_write_targets()` has no `cd` awareness at all (zero occurrences of `cd` in the file). It
flat-tokenises the compound command, so the `cd` prefix is invisible and `tests/…` resolves under
the repo root.

Fixing this also closes what looked like a second, separate defect: the same agent's *other* denial
had its real mutations in `src/`, and died only because a leading `rm -f tests/.../test_probe.py`
sat in the same compound command. There is no per-target deny to add — a PreToolUse hook can only
allow or deny the whole call — but once that `rm` target correctly resolves into the `/tmp` copy, it
falls outside the repo and never fires. One fix, both symptoms.

Cost of leaving it: the agent rerouted and completed all 8 mutations anyway. That is the bypass
reflex the guard exists to prevent, trained by the guard itself. Under S8 the gate is the backstop,
so a false positive is strictly more expensive than a miss — keep T06b's precision bias.

## Depends on
T06, T06b (precision-first tokeniser), T06d (role-aware owned-tree allowance), T06e (repo-root
anchor — do not regress it).

## Read first
- `.claude/hooks/bash_guard.py` — `_write_targets()` (the flat tokeniser), `_repo_relative()`
  (`:190-201`, already cwd-aware), `offending()` (`:218-249`, first-match return), `deny()`.
- `tasks/T06e-bash-guard-repo-root-anchor.md` — what was already fixed, and its fallback rule.
- `PRINCIPLES.md` S8 — why precision beats prevention here.

## Deliverables
- `.claude/hooks/bash_guard.py` — track the command's **effective** cwd when resolving relative
  write targets:
  - honour a leading `cd <dir>` (and `cd <dir> &&` / `pushd`) before resolving subsequent relative
    targets in that command;
  - when the effective cwd cannot be determined with confidence, or the command `cd`s to a path
    outside the repo root, **do not fire** on relative targets (T06b precision bias — the gate
    backstops).
  - Keep T06e's absolute-path anchoring and T06d's owned-tree allowance intact.
- `.claude/tools/test_enforcement.py` — cases:
  - `cd /tmp/mut && cat > tests/integration/x_test.py` (non-owner role) → **allowed** (regression);
  - `cd /tmp/mut && rm -f tests/x.py && cat > src/y.py` (non-owner) → **allowed** (the compound-veto
    regression);
  - `cat > tests/x.py` with no `cd`, session cwd = repo (non-owner) → still **denied**;
  - `cd /tmp/mut && cat > /repo/tests/x.py` (absolute, non-owner) → still **denied**;
  - owned-tree write under a T06d role → still allowed.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green with the new cases.
- Simulated PreToolUse payload replaying both `users/002` denials verbatim → exit 0 (allowed).
- The in-repo denial cases from T06/T06b/T06d/T06e all still deny — run the full module, not just
  the new cases.

## Out of scope / Escalate if
- Do NOT implement a general shell interpreter. Handle the `cd`-prefix idiom agents actually emit;
  anything ambiguous degrades to not-firing, and the gate catches the miss.
- Do NOT relax in-repo protection for a non-owning role. This narrows resolution, not ownership.
- If honouring `cd` cannot be done without materially widening the bypass surface *inside* the repo
  (e.g. `cd .. && cat > repo/tests/x.py` slipping through), record the trade-off and escalate before
  choosing — that is a canon call about how much prevention the guard is meant to carry.
