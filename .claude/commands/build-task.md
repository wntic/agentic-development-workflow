# /build-task — execute one v3 build task

Dispatch the `v3-builder` agent on one task file from `tasks/` and relay its report.

## Usage

`/build-task tasks/T04-gate.md` (or just `T04` — resolve the unique file by prefix).

## Procedure

1. Resolve `$ARGUMENTS` to exactly one `tasks/TNN-*.md`; ambiguous or missing → ask.
2. Pre-flight (cheap, deterministic — do it yourself, don't burn the agent's session):
   - the task's "Depends on" entries are `[x]` in `tasks/INDEX.md`;
   - `git status` is clean and the current branch is the v3 work branch (not `main`).
   Any failure → report to the human, do not dispatch.
3. Dispatch ONE `v3-builder` subagent with the task file path and nothing else — the task
   file + its "Read first" list is the whole briefing by design. Do not paste task content
   into the prompt (two sources drift).
4. On return, relay the builder's report to the human VERBATIM in structure (status,
   deliverables, verification, findings, pending human verification). Do not soften RED
   into "mostly done".
5. If status is ESCALATE — surface the question and stop. If RED — offer exactly two
   options: re-dispatch with the failure attached, or hand to the human.
6. Never mark INDEX checkboxes yourself — the builder does it only on green verification;
   your job is orchestration and honest relay.

## Notes

- One task per invocation. Parallel tasks (per INDEX's parallelizable groups) = separate
  /build-task invocations; keep at most two builders in flight to keep review humanly
  possible.
- After T06 completes, its bypass suite result is the gate for dispatching T09 — check the
  INDEX note before proceeding past it.
