# T06h — Make the `ESCALATE` lock real: a commit, a history check, and a way to clear it

---

## ESCALATION RESOLVED — author's decisions, 2026-07-26

The first dispatch stopped correctly: part 3 is not derivable from §5.3, which says only «снять файл
может только человек» and specifies no mechanism. Its probe table is confirmed and is the
specification — read it in that report. Both decisions:

**Mechanism: option A — `red_check.py --change <ctx>/NNN --clear-escalate`.** Not option B.

- It makes an existing promise true instead of replacing it: `gate.py`'s own comment (verified, at
  `check_escalate_intact`) already says *"clear the file, then move the baseline
  (`red_check.py --rebaseline`)"*. That sentence is false today, because `--rebaseline` refuses a
  non-`tests/` commit. A closes the gap it describes.
- One home for baseline-tag movement (C7) — `red_check` already owns it. Option B is, in the first
  dispatch's own words, "A's script plus a new vocabulary": the enforcement still has to live in a
  script (S4), so B adds a concept without removing work.
- Guards, all three required: (i) an ESCALATE was added on this branch since the baseline and is now
  absent; (ii) **every** commit in `old-baseline..HEAD` touches nothing but
  `specs/*/changes/*/ESCALATE`; (iii) `--rebaseline`'s no-dropped-ac-marked-test guard. Guard (ii) is
  what makes this *strictly narrower* than `--rebaseline` — the old and new baseline trees differ only
  by the ESCALATE, so no criteria flip, `change.md` edit or dropped test can be laundered through it.
- **The ordering objection answers itself, which the first dispatch only half-noticed.** Guard (ii)
  requires the lock be cleared before anything else is committed — and in a *real* ESCALATE that
  holds by construction: since T09e the implementer commits `src/**` **only on green**, and an
  escalated change never reached green, so its `src/` is uncommitted. Say this in the error message
  when (ii) refuses, so the human knows the rule rather than guessing.
- Document the flag next to the existing `--rebaseline` paragraph in `.claude/commands/implement.md`
  §5. A thin `/adw:escalate-clear` wrapping the same flag can be added later without touching
  enforcement; do not add it now.

**Sub-question: (a) — accept that the path cannot distinguish a human from an agent.** An agent at its
ceiling can delete the file, commit, and run the clearing flag itself. That is S8's stated position:
the deliverable is that the act is **recorded** — a commit plus a tag move — not that it is prevented.
Do **not** add a `bash_guard` denial for the clearing invocation: a hook denial is ergonomics, and
T06i just closed the seventh false positive in that family (12 measured). Note (b) in the report as an
available follow-up if the recorded-act evidence ever proves insufficient.

**Also settled from the first dispatch's findings, so it is not rediscovered:**

- **Finding 1 — part 1 alone closes the worktree hole.** Once the ESCALATE is *tracked*, a fresh
  worktree carries it and today's `escalate.exists()` already denies. So the task's "the worktree case
  must deny" bullet is discharged by the commit; the history check is needed only for the
  delete-and-commit bypass. Keep the accept-side change small accordingly.
- **Finding 2 — do not add a second implementation in `accept.py`.** It re-runs `gate.py` in-process
  and echoes its checks, so a gate-side FAIL already turns `gate.green` red and denies. The
  accept-side edit is only about the **precheck** short-circuit that prints the human-facing reason.
- **Finding 3 — `git commit -- <path>` cannot commit an untracked path** (verified: *"did not match
  any file known to git"*). Part 1 is `git add -- <path>` then `git commit -- <path>`; partial-commit
  mode still ignores the rest of the index, so an agent's uncommitted `src/` is untouched.
- **Finding 4 — the hook currently does no git work at all**, and a consumer repo may have no
  `user.email`. Approved behaviour: attempt the commit; on failure still write the file and append the
  failure sentence to the `systemMessage`. **Never crash the hook, never lose the escalation** — that
  is the T06j rule (a precondition failure must be legible to whoever can act on it) applied here.
- **Finding 6 — preserve the asymmetry:** a *live* lock does not make `gate.py` RED (presence is
  `accept.py`'s business, §5.3); the gate judges only *removal*. Break this and every escalated change
  becomes un-gateable.
- **Finding 7 — keep T04e's rc-guard.** An unanswerable `git log` must FAIL, not read as "no
  ESCALATE" (`notes/19`'s fail-open class). `_baseline_paths()`'s swallowed rc one function away is
  **T04f**, not this task.

**Do not escalate again on shape.** Escalate only if a specific guard cannot be implemented as
written, and say which and why.

---

## Goal
§5.3 makes `ESCALATE` a human-only lock. It still isn't one. T04e built the fix as specified
(`integrity.escalate-intact`, commit `086fee5`) and the T04e builder then proved the specification
wrong — **the check cannot fire in the shipped flow.** Two independent reasons:

1. **The file is never tracked.** `.claude/hooks/subagent_stop.py:169` writes it with a bare
   `escalate.write_text(...)` — no `git add`, no commit — and `.gitignore` does not mention it. Git
   retains nothing about a never-committed file, so **no `gate.py`-only check can ever see its
   removal.** No agent misbehaviour is needed to defeat the lock; deleting a scratch file suffices.
2. **Even tracked, a baseline-vs-HEAD check would still miss it.** The hook fires at the
   *implementer's* ceiling — after the test-author's RED baseline is committed and tagged — and
   `red_check` refuses any baseline commit touching non-`tests/` paths. So an ESCALATE can never sit
   in the baseline tree: baseline "absent", HEAD "absent" → PASS.

Second victim of the same root cause: `accept.py`'s gate is `escalate.exists()` on the work tree. A
fresh `git worktree` never carries untracked files, so a **worktree-based acceptance cannot see a
genuine ESCALATE at all** — and that is how `notes/19`'s own `users/002` baseline was produced, and
how every acceptance run in the 2026-07-25/26 session was run. The gate that "denies while it
exists" has never been exercised against a real lock.

The three parts below are one task because any one alone leaves the lock broken: committing without
a history check is invisible; a history check without committing has nothing to read; and both
without a clearing step **deadlock the change** (see part 3).

## Depends on
T04, T04e (the shipped narrow check — extend it, do not duplicate it), T06 (the hook), T09b /
T09f (`red_check`'s tests-only baseline rule, which part 3 must not break), T10f.

## Read first
- `notes/19_accept_gate_audit.md` — the S8 Question-3 table **and the dated CORRECTION block under
  it**; that block is this task's specification.
- `.claude/hooks/subagent_stop.py` — the ceiling path and the `escalate.write_text` site; also how
  the hook currently avoids doing any git work at all.
- `.claude/tools/gate.py` — `integrity.escalate-intact` as shipped by T04e, and `_baseline_paths()`
  (see the escalate-if: it swallows the git rc).
- `.claude/tools/accept.py` — the `escalate` gate and the `GATES` TRUST/REVIEW registry from T10f.
- `.claude/tools/red_check.py` — `non_tests_paths`, `rebaseline()`; why an ESCALATE-only deletion
  cannot become a new baseline today.
- `workflow_v3_spec.md §5.3` (E-08, "escalation is material, not a line in an ephemeral report").
- `PRINCIPLES.md` S4, S8, S9.

## Deliverables
Three parts, all required:

1. **The hook commits the escalation.** `.claude/hooks/subagent_stop.py` writes *and* commits the
   `ESCALATE` — scoped to that one path (`git commit -- <path>`, never `-A`), so it cannot sweep an
   agent's uncommitted work into a commit it does not own. E-08's "material" becomes literal.
2. **A branch-history check, not a baseline diff.** `.claude/tools/gate.py` — the question is *"was
   an `ESCALATE` committed on this branch since the baseline, and is it now gone?"* → FAIL. Extend
   T04e's `integrity.escalate-intact` rather than adding a second check; keep its rc-guard (an
   unanswerable git call must not read as "no ESCALATE", per the `notes/19` fail-open class).
   Also fix `accept.py`'s presence-only gate to ask the same history question, so a worktree-based
   acceptance sees the lock.
3. **A sanctioned way for the human to clear it.** Today an ESCALATE-only deletion cannot become a
   new baseline: `red_check --rebaseline` refuses commits outside `tests/**` and `/implement`
   forbids a hand `git tag -f`. Without this, clearing a lock leaves the gate permanently RED.
   Choose and implement one — a `/escalate-clear` command, or a `red_check` flag that permits a
   baseline move over an ESCALATE-only deletion — and document it wherever §5.3's rule is stated.
- Tests for all three: `test_subagent_stop.py` (the commit is made, and is scoped to the one path),
  `test_gate.py` (committed-then-deleted FAILs; never-escalated unaffected; cleared-by-the-sanctioned-
  path passes), `test_accept.py` (a committed ESCALATE denies **through a detached worktree** — the
  case that would have caught this).

## Verification
- `uv run pytest .claude/tools .claude/hooks` (or the suites covering the three files) green.
- **The end-to-end bypass must fail.** Simulate the real sequence: ceiling → hook writes+commits
  ESCALATE → an agent deletes and commits over it → `gate.py` RED **and** `accept.py` DENIED.
  Demonstrate this fails against the pre-fix tooling (today it passes silently — that is the bug).
- **The worktree case must deny.** A committed ESCALATE, `accept.py --tree <detached worktree>` →
  DENIED. Today it PASSes.
- The `users/002` baseline still reproduces unchanged (branch `change/users-002` `a931ee6`, tag
  `baseline/users-002` `dd3a64b`, `--base markdown-specs`): it has no ESCALATE, so nothing about it
  may change.

## Out of scope / Escalate if
- Do NOT add the change dir to `gate.py`'s `PROTECTED_PATHS`. `criteria.md` flips and `verdict.md`
  writes are legal cycle traffic; freezing the directory deadlocks the cycle it guards.
- Do NOT try to identify *who* removed the file — the workflow cannot distinguish a human from an
  agent at the filesystem (the same reason `criteria_guard` cannot). The goal is to make removal
  **visible and gate-failing**, so that clearing a lock is a deliberate, recorded act.
- ~~**Escalate if** part 3's shape is not obvious from §5.3~~ — **discharged: option A, decided
  above.** Escalate only if a specific guard cannot be implemented as written.
- Do NOT add a `bash_guard` denial for the clearing invocation (sub-question (a) settled), and do NOT
  fix `_baseline_paths()`'s swallowed rc — that is **T04f**.
