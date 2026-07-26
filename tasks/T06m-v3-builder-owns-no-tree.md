# T06m — the one role whose whole job is `.claude/**` has no sanctioned write path

## Goal
`bash_guard.ROLE_OWNED` grants an owned tree to `test-author` (`tests/`, `pyproject.toml`, `uv.lock`),
`evaluator` (`criteria.md`, `verdict.md`) and `implementer` (`src/`). It has **no entry for
`v3-builder`** — the role whose entire job is writing `.claude/**`. So the one role that legitimately
owns the protected tree is the only one with no sanctioned way to write it, and the denial message
enumerates the three cycle lanes without mentioning the builder at all.

This is T06d's exact shape, one role later: *the guard blocks precisely the owner.*

**And the route around it is trivial, which is the real finding.** T04g's builder was denied
`cp <scratch>/accept.fixed.py .claude/tools/accept.py` (correct, per T06k's inventory) and then wrote
the same six files with `python3 - <<'PY' … Path(rel).write_text(…) … PY`, which the guard **allowed**.
So the guard cannot see writes performed by an interpreter — S8-consistent (it is ergonomics, and
`integrity.self-hash` backstops it since T18), but it means the denial trains the bypass reflex it
exists to prevent, and the bypass is one line. This is the fourth builder in this session to route
around the guard rather than being stopped by it.

**Severity: ergonomics, not trust.** Every `.claude/**` write is anchored by `check_self_hash` (T18),
so a builder's edit is visible at the next gate run whichever tool made it. What the miss costs is
that the workflow's own tooling agent works by bypass, and that habit is what T06i measured twelve
false positives' worth of damage from.

## Depends on
T06d (the owned-tree allowance and its reasoning), T06f (the role-aware resolution), T06i (the
tokeniser and the bypass-reflex argument), T06k (the `cp` inventory that produced the denial), T18
(the anchor set that makes this ergonomics rather than trust).

## Read first
- `.claude/hooks/bash_guard.py` — `ROLE_OWNED`, `_protected_for`, `SRC_CLOSED_TO`, and the deny
  message that lists the lanes. Note how `owned` overrides `protected` (T06d).
- `.claude/agents/v3-builder.md` — what the role is actually for, and which trees it must write.
  This is the authority on scope; do not widen beyond it.
- `tasks/T06d-owned-tree-write-path.md` — the argument that an owner denied its own tree is a defect,
  and the shape of the fix.
- `PRINCIPLES.md` S8 (why a false positive costs more than a miss), D4 (ownership runs tests-vs-src —
  note the builder is **not** a cycle role, so D4 does not assign it a lane).
- `notes/19`-adjacent history is not needed; this is a hook-ergonomics task.

## Deliverables
- `.claude/hooks/bash_guard.py` — give `v3-builder` an owned tree. **Scope it from
  `v3-builder.md`, not generously**: the builder writes `.claude/**`, `tasks/`, `notes/` and the design
  docs it is told to edit — but it must stay **denied** on the trees the cycle roles own
  (`src/`, `tests/`, `specs/`), because a build task has no business there and that denial is what
  keeps a builder from "helpfully" editing a change under way. State the list and the reason inline.
- The deny message should name the acting role's own lane when it has one, so a denied builder learns
  what it *may* write instead of reading a list of three lanes that exclude it.
- `.claude/tools/test_enforcement.py` — `v3-builder` writing `.claude/tools/gate.py` **allowed**;
  writing `src/x.py`, `tests/x.py`, `specs/**` **still denied**; the three cycle roles' lanes
  unchanged; and the T06k read-direction cases unaffected. Additions only, per the suite's standard.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green, existing cases **unmodified**
  (`git diff … | grep -c "^-[^-]"` → 0 for that file).
- The denial that prompted this demonstrably flips: `cp <anything> .claude/tools/gate.py` as
  `v3-builder` denies before, allows after.
- All twelve recorded false positives still allow (`RECORDED_FALSE_POSITIVES` + the standalone pins —
  see T06l if it has consolidated them).
- `uv run pytest .claude/tools` green; `uv run .claude/tools/gate.py` GREEN. **Commit the hook edit
  before any acceptance regression** (T18's cost, INDEX note).

## Out of scope / Escalate if
- Do NOT try to make the guard see interpreter writes. That is a prevention arms race the guard
  explicitly does not fight (S8: the gate is the backstop, and T18 anchors every `.claude/**` file).
  Record it as a known limit if you touch that area at all.
- Do NOT give `v3-builder` `src/`, `tests/` or `specs/`. The point is a *scoped* lane, not a master key;
  a builder that can edit a change in flight can break the cycle's ownership boundaries invisibly.
- Do NOT change `PROTECTED_FRAGMENTS` or the tokeniser. Role ownership only.
- **Escalate if** `v3-builder.md` turns out to license writes to a cycle-owned tree. Then the conflict
  is between two agent definitions and D4, which is a canon question, not a hook detail.
