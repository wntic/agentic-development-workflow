# T09g — A change that only strengthens tests has no red phase, and therefore no home

---

## ESCALATION RESOLVED — author's decisions, 2026-07-26

The first dispatch reproduced all three premises (P1 the `--rebaseline` refusal, P2 the `invisible`
wall, P3 that F1/F2 are exposure not bugs) and escalated correctly. Its central finding changed the
question, so read that report first. Decisions:

**Option (b): a new class `hardening`, proved by mutation.** Not (a).

The dispatch's argument against extending `invisible` is decisive and I accept it: for a tests-only
change `invisible`'s declared proof is **trivially** satisfied — the `src` diff is empty, so the
OpenAPI diff cannot be non-empty and the gate cannot be non-green. It replaces the anti-collusion
property with *nothing*, which this task's own Out-of-scope forbids. And its finding 1 answers the
"which is it" question in an unexpected direction: **`invisible` is not a lane to extend, it is a
second unrunnable one** — `red_check.py` contains no `Class:` parse at all (verified: zero
occurrences of `invisible` or `Class:`), so an `invisible` change can never obtain a baseline tag and
`/implement` step 1 blocks on it. There is nothing there to extend.

**The shape:** `Class: hardening` on the `Class:` line; `change.md` grows a `## Mutations` section —
one fenced unified diff per mutation, each naming the AC ids it must kill. `red_check` gains a
class-keyed path that replaces redness with a strictly stronger pair:

- **GREEN-on-clean** — every ac-marked test passes in a worktree of the candidate commit; and
- **RED-on-mutation** — in a throwaway worktree with the patch applied, the named ACs **fail**.

Then it tags as usual, and `--rebaseline` reuses the same path, so both routes work with no hand
`git tag -f`. Three facts make this cheaper than "the most work", all from the dispatch: the mutation
is **attested for free** (E-12 already freezes `change.md`'s hash at baseline, and `change.md` is
already machine-read for `allowed_removals_text`); the **producing end already exists** (the
`users/002` adversarial section emits a mutation table in promotable form); and **D3/D4 survive** —
the mutation is spec content, applied only in a throwaway worktree, and nobody writes `src/**`.

**Sub-decisions the dispatch listed, all settled:**

- **Class name: `hardening`.** Short, matching the existing `behavioral | bugfix | invisible`
  register. It is a new `Class:` spelling, so **land it consistently with T03c** (which pins that
  vocabulary) rather than against it — if T03c has not run yet, write the value the way §3.1's
  register reads and say so in the report.
- **Who authors the mutation: the human at `/spec`**, lifting the M-table from the verdict of the
  change that found the weakness. Not the adversarial evaluator writing into the successor's
  `change.md` — that is the D4 exception this task warns about, and the dispatch found the agents are
  *currently honouring* the boundary (the `users/002` reviewer wrote "Fix shape (test-author's, not
  this reviewer's)"), so breaking it would be a live regression.
- **Scope of the mutation obligation: the new class only.** Generalising "every AC names a mutation it
  must kill" to all M/L changes is the strongest reading of mutation-as-proof and much the largest
  scope increase — it has to be earned by this class working first, not assumed.
- **`invisible`'s phantom proof: filed separately (T20), not folded in.** Its declared "empty
  before/after OpenAPI diff" is implemented in **no script** (verified: `openapi` appears in
  `.claude/tools/*.py` only where `gate.py`'s construct-smoke *calls* `app.openapi()`, never diffs it;
  `accept.py` defers the OpenAPI half to `/orient`, and T17 records that `/orient` defers it back).
  Same S4 family as T17, but a different class and a different lane.

**Canon edit: authorised, and it is mine to make — do not edit `workflow_v3_spec.md` yourself.**
§3.1's class register needs `hardening` with its proof obligation. Report the exact wording you need
and I will land it; write the code against the shape above meanwhile.

**Scope correction from the dispatch's findings 4 and 5 — this changes what "done" means:**

`markdown-specs` has no `specs/`, `src/` or `tests/` at all, `users/002` is unmerged on its branch,
and a builder subagent cannot dispatch subagents. So verification bullets 2–4 ("F1 lands and bites",
"F2 lands", "the route runs end to end") **cannot be discharged in this dispatch** — the dispatch was
right that they sit behind accepting `users/002`, which the task never listed as a dependency.
Therefore:

> **T09g delivers the *lane*, proved at fixture level.** The `red_check` class-keyed path, the
> `## Mutations` parse, the template section, `/implement`'s route for a change with an empty `src`
> diff, and tests that demonstrate GREEN-on-clean + RED-on-mutation against a synthetic repo. **F1
> and F2 landing as its first real customer is deferred to T11**, where a real cycle runs with real
> subagents. Say so in the report rather than claiming the lane is exercised.

**Do not escalate again on shape.** Escalate only if a specific piece of the lane cannot be built as
described — and name which.

---

## Goal
`users/002`'s adversarial pass found two surviving mutations:

- **F1** — deleting `.where(id == …)` from `save()` (so a PATCH rewrites **every** row) leaves all 19
  tests green. AC-8 and AC-9 each create exactly one user; AC-10 has a bystander but its PATCH 409s,
  so no test performs a *successful* PATCH with another row present.
- **F2** — a filtering soft delete passes AC-13. "No tombstones" is *устройство* and unenforceable as
  a criterion (S1), but the consequence is observable and belongs as an AC: re-creating a deleted
  user's email would 409 under the unique constraint.

Both are future-regression exposure, not shipped bugs — the shipped `save()`/`delete()` are correct
(verified: both carry `.where(id == …)`). The right response is to strengthen AC-8/AC-9 and add the
re-create criterion. **The workflow has no way to do that.**

The cycle assumes tests-before-code, red-then-green. `red_check.rebaseline` refuses unless the tests
are still a valid RED baseline:

```python
if not result.ok:
    failures.append("the corrected tests are no longer a valid RED baseline (see above)")
```

Strengthened tests over already-correct code are **green on arrival**. So a TESTS-HANDBACK is
refused, and a fresh change would hit the same wall at its own baseline. The adversarial pass — the
one step whose entire job is measuring test strength — produces findings the workflow cannot act on.
That makes it advisory theatre, which is precisely what S5/D3 exist to prevent.

## Depends on
T09 (the cycle), T09b / T09f (`red_check`'s baseline rules), T03 (change classes), T10 (acceptance).

## Read first
- `.claude/tools/red_check.py` — `rebaseline()` (the RED requirement at step (c)), `analyze()`,
  `non_tests_paths`, and the greenfield collection-error fallback.
- `workflow_v3_spec.md §3` — the change classes (`behavioral` / `bugfix` / `invisible`) and their
  proofs. **`invisible` is the closest existing fit** (AC = "behaviour has not changed", proof = a
  green gate + an empty OpenAPI diff) and it *also* has no natural red phase — so the workflow may
  already tolerate the shape, or may quietly have the same hole there. Establish which; it decides
  whether this is a new class or an existing one being extended.
- `.claude/commands/implement.md` §4 — the adversarial review, and what it is meant to produce.
- `PRINCIPLES.md` S3 (criteria are observable behaviour; append-only for agents), S5, D3, D4.
- `tasks/INDEX.md` — the F1/F2 entry under the users/002 findings.

## Deliverables
This is **design-sensitive**: bring the shape before building it. The question is *"what is the
sanctioned route for a change whose tests get stronger while behaviour stays identical?"* Candidates:

- **(a) extend `invisible`** — its proof is already "behaviour did not change"; a strengthened test
  suite fits that claim, and `red_check` grows an explicit no-red-phase path for the class.
- **(b) a new class** (`hardening` / `test-strengthening`) with its own proof obligation — e.g. the
  new tests must **fail against a stated mutation** rather than against the current code. That is
  strictly stronger than redness and it is exactly what the adversarial pass already produces.
- **(c) fold it into the adversarial pass** — let that step commit the strengthened tests directly
  within the change that produced the finding, before acceptance, under the evaluator's ownership.
  Cheapest in ceremony; but it puts test-authoring in the evaluator's hands, which collides with D4.

**(b) is the most interesting** because mutation-as-proof generalises: "this test fails when the code
is wrong in *this specific way*" is a better baseline than "this test fails when the code is absent".
It is also the most work. Whichever wins, F1/F2 must land as its first customer, and the AC wording
is the human's under S3 (drafts recorded in `tasks/INDEX.md`).

## Verification
Depends on the shape. Whatever it is, all of these must hold:

- `uv run pytest .claude/tools` green.
- **F1 lands and bites**: with AC-8/AC-9 strengthened, deleting `.where(id == …)` from `save()` makes
  the suite RED. Demonstrate it by mutation, not by assertion.
- **F2 lands**: a filtering soft delete fails the new re-create-a-deleted-email criterion.
- The sanctioned route runs end to end on `users/002`'s successor without a hand `git tag -f`.
- No existing change class loses its current proof obligation.

## Out of scope / Escalate if
- Do NOT weaken `red_check`'s RED requirement for ordinary changes. The anti-collusion property
  (D3: tests written before, and demonstrably failing without, the code) is load-bearing — a class
  that skips it must justify what it replaces it with, not simply drop it.
- Do NOT let the evaluator author tests without settling D4 explicitly. If (c) wins, the ownership
  boundary needs a conscious decision, not a silent exception.
- ~~**Escalate with the shape before coding.**~~ — **discharged: option (b), `hardening`, decided
  above.** Escalate only if a specific piece of the lane cannot be built as described.
- Do NOT edit `workflow_v3_spec.md` — §3.1's class register is the author's edit. **Report the exact
  wording you need** and write the code against the decided shape meanwhile.
- Do NOT fix `invisible`'s phantom OpenAPI-diff proof — that is **T20**.
- Do NOT claim the lane is exercised end to end. Fixture-level proof is this task's ceiling; F1/F2 as
  its first real customer is **T11**'s, for the reasons in the scope correction above.
