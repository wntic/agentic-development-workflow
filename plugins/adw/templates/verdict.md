# Verdict — <NNN-slug>

<!-- The report of ONE run, written by someone who authored neither the tests nor the code. It does
     not describe the system — that is the living spec's job — so it belongs to history and is
     deleted with the delta on acceptance.
     Fill the placeholders, delete these comments. -->

<!-- `Baseline` is the full SHA, never abbreviated: acceptance reads `git diff <baseline>..HEAD --
     tests/` from it — the one defence against tests bent until the code passed — and a diff taken
     from the wrong commit is empty and looks reassuring. -->

Baseline: <full git SHA of the commit holding the tests, before any implementation>
Commit: <git SHA the run was made against>
`make check`: <green | red — and which of the four commands failed, with the first real error>

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

<!-- Not "do the tests pass" — that is above. Would each marked test FAIL if the implementation were
     wrong in the obvious ways? Take a criterion, name a plausible wrong implementation, and say
     whether any test would catch it. Assertions that hold for both the right and the wrong version
     (status checked but body ignored, a call counted but its arguments not, a truthiness check where
     the value matters) are named here even when everything is green. -->
