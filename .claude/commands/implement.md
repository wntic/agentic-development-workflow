---
description: "Run the change cycle on change/<context>-NNN: test-author (red baseline) → implementer (to green gate) → fresh evaluator (verdict + flips) → adversarial pass; ≤3 passes then a human ESCALATE"
---

# /implement <context>/NNN

The working loop for one change, on its own `change/<context>-NNN` branch (spec §6). You are
the main session orchestrating three subagents in sequence — **test-author**, **implementer**,
**evaluator** (spec §4). You never write `src/**` or `tests/**` yourself; you dispatch the
role agents and route their results. Trust lives in `gate.py` and the git baseline (S8), not
in what an agent reports — every "done" is re-derived from a gate run.

Subagents run **sequentially, one dispatch at a time** (per-dispatch tool tuning is not a
thing — each role is a distinct agent definition with its own `disallowedTools`, notes/15
F-7). At most **one change per context** is in `/implement` at a time (spec §6).

## 0. Orient and reset the ceiling

1. Parse `$ARGUMENTS` into `<context>/NNN`; confirm you are on branch `change/<context>-NNN`
   and that `specs/<context>/changes/NNN-<slug>/change.md` + `criteria.md` exist. If not,
   stop — the change must come from `/spec` first.
2. **Reset the SubagentStop ceiling counter.** Delete `.gate/subagent-stop-count` (owned by
   `.claude/hooks/subagent_stop.py`, T06) if it exists. A stale counter left by a prior
   change would otherwise trip an instant, false ESCALATE on this one — the ceiling counts
   blocks *within this change's* implementer loop, so it starts at zero here.
3. Read `change.md` to learn the **Class** (behavioral / bugfix / invisible; removal is a
   behavioral flavour) and **Depth** (S / M / L) — they decide the fast-lane and the
   adversarial pass below.

## 1. test-author → red baseline

Dispatch the **test-author** subagent for `<context>/NNN`. It writes red `@pytest.mark.ac`
tests from `criteria.md` + the Interface sketch (and, for a removal change, deletes the
obsolete tests listed in `change.md`), commits them, then runs the red-check script:

```
uv run .claude/tools/red_check.py --change <context>/NNN
```

`red_check` asserts every `AC-n` has a marked test and every marked test is **RED**
(green-before-implementation is flagged), then tags `baseline/<context>-NNN` on the red commit
— the integrity baseline the whole cycle checks against (spec §5.1). Do not proceed until
`red_check` is green and the baseline tag exists. If the test-author reports an **`[m]`-candidate**
(an AC no test can cover), carry it forward: the evaluator will mark it MANUAL-candidate and
only the human sets `[m]`.

## 2. implementer → green gate

Dispatch the **implementer** subagent. It writes `src/**` (and owns any Alembic revision)
until `gate.py` is GREEN, running `uv run .claude/tools/gate.py --change <context>/NNN`. The
SubagentStop hook holds it while the gate is red and, at the internal ceiling (**3 blocks per
red test**), the hook itself writes `changes/NNN-<slug>/ESCALATE` and releases it (spec §5.3).

- **CONTRACT-CHANGE**: if the implementer reports it hit the Interface sketch (needs another
  ctor dep, a name is wrong, a lookup must return `T | None` not raise) it does **not** work
  around it. The cycle returns to **step 1** with a fresh test-author that reworks the tests
  against the corrected sketch — the sketch edit is approved by the human for an M/L change,
  otherwise by you (this session). No silent workarounds ever.
- If an `ESCALATE` file appears, stop the loop and surface it to the human (see §5).

## 3. evaluator → verdict + flips

Dispatch the **evaluator** subagent in a **fresh context** (it must not be the implementer —
self-evaluation bias, spec §4/§5). It runs `gate.py --criteria`, live-runs the criteria whose
environment the Verification section provisioned, flips `criteria.md` both ways with proof,
and writes `verdict.md` (per-AC PASS / FAIL / MANUAL-candidate + proof method + the gate SHA).

- **Fast-lane for S depth:** the evaluator is `gate.py --criteria` only — no live run.
- For M/L and every criterion Verification provisioned an environment for, the live run is
  required; a pytest citation may not silently stand in for it (honesty rule, spec §4).

## 4. Adversarial pass

Mandatory for **M/L** changes and the **first change of a capability** (opt-in `--adversarial`
for S). A fresh agent applies the assert-strength recipes from the **`testing-unit`** skill to
the diff of the tests and records the result as a section of `verdict.md`. Point the agent at
that skill — the recipes have one home there (C7); do not restate a checklist in this command.
`accept.py` later checks the section exists for the change's class.

## 5. Branch

- **All criteria `[x]`** (and `[m]` recorded by the human) with `verdict.md` present and no
  `ESCALATE` file → the change is ready; tell the human the next step is
  `/accept-change <context>/NNN`.
- **Any FAIL** → send `verdict.md` (with the concrete failure) back to a new **implementer**
  dispatch (step 2). A CONTRACT-CHANGE instead returns to step 1.
- **Full-cycle ceiling: 3 passes.** After the third pass still not all-green, write/expect the
  `ESCALATE` file and hand off to the human — the loop does not silently churn.
- The main-session Stop hook (T06) will not let this turn end while `criteria.md` has any `[ ]`,
  `verdict.md` is missing, or an `ESCALATE` file exists — the last resolves only by a human turn.

Everything for this change — red tests, code, verdict — lives on the change branch; `main`
receives it only later, green, through `accept.py` (S9).
