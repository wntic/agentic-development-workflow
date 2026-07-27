# T10e — Classify removal-flavour structurally, not by grepping prose

## Goal
`accept.py`'s `_orphan_sweep` misclassifies ordinary changes as removal-flavour and then harvests
half the Interface sketch as "removed symbols". It blocked `/accept-change users/002` with a
`[FAIL] orphan.sweep` reporting `DomainError`, `Email`, `IUserRepository` as "removed behaviour
still present" — on a `Class: behavioral` change that removes nothing.

Two compounding defects, both at `.claude/tools/accept.py:868` / `:872`:

1. **The classifier never required a heading.** `(?im)^#*\s*removed\b` uses `#*` — *zero*-or-more —
   so it matches any line starting with optional whitespace followed by `removed`. In `users/002` it
   fires on a wrapped sketch continuation line: `  removed id, or ` + "`None` when no user held it."
2. **The section capture starts at the wrong match.** `(?is)removed[^\n]*\n(.*?)(?:\n##|\Z)` anchors
   on the *first* `removed` anywhere in the file — in `users/002` that is `` `True` when a row was
   removed `` — and runs to the next `##`. Measured on that change: 2206 captured chars yielding 19
   terms, including `id`, `email`, `name`, `save`, `find`, `None`.

Defect 2 matters even once defect 1 is fixed: a *genuine* removal change would harvest the same
generic identifiers and drown its real signal. Fix both.

The structural signal already exists and is ignored: `Class: behavioral` sits at `change.md:3`.

## Depends on
T10 (the acceptance script), T05 (`accept.py` gate inventory), T03 (the `change.md` template that
owns the `Class:` line and any `## Removed` heading).

## Read first
- `.claude/tools/accept.py` — `_orphan_sweep()` (the classifier + capture + `orphan_violations`).
- `.claude/templates/` — the `change.md` skeleton: confirm what `Class:` accepts and whether a
  `## Removed` section is part of the template or ad-hoc prose.
- `specs/users/changes/002-user-crud/change.md` on `change/users-002` — the regression fixture.
- `workflow_v3_spec.md §5` (V-02, the orphan sweep's purpose) — the sweep must keep working for
  real removals; this narrows *classification*, not the check.

## Deliverables
- `.claude/tools/accept.py` — classify removal-flavour from **structure**:
  - primary: the `Class:` line declares the removal flavour;
  - secondary: a real heading — `(?m)^#+\s*Removed\b` (note `#+`, one-or-more);
  - and **anchor the term capture to the matched heading**, not to a free-floating `removed`. When
    classification comes from `Class:` alone with no `## Removed` heading present, prefer an
    explicit SKIP-with-reason over harvesting the whole document.
- `.claude/tools/test_accept.py` — cases:
  - `users/002`'s `change.md` verbatim as a fixture → classifier does **not** fire (regression);
  - a `## Removed` heading listing two backticked symbols → fires, captures exactly those two;
  - prose containing "removed" with no heading and a non-removal `Class:` → does not fire;
  - a genuine removal change whose sketch *also* says "removed" in passing → captures only the
    heading's terms, not the sketch's.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green, including the `users/002` regression case.
- `uv run .claude/tools/accept.py users/002` on the rebased branch → `orphan.sweep` SKIP or PASS,
  and no other gate regresses. (`spec.lint` FLAG for the missing `user-management.md` is expected
  and correct — `--execute` creates it.)

## Out of scope / Escalate if
- Do NOT weaken `orphan_violations` itself — the sweep's *check* is sound; only its input is wrong.
- Do NOT add an override or `--force` path for a red `orphan.sweep`. The whole point of the finding
  is that a gate must not be readable-past (S4, S8).
- If the `change.md` template turns out not to pin a vocabulary for removal-flavour on the `Class:`
  line, that is a T03 template gap — record it and escalate rather than inventing the vocabulary
  here, since `/spec` has to emit whatever this classifier reads.
