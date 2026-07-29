---
description: Run the change cycle on a change branch — tests, a verdict on them, the baseline commit, the implementation, a verdict on that
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
    stop: the `Makefile` arrives with the rest of the substrate at step 4, and from that change on this
    precondition has something to run. Say which of the two cases you found, and carry on.
  - `specs/` carries **at least one** capability file → **stop and ask the human before you dispatch
    anything.** A project with a living spec has been green before, so a check that is now missing says
    the tree is in a state nobody described, and that is theirs to look at. An absent check is not a
    green one, and deciding on their behalf that it is would be the first guess of the change.

Read the delta yourself before step 1 — `spec.md` and `criteria.md`, in full. You need to know
whether the change carries a `Design` section and a `Verification` section, because who gets each of
them is the substance of the handoffs below.

## 1. `test-author` — the tests

Dispatch it with, and only with:

- the path to the delta's `spec.md`;
- the path to its `criteria.md`;
- the `Design` section of `spec.md` **if the delta has one** — say that the names it publishes are
  the contract the tests are written against. If it has none, say so in as many words, so the agent
  does not go looking for a section that was deliberately not written.

On a repeat of this step — sent back from step 2, or from step 4 — add the returning role's own text,
quoted, and nothing else new.

Read the report it returns. Two of its lines are yours to act on and not the next role's:
`UNCOVERED CRITERIA` and `QUESTIONS FOR THE SPEC`. A criterion with no test, or an ambiguity about
what the criterion means, is a question for the **human** — a criterion's wording is frozen and
changes only through `/adw:spec`. Take it there rather than to the reviewer, who cannot answer it
either. `PHASE: BLOCKED` is the same: stop, with what the agent reported.

## 2. `test-review` — the verdict on the red phase

A **fresh dispatch**, not a continuation of anything. Give it the paths to `spec.md` and
`criteria.md`, and nothing the author told you. That omission is deliberate: it must run the tests
itself and read the criteria itself, because a report of a run in place of a run is precisely the
failure this role exists to catch.

You do not judge the red phase yourself — not by running the tests to double-check, not by reading
the test files and forming an opinion. A verdict from the orchestrator is a verdict from someone who
chose the dispatch, and it is worth no more than one from the author.

- `VERDICT: FAIL` → back to step 1, carrying the verdict's own `REQUIRED FIXES` lines, and its `Q1`
  to `Q4` answers where they say why. Paste them; do not summarise them. A paraphrase drops the one
  detail the next attempt needed, and it is not even cheaper.
- `VERDICT: PASS` → step 3, and only now.

## 3. The baseline commit

Commit the tests the review just passed, and nothing you added to them.

**Write a message that makes the commit recognisable as the baseline** — the word *baseline* and the
change number in the subject line. Nothing in this workflow stores that commit for you: the evaluator
later, `/adw:accept` later still, and a human reading `git log` all find it by its message, and a
diff taken from the wrong commit comes back comfortingly empty.

Then **record its SHA and hand it forward explicitly**, as a SHA, to every dispatch below that needs
it. The whole defence against tests bent to fit an implementation is one command against this
commit — `git diff <baseline>..HEAD -- tests/` — read by the evaluator and again by the human at
acceptance. "The baseline commit" as a phrase in a prompt is not that; a SHA is.

The dependencies the tests need were committed by the author, on their own, before this commit. This
one is the tests.

## 4. `implementer` — the code

Dispatch it with:

- the baseline SHA;
- the paths to `spec.md` and `criteria.md`;
- the `Design` section if the delta has one — its published names are what the tests were written
  against;
- on a repeat dispatch: the path to `verdict.md` and the evaluator's own `WHAT REMAINS` and
  `ADVERSARIAL FINDINGS` lines, quoted.

Green means the project's `make check`, and the answer you accept is a run of the whole target, not
of a subset. Red at the end is a legitimate thing for it to report; carry that report to step 5
rather than re-dispatching to try again, because what a stuck green phase needs is a verdict from
someone else, not another attempt at the same reading.

**`PHASE: CONTRACT-CHANGE` goes back to step 1, never around it.** It means a published name cannot
carry the behaviour, and the honest repair is that the tests and the code are written against a
corrected name. Carry the implementer's own lines — which name fails, on which test, what is needed
instead. What you must not do is re-dispatch the implementer with permission to make do: a default
argument, a second name meaning the same thing, an adapter over the mismatch. Each of those ends with
the tests and the code agreeing with each other and both disagreeing with the change everyone thinks
was made.

Going back to step 1 restarts the red phase in full: the tests change, so they need their verdict
again (step 2) and the baseline moves to the new commit (step 3). Record the new SHA and hand that
one forward. A diff taken from the superseded baseline reports the corrected tests as edits made
after it, which is the opposite of what it is for.

## 5. `evaluator` — the verdict on the green phase

A **fresh dispatch**: not a continuation of the implementer's, and not the dispatch that did step 2.
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

## 6. The branching, and the ceiling

- **`VERDICT: PASS`** → the cycle is done, and the change is not accepted. Report (below) and stop.
  Acceptance is a human's step, `/adw:accept NNN`, and it exists so that somebody reads two diffs.
- **`VERDICT: FAIL`** → a **new** dispatch of step 4, carrying the path to `verdict.md` and the
  evaluator's own lines about what remains.

**The ceiling is two dispatches of the implementer in this change.** It counts dispatches, whatever
each of them returned — a `FAIL` loop and a `CONTRACT-CHANGE` round trip both spend one. A `FAIL`
returning after the second → **stop and talk to the human.** Do not dispatch a third.

The design document's own §6 says "3 full passes"; the number in force is **2**, decided on
2026-07-29, and it counts implementer dispatches rather than full passes. Two reasons, both about
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
- how many implementer dispatches were spent, and what each returned;
- the state of `criteria.md`: how many `[x]`, how many `[m]`, and **which** are still `[ ]`, by number;
- the path to `verdict.md`, and what it says about edits to `tests/**` after the baseline;
- what remains, concretely, or that nothing does;
- the next step: `/adw:accept NNN` on a pass, or the decision you are waiting for.

Write it in the language the human is speaking to you in. Report what the agents returned and what
you observed — not that a step "succeeded". Every stop in this file is designed to be readable by a
human who was not watching, and a summary that smooths over a `FAIL` costs the next reader the one
thing they came for.
