---
description: Accept a finished change — merge its delta into the living spec, put both diffs in front of the human, and only on their word merge the branch, tag it and delete the delta
argument-hint: <NNN>
---

# Accept change `$ARGUMENTS`

> Invoked as `/adw:accept` when the workflow is installed as a plugin, `/accept` when it is loaded
> from a project's own `.claude/`. Both forms name this same file.

`$ARGUMENTS` is the change number, `NNN`. Its delta lives in `specs/changes/NNN-<slug>/`.

Accepting is the one place in this workflow where a **human** decides. Everything upstream — tests
written by one role and judged by another, an implementation judged by a third, a verdict from
someone who authored neither side — exists to make two diffs worth reading at this step. So the job
here is narrow and it is not "check the change again": it is to merge the delta into the living
spec, hand the human exactly what they must see, and act only on their answer.

## 1. Preconditions — read them yourself

Nothing below is checked by a program. The checklist and the verdict are prose written for a
reader, and at this step the reader is you, on behalf of the human.

- **You are on the change's branch** `change/NNN`, and the working tree is clean. Not on it → check
  it out. Uncommitted work already there → stop; someone is mid-step and you would accept a state
  nobody judged.
- **The delta directory exists** and carries `spec.md`, `criteria.md` and `verdict.md`. No verdict →
  the change was never judged; stop and say so. Producing a verdict is not your step.
- **Read `criteria.md`.** Every box is `[x]` or `[m]`. A single `[ ]` → stop and name it. The change
  is unfinished, and ticking a box here is the one edit that would make every tick in the project
  meaningless.
- **Every `[m]` has its reason in `verdict.md`.** A criterion accepted by hand with no reason
  written down cannot be told apart later from one that was forgotten. Missing → stop and ask for it
  to be recorded where it belongs, in the verdict.
- **Run `make check` on the branch, now**, and read the output. The verdict reports a run at some
  commit; the branch may have moved since. Red → stop with the failing command and its first real
  error.

## 2. Merge the delta into the living spec

The `Affects:` line of `spec.md` names the living spec file (or files) under `specs/` this delta
merges into. Work through `Changes` operation by operation:

- **`ADDED`** → new lines under `Operations`: the operation and what is observable when it runs.
- **`MODIFIED`** → find the line the living spec already carries and *change* it. The delta names
  the behaviour the way the living spec names it precisely so the merge has a target. Appending a
  second line beside the old one leaves the file asserting both.
- **`REMOVED`** → delete the operation line, and delete any invariant that pinned only the behaviour
  that is gone; its test went with it.

Then **every criterion that closed becomes an invariant, and every invariant carries its
provenance**. Without the name of the test, an invariant that has gone stale cannot be found:

- `[x]` → `- <the rule that now always holds> *(verified by: <test_id>)*`. The `<test_id>` is
  **copied** from that criterion's PASS line in the verdict, never invented. An invariant naming a
  test that does not exist is worse than one that admits nothing pins it — grep comes back empty and
  the reader believes the claim anyway.
- `[m]` → `- <the rule that always holds> *(MANUAL)*`. The reason stays in the verdict, in history;
  the living spec says what holds, not how one run went.
- A criterion whose only evidence in the verdict is a live run that no marked test repeats → also
  `*(MANUAL)*`.

An invariant is a rule about the system, not a checklist line: rewrite "AC-2: a refund above the
paid amount → 422" into the rule it implies. The AC numbers do not travel — they belong to the
delta and they die with it. Write in the language the living spec is written in.

**No capability file yet** — the project's first change, or a change that creates a capability:
create it from the workflow's `capability.md` template, fill `Purpose`, `Operations` and
`Invariants` from the delta, and delete the template's comments.

Leave the merge **uncommitted** for now. That edit is the first of the two diffs.

## 3. When `Affects` names more than one file

You **propose** the distribution; the **human approves** it. Say, operation by operation and
invariant by invariant, which file you would put it in and why, then ask and wait. Never pour
everything into the first file named because it was named first: an invariant filed under the wrong
capability is found by nobody, and it makes the next change's blast radius wrong.

## 4. After the merge: the size threshold

Count the lines of each living spec file you touched. Past roughly 300, tell the human and
**propose** a cut along what changes together — name the part of the file that recent deltas keep
touching on its own, and what you would call it. Then stop.

**You do not cut.** The threshold is a signal to a human, not an action of yours: re-slicing a
capability in the same breath as accepting a change buries a structural decision inside a merge diff
nobody agreed to review — and the whole point of the 300 lines is to keep that diff small enough
that it is actually read.

## 5. The two diffs, and the stamp

Both are mandatory. Neither may be skipped, summarized, or replaced by your account of it.

1. **The merge diff** — `git diff -- specs/`. What the system will claim about itself from here on.
2. **The test diff** — `git diff <baseline>..HEAD -- tests/`. Every edit made to the tests after
   they were committed, ahead of the code. This is the whole defence against tests bent until an
   implementation passed, and it works only because a human reads it.

The baseline is the commit on this branch where the tests were committed before any implementation;
its message identifies it, and the verdict's section on edits after baseline was written against it.
Cannot identify it unambiguously from `git log <base-branch>..HEAD` → **ask, do not guess**: a diff
taken from the wrong commit reads reassuringly empty.

Show both in full. When the second one is not empty, put it beside what the verdict says about it: a
test corrected and a test relaxed to let the code through look identical in a summary and different
in a diff.

**Then ask for the go-ahead and stop until it arrives.** A green checklist is not consent. A green
`make check` is not consent. "Looks good" said earlier about something else is not consent. Silence
is not consent. Nothing is merged, tagged or deleted before the human answers — a change waved
through here leaves the workflow with no human stamp at all, and the four roles upstream were spent
producing something no one signed.

Refused, or changes asked for → nothing is merged, nothing is tagged, nothing is deleted. Say what
would have to change, and stop.

## 6. Finish — in this order

The order carries weight: it is what keeps the delta reachable after it leaves the tree.

1. **Commit** the living spec merge on the change branch.
2. **Check out the base branch.** It is named as a step because merging is directional and you are
   standing on the wrong side of it: run the next step from `change/NNN` and you merge the base
   branch *into the change*, which succeeds quietly, leaves the delta sitting on the branch and puts
   the tag on a commit the base branch never sees.
3. **Merge** the branch into the base branch it started from (`git merge --no-ff`). Ambiguous which
   branch that is → ask.
4. **Tag** that merge commit `change/NNN`. Its tree still holds `specs/changes/NNN-*/`, and that is
   what makes the delta recoverable afterwards.
5. **Delete** `specs/changes/NNN-*/` and commit the deletion.
6. **Delete** the merged branch: `git branch -d change/NNN`. After the merge and the tag exactly one
   ref carries the change, so `change/NNN` written bare stops being two things at once and names the
   tag.

The delta is deleted, not kept somewhere else under another name. A second copy of the answer to
"what does the system do" poisons search: an agent greps the specs and finds a snapshot from change
003 that change 007 already overturned, and from then on grep cannot be trusted. After this step the
living spec is the only place that answers that question, and `verdict.md` — which describes one run
and never the system — belongs to history.

Finally tell the human, in a few lines: which living spec files changed and by how much, whether any
is over the threshold and what cut you proposed, whether anything was edited in `tests/**` after
baseline, the tag that was created, and how to get the delta back:

```
git show change/NNN:specs/changes/NNN-<slug>/verdict.md
git show change/NNN --stat
```
