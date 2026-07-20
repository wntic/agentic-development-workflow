# T10b — accept.py honours a multi-target placement map

## Goal
Close the T10 finding-2 gap: the `/accept-change` command proposes a per-invariant placement
for a multi-target change and the human approves it, but `accept.py --execute` can't consume
that decision — T05's `compute_merge` dumps every invariant into `Affects[0]` and only flags
the extras. So the approved placement is silently ignored and the base branch gets a wrong
spec state a human must fix post-merge (the exact dirty-intermediate spec §5.4 was amended to
prevent). Make accept.py execute the placement the command produced.

## Depends on
T05, T10.

## Read first
- `.claude/tools/accept.py` — `compute_merge` (the Affects[0] dump + the multi-target flag).
- `.claude/commands/accept-change.md` — step 4 (the placement proposal + human approval).
- Spec §5.4 ("accept.py при multi-target только флагует... не сваливает всё в первый файл";
  the command owns the semantic placement); T10 finding 2.

## Deliverables
- `.claude/tools/accept.py` — `--execute` accepts an optional placement map (invariant → target
  capability file; a simple JSON/arg the command writes from the human-approved distribution).
  Behaviour: single-target → write to the one target (deterministic, unchanged). Multi-target
  WITH a map → write each invariant to its mapped file. Multi-target WITHOUT a map → **refuse**
  (exit non-zero, "multi-target needs a placement map from /accept-change") — never dump into
  the first file.
- `.claude/commands/accept-change.md` — step 4 passes the human-approved map to `--execute`.
- `.claude/tools/test_accept.py` — cases: single-target unchanged; multi-target + valid map →
  each invariant in its file; multi-target + no map → refused; map naming a file not in
  `Affects` → refused.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green with the new cases; the existing
  single-target and flag tests still pass.
- `grep -n "placement\|--map\|multi-target" .claude/commands/accept-change.md` shows the
  command passing the approved map to `--execute`.

## Out of scope / Escalate if
- No change to how the command PROPOSES the placement (that UX is T10, done). If a change
  legitimately wants its invariants re-cut into separate changes rather than distributed,
  that is the `/spec` re-cut path, not this map — keep the two distinct.
