# T09f — `red_check.py` screens the baseline for lint before tagging

## Goal
Stop a lint-dirty RED baseline from **deadlocking the implementer**. On the 2026-07-24
`/implement health/001` run the test-author's `tests/integration/conftest.py` split its two
third-party imports into two blocks (`ruff I001`). `red_check.py` checks only marker-coverage +
redness + tests-only baseline, so it tagged `baseline/health-001` over the defect. The implementer
is tool-blocked from `tests/**` and ruff is per-file, so **no `src/**` edit could ever clear it** —
it correctly refused to touch the tests, burned all 3 SubagentStop blocks, and the hook wrote
`ESCALATE` over a failure entirely outside its lane. A one-file lint reorder cost a full implementer
run plus a human escalation.

The defect is un-greenable by the one agent whose job is to green it. Per S4 the fix belongs in the
gate that runs at baseline time: `red_check.py` must lint `tests/**` before tagging and refuse a
lint-dirty baseline, so the test-author fixes it at author time instead.

## Depends on
T09b (the red_check anti-collusion / tests-only-baseline logic this extends), T04 (gate.py owns the
ruff config this reuses). No new dependency on T06d/T09e.

## Read first
- `.claude/tools/red_check.py` — the coverage/redness/tests-only-baseline flow and the tag step
  (`main()`, `analyze()`, `non_tests_paths()` + `baseline_commit_paths()`); the new screen is
  another pre-tag precondition beside the tests-only check.
- `.claude/tools/gate.py` — `check_ruff()` and the `RUFF_SELECT` / `RUFF_LINE_LENGTH` /
  `RUFF_TARGET` constants, plus the exact `--isolated --no-cache` invocation. **C7: import these
  from gate.py — do NOT restate the select string in red_check.** "Lint-clean at baseline" must
  mean byte-identical to what gate.py later enforces, or the screen and the gate can disagree.
- `.claude/tools/test_red_check.py` — the existing suite; the new cases extend it.
- `notes/greenfield-first-change-blockers.md` finding #5 (the deadlock, the fix-forward used, the
  `--isolated`-drops-`I` confusion) — in the user's Claude memory dir, not the repo `notes/`.

## Deliverables
- `.claude/tools/red_check.py` — a lint screen over the change's `tests/**`, run as a precondition
  of tagging (report it in `format_report`, make it fail the run / block the tag like coverage and
  redness do). It runs the gate's **ruff-check** and **ruff-format --check** over `tests/**` using
  gate.py's imported `RUFF_SELECT`/`RUFF_LINE_LENGTH`/`RUFF_TARGET` and the same `--isolated`
  `--no-cache` flags; any finding → RED with the offending file(s) named, and **the baseline is not
  tagged**. Runs after redness is confirmed, before `tag_baseline`.
- **Explicitly NOT mypy.** At a greenfield first change the tests import a not-yet-written package;
  mypy would fail import-resolution by design (that is the intended redness). The screen is ruff +
  ruff-format only. State this in a code comment so a later hand does not "complete" it with mypy.
- `.claude/tools/test_red_check.py` — cases: (1) a `tests/` file with a real ruff violation (an
  `I001` split-import block, mirroring the health/001 conftest) → red_check FAILS and does **not**
  create the baseline tag; (2) a lint-clean `tests/` baseline → still RED-CONFIRMED and tagged as
  today (no regression); (3) a ruff-format-only violation (badly formatted but lint-passing) →
  caught by the format arm. Keep the existing suite green.

## Verification
- `uv run pytest .claude/tools/test_red_check.py` green with the new cases.
- Reproduce the health/001 shape: a tests tree whose `conftest.py` has `from x import Y` then a
  blank line then `import z` → `uv run .claude/tools/red_check.py --change <ctx>/NNN` exits non-zero,
  names the file, and leaves no `baseline/<ctx>-NNN` tag. After `ruff check --fix` on that file, the
  same command is RED-CONFIRMED and tags.
- Confirm C7: `grep -n "E,W,F,I" .claude/tools/red_check.py` finds **nothing** — the select string
  lives only in gate.py; red_check imports the constant.
- `uv run .claude/tools/gate.py` still self-hashes clean (gate.py is untouched — this is a red_check
  change only; if a shared helper is factored into gate.py, its self-hash inventory must still pass).

## Out of scope / Escalate if
- Do NOT weaken the existing tests-only-baseline / anti-collusion check (T09b) — the lint screen is
  additive, both must hold to tag.
- Do NOT add the screen to `gate.py` — the gate already lints `tests/**` at every run; the whole
  point is to catch it *at baseline time* in red_check, before the implementer is dispatched.
- Do NOT restate the ruff config in red_check (C7). If reuse forces a small refactor of gate.py's
  `check_ruff` into an importable helper, that is acceptable **only if** gate.py's behaviour and
  self-hash inventory are unchanged; if it cannot be done without altering gate.py's verdict
  surface, escalate rather than fork the config.
- If linting `tests/**` at baseline time turns out to require the target package to import (it must
  not — ruff is static and per-file), escalate: that would mean the screen cannot run pre-code.
