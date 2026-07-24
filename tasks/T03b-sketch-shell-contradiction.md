# T03b — Interface sketch must not claim "no layers" when the mandated shell ships them

## Goal
Remove a wording trap that fires a false alarm on every capability-birthing first change. On
`/implement platform/001` the Interface sketch said *"No domain / application / infrastructure
layers"*, but the `restapi` skill's mandated app shell (central `DomainError` handler) forces
`src/app/domain/exceptions.py` + `restapi/error_handler.py` + `schemas/errors.py`. The implementer
had to flag it as a "judgment call" and the evaluator as a **V-09 "loud, not a block"** observation.
Both proceeded correctly, but the sketch and the house-style shell contradict each other, so every
first change burns reasoning on reconciling them and lands a V-09 the human must read past.

## Depends on
T03 (the `/spec` interview + change.md template + Interface-sketch guidance), and the shell
definition in the `restapi` / `architecture` skills.

## Read first
- `.claude/skills/restapi/SKILL.md` — the one-shot app-shell bootstrap (what it ALWAYS ships:
  central `DomainError` handler → needs a domain-exception base + an error response schema).
- `.claude/commands/spec.md` + `.claude/templates/change.md` — where the Interface-sketch prose /
  guidance for a first change is authored.
- `specs/platform/changes/001-health-endpoint/change.md` — the offending sketch wording, and the
  evaluator's V-09 note in the run's `verdict.md`.
- `notes/greenfield-first-change-blockers.md` finding #4.

## Deliverables
- The `/spec` Interface-sketch guidance (command prose and/or the change.md template comment) —
  stop asserting "no domain/application/infrastructure layers" as a blanket statement for a
  first change. Instead distinguish the **always-present app shell** (the `restapi` skill's
  `create_app()` + central `DomainError` handler + its domain-exception base + error schema) from
  **business layers** (entities, handlers, repositories, adapters), and phrase the sketch as
  "no business domain / application / infrastructure — the standard app shell only". So a
  first-change sketch that ships the shell is CONSISTENT with what it declares.
- If the mismatch is better fixed at the evaluator's V-09 heuristic (recognise the shell files as
  in-scope substrate rather than out-of-scope diff), note that as the alternative and pick one —
  do not fix it in both places.

## Verification
- Re-author (or dry-review) a greenfield first-change sketch with the new guidance: the shell
  files it will need (`domain/exceptions.py`, `error_handler.py`, `schemas/errors.py`) are
  clearly WITHIN what the sketch declares, so a correct implementation produces **no V-09**.
- `uv run pytest .claude/tools/test_skill_catalog.py` still green (no paid-fix phrase dropped if
  skill text is touched).

## Out of scope / Escalate if
- Do NOT change what the `restapi` shell actually generates — the shell is correct; only the
  sketch's DESCRIPTION of it is wrong. This is a wording/altitude fix (C6), not a code-shape change.
- If it turns out some apps genuinely want a shell WITHOUT the central error handler (so the shell
  is contingent, not universal), that is a C6 scope-overclaim question — escalate rather than
  freezing either variant as universal.
