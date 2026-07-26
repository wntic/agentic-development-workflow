# T09g — A change that only strengthens tests has no red phase, and therefore no home

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
- **Escalate with the shape before coding.** This adds or redefines a change class, which is spec §3
  territory — and `workflow_v3_spec.md` is never edited by agents. Expect the outcome to include a
  canon edit the author makes.
