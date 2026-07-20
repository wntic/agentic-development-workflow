# T06b — Tighten bash_guard toward precision

## Goal
Fix the T06 finding-3 false positives: `bash_guard` denied the builder's own `git commit -m`
(angle brackets + `.claude/hooks` in the message) and a `2>&1` redirect. Because bash_guard
is *ergonomics* and `gate.py` is the real net (S8), its cardinal sin is the **false
positive**, not the miss — a guard that cries wolf on `git commit` trains the operator to
reach for `--no-verify`/`-F`, habituating the exact bypass reflex the enforcement layer
exists to prevent. Optimize for precision; recall is gate.py's job.

## Depends on
T06.

## Read first
- `.claude/hooks/bash_guard.py` and its cases in `.claude/tools/test_enforcement.py`.
- Spec §5.2 (bash-guard is ergonomics), S8 (the gate is the trust anchor).

## Deliverables
- `.claude/hooks/bash_guard.py` — retargeted matching.
- `.claude/tools/test_enforcement.py` — false-positive cases added.

## Steps
1. Fire only when a write operation's **resolved target** is a protected path — parse
   (operation, target) and match the *target*, not the mere presence of `>`/`>>`/`rm`/`mv`
   anywhere in the line. `2>&1` (fd duplication, target `&1`) and a `>` inside a quoted
   `-m "…"` string are not writes to a protected path and must not fire.
2. Keep it best-effort and stdlib-only; when the target cannot be resolved with confidence,
   **do not fire** (precision bias — the gate backstops a miss). Header note stays: this is
   ergonomics, trust is gate.py.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green, with NEW passing cases:
  - `git commit -m "msg with <brackets> and .claude/hooks"` → NOT denied;
  - `pytest 2>&1 | tee /tmp/log` → NOT denied;
  - `echo x > tests/test_foo.py` (real write to a protected path) → still denied;
  - `sed -i … specs/<ctx>/foo.md` → still denied.
- The T06 bypass cases still pass (no recall regression on real protected-path writes).

## Out of scope / Escalate if
- Do not turn bash_guard into a full shell parser (E-01: parsing Bash as the primary defense
  is unreliable — that is why gate.py exists). If a construct is genuinely ambiguous, err
  toward not-firing and note it.
