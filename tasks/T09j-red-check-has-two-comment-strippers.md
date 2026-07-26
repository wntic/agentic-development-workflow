# T09j — `red_check.py` uses two different comment-strippers, and `accept.run()` prints a false sentence

## Goal
Two small findings from T10k, both in code it was forbidden to widen into.

**1. One file, two grammars for one rule.** `red_check.py` calls the shared
`criteria_lint.strip_html_comments` **and** carries its own
`_strip_html_comments(text: str) -> str` (a `re.sub(..., DOTALL)`) about thirty lines below that call.
They are not equivalent: the regex form **deletes** the span including newlines, so every line number
after a multi-line comment shifts, while the shared helper **blanks in place** and preserves line
count. T10k made the shared one public precisely because the whole enforcement layer depends on that
property — and this file quietly disagrees with itself.

Nothing is known to be broken today; the two are used for different needs (line-oriented vs
text-oriented). The defect is that one rule has two implementations in one file with no note saying
why, which is the C7 mistake that the `_section`-parse trio (T10h finding 2, T03c finding 8) already
had to be ruled on once.

**1b. And `accept.py` carries three more of the same** (T04h finding 4, added 2026-07-27):
`classify_removal`, `_significant_tokens` and `_has_real_content` each do their own
`re.sub(r"<!--.*?-->", …)` — the **deleting** grammar again — while the same file imports the public
line-preserving `strip_html_comments` for `_spec_lint` and `_overview_capability_tokens`. So the count
across the layer is **one shared helper plus four private re-implementations in two files**, and T10k
promoted the shared one to public precisely because the layer depends on its contract. Same rule, same
task: pick one grammar per need and write down why, or route them through the shared helper.

**2. `accept.run()`'s no-plan branch prints a merge that did not happen.** T10k fixed its arguments
(it was passing raw `base`/`tree`, a latent `TypeError`), but the branch then prints
`merged <branch> into <base>, tagged change/…, deleted the change dir` **although nothing was merged**
— it only ran the drift report. Currently unreachable (`plan is None` implies a FAIL implies an earlier
`return 1`), which is the reason to fix it rather than trust it: the next refactor that makes it
reachable produces a confident false statement about a merge, in the one script whose output the human
reads to decide whether `main` is safe.

## Depends on
T10k (which promoted the helper, fixed the arguments, and found both), T17 (which added `drift.py` and
the `drift_report` split), T09f (`red_check`'s baseline lint, the neighbourhood of the second stripper).

## Read first
- `.claude/tools/red_check.py` — the `cl.strip_html_comments` call site **and** the local
  `_strip_html_comments` below it; establish what each caller actually needs (a list of lines with
  positions preserved, or a blob).
- `.claude/tools/criteria_lint.py` — `strip_html_comments`'s docstring after T10k: it states that
  callers depend on line-count preservation. That is the contract to respect.
- `.claude/tools/accept.py` — `run()`'s tail, the `plan is None` branch, and `execute()`'s own report
  string, so the fix reports what actually happened rather than inventing a second wording.
- `tasks/T10h-*.md` finding 2 and `tasks/T03c-*.md` finding 8 — the precedent: three section parses
  were **ruled on and kept**, with the reason written beside the code. Either outcome is acceptable
  here; an unexplained duplicate is not.
- `PRINCIPLES.md` C7.

## Deliverables
- `.claude/tools/red_check.py` — one of: (a) route the text-shaped need through the shared helper
  (`"\n".join(strip_html_comments(text.splitlines()))`) and delete the local regex; or (b) keep both and
  write the reason beside the regex, naming the difference (span-deleting vs blanking, and which caller
  needs which). **Prefer (a)** unless a caller genuinely needs the span gone — then (b) with the reason.
- `.claude/tools/accept.py` — the no-plan branch reports the drift run truthfully and never claims a
  merge, tag or deletion. Keep it a single source: derive the sentence from what ran, do not add a
  second hand-written string that can drift from `execute()`'s.
- Tests: for (1), a multi-line comment followed by content — whichever grammar survives, pin the
  line-number behaviour its callers rely on, so the next reader cannot "simplify" one into the other.
  For (2), drive the no-plan branch directly (T10k's test already reaches it) and assert the output
  does **not** contain "merged" / "tagged" / "deleted".

## Verification
- `uv run pytest .claude/tools` green.
- For (2): the branch's output demonstrably differs from pre-fix — today it prints the merge sentence.
- For (1) under (a): `red_check`'s existing behaviour is unchanged. `red_check` is the anti-collusion
  screen, so a silent change in what it strips would move which baselines it accepts — run the full
  `test_red_check.py` and say so explicitly.
- `users/002` reproduces unchanged (INDEX recipe). **Commit tool edits before that run** (T18's cost).

## Out of scope / Escalate if
- Do NOT unify the three `_section`-style heading parses. That was ruled on in T03c and kept
  deliberately; this task is about comment-stripping and one report string.
- Do NOT make the `plan is None` branch reachable as part of this fix. Fixing what it prints is the
  scope; changing control flow in the acceptance script is not.
- **Escalate if** routing `red_check`'s text-shaped caller through the line-preserving helper changes
  any current verdict. That would mean the two grammars were load-bearing in different directions, and
  which one is right is then a question about the anti-collusion screen, not about tidiness.
