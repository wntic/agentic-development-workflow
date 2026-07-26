# T09i — the tests-only baseline screen inspects HEAD only, so earlier commits go unscreened

## Goal
`red_check`'s anti-collusion screen refuses a baseline whose commit writes outside `tests/**` (T09b:
the red-tests commit must be tests-only, so the test-author cannot smuggle in code). It inspects
**HEAD only** — `baseline_commit_paths()` looks at one commit.

Since **T12**, a change branch always has at least two commits before the baseline: the test-author's
pre-baseline `deps:` commit (`pyproject.toml` + `uv.lock`) and then the tests-only commit. That is by
design and the screen correctly passes, because only the last commit is examined.

But nothing forces the *shape* of what comes before. A test-author who commits `conftest.py` first and
the tests second — or `src/` first and tests second — gets the first commit **unscreened**, and the
baseline tag then anchors a tree containing unreviewed non-test content. The screen's stated property
("the baseline commit is tests-only") is true; the property it exists to buy ("nothing but tests and
declared deps entered the tree before the baseline") is not.

Found by T09h's builder while reading `analyze()` (its finding 6). Not its defect, and it noted that
it is filed nowhere — this is that filing.

**Severity: latent, and it fails open.** No run has hit it (every test-author so far committed deps
then tests, in that order), and the gate's `integrity.protected-trees` covers `.claude/**`,
`pyproject.toml` and settings — but **not** `src/**`, because `src/` is legitimately the implementer's
lane *after* the baseline. So a `src/` file introduced in a pre-baseline commit is invisible to both
scripts, which is the shape D3 exists to prevent (test and code written from one understanding).

## Depends on
T09b (the screen), T12 (which introduced the legitimate second commit), T09f.

**Not** T09h — corrected 2026-07-27. The original line listed it, but T09h only *found* this and its
judged/ignored reporting is a **model to imitate, not a precondition**; T09h is itself blocked on an
author decision about `users/002`, and blocking this task behind that would be a dependency I invented.
If T09h has landed by the time you run, read its reporting for the shape; if not, design the
"what did this screen examine" output yourself and say so.

## Read first
- `.claude/tools/red_check.py` — `baseline_commit_paths()`, `non_tests_paths()`, `tag_baseline()` /
  `finish_tagging()` (T09g made the screen class-independent), and `rebaseline()`'s guard (a) which
  asks the same question over a *range* — **that range logic is the shape this task wants**, so reuse
  it rather than writing a second one (C7).
- `.claude/commands/implement.md` §1 — the sanctioned pre-baseline sequence: `deps:` commit, then the
  tests-only commit. That sequence is the specification of what "legal before the baseline" means.
- `.claude/agents/test-author.md` — what the test-author is told to commit, in what order.
- `PRINCIPLES.md` D3, D4, S8; `workflow_v3_spec.md §5.1` (the baseline integrity inventory).
- `notes/19_accept_gate_audit.md` — the fail-open direction rule: an unanswerable git call FAILs.

## Deliverables
- `.claude/tools/red_check.py` — screen the **whole pre-baseline range**, not just HEAD. The question
  is: *between the branch point and the baseline candidate, does every commit write only `tests/**`
  or only the declared deps files (`pyproject.toml`, `uv.lock`)?* Reuse `rebaseline()`'s range walk;
  keep its **merge-commit refusal** (T06h found that `git diff-tree -r <merge>` prints no paths, so a
  merge would read as "touches nothing") and its rc-guards.
- **Decide and state the anchor** for "branch point". `rebaseline` has the old baseline tag; a *first*
  baseline has no tag yet. Candidates: the base branch's merge-base with HEAD (needs a base, and
  T10g's `derive_base` exists — but it aborts on ambiguity, so a first baseline would start failing in
  a two-branch repo), or the change branch's first commit. **Prefer the narrowest thing that works,
  and if the anchor cannot be resolved, FAIL loudly** rather than degrading to today's HEAD-only check
  — a screen that silently narrows is worse than one that is known to be narrow.
- Print what was screened (how many commits, which paths were allowed and why), in the same spirit as
  T09h's judged/ignored partition. A screen nobody can see the scope of is how this survived.
- `.claude/tools/test_red_check.py` — cases: `conftest.py`-then-tests **refused**; `src/`-then-tests
  **refused**; the sanctioned `deps:`-then-tests **passes**; a merge commit in the range **refused**;
  an unresolvable anchor **FAILs**, never passes.

## Verification
- `uv run pytest .claude/tools` green.
- Each new case demonstrably behaves differently against pre-fix `red_check` — today all of them tag
  happily, which is the defect.
- **The sanctioned sequence still works**, and this is the case that matters: replay a real
  greenfield first change's commit shape (`deps:` commit + tests-only commit) and confirm the baseline
  is still tagged. If this regresses, every future first change is blocked.
- `users/002` still reproduces (detached worktree at `a931ee6`, `--base markdown-specs`,
  `GATE_DOCKER=0` → ACCEPTABLE) — its branch carries exactly the sanctioned two-commit shape, so it is
  the live regression fixture for this task.

## Out of scope / Escalate if
- Do NOT widen the gate's `PROTECTED_PATHS` to include `src/**`. `src/` is the implementer's lane after
  the baseline (D4); freezing it would deadlock the cycle.
- Do NOT change what the sanctioned sequence *is* — that is `/implement` §1 and T12's ruling. This task
  enforces the existing rule over a range; it does not redesign the rule.
- **Escalate if** the branch-point anchor cannot be resolved without depending on `derive_base`'s
  ambiguity abort. Making every first baseline depend on a resolvable base branch trades a latent
  fail-open for a live fail-closed, and that trade is the author's to make, not a builder's.
