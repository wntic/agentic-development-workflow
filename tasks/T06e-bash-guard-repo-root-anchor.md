# T06e — Anchor bash_guard's protected-path match to the repo root

## Goal
Stop `bash_guard.py` from denying writes to paths that merely *contain* a protected fragment
anywhere on the filesystem. It substring-matches `tests/`, `specs/`, `criteria.md`, … against the
resolved write target, so a non-owning role writing to `/tmp/<scratch>/tests/fixture` or a
scratch dir under `/private/tmp/.../specs-work/` is denied even though that path is nowhere near
the repo. This blocked a T09f builder's legitimate `/tmp` fixture setup. Harmless in the trust
sense (the gate backstops, S8) but a false-positive that trains the `--no-verify` / bypass reflex
the guard exists to avoid (T06b's precision bias).

## Depends on
T06, T06b (the precision-first tokeniser), T06d (the role-aware owned-tree allowance).

## Read first
- `.claude/hooks/bash_guard.py` — `PROTECTED_FRAGMENTS` + `offending()`: the substring match
  (`if frag in target`) is location-insensitive; `_write_targets()` already resolves the target token.
- `notes/` (or the greenfield-blockers findings) for the observed `/tmp` false-positive.
- How the hook learns the repo root: `CLAUDE_PROJECT_DIR` env in `.claude/settings.json`.

## Deliverables
- `.claude/hooks/bash_guard.py` — resolve each write target to an absolute path and fire ONLY when
  it falls **under the repo root** (`CLAUDE_PROJECT_DIR`, or the git toplevel) AND matches a
  protected fragment relative to that root. A write whose absolute target is outside the repo tree
  (a `/tmp` scratch dir, the user's home, a sibling repo) never fires. Keep T06b's precision bias
  (unresolvable target → do not fire) and T06d's role-aware owned-tree allowance intact.
- `.claude/tools/test_enforcement.py` — cases: write to `<repo>/tests/x.py` (non-owner) → denied;
  write to `/tmp/scratch/tests/x.py` → allowed; write to `<repo>/specs/...` (non-owner) → denied;
  relative-path target that resolves under the repo → still denied; owned-tree write (T06d role)
  → still allowed.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green with the repo-root-anchored cases.
- Simulated PreToolUse payload: `cat > /tmp/x/tests/conftest.py` under a non-owner role → exit 0
  (allowed); the same relative write inside the repo → denied.

## Out of scope / Escalate if
- Do NOT relax the in-repo protection — a write to a protected tree INSIDE the repo by a non-owning
  role must still fire. This narrows only the location, not the ownership rule.
- If `CLAUDE_PROJECT_DIR` is unavailable in the PreToolUse payload/env and the git toplevel cannot
  be resolved cheaply, record the constraint and keep the substring match as a documented
  conservative fallback rather than guessing a root.
