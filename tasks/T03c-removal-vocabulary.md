# T03c — Pin the removal-flavour vocabulary; nothing emits the heading the gate reads

## Goal
Four documents describe how a change declares that it removes behaviour, and each says something
different:

| Source | What it says |
|---|---|
| `workflow_v3_spec.md §3.1` | «Removal-вкус (`REMOVED`)» |
| `.claude/templates/change.md` (Class line comment) | "behavioral, removal flavour: list the removed behaviour explicitly" |
| `.claude/commands/spec.md:38` | only "a removal is behavioral with the removed behaviour listed explicitly" |
| `.claude/agents/test-author.md:79-82` | list deleted tests in the change's **"Removed tests block"** — a section that **exists in no template** |

Meanwhile the V-02 orphan sweep, after T10e, keys on a structural `#+ Removed` heading — and
**nothing instructs `/spec` or the test-author to emit one.** Two workarounds are load-bearing
because of it: T10e's classifier tolerates all three spellings on the `Class:` line, and T06f Part B
downgrades a missing heading to a FLAG so a legitimate removal is not deadlocked. Both are honest
holding patterns; neither is the fix.

Net effect: V-02's coverage on a genuine removal rests on a heading nobody is told to write. Under
S4 that rule does not exist — and T10f's F-05 shows the remaining sharp edge (a `## Removed` heading
whose body carries no backticked symbol still PASSes, so the sweep quietly does nothing).

## Depends on
T03 (the templates + `/spec`), T10e (the classifier), T06f (Part B's FLAG), T10f (F-05's PASS).

## Read first
- `workflow_v3_spec.md §3.1` — the canonical vocabulary; **the spec wins on any conflict** and is
  never edited by agents. If the fix needs the spec changed, that is an escalation.
- `.claude/templates/change.md` — the `Class:` line and its comment.
- `.claude/commands/spec.md` — where `/spec` decides and writes the class.
- `.claude/agents/test-author.md:79-82` — the "Removed tests block" instruction with no template.
- `.claude/tools/accept.py` — `classify_removal()` / `RemovalFlavour` (T10e) and `_orphan_sweep`'s
  FLAG/SKIP/PASS directions (T06f Part B, T10f F-05).
- `PRINCIPLES.md` S1 (behaviour not construction), S4, C7 (derivation has one home).

## Deliverables
- **One spelling, one home.** Pick the `Class:` vocabulary (spec §3.1's `REMOVED` is the canonical
  candidate) and make the template emit it; every other document *cites* rather than restates (C7).
- **A `## Removed` section skeleton in the `change.md` template**, with a comment saying what goes in
  it: the removed behaviour, with the symbols/node-ids that must disappear written as backticked
  identifiers — because that is exactly what the sweep harvests. Today an author has no way to know.
- **`/spec` writes both** when it classifies a change as a removal, and `test-author.md`'s "Removed
  tests block" is reconciled with whatever the template actually ships (right now it references a
  section that does not exist — fix the agent, the template, or both, but not by inventing a third
  name).
- **Narrow the tolerant classifier** in `accept.py` to the pinned spelling, and **update T06f Part
  B's FLAG reason text** to name the section the template now ships.
- **Close F-05**: a `## Removed` heading whose body lists no sweepable symbol should not PASS. With
  the template shipping a skeleton, an empty one is now an authoring error the human can see — FLAG
  it (consistent with Part B), or FAIL it if you argue removals must always name symbols; state
  which and why.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green, including: the pinned spelling classifies; an
  old/unpinned spelling does **not** silently classify (it must be visible, not ignored); a
  `## Removed` with symbols sweeps exactly those; an empty one hits the F-05 direction you chose.
- `uv run pytest .claude/tools/test_criteria_lint.py` and the template guards green.
- A `/spec`-shaped removal change written from the updated template passes `criteria_lint` and is
  classified correctly end to end.
- **`users/002` unchanged**: it removes nothing, so `orphan.sweep` must still SKIP with its current
  reason (detached worktree at `a931ee6`).

## Out of scope / Escalate if
- Do NOT edit `workflow_v3_spec.md`. If the pinned spelling should differ from §3.1's `REMOVED`,
  that is an escalation with a recommendation, not an edit.
- Do NOT make the sweep block a legitimate removal that simply has nothing to list. The failure mode
  to avoid is T10e's inverted: a gate so strict that authors route around it.
- **Escalate if** pinning the vocabulary would invalidate an in-flight change's `change.md` — the
  file is frozen against its baseline (E-12), so a vocabulary change is a rebase for anyone mid-cycle.
  There is no such change today (`users/002` is behavioral), but check before landing.
