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

## 0.5 Precondition — a Python project exists (no bootstrap, no template)

The workflow does **not** bootstrap and generates no code (D1/A3). A brand-new project needs
nothing but a plain `uv init` project (a `pyproject.toml` with `[project] name` — the package
root `src/<pkg>/` is derived from it, `-`→`_`) plus the installed workflow plugin. That is
ordinary one-time project setup done by the human **outside** `/implement`, not a workflow step
and **not** a scaffold template that ships `fastapi`/a shell (that would re-encode the very
prediction the workflow forbids — deps and the shell are agent-owned, per change).

Everything else the app needs is produced **inside** the cycle: the test-author declares this
change's **dependencies** in a pre-baseline `deps:` commit (step 1), and the implementer writes
the **app shell** on a first change and the behaviour thereafter (step 2). So the first-ever
change is genuine greenfield — there is no shell to import yet — and `red_check`'s greenfield
fallback (a static `ac`-marker scan) treats the tests' import-of-the-unwritten-package as a real
RED. Every later change is brownfield: the shell and prior deps are already present.

If `pyproject.toml` (with a `[project] name`) is absent, **stop** — that is `uv init`, the
human's one-time setup, not something `/implement` does.

## 1. test-author → deps commit, then red baseline

Dispatch the **test-author** subagent for `<context>/NNN`. It:

1. Adds this change's runtime + dev **dependencies** to `pyproject.toml` (from the Interface
   sketch; the substrate list lives in the `conventions` skill §D, names only), refreshes
   `uv.lock` (`uv lock`), and commits that as a **distinct pre-baseline `deps:` commit** — a
   greenfield first change adds the whole framework substrate, a brownfield change adds only
   what it newly imports (often nothing). The implementer is tool-blocked from `pyproject.toml`,
   so deps are the test-author's lane.
2. Writes red `@pytest.mark.ac` tests from `criteria.md` + the Interface sketch (and, for a
   removal change, deletes the obsolete tests listed in `change.md`), commits them as a
   **separate, tests-only** baseline commit, then runs the red-check script:

```
uv run .claude/tools/red_check.py --change <context>/NNN
```

`red_check` asserts every `AC-n` has a marked test and every marked test is **RED**
(green-before-implementation is flagged; on a greenfield first change a collection error from
the not-yet-written package counts as RED via the fallback), then tags `baseline/<context>-NNN`
on the tests-only red commit — the integrity baseline the whole cycle checks against (spec §5.1).
The `deps:` commit is earlier, so `pyproject.toml` is unchanged from baseline through evaluation
and the gate's frozen-tree check never bites. Do not proceed until `red_check` is green and the
baseline tag exists. If the test-author reports an **`[m]`-candidate** (an AC no test can
cover), carry it forward: the evaluator will mark it MANUAL-candidate and only the human sets
`[m]`.

## 2. implementer → green gate

Dispatch the **implementer** subagent. It writes `src/**` (and owns any Alembic revision)
until `gate.py` is GREEN, running `uv run .claude/tools/gate.py --change <context>/NNN`. On a
**greenfield first change** it first writes the behaviorless app shell (`create_app()` +
container + error handler + `domain/exceptions.py` + `restapi/schemas/errors.py`) from the
`architecture`/`restapi` skills, then the change's behaviour on top; brownfield changes add only
behaviour. It stays tool-blocked from `pyproject.toml` — an unforeseen dependency is a
CONTRACT-CHANGE back to the test-author, never a `uv add`. The
SubagentStop hook holds it while the gate is red and, at the internal ceiling (**3 blocks per
red test**), the hook itself writes `changes/NNN-<slug>/ESCALATE` and releases it (spec §5.3).

On green the implementer **commits its own `src/**` (and Alembic revision)** as the code
commit and reports the SHA — you do **not** commit `src/` for it. If it reports green but an
uncommitted tree, that is a bug in the run, not your cue to commit; send it back to finish its
own commit.

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

The evaluator **commits its own artifacts in the freshness-correct order** on top of the
implementer's code commit: (1) the `criteria.md` flip alone → (2) a gate run at that HEAD whose
SHA it pins into `verdict.md` → (3) `verdict.md` committed LAST as pure metadata (`accept.py`
excludes the verdict.md-only commit from L-04's `changed_since`, so the verdict stays fresh).
It reports the three SHAs. **You commit nothing** — do not offer to finalize its commits;
a completed step 3 leaves `git status` clean and the verdict pinned.

## 4. Adversarial pass

Mandatory for **M/L** changes and the **first change of a capability** (opt-in `--adversarial`
for S). A fresh agent applies the assert-strength recipes from the **`testing-unit`** skill to
the diff of the tests and records the result in the **`## Adversarial review`** section of
`verdict.md` (that exact heading — `accept.py`'s `adversarial.presence` gate and the verdict.md
template both key on it). Point the agent at that skill — the recipes have one home there (C7);
do not restate a checklist in this command. `accept.py` later checks the section is filled for
the change's class.

## 5. Branch

- **All criteria `[x]`** (and `[m]` recorded by the human) with `verdict.md` present and no
  `ESCALATE` file → the change is ready; tell the human the next step is
  `/accept-change <context>/NNN`. By now the branch is **acceptance-ready with no manual
  commits**: the implementer committed the code, the evaluator committed criteria then verdict
  in freshness order, and `git status` is clean — `accept.py` passes L-04 with no re-pin.
- **Any FAIL** → send `verdict.md` (with the concrete failure) back to a new **implementer**
  dispatch (step 2). A CONTRACT-CHANGE instead returns to step 1.
- **Full-cycle ceiling: 3 passes.** After the third pass still not all-green, write/expect the
  `ESCALATE` file and hand off to the human — the loop does not silently churn.
- The main-session Stop hook (T06) will not let this turn end while `criteria.md` has any `[ ]`,
  `verdict.md` is missing, or an `ESCALATE` file exists — the last resolves only by a human turn.

Everything for this change — red tests, code, verdict — lives on the change branch; `main`
receives it only later, green, through `accept.py` (S9).
