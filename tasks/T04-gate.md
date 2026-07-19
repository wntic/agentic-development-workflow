# T04 — gate.py + its test suite (WP3a)

## Goal
The trust anchor of v3: one stdlib script that decides "green" by verifying BOTH the
toolchain result AND the integrity of its inputs against the change's git baseline (S8).

## Depends on
T02 (old tools purged; the name `gate.py` is unambiguous).

## Read first
- Spec §5.1 — the exhaustive check inventory (every check cites its E/L/V/O/F finding; do
  not drop one silently), §5.3 (what SubagentStop consumes), §3.3 (`--criteria` semantics).
- `notes/15_v3_design_review.md` — E-01/02/05/07, V-04, L-06.
- `.claude/tools/criteria_lint.py` (T03) — `--criteria` MUST import its `iter_criteria`/
  `Criterion` parser instead of re-implementing the checkbox grammar: one grammar, one home
  (C7). It is stdlib-only, so gate.py's dependency rule holds.

## Deliverables
- `.claude/tools/gate.py` — stdlib-only (PyYAML allowed as in v2's validator; nothing else).
- `.claude/tools/test_gate.py` — pytest suite with fixture mini-trees.

## Steps
1. **Contract.** CLI: `gate.py [--criteria] [--baseline <ref>] [--change <context>/NNN>] [tree]`.
   Output: human summary + machine block (`GREEN`/`RED` + failed-check list), junit-xml to
   `.gate/last-run.xml`, run git SHA recorded. Exit 0 only on GREEN.
2. **Baseline convention** (define here, document in the script's docstring): the red-tests
   commit is tagged `baseline/<context>-NNN` by the /implement step 1 runner (T09 consumes
   this); `--baseline` overrides. No tag and no override → integrity checks SKIP loudly
   (greenfield tree before first change), never silently.
3. **Checks, in spec §5.1 order** — toolchain with pinned pytest config; the four greps
   (type-ignore / __future__ / noqa:F401 / NotImplementedError in src); construct-smoke +
   table metadata-import smoke (present only when the tree has an app package — detect,
   don't assume); Docker-tier incl. `alembic upgrade head` with loud `DOCKER SKIPPED`;
   `--criteria` (junit cross-check of every `[x]`, `[m]` requires a verdict.md entry);
   integrity block (protected-tree diff vs baseline, change.md hash, test-inventory
   superset check with missing/skipped/xfail = RED, self-hash of gate.py + toolchain config
   vs git HEAD).
4. Toolchain config (mypy/ruff flags, ruff select incl. B006/B904) lives as constants IN
   gate.py — spec §5: conventions cites it, not vice versa.
5. Test suite: one fixture mini-tree per check class, red and green case each. Integrity
   cases simulate bypasses: criteria reworded under same checkboxes → RED; baseline test
   deleted / skipped via conftest → RED; gate.py edited on the work tree → RED (self-hash).

## Verification
- `uv run pytest .claude/tools/test_gate.py` green.
- `uv run .claude/tools/gate.py --help` works; running on this repo (no app tree, no
  baseline) exits with a loud SKIP-annotated report, not a crash and not silent GREEN.
- Every §5.1 bullet maps to a named check id in the code (`grep -n "E-05\|F-012\|N-03"
  .claude/tools/gate.py` shows the finding refs as comments).

## Out of scope / Escalate if
- accept.py (T05), hooks (T06). If a §5.1 check is ambiguous against a real repo layout,
  implement the strict reading and flag the ambiguity in the report — never skip the check.
