# T11 — E2E probe runbook (WP7, human-driven)

## Goal
The moment of truth: drive the full v3 loop on the Meeting Assistant corpus, measure, and
produce an honest defect log. This task is a RUNBOOK for the human + main session — the
v3-builder agent does not execute it.

## Depends on
T01–T10 all `[x]`; T06's bypass suite green (the spec's hard gate).

## Read first
- Spec §9 (both cases), §10 WP7, §12 (what to measure); `specs/use-cases/UC-10..17`;
  `notes/pipeline_dryrun_feedback.md` (the honesty discipline to replicate).

## The probe script
1. **Greenfield vertical slice:** `accounts` context from empty overview.md — `/spec` the
   §9-L-style first change (sign-in slice from UC-10: one observable AC + substrate),
   `/implement`, `/accept-change`. Then UC-11 as a normal M-change.
2. **Brownfield S-case:** UC-16 complete-action-item per §9 (requires a meetings context —
   scope it as its own vertical slice first, or run the S-case against accounts with an
   analogous small delta; decide at runtime, record the decision).
3. **Concurrency check (S9):** two changes in flight on different capabilities —
   branches isolate, accept order exercises the Affects-intersection flag.
4. **One deliberate escalation:** pick a change with an intentionally under-specified
   Interface sketch → observe CONTRACT-CHANGE protocol fire.
5. **One removal-class change** (drop a behavior added earlier; the toy /health accepted
   in T10 is the natural candidate) → orphan sweep exercised.

## Deferred completions to close here (need a constructed app)
- **OpenAPI-drift half of §5.5** (T05 finding 5): accept.py + /orient do the git-attributable
  half (unlinked src commits); the route⊆operation comparison needs a running app — wire and
  exercise it now, against the real probe app.
- **Orphan sweep** (T05 finding 6): the removal-class change below is its first real exercise
  — confirm it actually catches a dead symbol / dropped spec text, not just unit fixtures.

## Measurements (spec §12.3 decision inputs)
Per change: human touchpoints count · wall-clock · agent dispatches · iterations-to-green ·
fast-lane vs full evaluator · any manual intervention (= finding, no exceptions).

## Deliverables
- `notes/18_v3_probe.md` — growing defect log, same format as the v2 dry-run feedback
  (severity legend, findings F-101+, executive synthesis last, honesty caveats explicit).
- Verdict on the §12 open questions: fast-lane sufficiency, batch-accept need, evaluator-env
  reality, cost per change vs "just asking Claude".

## Exit criteria
- ≥5 changes merged to main through the full loop; ≥1 escalation exercised; ≥1 removal;
  bypass suite still green at the end (run gate + enforcement tests once more);
  notes/18 synthesized.

## Escalate if
- Any gate has to be manually overridden to proceed → STOP the probe, log it as a blocker
  finding, fix the tooling task (T04–T06) first. Laundered green is worse than red —
  the v2 dry-run's chief lesson.
