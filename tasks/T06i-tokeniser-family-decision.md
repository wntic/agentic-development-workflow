# T06i — Six point fixes into the `bash_guard` tokeniser: decide whether to keep patching

## Goal
`bash_guard`'s command tokeniser has now produced **six** distinct false positives, each found by an
agent it blocked, each closed by a point fix that left another variant open:

| # | Task | The variant |
|---|---|---|
| 1 | T06b | a protected path inside a quoted `-m "…"` commit message read as a target |
| 2 | T06e | absolute paths matched location-insensitively (`/tmp/.../tests/…` denied) |
| 3 | T06f A | relative targets resolved against the session cwd, no `cd` awareness |
| 4 | T06f A | filename fragments matched as bare substrings (`change.md` ⊂ `users-002-change.md`) |
| 5 | T06g | heredoc **bodies** tokenised — prose in a commit message read as a redirect |
| 6 | open | `rm -rf "$S"; mkdir …` — the `;` glues onto the quoted word, `_slice_until_control` never sees a CONTROL token, and `rm`'s target slice swallows **the rest of the command**, including a later `cp`'s *source* path. A single space before the `;` flips the verdict, and the reason string blames a path the command only reads. (Found building T04e; cost that builder two denied commands.) |

Each fix was individually correct and cheap. The pattern is the problem: we are hand-parsing shell
with regex and slices, discovering the grammar one denial at a time, and every miss trains the
bypass reflex the guard exists to prevent (S8) while blaming the wrong path.

**This task is the decision, and then the work it implies** — not automatically a rewrite.

## Depends on
T06, T06b, T06e, T06f, T06g (the whole family — read what each already fixed before proposing to
replace it).

## Read first
- `.claude/hooks/bash_guard.py` in full — `_write_targets()`, `_slice_until_control()`, `CONTROL`,
  `REDIRECT`, `_heredoc_tags()`, `_repo_relative()`, `offending()`. Note how much of it is now
  genuinely grammar-shaped.
- `.claude/tools/test_enforcement.py` — **113 cases**. This is the asset: whatever shape wins must
  keep every one of them, so the suite is the specification of "what the guard means".
- `tasks/T06b/T06e/T06f/T06g-*.md` — each fix's reasoning, especially T06b's *precision bias*
  (unresolvable → do not fire) and T06f's *owned-tree overrides protected* (T06d).
- `PRINCIPLES.md` S8 — the guard is ergonomics, the gate is the backstop. This is what makes a false
  positive **more** expensive than a miss, and it should drive the choice.

## Deliverables
First, a short written comparison (in the report, or `notes/` if it runs long) of:

- **(a) a seventh point fix** for variant 6 — `;` / `&&` / `||` splitting that survives quoted words.
  Cheapest, keeps every test, leaves variant 7 to be discovered by whoever it blocks next.
- **(b) a real tokeniser** — split the command into segments on unquoted control operators first,
  then parse each segment's redirects and mutator arguments. Python's stdlib `shlex` already has
  `punctuation_chars=True`, which tokenises `;`, `&&`, `||` as separate tokens — this may be far
  closer to a drop-in than it sounds, and it is stdlib, which the hook requires.
- **(c) shrink the guard's job** — if precision keeps costing this much, argue for guarding fewer
  constructs and leaning harder on the gate. S8 permits this; it is not defeat.

Then **implement the choice.** If (b), the 113 existing cases must all still pass unchanged — that
is the acceptance criterion, not a nice-to-have.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green — **all 113 existing cases unmodified**,
  plus a case for variant 6 (`rm -rf "$S"; cp .claude/tools/x.py "$S/x.py"` → allowed; the same
  command writing genuinely into a protected tree → still denied).
- Replay the recorded false positives from all six variants through the live hook: none fire.
- The in-repo denials still deny: non-owner `cat > tests/x.py`, `cd .. && cat > <repo>/tests/x.py`,
  a real `specs/**/change.md` write.
- `uv run pytest .claude/tools` — whole meta suite green.

## Out of scope / Escalate if
- Do NOT relax the ownership rules (T06d) or the repo-root anchoring (T06e). This is about *parsing*
  the command, not about who may write where.
- Do NOT add a third-party dependency. The hooks are stdlib-only by design.
- **Escalate with the comparison before implementing (b) or (c).** (a) is a builder's call; the
  other two change the guard's shape and (c) changes what the workflow claims to prevent — those are
  the author's. Bring the comparison, not a finished rewrite.
