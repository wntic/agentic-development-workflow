# T06i — Seven point fixes into the `bash_guard` tokeniser: decide whether to keep patching

## Goal
`bash_guard`'s command tokeniser has now produced **seven** distinct false positives, each found by an
agent it blocked, each closed by a point fix that left another variant open:

| # | Task | The variant |
|---|---|---|
| 1 | T06b | a protected path inside a quoted `-m "…"` commit message read as a target |
| 2 | T06e | absolute paths matched location-insensitively (`/tmp/.../tests/…` denied) |
| 3 | T06f A | relative targets resolved against the session cwd, no `cd` awareness |
| 4 | T06f A | filename fragments matched as bare substrings (`change.md` ⊂ `users-002-change.md`) |
| 5 | T06g | heredoc **bodies** tokenised — prose in a commit message read as a redirect |
| 6 | open | `rm -rf "$S"; mkdir …` — the `;` glues onto the quoted word, `_slice_until_control` never sees a CONTROL token, and `rm`'s target slice swallows **the rest of the command**, including a later `cp`'s *source* path. A single space before the `;` flips the verdict, and the reason string blames a path the command only reads. (Found building T04e; cost that builder two denied commands.) |
| 7 | open | **Unexpanded shell variables resolve against the repo root.** `rm -f "$CD/specs/…/ESCALATE"`, where `$CD` is a scratchpad path *outside* the repo, was DENIED for role `v3-builder`: the guard does not expand `$CD`, so the token is not absolute, `_repo_relative` joins it onto the repo root, and `specs/` then matches as whole components. **Every** out-of-repo path referenced through a variable is mis-attributed to the repo tree. Found building T06j, and it trained the bypass reflex on that builder — it re-ran with literal absolute paths. Cheap fix in the family's own idiom: a token containing an unexpanded `$` is *indeterminate*, so return `None`, exactly like T06f's unknown-cwd case. |

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

---

## DECISION MADE IN ADVANCE — author, 2026-07-26

**Go with (b): the real tokeniser.** Do not spend a dispatch escalating the comparison; the evidence
that would have driven it is already in. Reasons, in order of weight:

1. **Seven variants, and variant 7 arrived *after* this task was filed** to describe six. That is the
   trajectory argument settled by observation rather than opinion: (a) does not converge.
2. **Under S8 a false positive is the expensive failure.** The guard is ergonomics — the gate is the
   backstop — so its job is to be *accurate*, not smaller. Every miss so far trained the bypass
   reflex on the agent it blocked (measured on four separate builders) and named a path the command
   only *read*. That argues for a correct parse, not fewer constructs.
3. **The risk is bounded by the suite.** The 116 existing cases are the specification of what the
   guard means; if they all pass unchanged, the rewrite is behaviour-preserving by construction.
4. `shlex(punctuation_chars=True)` is stdlib, which the hooks require, and tokenises `;` / `&&` /
   `||` as their own tokens — the exact defect in variant 6.

**(c) is rejected for now.** Shrinking what the guard claims to prevent is a change to the
workflow's promises, not to its parser, and nothing forces it while (b) is available.

**Still write the comparison** — briefly, in the report — because it is how you discover that (b)
cannot work. **Escalate only if** the measurement contradicts the decision: `punctuation_chars=True`
cannot keep all 116 cases, or keeping them requires re-introducing the hand-rolled slicing this task
exists to remove. In that case bring the failing cases, not a redesign.

---

## Deliverables
First, a short written comparison (in the report, or `notes/` if it runs long) of:

- **(a) two more point fixes** — for variant 6, `;` / `&&` / `||` splitting that survives quoted
  words; for variant 7, treat a token containing an unexpanded `$` as indeterminate. Cheapest, keeps
  every test, leaves variant 8 to be discovered by whoever it blocks next. Note that variant 7
  appeared *after* this task was filed, which is itself evidence about (a)'s trajectory.
- **(b) a real tokeniser** — split the command into segments on unquoted control operators first,
  then parse each segment's redirects and mutator arguments. Python's stdlib `shlex` already has
  `punctuation_chars=True`, which tokenises `;`, `&&`, `||` as separate tokens — this may be far
  closer to a drop-in than it sounds, and it is stdlib, which the hook requires.
- **(c) shrink the guard's job** — if precision keeps costing this much, argue for guarding fewer
  constructs and leaning harder on the gate. S8 permits this; it is not defeat.

Then **implement the choice.** If (b), the 116 existing cases must all still pass unchanged — that
is the acceptance criterion, not a nice-to-have.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green — **all 116 existing cases unmodified**
  (count as of T06j; re-check before starting), plus:
  - variant 6: `rm -rf "$S"; cp .claude/tools/x.py "$S/x.py"` → allowed; the same command writing
    genuinely into a protected tree → still denied;
  - variant 7: `rm -f "$CD/specs/x/ESCALATE"` with `$CD` unexpanded → allowed; a *literal*
    `specs/x/ESCALATE` write by a non-owner → still denied.
- Replay the recorded false positives from all seven variants through the live hook: none fire.
- The in-repo denials still deny: non-owner `cat > tests/x.py`, `cd .. && cat > <repo>/tests/x.py`,
  a real `specs/**/change.md` write.
- `uv run pytest .claude/tools` — whole meta suite green.

## Out of scope / Escalate if
- Do NOT relax the ownership rules (T06d) or the repo-root anchoring (T06e). This is about *parsing*
  the command, not about who may write where.
- Do NOT add a third-party dependency. The hooks are stdlib-only by design.
- ~~**Escalate with the comparison before implementing (b) or (c).**~~ — **discharged: the decision
  is (b), recorded above.** Escalate only if the measurement contradicts it (all 116 cases cannot be
  kept), and then bring the failing cases rather than a redesign.
- Do NOT fix the `agent_type` namespace handling (T15/D1 already did it) and do NOT touch the
  `ROLE_OWNED` / `PROTECTED_FRAGMENTS` contents — this is the parser, not the policy.
