---
description: Run the change cycle on a change branch — the skeleton, the tests, a verdict on them, the baseline commit, the implementation, a verdict on that
argument-hint: <NNN>
---

# Build change `$ARGUMENTS`

> Invoked as `/adw:build` when the workflow is installed as a plugin, `/build` when it is loaded
> from a project's own `.claude/`. Both forms name this same file.

`$ARGUMENTS` is the change number, `NNN`. Its delta lives in `specs/changes/NNN-<slug>/`, and its
branch is `change/NNN`.

You are the orchestrator and nothing else. You dispatch four roles in a fixed order and you carry
concrete facts from each one to the next. You write no test, no line of source and no verdict of your
own: the entire value of four roles is that each judges work it did not author, and an orchestrator
who quietly writes part of the work removes exactly that.

Nothing below is ordered by a program. This prose is the order, which is why it is worth reading
before the first dispatch, and why two things in it have to be done honestly — both were measured to
fail otherwise:

- **the baseline commit happens only after the red phase has a verdict.** Tests committed before
  anyone judged them make a baseline nobody read, and every diff taken from it afterwards is
  reassuring for the wrong reason;
- **what you hand to the next role is the previous role's own text.** "The reviewer found some
  problems" is not a handoff. The reviewer's `REQUIRED FIXES` lines are.

Each role is a subagent shipped next to this command, in `agents/`. Dispatch it by its type —
`adw:test-author` when the workflow is installed as a plugin, `test-author` when it is loaded from a
project's own `.claude/`; the same pairing as the two names of this command.

## 0. Preconditions — all of them, before the first dispatch

An unmet precondition is a **stop with an explanation**, not a reason to try anyway. Every one of
them fails silently later if you skip it here: on the wrong branch you build into someone else's
change, and against an already-red base branch you cannot tell your own breakage from the one that
was waiting for you.

- **You are on `change/NNN`.** Not on it → check it out. The working tree is dirty → stop and say
  what is uncommitted; somebody is mid-step, and their work is not yours to commit or discard.
- **`specs/changes/NNN-<slug>/` exists and carries `spec.md` and `criteria.md`.** Missing → the
  change was never specified. `/adw:spec` writes them, with a human, and that is not this step.
- **No other change is in flight against the same capability.** Read the `Affects:` line of every
  delta under `specs/changes/`. Another one names a living spec file this delta also names → stop and
  say which two. They would be written against the same file blind to each other, and the second
  acceptance would merge into a spec the first has already moved.
- **The base branch is green.** Run `make check` on it and read the output; the project's `Makefile`
  is the whole definition of green. Red → stop with the failing command and its first real error.
  There is no `make check` to run at all → say so, and then read `specs/` before you decide what it
  means. Exactly one of two things is true, and which one is a matter of reading, not of a setting:
  - `specs/` carries **no capability file at all** → this is the project's first change, and there is
    nothing in the tree for a check to be green about yet. That absence is the expected state, not a
    stop: the `Makefile` arrives with the rest of the substrate at step 5, and from that change on this
    precondition has something to run. Say which of the two cases you found, and carry on.
  - `specs/` carries **at least one** capability file → **stop and ask the human before you dispatch
    anything.** A project with a living spec has been green before, so a check that is now missing says
    the tree is in a state nobody described, and that is theirs to look at. An absent check is not a
    green one, and deciding on their behalf that it is would be the first guess of the change.

Read the delta yourself before step 1 — `spec.md` and `criteria.md`, in full. You need to know
whether the change carries a `Design` section and a `Verification` section, because who gets each of
them is the substance of the handoffs below.

## 1. `implementer` — the skeleton

Before a test can be written, the names it imports have to exist. Dispatch `implementer` with:

- the path to the delta's `spec.md`;
- the path to its `criteria.md`;
- the `Design` section of `spec.md` **if the delta has one**. If it has none, say so in as many
  words, so the agent does not go looking for a section that was deliberately not written.

What comes back is packages, modules and the signatures of classes and methods — full annotations,
**bodies of `...`**, **no docstrings**, no behaviour of any kind. It is the shape of the change and
nothing else; nothing in it is written to make a test pass, because there are no tests yet.

**Why this step exists is the language, not the model.** A test has to import a name, and against a
name nothing defines yet Python raises `ModuleNotFoundError` while it is still *collecting* the file:
the whole file disappears from the run — every test in it, every marker — and the reviewer at step 3
never sees a single one of them by name. A skeleton removes that condition instead of working around
it: the imports are ordinary imports, and the tests fail on their assertions.

**Then commit the skeleton — here, before you dispatch step 2.** The implementer leaves its work in
the working tree and lists every path under `FILES`; the committing is yours, as it is for every
commit in this cycle. Write a message that makes the commit recognisable **as the skeleton** — the
word *skeleton* and the change number in the subject line — for the same reason the baseline commit
below carries its own word: a later reader separating "the shape was laid" from "the behaviour was
written" has `git log` and nothing else to do it with. If the skeleton needed a dependency declared,
that edit is in the working tree too; it goes in this same commit.

This dispatch **does not count against the ceiling** at step 7. The ceiling counts dispatches of the
implementation, and this is not one.

Do not add to the skeleton yourself and do not ask for behaviour "while it is open". A body that is
not `...` at this point is implementation before the baseline, and the review at step 3 fails the red
phase over it — correctly.

## 2. `test-author` — the tests

Dispatch it with, and only with:

- the skeleton just committed: its commit SHA, and the paths the implementer listed. These are the
  names the tests are written against, and they are in the tree — so an import of one of them is an
  ordinary module-level import;
- the path to the delta's `spec.md`;
- the path to its `criteria.md`;
- the `Design` section of `spec.md` **if the delta has one**. If it has none, say so in as many
  words, so the agent does not go looking for a section that was deliberately not written.

On a repeat of this step — sent back from step 3, or reached again because step 5 returned
`CONTRACT-CHANGE` and the skeleton was re-laid at step 1 — add the returning role's own text, quoted,
and nothing else new.

Read the report it returns. Two of its lines are yours to act on and not the next role's:
`UNCOVERED CRITERIA` and `QUESTIONS FOR THE SPEC`. A criterion with no test, or an ambiguity about
what the criterion means, is a question for the **human** — a criterion's wording is frozen and
changes only through `/adw:spec`. Take it there rather than to the reviewer, who cannot answer it
either. `PHASE: BLOCKED` is the same: stop, with what the agent reported.

## 3. `test-review` — the verdict on the red phase

A **fresh dispatch**, not a continuation of anything. Give it the paths to `spec.md` and
`criteria.md`, and nothing the author told you. That omission is deliberate: it must run the tests
itself and read the criteria itself, because a report of a run in place of a run is precisely the
failure this role exists to catch.

You do not judge the red phase yourself — not by running the tests to double-check, not by reading
the test files and forming an opinion. A verdict from the orchestrator is a verdict from someone who
chose the dispatch, and it is worth no more than one from the author.

- `VERDICT: FAIL` → back to step 2, carrying the verdict's own `REQUIRED FIXES` lines, and its `Q1`
  to `Q4` answers where they say why. Paste them; do not summarise them. A paraphrase drops the one
  detail the next attempt needed, and it is not even cheaper.
- `VERDICT: PASS` → step 4, and only now.

**What the verdict is a verdict about.** It answers one question — *can the baseline be committed
now?* — and not *are these tests good?*. That is a decision about the route, not a grade, so a review
that finds the tests healthy and still names weaknesses that have to be closed before any code is
written is a `FAIL` carrying `REQUIRED FIXES`, and reads as one. A `PASS` that arrives with fixes
attached to it is the same thing said the other way round and is not a pass: send it back to step 2
with those fixes, and say that is what you did. Measured on change 003 — a reviewer wrote `PASS` with
a note because the tests were sound, the baseline went in with the gap open, and a human closed it by
hand afterwards, which is the most expensive place to close it.

## 4. The baseline commit

Commit the tests the review just passed, and nothing you added to them.

**Write a message that makes the commit recognisable as the baseline** — the word *baseline* and the
change number in the subject line. Nothing in this workflow stores that commit for you: the evaluator
later, `/adw:accept` later still, and a human reading `git log` all find it by its message, and a
diff taken from the wrong commit comes back comfortingly empty.

Then **record its SHA and hand it forward explicitly**, as a SHA, to every dispatch below that needs
it. The whole defence against tests bent to fit an implementation is one command against this
commit — `git diff <baseline>..HEAD -- tests/` — read by the evaluator and again by the human at
acceptance. "The baseline commit" as a phrase in a prompt is not that; a SHA is.

**A test edited between the baseline and the implementation is legitimate when the commit that edits
it explains why** — the guard shows the edit either way, and what it is looking for is an
explanation, not an empty diff; unexplained, it stays what the verdict has to account for.

The skeleton was committed at step 1, and the dependencies the tests need by the author, on their
own, after it. This commit is the tests, and it is **yours and not the author's**: the author leaves
the tests in the working tree and lists them, so that exactly one commit exists for every later
reader to diff from, and its message is the one written here. Tests arriving under a message of the author's own make no commit
identifiable as the baseline at all.

## 5. `implementer` — the code

Dispatch it with:

- the baseline SHA;
- the paths to `spec.md` and `criteria.md`;
- the `Design` section if the delta has one;
- on a repeat dispatch: the path to `verdict.md` and the evaluator's own `WHAT REMAINS` and
  `ADVERSARIAL FINDINGS` lines, quoted.

Green means the project's `make check`, and the answer you accept is a run of the whole target, not
of a subset. Red at the end is a legitimate thing for it to report; carry that report to step 6
rather than re-dispatching to try again, because what a stuck green phase needs is a verdict from
someone else, not another attempt at the same reading.

**`PHASE: CONTRACT-CHANGE` goes back to step 1, never around it.** It means the skeleton laid at
step 1 cannot carry the behaviour the criteria ask for — a signature has to change, and the tests
written against that signature change with it. Carry the implementer's own lines: which signature
fails, on which test, what is needed instead. What you must not do is re-dispatch the implementer
with permission to make do: a default argument, a second name meaning the same thing, an adapter over
the mismatch. Each of those ends with the tests and the code agreeing with each other and both
disagreeing with the change everyone thinks was made.

Going back to step 1 restarts the red phase in full: the skeleton is re-laid and committed again, the
tests are written against it (step 2), they need their verdict again (step 3) and the baseline moves
to the new commit (step 4). Record the new SHA and hand that one forward. A diff taken from the
superseded baseline reports the corrected tests as edits made after it, which is the opposite of what
it is for.

**Then commit the implementation — here, before you dispatch step 6.** The implementer leaves its work
in the working tree and lists it; committing it is yours, and the moment matters more than it looks.
Write a message that says this is the implementation of change `NNN`, so a reader of `git log` can see
which phase put it there. Do this before every dispatch of step 6, the repeat passes included — a
green report and a red one alike, because a verdict is exactly what a stuck green phase is being sent
for.

Dispatching the evaluator with the source uncommitted empties out the one reading the whole cycle rests
on: `HEAD` is then still the baseline commit, so `git diff <baseline>..HEAD -- tests/` returns nothing —
not because the tests were left alone, but because there is no range. **An empty diff looks reassuring
and proves nothing**, and that is measured, not feared: on the first real change run through this
workflow the implementation went uncommitted, the guard read empty, and the orchestrator ended up
rewriting history to give it something to say. Commit here and it has something to say by construction.

**This commit now has a second consumer, and that one is destructive:** the evaluator's adversarial pass
applies wrong implementations to the working tree and reverts them, and a revert restores what is
committed — so an uncommitted implementation would be reverted away rather than restored.

## 6. `evaluator` — the verdict on the green phase

A **fresh dispatch**: not a continuation of the implementer's, and not the dispatch that did step 3.
Give it:

- **the baseline SHA**, as a SHA;
- the path to `criteria.md`;
- the `Verification` section of `spec.md` if the delta has one — the commands, the environment and the
  seed data that make a live proof possible. If the delta has none, say so: then no criterion can be
  proven against a running system on this change, and the evidence is the marked tests. Saying it now
  is a decision; discovering it inside the verdict is a surprise.
- the implementer's `NOTES FOR THE EVALUATOR` line, if it wrote one, marked for what it is: a pointer
  to look at something closely, not evidence about it.

Do not pass on the implementer's claim of green. The evaluator runs `make check` itself, moves the
boxes in `criteria.md` in both directions, and writes `verdict.md`. Its verdict is the one that
counts; yours does not exist.

**Then commit the verdict and the moved boxes.** The evaluator leaves `verdict.md` and the edited
`criteria.md` in the working tree; commit both here, with a message that says the verdict of the green
phase produced them, and do it on a `FAIL` exactly as on a `PASS`. A `FAIL` is a state of the change
worth reading later, and step 7 may send the cycle round again, which writes over the same two files —
whoever looks afterwards wants to see which verdict was written against which implementation.

That is the fourth and last commit this command makes in a pass: the skeleton at step 1, the tests at
step 4, the implementation at step 5, the verdict here. The author's dependency commit sits between
the first two of them and is theirs, not yours. Nothing else about the state of the change is written
down anywhere — it is these commits, plus `criteria.md` and `verdict.md`, and it needs no fifth kind.

## 7. The branching, and the ceiling

- **`VERDICT: PASS`** → the cycle is done, and the change is not accepted. Report (below) and stop.
  Acceptance is a human's step, `/adw:accept NNN`, and it exists so that somebody reads two diffs.
- **`VERDICT: FAIL`** → a **new** dispatch of step 5, carrying the path to `verdict.md` and the
  evaluator's own lines about what remains.

**The ceiling is two dispatches of the implementer for the implementation in this change.** It counts
the dispatches of step 5 that **came back**, whatever each of them returned — a `FAIL` loop and a
`CONTRACT-CHANGE` round trip both spend one. A `FAIL` returning after the second → **stop and talk to
the human.** Do not dispatch a third.

Three kinds of dispatch do not count against it, and all three for the same reason — nothing of the
implementation was spent:

- **the skeleton at step 1**, and its re-laying after a `CONTRACT-CHANGE`. It is not an
  implementation dispatch;
- **a dispatch the platform cut off mid-flight.** Measured: a 529 arrives as a real error to you,
  loudly, in direct contrast with the iteration limit below, which arrives silently. It costs the
  full wall time of the dispatch and produces no work at all, so there is nothing to have spent —
  dispatch it again, and say in your report that you did and why;
- **a dispatch the platform killed for stalling.** Measured, and it arrives just as loudly:
  `Agent stalled: no progress for 600s (stream watchdog did not recover)`. Same conclusion as the 529 —
  nothing of the implementation was spent, so dispatch it again and say that you did. One thing differs
  and it matters: a killed agent's edits **stay on disk**. **Read the tree before you re-dispatch** —
  `git status`, and the files that dispatch was told to produce — and say what you found, because a
  blind re-dispatch writes over somebody's unfinished work and the second attempt then builds on half of
  a first one nobody read.

A **resume of a dispatch that already came back** — a `SendMessage` to the same agent rather than a
new dispatch — is not a new dispatch and does not count against the ceiling either. Measured on
change 004: the implementer returned `BLOCKED`, was resumed, and finished green; counting that
resume would have put a healthy run at the ceiling on its correct move.

The number was decided on 2026-07-29, and the design document's own §6 states it the same way — a
count of implementer dispatches rather than of full passes. Two reasons, both about
cost: it reaches the human sooner, and a dispatch of this role is expensive before it does anything
at all — the house-style knowledge preloaded into it was measured at roughly 41.7 thousand tokens of
context, paid again on every dispatch.

**The ceiling is held here, by this prose, and not by any per-agent iteration limit in the agent
definitions.** Measured on 2026-07-29: when the platform's own iteration limit fires, the parent
receives `completed` — sometimes an empty result, sometimes an early fragment of the agent's own text
that reads like a report — with no error and no field saying a limit was reached. A truncated phase
and a finished one are indistinguishable from the return value, so a limit you cannot observe cannot
be what protects a human's attention. A count you keep in this conversation is observable.

Hitting the ceiling is a conversation, not an artifact and not a failure. Tell the human what is
known — the branch, the baseline SHA, the path to `verdict.md`, which criteria are still `[ ]`, what
each implementer dispatch returned, and what you would try next — and wait for their answer. They may
well say carry on, and that answer is the reset; nothing needs to be written down for it. Do not
create a marker file, a status file or a record of where the cycle got to: the state of a change is
git — the branch, the baseline commit, the commits after it — plus `criteria.md` and `verdict.md`.
Anything else is a second copy of that answer, and it goes stale the first time somebody runs a step
by hand.

## When the spec itself is wrong

Any role may come back saying that `spec.md` or its `Design` section is wrong — a criterion asserts
something the delta contradicts, a structural decision cannot be built, two sections disagree. **No
role fixes it, and neither do you.** The role returns it as a question and stops; you take that
question to the human, quoted, and wait. If they change the spec, the change to it is a commit of its
own, made through `/adw:spec` and separate from anything this cycle commits, so that a later reader
can see the spec moved and when. Then the cycle restarts from the step the correction touched — the
skeleton if the shape moved, step 2 if only the criteria's wording did — and the steps after it run
again in order. What this exists to prevent is measured: on change 002 the cycle improvised a
spec commit in the middle of its own work, and afterwards nothing distinguished what was specified
from what was discovered while building.

## One at a time

Inside one change the four roles run **strictly one after another**, one dispatch at a time. Never
two in a single message, and never a second role started while the first is still working. This is
not caution about resources: test-driven development is sequential by construction — the reviewer
judges tests that exist, the implementer works against tests already committed, the evaluator judges
code already written. There is nothing for a second role to do concurrently except duplicate a
reading that is about to change. A change that feels like it wants to be worked in parallel is a
change that wants to be cut into two deltas, and cutting it is `/adw:spec`'s job, not a matter of
more dispatches here.

Across the repository the limit is the one checked in step 0: at most one change in flight per
capability.

## What you tell the human at the end

However the cycle ended — pass, fail at the ceiling, or a stop in the middle — report in a few lines:

- the branch, and the baseline commit SHA;
- how many implementation dispatches were spent against the ceiling, and what each returned — and
  separately, any dispatch that did not count, the skeleton and anything the platform cut off;
- the state of `criteria.md`: how many `[x]`, how many `[m]`, and **which** are still `[ ]`, by number;
- the path to `verdict.md`, and what it says about edits to `tests/**` after the baseline;
- what remains, concretely, or that nothing does;
- the next step: `/adw:accept NNN` on a pass, or the decision you are waiting for.

Write it in the language the human is speaking to you in. Report what the agents returned and what
you observed — not that a step "succeeded". Every stop in this file is designed to be readable by a
human who was not watching, and a summary that smooths over a `FAIL` costs the next reader the one
thing they came for.
