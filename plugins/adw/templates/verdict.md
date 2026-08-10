# Verdict — <NNN-slug>

<!-- The report of ONE run, written by someone who authored neither the tests nor the code. It does
     not describe the system — that is the living spec's job — so it belongs to history and is
     deleted with the delta on acceptance.
     Fill the placeholders, delete these comments. -->

<!-- `Baseline` is the full SHA, never abbreviated: acceptance reads `git diff <baseline>..HEAD --
     tests/` from it — the one defence against tests bent until the code passed — and a diff taken
     from the wrong commit is empty and looks reassuring. -->

<!-- `Workflow tree` pins the other half of the run: the workflow is read from its own working tree,
     not from a frozen copy, so the agents, commands and skills behind this run are whatever that tree
     held at the time — and it has been edited while runs were in flight. A defect later attributed to
     this run ("measured on change NNN") is only checkable if the workflow it ran under can be named,
     and this line is the only place that names it. Full SHA, same reason as above. -->

Baseline: <full git SHA of the commit holding the tests, before any implementation>
Commit: <git SHA the run was made against>
Workflow tree: <full git SHA of the workflow repository the plugin was read from during this run>
`make check`: <green | red — and which of the four commands failed, with the first real error>

<!-- `alembic check` runs beside `make check` and is no part of it: nothing inside that target sees a
     `Table` drifting from the migration that creates it, and a suite stays green straight through the
     divergence. It is run only when this change's diff touched both a `Table` and an Alembic revision;
     a change that left the migrations alone writes `not applicable` and the line stops there. -->

`alembic check`: <its answer verbatim | not applicable — the diff touched no `Table`+revision pair>

## Criteria

<!-- One line per criterion of the checklist, in order, no criterion skipped.
       PASS    · the marked test that proves it, by test id — or the live run, described concretely
                 enough to repeat (request made, response seen)
       FAIL    · what the run actually showed, next to what the criterion requires
       MANUAL  · who accepted it, on what evidence, and why no test can pin it
     If a criterion was proven at a different commit than the one above, its line names that SHA. -->

- AC-1 — <PASS | FAIL | MANUAL> · <what proves it>
- AC-2 — <PASS | FAIL | MANUAL> · <what proves it>

## Edits to `tests/**` after baseline

<!-- Read `git diff <baseline>..HEAD -- tests/` and answer here. "None" is a complete answer and the
     expected one. Anything else is listed hunk by hunk with the reason it was necessary — a test
     relaxed to make the code pass is the failure this section exists to surface, and it is visible
     only if someone reads the diff. -->

## Adversarial pass

<!-- Not "do the tests pass" — that is above. For each criterion, take a plausible wrong
     implementation and, where you can build it as an edit, run it: apply it to the working tree, run
     the suite, revert the edit, and confirm the mutation is out — `git status --porcelain` asked
     about the paths that mutation touched, empty — with `make check` green. Ask it about those paths
     and not about the tree: the moved boxes in `criteria.md` and this verdict are dirty by design at
     this point, so a bare status can never come back empty and clearing it would destroy them. The
     number the run gave you goes on the line, not the number you
     expected. Where the wrong version cannot be built as an edit — the behaviour lives outside the
     tree, the criterion is only provable live — the named wrong version with the reasoning about it
     stands, and the line says which of the two was done. Assertions that hold for both the right and
     the wrong version (status checked but body ignored, a call counted but its arguments not, a
     truthiness check where the value matters) are named here even when everything is green. -->

<!-- The two forms, one line each — applied on top, reasoned below. Delete the one you did not use
     for that criterion; the run's own output is what goes where the numbers are. -->

- AC-1 — applied · <the wrong implementation, as the edit that built it> · suite: <what the run
  gave, e.g. "72 passed, 1 failed — tests/…::test_x"> · reverted, `git status --porcelain
  -- <the paths it touched>` empty, `make check` green again
- AC-2 — reasoned · <the wrong version, named> · <why it cannot be built as an edit> · <what
  would or would not catch it>
