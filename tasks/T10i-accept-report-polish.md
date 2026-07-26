# T10i — Two leftovers from T10f: `merge.placement`'s class, and a stale gate list

## Goal
Two small items the T10f builder flagged rather than deciding, plus one cosmetic defect from its
register. None is urgent; all three are cheap and each is a small honesty debt in what the operator
reads.

1. **`merge.placement` is registered `REVIEW`, not `TRUST`** (T10f finding 4). Its undetermined input
   — multi-target `Affects` with no approved placement map — is a FLAG in check mode by §5.4's
   design, with the actual refusal living in `--execute`
   (`test_multi_target_execute_without_map_is_refused`). That is defensible, but it means a
   multi-target change reads `verdict: ACCEPTABLE` in check mode while being un-executable. Decide
   whether the split is right, or whether check mode should say so more loudly.
2. **`/accept-change`'s prose gate list omits `invariant.provenance`** (T10f finding 12), the gate
   T10f added. The list was already non-exhaustive and the command tells the reader to read
   `accept.py`'s output, so nothing contradicts — but the omission is exactly the drift C7 warns
   about, and T10g has since touched this file anyway.
3. **`spec.lint` emits duplicate findings** (T10f register, F-10 area): a reference appearing twice
   in `overview.md` produces two identical lines. Cosmetic noise in the human's review output.

## Depends on
T10f (both findings), T10g (which last touched `.claude/commands/accept-change.md`).

## Read first
- `.claude/tools/accept.py` — the `GATES` registry (TRUST vs REVIEW and what each implies under the
  undetermined-input rule), `merge.placement`'s check-mode behaviour, `_spec_lint`'s findings list.
- `.claude/tools/test_accept.py` — `test_multi_target_check_mode_flags_need_for_placement_map`,
  which **deliberately pins `verdict: ACCEPTABLE` with the FLAG**. Reclassifying to TRUST means
  rewriting it; that rewrite is only sanctioned if item 1 is decided that way.
- `.claude/commands/accept-change.md` — step 1's gate list, and step 4 (multi-target placement),
  which is the human-facing half of item 1.
- `workflow_v3_spec.md §5.4` — the placement-map design; **the spec wins**, so read it before
  concluding the current split is wrong.
- `PRINCIPLES.md` C7 (a restated derivation drifts), S4.

## Deliverables
- **Item 1** — a decision with its reasoning, then the code. If `merge.placement` stays REVIEW,
  say so in the docstring next to the registry entry so the next auditor does not re-open it. If it
  becomes TRUST, rewrite the pinning test and check no legitimate multi-target change is deadlocked
  in check mode.
- **Item 2** — refresh the gate list in `.claude/commands/accept-change.md`, or (better, C7) replace
  the enumeration with a pointer to `accept.py`'s registry so it cannot drift again. Prefer the
  pointer; enumerations in prose are how this happened.
- **Item 3** — dedupe `_spec_lint`'s findings, preserving order.
- Tests for items 1 (if it changes) and 3.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green.
- **`users/002` unchanged** — detached worktree at `a931ee6`: `verdict: ACCEPTABLE`. Item 3 is
  visible there (its `spec.lint` prints the `user-management.md` line twice pre-fix, once after),
  so it doubles as the regression check.
- `uv run pytest .claude/tools` — whole meta suite green.

## Out of scope / Escalate if
- Do NOT restate `accept.py`'s gate semantics in the command prose while fixing item 2. The command
  says explicitly that it does not re-judge the script's gates (S4/S8); a longer list is a step
  toward exactly that.
- **Escalate on item 1 if** the answer requires changing what `--execute` refuses. That is §5.4
  behaviour, not a registry label, and it is a canon question.
