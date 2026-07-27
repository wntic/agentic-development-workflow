# T06l — `git rm` deletes protected files unguarded, and the family pins live in two places

## Goal
Two leftovers from T06k, both small, both with evidence rather than speculation.

**1. `git rm` is not in the write-op inventory, and it is a documented instruction.**
`bash_guard` denies `rm tests/x.py` for a non-owner but allows `git rm tests/x.py`. This is not a
hypothetical: `tasks/T02-harvest-and-purge.md:40` says *"Delete per spec §8. Use `git rm` so the commit
is reviewable"* — verified — so a `v3-builder` has actually removed files under `.claude/**` with it.
T06k left it out because its own rule forbade adding operations speculatively, and this one arrived as
a finding after the deliverable set was closed.

It is **not** the asymmetry trap that made `cp` a task: `git rm`'s rule is `rm`'s — every non-flag
operand after the subcommand, `--` respected — so there is no read-direction to get wrong.

**The ruling that was owed, so you do not have to re-derive it: `--cached` counts as a write.**
`git rm --cached <path>` leaves the file on disk but removes it from the index, which is a mutation of
*tracked* state — and tracked state is exactly what every integrity check compares
(`integrity.protected-trees` diffs tracked paths, so untracking a protected file shows up as a
deletion). Treating it as a write costs nothing (there is no legitimate reason for a non-owning role to
untrack a protected path) and avoids a second rule to get wrong. Same operands either way.

Severity is T06k's: **ergonomics, not trust.** The gate backstops — a protected file removed by any
means fails `integrity.protected-trees`, and `check_self_hash` catches an anchor. What the miss costs
is the early, legible denial.

**2. `RECORDED_FALSE_POSITIVES` promises the family and delivers 7 of 12.** T06k found that the list
carries only the seven *filed* variants; the five T06i *measured* ones live in separate tests
(`..._unresolvable_target_location_does_not_fire`, `..._quoted_operator_is_data`,
`..._mutator_counts_in_command_position`). My T06k Verification line said "run the
`RECORDED_FALSE_POSITIVES` pins" for all twelve, which was imprecise — running the whole file covers
them, but the **name** promises the family, and T06i's stated purpose for that list was that *"the next
rewrite is measured against the family rather than the fix at hand"*. A name that under-delivers is
how the next rewrite misses variant 13. T06k could not fix it because consolidating edits existing
lines, which its additions-only standard forbade.

## Depends on
T06i (the tokeniser and the list), T06k (both findings; its target-rule helpers are the model).

## Read first
- `.claude/hooks/bash_guard.py` — `_write_targets`'s dispatch, the existing two `git` branches
  (`checkout -- ` and `restore`), and `_paths`. The `git rm` branch sits beside them and reuses `_paths`.
- `.claude/tools/test_enforcement.py` — `RECORDED_FALSE_POSITIVES` and the three separate tests named
  above; T06k's section as the model for pinning both directions.
- `tasks/T06i-tokeniser-family-decision.md` — the twelve-variant table and why the list exists.
- `PRINCIPLES.md` S8 — the reason a false positive costs more than a miss, which is why `git rm`'s
  lack of a read-direction makes it cheap.

## Deliverables
- `.claude/hooks/bash_guard.py` — `git rm` in the inventory, operands per `rm`'s rule, `--` respected,
  `--cached` treated as a write (per the ruling above; state it in a comment so it is not "fixed" later).
  Keep every T06i property intact: masking, command position, first-component expansion, segmenting.
- `.claude/tools/test_enforcement.py` — `git rm tests/x.py` (non-owner) **denies**; `git rm --cached
  .claude/tools/gate.py` **denies**; `git rm` on an **owned** tree (test-author → `tests/`) still
  **allows**; `git rm -- tests/x.py` denies; a `git rm` whose target resolves outside the repo allows.
- **Consolidate the twelve family pins into `RECORDED_FALSE_POSITIVES`** so the list means what its
  name says, and leave the three standalone tests as thin wrappers or delete them — but say which and
  why. This is the one place in the guard's suite where editing existing lines is sanctioned; note it
  in the commit message so a future reader does not think the additions-only rule was ignored.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green.
- **All twelve** recorded false positives still allow, now via the one list.
- The new cases demonstrably differ against pre-fix `bash_guard.py`: `git rm tests/x.py` allows before
  and denies after.
- The T06k read-direction cases still allow (`cp <protected> /tmp/x`, `dd if=<protected>`) — the fix
  must not disturb the asymmetry that task established.
- `uv run pytest .claude/tools` green. **Commit the hook edit before any acceptance regression** —
  since T18 an uncommitted hook makes `integrity.self-hash` FAIL (INDEX note).

## Out of scope / Escalate if
- Do NOT add `ln -sf`, `git mv`, or `mkdir`. T06k checked: no observed use against a protected tree, so
  each is a guess, and the family's whole history is guesses that became false positives.
- Do NOT change `ROLE_OWNED` / `PROTECTED_FRAGMENTS` or the tokeniser. Inventory and pins only.
- **Escalate if** consolidating the pins changes any verdict. The list is the guard's specification; a
  moved verdict means the standalone tests and the list disagreed, which is a finding in itself.
