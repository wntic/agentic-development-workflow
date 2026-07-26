# T04i — the removal allowance is read from every change dir, and grants leave no trace

## Goal
Two findings from T04h about the same permission — the legal-removal allowance that lets a
removal-flavour change delete a baseline test without `integrity.test-inventory` going RED.

**1. The allowance is collected from EVERY change directory in the baseline tree.**
`check_test_inventory` walks all `specs/**/changes/**/change.md` blobs and concatenates them, so
change **A**'s `## Removed` list authorises deleting a baseline test during change **B**'s cycle.
S9 (one change per branch) usually makes that a single document, but a `Companion:` pair puts two in
the tree by design, and a leftover directory does it by accident.

T04h declined to narrow this (a behaviour change of the same family as the scoping half it also
declined) and reported it instead. The narrowing is obvious — read only the change under gate — but
the `Companion:` case makes it a real question: paired changes are accepted together (§2), so a
companion's removals may legitimately belong to the same cycle.

**2. A granted removal is silent, and the PASS message it prints is literally false.**
With a legal removal the check reports `all N baseline tests collected and run (E-05)` — where N counts
the removed test that was neither collected **nor** run. Compare the Docker carve-out (T04b), which is
loud by construction: a `DOCKER SKIPPED` block plus `docker_exempt` in the verdict, so accepting without
that tier is a visible human decision. Here the permission leaves **no trace in the verdict at all**.

That asymmetry is the point. A grant nobody can see in the report is the ergonomic half of the
fail-open direction: `/accept-change` puts the gate's output in front of the human precisely so
consequential things are noticed, and this one is invisible **and** mislabelled.

## Depends on
T04h (which found both and fixed the comment-stripping half), T04b (the Docker carve-out — the
worked example of a loud, verdict-recorded exemption), T09b, T03c (the `## Removed` section this
allowance reads).

## Read first
- `.claude/tools/gate.py` — `check_test_inventory` (how the blobs are gathered and concatenated) and
  `inventory_violations` (the matcher, post-T04h). The comment block T04h left there argues the
  *scoping* question and is the input to item 1, not its answer.
- `.claude/tools/accept.py` — the `companion` gate and how a `Companion:` pair is accepted together;
  this is what stops item 1 from being a one-line narrowing.
- `.claude/tools/gate.py`'s Docker carve-out (`docker_exempt`, the `DOCKER SKIPPED` block) — copy its
  *shape* for item 2 rather than inventing a second reporting idiom (C7).
- `workflow_v3_spec.md §5.1` (the inventory check, E-05) and `§2` (companion changes).
- `PRINCIPLES.md` S4, S8.

## Deliverables
- **Item 1 — decide and implement, or decline with the reason in code.** Candidates: read only the
  change under gate; or read the change under gate **plus** any `Companion:` it declares. Prefer the
  latter if the companion mechanism makes it necessary — but check first whether the gate even knows
  which change it is judging in every mode (it takes `--change`, and the integrity block SKIPs without
  a baseline). If the answer is "decline", say what a leftover directory can actually authorise, so the
  next reader can judge the risk rather than the wording.
- **Item 2 — make a granted removal loud.** The message must not claim a removed test was collected.
  Report the grants explicitly (a `LEGAL REMOVALS` list naming each node-id and the `change.md` that
  authorised it) and carry them into the verdict the way `docker_exempt` is carried, so `accept.py` and
  the human both see them. Keep `integrity.test-inventory`'s PASS/FAIL semantics unchanged — this is
  about what the report says, not about what is allowed.
- Tests: item 1's chosen scope, both directions (a foreign change dir's list does **or** does not
  authorise, per the ruling, with the ruling pinned); item 2's message and verdict entry present on a
  legal removal and absent otherwise.

## Verification
- `uv run pytest .claude/tools` green.
- **A legal removal still passes** — `test_removal_listed_in_change_md_is_legal` (T04h) stays green.
  This is the regression that would hurt: break it and no removal change can ever gate again.
- Item 2 demonstrably differs from pre-fix: today the run prints `all N baseline tests collected and
  run` with the removed test silently inside N; after, the grant is named. Assert on the message.
- Item 1's chosen behaviour differs from pre-fix in a fixture with **two** change dirs, one authorising
  the other's deletion.
- `users/002` reproduces unchanged (INDEX recipe; it removes nothing, so both halves are inert for it).
  Commit tool edits first (T18).

## Out of scope / Escalate if
- Do NOT change **what** is allowed. Item 2 is a reporting change; item 1 is a scoping decision. Neither
  may make a legitimate removal fail — that would deadlock the removal flavour entirely.
- Do NOT revisit the substring-vs-`## Removed` scoping question. T04h declined it with an argument
  (`change.md` is frozen at baseline and no agent may edit it, so content outside the section is the
  human's own authoring); reopening it needs new evidence, not a preference.
- **Escalate if** item 1's narrowing would break the `Companion:` flow. Paired changes are accepted
  together by §2, so if a companion's removals are legitimately part of one cycle, the "obvious" fix is
  wrong and the right scope is a canon question about what a companion shares.
