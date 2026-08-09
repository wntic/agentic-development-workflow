---
description: Debrief of one completed adw-cycle run in a consuming project — dispatches adw-analyst over the report bundle; draft findings that pass go to the plan/FINDINGS.md register. Renders no dispositions, fixes nothing, gives the run no score.
argument-hint: "[bundle-path | consumer-repo-path] [change/NNN]"
---

# /debrief — debrief of one run

You are the main session of this repository. Your work here is four steps and nothing beyond
them: dispatch the analyst, check its drafts, record the ones that pass into the register,
report to the human. The protocol for reading a run does not belong to you — it lives with the
`adw-analyst` role and in `plan/ORIENT.md` §5; it is not restated here.

## Steps

1. **Input.** From `$ARGUMENTS` — a path to a report bundle **or** a path to the consumer
   repository, optionally plus `change/NNN`. If there is no bundle — generate the report over
   the consumer repository with the `agent-report` plugin; the invocation form and where the
   bundles live are in the plugin's own command (`/agent-report`) and are not restated here.
   Given neither a bundle nor a consumer — ask the human. Do not guess.

2. **Dispatch `adw-analyst`, one per run.** In the prompt: the bundle path, the consumer
   repository path, and the change's tag or branch. And nothing more: what to read and in what
   order, the role knows itself (its definition and `ORIENT` §5).

3. **On return — your work, not its.**
   - Every draft of class `ИЗМЕРЕНО` carries a command and its output; where the run is cheap,
     re-verify by running it, not on trust.
   - Deduplicate against the register by headers: `rtk proxy grep '^## F-' plan/FINDINGS.md`.
   - Write the ones that pass to the end of `plan/FINDINGS.md` in the house format from its
     header, with the lines
     `Найдено: разбор прогона <NNN> в <потребитель>, adw-analyst` and
     `Решение отложено до: человек`.
   - Write no dispositions — only the human gives those, expectedly via `/interview`.

4. **Report to the human.** How many drafts were recorded; which were discarded and why
   (a duplicate, did not reproduce, not about this repository); the next step — `/interview`.

## Boundaries

- No edits outside `plan/FINDINGS.md` — neither in this repository nor in the consumer.
- Nothing gets fixed: a discovery is a register entry, not an edit.
- `plan/INDEX.md` is not touched.
- A run score does not exist — the debrief's output is draft findings and reproducible facts,
  not a grade.
