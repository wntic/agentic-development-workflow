---
description: Interview a human into one change — writes spec.md and criteria.md on a new change branch
argument-hint: [what the change should do]
---

> Invoked as `/adw:spec` when the workflow is installed as a plugin, `/spec` when it is loaded from
> a project's own `.claude/`. Both forms name this same file.

`$ARGUMENTS` is a free-form description of what the change should do. It may be one line, it may be
a paragraph, it may be empty — an empty one is not an error, it just means the first question comes
sooner.

This is the one place in the workflow where the decisions are a human's. So the standing rule for
everything below is: **where an answer would change what gets built, ask. Do not fill in the
plausible reading.** A guessed requirement becomes a guessed test and then a guessed implementation,
and by then nobody remembers it was a guess.

## 1. Orient

Read before you ask anything:

- every capability file in `specs/` — what the system already does. A requirement you would have
  written for behaviour that already exists is the most common way a delta wastes a cycle;
- `specs/changes/` — the deltas currently in flight;
- the code the description touches. Use file search and reading for a narrow question; hand a wide
  one ("where does anything like this live?") to the built-in read-only `Explore`.

Whether `specs/` holds even one capability file **is the entire answer** to "is there anything here
yet". There is no mode, no flag and no question to the human about it: every change does the same
three things — read what exists, write a delta, merge the delta — and on change number one the first
step simply returns nothing.

**If `specs/` is empty, say this to the human explicitly, before the interview goes further:** this
is the project's first change, so it drags the substrate along — package root, application shell,
wiring — and the substrate has no observable behaviour, which means no criterion can be written for
it. Therefore the change is shaped as a **vertical slice**: one criterion that runs end to end
through the assembled application, with the substrate riding underneath it. One thin behaviour that
really works beats a scaffold with nothing to prove.

## 2. Allocate the number

`NNN` is one more than the highest number already used, and "already used" means **both** of these
sets:

- the delta directories under `specs/changes/` — `ls specs/changes/`;
- the change tags in git — `git tag --list 'change/*'`.

Both, because a delta directory is deleted when its change is accepted. The directories alone will
happily re-issue a number that history already holds, and two changes with one number make the
history unreadable exactly when someone needs it.

Take the maximum of the numeric parts of the two sets, add one, and pad to three digits: `007`. That
identifier is then used unchanged in three places — the delta directory `specs/changes/NNN-<slug>/`,
the branch `change/NNN`, and the tag `change/NNN` that acceptance writes.

## 3. Interview

Ask about the things whose answer changes the work, and only those. Typically:

- **the edges** — what happens the second time the same call arrives, what happens on refusal, who
  is allowed to do this at all;
- **what is observable** — the status returned, the field in the response, the state left behind,
  the message that leaves the system. If the human describes an intention, ask what they would look
  at to see it happened;
- **what is deliberately out of scope** — what a reader would reasonably expect from this
  description and is not part of it;
- **every place the description can be read two ways.** Name both readings and let the human pick.

Where the choice is bounded, ask with `AskUserQuestion` — a short list of real options beats an open
question the human has to compose an answer to. Where it is genuinely open, ask in prose. Ask about
one thing at a time; twenty questions in a batch get one answer that covers three of them.

**Depth.** Propose one of S / M / L with your reason, and let the human decide:

- **S** — one behaviour, a bugfix. `Changes` and one to three criteria, nothing else.
- **M** — a typical feature. Adds `Why`, `Out of scope`, `Verification`.
- **L** — carries a cross-cutting structural decision, so it also has `Design` (step 4).

Propose the smallest depth that fits. A bugfix that arrives with four sections and sixteen criteria
is ceremony being filled in, not behaviour being named.

## 4. The five structural triggers

Run all five explicitly, and **tell the human the result** — for each one, fired or not, and if it
fired, which:

1. a new capability file or a new bounded context appears;
2. a new datastore or a new external integration appears;
3. the boundary of an existing aggregate moves;
4. a dependency between contexts appears;
5. a contract someone already relies on changes.

**None fired → the change has no `Design` section at all.** Not an empty heading, not a placeholder:
absent. This is the default and it covers most changes — local structure (where a module goes, a
value object versus a primitive, what a handler is called) is decided while the code is written, by
whoever writes it. Depth does not override this in either direction: a large change with no trigger
still carries no `Design` section, and a small change that moves an aggregate boundary carries one.

**One or more fired → the question goes to the human.** It is a question, not a proposal you adopt on
their behalf: the answer needs someone who knows where the project is going. When answering it needs
reading you have not done — "is this a new context or an extension of an existing one?" — give that
reading to the built-in read-only agents: `Explore` to find and summarise what is there, `Plan` to
weigh options against the existing tree. They read and report; the human decides; you write the
decision down. (Neither available? Read the code yourself — the decision was never theirs.)

What the decision looks like in the `Design` section:

- **binding** — the structural decision itself, the one the trigger fired for: where the boundary
  runs, which side of it a fact lives on, that this is a context of its own. A binding decision that
  turns out wrong is changed by coming back here, never by a silent workaround;
- **no identifiers at all** — not a module, not a class, not a constructor dependency. Naming is not
  a decision this interview takes: the first code of the change is its skeleton, written before any
  test, so whoever writes it chooses the names and everyone after reads them from the code. A name
  written here would be a contract published ahead of the code that has to carry it, and read twice;
- **non-binding** everywhere else — the approach taken, the options rejected, the reasoning. If that
  part and the code disagree later, the code is right.

## 5. Write

**Draft first, on screen, not on disk.** Compose both documents in full in your reply and put them
through the checks in step 6. Nothing is written until those pass, because a criterion that fails one
of them is fixed by asking the human another question — not by polishing the wording of a sentence
whose meaning was never settled.

Once they pass:

1. Create the branch `change/NNN` from the base branch, with a clean working tree.
2. Create `specs/changes/NNN-<slug>/`, where `<slug>` is two or three words of the title, lowercase,
   hyphen-separated.
3. Fill `spec.md` and `criteria.md` from the workflow's own skeletons — `templates/spec.md` and
   `templates/criteria.md`, shipped next to this command. Their comments say what each section is
   for and which depth carries it; a section this change does not carry is **deleted**, not kept as
   an empty heading, and the comments themselves are deleted once the section is filled. A criterion
   line carries a number **and** a slug — `- [ ] AC-1 · refund-exceeds-paid-amount: a refund above
   the paid amount → 422` — and the slug is written here, together with the criterion's text:
   lowercase, hyphen-separated, naming the observable behaviour, unique within this change. The
   number is for the human reading the checklist; the slug is what the test's marker will carry.
4. Commit the two files on their own, with a message naming the change. The delta belongs to git
   before any test exists, so that the diff a reviewer reads later is tests and nothing else.

That is all this command writes. No tests, no source, no `Makefile`, and it does not run the change
cycle that follows.

## 6. Output control — by a human, not by a machine

Seven checks, read by you and confirmed by the human. There is no pattern-match and no tool behind
them; reading is the mechanism, deliberately.

- **The delta's header is filled in** — `Affects:` names the capability file this delta merges into,
  `Depth:` names the depth agreed in step 3. Read the two lines in the draft; do not take it on
  trust that the skeleton carried them through. Without `Affects:` acceptance does not know which
  living spec to merge into, and the build cycle cannot check the invariant of at most one change in
  flight per capability — both read that field, and both read its absence as "no target".
- **If the change has a `Design` section: its binding part carries the decision and no identifiers.**
  Read it and strike every module, class, attribute and constructor dependency it names; what has to
  remain is the structural decision the trigger fired for. The names are not this document's to
  publish — the change's skeleton is written before any test, so they are chosen there and read from
  the code by everyone afterwards, and a name written here stands as a second account of the same
  thing, ahead of the code that has to carry it. This does not make `Design` mandatory: the section
  is present only when a trigger fired (step 4).
- **Every criterion names an observable artifact** — a status code, a field in a response, the state
  the system is in after the call, a message that left it. Not a property of the code: "a request
  over the size limit returns 413" is a criterion, "the middleware is configured correctly" is not.
  If you cannot say what you would look at, the criterion has not been written yet.
- **Vagueness markers.** If a criterion contains `correctly`, `properly`, `works`, `as expected` —
  or the same words in the language you are writing in — the observable part is still missing.
  Rewrite it. These four words are where an unwritten criterion hides most often.
- **Every criterion carries a slug, and the slug says what the criterion says** — the behaviour, not
  the implementation — and no two criteria of this change share one. That slug is the value the
  test's marker will carry, so a vague or a duplicated one loses the link between a criterion and
  its evidence.
- **`Verification` answers "how would this be proven"** — the commands, the environment they need,
  the seed data. A criterion whose environment is not covered there cannot be proven against a
  running system; saying so now is a decision, discovering it at the verdict is a surprise.
- **At least one criterion is provable through a really running application** — the real process
  against its real backing services, not only a unit test with in-memory fakes. A fully green suite
  of fakes and an application that does not start are compatible states, which is precisely why this
  check exists.

A check that fails sends you back to a question in step 3. It does not send you to a thesaurus, and
it does not lower the bar for one criterion because the rest are fine.

## Language

The spec and the criteria are written in the language the human is speaking to you in — they are
that human's documents. This command file is in English; the artifacts it produces are not
necessarily.

## When you are done

Tell the human, in four lines: the branch, the two file paths, the depth agreed, and which of the
five triggers fired (or that none did, and therefore there is no `Design` section).
