# T20 — The `invisible` class cannot be run, and its declared proof exists in no script

## Goal
`invisible` is one of three change classes canon declares (`workflow_v3_spec.md:211-214`, echoed by
`.claude/templates/change.md:8-10` and by `CLAUDE.md`). Two measurements, both from T09g's escalation:

1. **It cannot obtain a baseline tag, so `/implement` cannot start it.** `red_check.py` contains **no
   `Class:` parse at all** — verified: zero occurrences of `invisible` or `Class:` (the only `Class`
   hit is `ast.ClassDef`). Neither `test-author.md` nor `evaluator.md` mentions it either. So the
   class-specific proof it is supposed to get never happens, and `red_check` simply applies the
   redness rule; T09g's repro `repro2.py` drove a `Class: invisible` change to `RED-CHECK: FAILED`,
   no tag. `/implement` step 1 blocks on the tag, so the class is unreachable.
2. **Its declared proof is implemented nowhere.** The promise is "a green gate **+ an empty
   before/after OpenAPI diff**". Grepping `openapi` across `.claude/tools/*.py` finds only
   `gate.py`'s construct-smoke, which **calls** `app.openapi()` and never diffs it, plus
   `accept.py`'s line saying the OpenAPI half is "surfaced by `/orient`" — and **T17** records that
   `/orient` defers it straight back to `accept.py`. Nobody runs it.

So a class exists in canon, in the template, and in the always-loaded project instructions, while
being both unrunnable and unprovable. Under S4 that means it does not exist — this is the same family
as T17 (a proof obligation living only as prose), one lane over.

T09g settled that `invisible` is **not** a lane to extend for test-strengthening (it took `hardening`
instead, because `invisible`'s proof is trivially satisfied by an empty `src` diff and so replaces the
anti-collusion property with nothing). That decision is independent of this one: `invisible` still
needs to either work or go.

## Depends on
T09g (which measured both facts and which adds the first `Class:`-keyed path to `red_check` — build on
that mechanism rather than a second one), T17 (the other half of the OpenAPI deferral), T03/T03c (the
template and the `Class:` vocabulary).

## Read first
- `workflow_v3_spec.md §3` — the class register and `invisible`'s exact declared proof. **The spec
  wins**; it is never edited by agents, so a change to the class's definition is an escalation.
- `.claude/tools/red_check.py` — after T09g, the `Class:`-keyed dispatch. This task adds a second
  branch to an existing mechanism, not a new one.
- `.claude/tools/accept.py` — the drift line that hands the OpenAPI half to `/orient`;
  `.claude/commands/orient.md` and `tasks/T17-*.md` — the other side of that hand-off.
- `.claude/tools/gate.py` — `smoke.construct` already constructs the app and calls `app.openapi()`.
  The route list is therefore already reachable; the missing part is *comparing two of them*.
- `PRINCIPLES.md` S4, C7; `tasks/T09g-*.md`'s escalation block for the measurements.

## Deliverables
Two independent questions. Answer both; the second may legitimately be "delete it".

**1. Make `invisible` reachable.** A `Class: invisible` change needs a `red_check` path that can tag a
baseline without the redness rule — its whole premise is that behaviour does not change, so there is
nothing to be red. Reuse T09g's class dispatch. State what replaces redness as the anti-collusion
property, because "nothing" is not an option (T09g's Out-of-scope, and the reason it rejected
extending this class): the candidate is the pair *green gate* + *empty OpenAPI diff*, which is
deliverable 2.

**2. Implement the OpenAPI diff, or retire the promise.** Either:

- **(a) build it** — construct the app at the baseline and at HEAD, diff the route/operation sets, and
  make an `invisible` change's non-empty diff a **FAIL**. `gate.py` already constructs the app, so the
  machinery exists; the new part is doing it twice and comparing. Note this also gives **T17** its
  missing half — coordinate, do not duplicate (C7: one implementation, cited by both); or
- **(b) retire it** — if the diff cannot be made deterministic (route ordering, dynamic schemas), say
  so with evidence and **remove the promise from the template and `CLAUDE.md`**, leaving the spec edit
  as an escalation. A promise nobody implements is worse than an honest absence.

Prefer (a): `invisible` without it has no proof at all, and (b) leaves the class needing a different
one anyway.

## Verification
- `uv run pytest .claude/tools` green.
- **A `Class: invisible` change reaches a baseline tag** — the thing that is impossible today.
  Demonstrate the before state (`RED-CHECK: FAILED`, no tag) and the after.
- Under (a): a genuinely invisible change (a refactor with an identical route set) passes; the same
  change **plus one added route** FAILs, naming the route. Both directions, or the check is decorative.
- Under (a): T17's OpenAPI half is satisfied by the same implementation, not a second one.
- `users/002` still reproduces unchanged (branch `change/users-002` `a931ee6`, detached worktree,
  `GATE_DOCKER=0`): it is `behavioral`, so nothing about it may move.

## Out of scope / Escalate if
- Do NOT edit `workflow_v3_spec.md`. If `invisible`'s definition itself must change, that is an
  escalation with proposed wording.
- Do NOT make the OpenAPI diff a network or Docker dependency. `smoke.construct` runs today without
  either; keep it that way.
- Do NOT fold in `hardening` (T09g) — different class, and its proof is mutation, not an empty diff.
- **Escalate if** an app cannot be constructed at the baseline commit for the comparison. A greenfield
  first change has no shell at baseline, so the "before" side may not exist — in which case say which
  changes the check can honestly cover, rather than skipping silently (`notes/19`'s fail-open class).
