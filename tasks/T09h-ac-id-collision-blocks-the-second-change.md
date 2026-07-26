# T09h — AC ids collide across changes, so the *second* change in any repo cannot get a baseline

## Goal
AC ids are **per change** (`AC-1`, `AC-2`, …) and the pytest marker carries nothing else — verified:
`@pytest.mark.ac("AC-8")` in `users/002`'s tests, bare. But `red_check.analyze()` judges **every**
ac-marked test in the tree.

So on the second change of any context:

1. change `002`'s test-author writes red tests for *its* `AC-1`;
2. change `001`'s tests for *its* `AC-1` are still in the tree, accepted and **passing**;
3. `analyze()` sees a passing `AC-1` test → `GREEN BEFORE IMPLEMENTATION (a test that passes before
   code is suspicious)` → `RED-CHECK: FAILED`, no tag;
4. `/implement` step 1 blocks on the missing tag. **The change cannot start.**

**This blocks brownfield — the primary mode (F1).** It has never fired only by accident of history:
`platform/001` and `health/001` were first changes in their repos, and `users/002` followed
`users/001`, which was **abandoned** (branch deleted, its tests never persisted). The moment a repo
has one accepted change and starts a second, it hits this. Found by T09g's builder (its finding 2)
while scoping the new `hardening` path; it deliberately scoped that path narrower — only tests mapped
to *this* change's ids, pinned by `test_analyze_green_ignores_tests_of_other_changes_acs` — and left
the red path alone, because widening or narrowing redness is a design decision.

Two knock-on consequences, both from the same root:

- The gate's `--criteria` cross-check matches a `[x]` criterion to a **passed `ac`-marked test in this
  run's junit**; with colliding ids, change `002`'s `AC-1` can be "backed" by change `001`'s test.
- A `hardening` change's coverage *or* kill could in principle be satisfied by a same-id test from an
  older change (T09g narrowed its own path, so this is latent there, not live).

## Depends on
T09b (the tests-only baseline), T09f, T09g (which measured it and whose narrowed path is the model),
T04 (the gate's `--criteria` cross-check, the second consumer of the same mapping).

## Read first
- `.claude/tools/red_check.py` — `analyze()` (the red path, the live defect), and `analyze_green()` +
  `test_analyze_green_ignores_tests_of_other_changes_acs` from T09g: **the shape of the fix already
  exists in this file**, applied to one path.
- `.claude/tools/gate.py` — the `--criteria` junit cross-check: the same id→test mapping, the same
  collision, a different consumer. Do not fix one and leave the other (C7).
- `.claude/skills/testing-unit/SKILL.md` — the `@pytest.mark.ac("AC-n")` convention as taught. If the
  marker's *grammar* must change, this is where the house style lives and it must change with it.
- `workflow_v3_spec.md §3.3` (the criteria checklist) and `§5.1` (the junit cross-check) — **the spec
  wins**; if ids are canonically per-change then scoping is the fix, and if they are canonically
  global then the templates are wrong. Establish which before coding.
- `PRINCIPLES.md` S3, D3 (why "a test that passes before code" is suspicious at all — the property
  being protected is anti-collusion, and the fix must not weaken it).

## Deliverables
Decide between two shapes and say why:

- **(a) Scope the judgement to this change's ids** — the model T09g already used. `analyze()` takes
  the change's AC ids (it has them) and ignores markers outside that set. Smallest diff, keeps the
  marker grammar, keeps every test's meaning. Risk to state: a test marked with an id this change does
  not declare becomes invisible to `red_check` — so pair it with a **loud** report line listing
  ignored ac-ids, or an unrelated typo'd marker disappears silently (`notes/19`'s class).
- **(b) Make the marker carry the change** — e.g. `@pytest.mark.ac("users/002", "AC-1")` or
  `"users-002:AC-1"`. Removes the ambiguity at the source and makes provenance greppable, but it is a
  **house-style change** touching the skills, every existing test, and the gate's parse. Only if (a)
  cannot be made honest.

Prefer **(a)**, with the loud ignored-ids line. Whichever lands, fix **both** consumers — `red_check`
and the gate's `--criteria` cross-check — from one implementation.

## Verification
- `uv run pytest .claude/tools` green.
- **The scenario, end to end in a fixture:** a repo with an accepted change `001` whose `AC-1` test
  passes, plus a fresh change `002` declaring its own `AC-1` with a red test → `red_check` **tags the
  baseline**. Demonstrate the *pre-fix* failure first (`GREEN BEFORE IMPLEMENTATION`, exit 1, no tag);
  without that, the fix is unproven.
- **Anti-collusion is not weakened:** a change `002` whose *own* `AC-1` test passes before the code is
  still refused. This is the case that matters — (a) must not become "ignore inconvenient greens".
- **The gate's `--criteria` half:** a `[x]` criterion in change `002` is **not** satisfied by change
  `001`'s same-id test.
- `users/002` still reproduces unchanged (detached worktree at `a931ee6`, `--base markdown-specs`,
  `GATE_DOCKER=0` → ACCEPTABLE).

## Out of scope / Escalate if
- Do NOT weaken the green-before-implementation rule itself. It is the anti-collusion property (D3);
  scoping *which tests it judges* is the fix, ignoring greens is not.
- Do NOT change the `hardening` path T09g just landed — it is already correctly scoped and is the
  reference, not a target.
- Do NOT renumber or namespace ACs inside existing `criteria.md` files. `change.md` is frozen against
  its baseline (E-12), so any grammar change is a rebase for anything in flight.
- **Escalate if** the spec turns out to make AC ids canonically *global* per context rather than per
  change. Then the defect is in the templates and `/spec`, not in `red_check`, and the fix is a
  different task with a canon edit attached.
