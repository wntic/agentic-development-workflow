# T09c — Greenfield bootstrap: substrate + shell in a pre-baseline commit

## Goal
Fix the greenfield-probe F2/F3 gap: a first change can't reach green because the framework
substrate (`pyproject.toml` deps) must exist at baseline time (it's a gate-protected frozen
tree), but the implementer is tool-blocked from `pyproject.toml` and no role establishes it.
Root cause: v3 dropped the scaffolder that owned bootstrap in v2, and the §9-L walkthrough
wrongly reassigned bootstrap to the implementer. RULING (human-approved): greenfield
bootstrap — framework substrate + a minimal BEHAVIORLESS importable app shell — lands in a
commit BEFORE the test-author's red baseline, owned by an `/implement` bootstrap step, so
T09b's tests-only baseline and the frozen-pyproject integrity check both stay intact and the
test-author's greenfield tests import the shell and fail cleanly (real red, not a collection
error).

## Depends on
T09.

## Read first
- `notes/greenfield-first-change-blockers.md` (F2/F3, the exact stuck state on
  `change/platform-001`); spec §9 (the §9-L vertical-slice walkthrough — its "bootstrap =
  implementer" line is the mistake being corrected), §5.1 (pyproject as a protected tree).
- `.claude/skills/conventions` §D (the always-present substrate list) and `.claude/skills/restapi`
  (the app-shell / `create_app` bootstrap content).
- `.claude/commands/implement.md`, `.claude/agents/test-author.md`, `.claude/tools/red_check.py`
  (T09b's tests-only baseline check — must stay green: bootstrap is a SEPARATE earlier commit).

## Deliverables
- An `/implement` **bootstrap step** (before the test-author, only on a first change / when the
  substrate is absent): establishes the conventions §D substrate in `pyproject.toml` + a
  minimal importable app shell (`create_app()` returning a bare app with the DI container +
  error handler, NO routes/behaviour) + the package skeleton, and commits it as a distinct
  **pre-baseline** commit. Deterministic where possible (the substrate list is §D; the shell
  is the restapi bootstrap content) — no business-logic judgment.
- Spec §9: correct the §9-L line that assigns bootstrap to the implementer → bootstrap is the
  pre-baseline step; the implementer adds only behaviour (the actual `/health` route).
- Update `.claude/agents/implementer.md` / `test-author.md` if their prose still implies either
  owns substrate.
- Tests for the bootstrap step (substrate present, shell imports, shell has no routes).

## Verification
- The greenfield `/health` change runs `/spec` → `/implement` → green gate **without a human
  override**: bootstrap commit (substrate + shell) → test-author tests-only red baseline
  (T09b still passes — baseline touches tests/** only) → implementer adds the route → gate GREEN.
- `red_check` still refuses a baseline commit containing `src/**` (T09b intact — the shell is
  in the earlier bootstrap commit, not the baseline).
- gate.py's frozen-pyproject integrity check passes (substrate is pre-baseline, unchanged after).

## Out of scope / Escalate if
- Do not revive a general per-component scaffolder (D1 — that was the v2 mistake). This is a
  narrow, deterministic first-change bootstrap only. If the app shell genuinely needs a
  judgment call for a richer first slice (auth, middlewares), keep the shell minimal here and
  let the implementer add those as behaviour — escalate if that line is unclear for a case.
