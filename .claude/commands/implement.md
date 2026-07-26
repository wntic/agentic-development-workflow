---
description: "Run the change cycle on change/<context>-NNN: test-author (red baseline) → implementer (to green gate) → fresh evaluator (verdict + flips) → adversarial review; ≤3 passes then a human ESCALATE"
---

# /implement <context>/NNN

> Invoked as `/adw:implement` when the workflow is installed as a plugin, `/implement` when it is
> loaded from a project's own `.claude/` — as in the workflow's own repo. The two forms name
> this same file; other commands are referred to below in the `/adw:` form.

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
   stop — the change must come from `/adw:spec` first.
2. **Reset the SubagentStop ceiling counter.** Delete `.gate/subagent-stop-count` (owned by
   `.claude/hooks/subagent_stop.py`, T06) if it exists. A stale counter left by a prior
   change would otherwise trip an instant, false ESCALATE on this one — the ceiling counts
   blocks *within this change's* implementer loop, so it starts at zero here.
3. Read `change.md` to learn the **Class** (behavioral / bugfix / invisible / hardening; a removal
   is the behavioral flavour marked `REMOVED`, spec §3.1) and **Depth** (S / M / L) — they decide the fast-lane, the
   adversarial review, and — for `hardening` and `invisible`, the two classes with no red phase —
   the route through steps 1–2 below.

## 0.5 Precondition — a Python project exists (no bootstrap, no template)

The workflow does **not** bootstrap and generates no code (D1/A3). A brand-new project needs
nothing but a `uv init --package` project (a `pyproject.toml` with `[project] name` **and**
`[build-system]` — the package root `src/<pkg>/` is derived from the name, `-`→`_`) plus the
installed workflow plugin. `--package` is load-bearing: plain `uv init` puts `main.py` at the root
and creates neither `src/<pkg>/` nor `[build-system]` (spec §9). That is
ordinary one-time project setup done by the human **outside** `/implement`, not a workflow step
and **not** a scaffold template that ships `fastapi`/a shell (that would re-encode the very
prediction the workflow forbids — deps and the shell are agent-owned, per change).

Everything else the app needs is produced **inside** the cycle: the test-author declares this
change's **dependencies** in a pre-baseline `deps:` commit (step 1), and the implementer writes
the **app shell** on a first change and the behaviour thereafter (step 2). So the first-ever
change is genuine greenfield — there is no shell to import yet — and `red_check`'s greenfield
fallback (a static `ac`-marker scan) treats the tests' import-of-the-unwritten-package as a real
RED. Every later change is brownfield: the shell and prior deps are already present.

If `pyproject.toml` (with a `[project] name`) is absent, **stop** — that is `uv init --package`,
the human's one-time setup, not something `/implement` does.

## 1. test-author → deps commit, then red baseline

Dispatch the **test-author** subagent for `<context>/NNN`. It:

1. Adds this change's runtime + dev **dependencies** to `pyproject.toml` (from the Interface
   sketch; the substrate list lives in the `conventions` skill §D, names only), refreshes
   `uv.lock` (`uv lock`), and commits that as a **distinct pre-baseline `deps:` commit** — a
   greenfield first change adds the whole framework substrate, a brownfield change adds only
   what it newly imports (often nothing). The implementer is tool-blocked from `pyproject.toml`,
   so deps are the test-author's lane.
2. Writes red `@pytest.mark.ac` tests from `criteria.md` + the Interface sketch (and, for a
   removal change, deletes the obsolete tests whose node-ids `change.md`'s `## Removed` section
   lists), commits them as a
   **separate, tests-only** baseline commit, then runs the red-check script:

```
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" red-check --change <context>/NNN
```

`red_check` asserts every `AC-n` has a marked test and every marked test is **RED**
(green-before-implementation is flagged; on a greenfield first change a collection error from
the not-yet-written package counts as RED via the fallback), then tags `baseline/<context>-NNN`
on the tests-only red commit — the integrity baseline the whole cycle checks against (spec §5.1).
The `deps:` commit is earlier, so `pyproject.toml` is unchanged from baseline through evaluation
and the gate's frozen-tree check never bites. Do not proceed until `red_check` is green and the
baseline tag exists.

It also screens **every commit from the change dir's creation up to the baseline**, not only the one
it tags (T09i): each may touch `tests/**`, `pyproject.toml`/`uv.lock` or `specs/**`, and the tagged
one `tests/**` alone. So the sanctioned shape is three commits — `/adw:spec`'s, the `deps:` one, the
tests-only one — and anything else committed on the branch beforehand is **refused with the path
named**. If that fires, it is a genuine finding about what the test-author committed, not a
`red_check` defect: route it back to step 1, do not work around it. If the test-author reports an **`[m]`-candidate** (an AC no test can
cover), carry it forward: the evaluator will mark it MANUAL-candidate and only the human sets
`[m]`.

## 1.5 `Class: hardening` — the change whose `src` diff is empty

A **hardening** change makes the tests stronger while behaviour stays identical (the follow-up an
adversarial pass earns when it finds a mutation the suite did not kill). It has no red phase and no
`src/**` work at all, so this one class takes a different route through steps 1–2. Everything else
(steps 0, 3, 4, 5) is unchanged.

- **Step 1 stands, minus redness.** The test-author writes `tests/**` and commits the tests-only
  baseline exactly as always, but its tests are **green on arrival** — do not ask it for redness and
  never accept a test weakened until it fails. The same `red-check` command runs: it reads the
  `Class:` line itself and asks this class's question instead — every ac-marked test **passes** at
  the candidate commit, and each mutation declared in `change.md`'s `## Mutations` makes the AC ids
  it names go **RED** in a throwaway worktree. On confirmation it tags `baseline/<context>-NNN` as
  usual.
- **Step 2 is skipped — dispatch no implementer.** There is nothing in `src/**` for it to write,
  and a hardening change that touches `src/**` is a different change (send it back to `/adw:spec`).
  Instead run the gate once yourself at the baseline commit:
  `uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" gate --change <context>/NNN`. GREEN → step 3.
- **RED there is a TESTS-HANDBACK, never an ESCALATE.** `src/**` is untouched from a green base, so
  the RED is in `tests/**` by construction (a type error in a new fixture, a lint finding) and only
  the test-author can clear it. Return to step 1 with a fresh test-author, then re-anchor with
  `red-check --change <context>/NNN --rebaseline`, which routes through the same hardening path.
- **A mutation that does not apply, or that nothing kills, is a SPEC defect** — stop and hand it to
  the human for `/adw:spec`. `## Mutations` is authored by the human and frozen in the baseline
  (gate integrity, E-12); no agent in this cycle edits it to make the check pass. A surviving
  mutation means the strengthened tests still do not catch the wrong code they were written for,
  which is the whole finding this change exists to close.

## 1.6 `Class: invisible` — the change whose OBSERVABLE SURFACE must not move

An **invisible** change (refactor / dependency upgrade / performance) claims that behaviour does not
change, so its ACs pin behaviour that *already* holds. That removes the red phase — and nothing
else: step 2 runs normally, because the refactor itself is ordinary `src/**` work.

- **Step 1 stands, minus redness.** The same `red-check` command reads the `Class:` line and asks
  this class's question: every ac-marked test **passes** at the candidate commit (green on arrival
  is correct here — do not ask the test-author for redness, and never accept a test weakened until
  it fails), and the baseline's app **constructs**, because the next bullet's diff reads the frozen
  baseline tree. It then tags `baseline/<context>-NNN` as usual.
- **The gate carries the class's second proof half.** `gate.py` runs
  `invisible.openapi-diff`: it constructs the app at the baseline commit and at HEAD and compares
  the METHOD+path operation sets. An added or removed endpoint is **RED**, named. So for this class
  "the gate is green" IS spec §3.1's "green gate + empty before/after OpenAPI diff".
- **A surface FAIL is a decision, not a retry.** Either the surface change was accidental (the
  implementer reverts it — an ordinary `src/**` fix), or it was intended, in which case the change
  is **not** invisible: stop and send it back to `/adw:spec` for a behavioral change with an
  observable AC. Do not let the implementer burn its ceiling on it.
- **Two shapes this class cannot prove, both loud.** A tree with no HTTP surface on either side (a
  domain-only refactor) reports the diff as having nothing to compare — legitimate, and the proof
  then rests on the whole baseline suite staying green (gate E-05). A **breaking** dependency
  upgrade whose baseline source will not import under the new versions makes the before-side
  UNDETERMINED, which `red_check` refuses at baseline time: that change needs another class, and no
  amount of `src/**` work will change the answer.

## 2. implementer → green gate

Dispatch the **implementer** subagent. It writes `src/**` (and owns any Alembic revision)
until `gate.py` is GREEN, running `uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" gate --change <context>/NNN`. On a
**greenfield first change** it first writes the behaviorless app shell (`create_app()` +
container + error handler + `domain/exceptions.py` + `restapi/schemas/errors.py`) from the
`architecture`/`restapi` skills, then the change's behaviour on top; brownfield changes add only
behaviour. It stays tool-blocked from `pyproject.toml` — an unforeseen dependency is a
CONTRACT-CHANGE back to the test-author, never a `uv add`. The
SubagentStop hook holds it while the gate is red and, at the internal ceiling (**3 blocks per
red test**), the hook itself writes `changes/NNN-<slug>/ESCALATE` and releases it (spec §5.3).
That ceiling is reached only by a gate that **answered** RED — a gate that could not *run* at all
never blocks and never counts (see ENV-BLOCKED below).

On green the implementer **commits its own `src/**` (and Alembic revision)** as the code
commit and reports the SHA — you do **not** commit `src/` for it. If it reports green but an
uncommitted tree, that is a bug in the run, not your cue to commit; send it back to finish its
own commit.

- **CONTRACT-CHANGE**: if the implementer reports it hit the Interface sketch (needs another
  ctor dep, a name is wrong, a lookup must return `T | None` not raise) it does **not** work
  around it. The cycle returns to **step 1** with a fresh test-author that reworks the tests
  against the corrected sketch — the sketch edit is approved by the human for an M/L change,
  otherwise by you (this session). No silent workarounds ever.
- **TESTS-HANDBACK**: if `.gate/verdict.json` carries `"red_localized_to": "tests"` (the
  SubagentStop hook releases the implementer with a matching systemMessage, spending **no**
  block), the RED is entirely in `tests/**` — the implementer cannot clear it (D4), and the
  static toolchain is already clean over `src/` alone. This is **not** an ESCALATE. Return to
  **step 1** with a fresh test-author, handing it the gate's failing checks to fix in `tests/**`
  (e.g. re-type `conftest` fixtures against the now-existing package, re-sort own-package
  imports). It consumes one of the 3 full-cycle passes, so a change that keeps bouncing between
  the two lanes still ESCALATEs rather than looping forever.
- **ENV-BLOCKED**: if the gate **could not run** at all — it exits 2 and writes no
  `.gate/verdict.json`, in practice because the project's environment is missing the toolchain
  (`mypy` / `ruff` / `pytest` / `alembic`) — the SubagentStop hook releases the implementer with
  the gate's own sentence in a systemMessage and spends **no** block and **no** pass (T06j). This
  is **not** an ESCALATE and **not** a code defect: nothing in `src/**` can fix it, and an
  `ESCALATE` file would record an environment fault as a change fault in the change directory.
  **Stop the cycle and surface the message to the human** — the fix is theirs (declare the dev
  group per `conventions` block D, then `uv sync`); the workflow never installs anything itself
  (F1). Resume the cycle unchanged afterwards: the block counter was left exactly as found.

  The handback's test-author commits `tests/**` only — **leave the implementer's uncommitted
  `src/` in place, do not stash it**. Then re-anchor the baseline onto that corrected commit:

  ```bash
  uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" red-check --change <context>/NNN --rebaseline
  ```

  It verifies each property in the world where it is decidable — redness in a throwaway worktree
  of the candidate commit (where `src/` is absent), mypy over `tests/**` in the live tree (where
  `src/` is present) — and refuses the move if the commit writes outside `tests/**`, drops an
  ac-marked test, or leaves `tests/**` lint/type-dirty. On OK it moves the tag; then resume the
  implementer, whose `src/` should carry the gate to green **unchanged**. Never move the tag with
  `git tag -f` by hand: the move re-anchors every integrity check gate.py makes (notes/18).
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

## 4. Adversarial review

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
  `/adw:accept-change <context>/NNN`. By now the branch is **acceptance-ready with no manual
  commits**: the implementer committed the code, the evaluator committed criteria then verdict
  in freshness order, and `git status` is clean — `accept.py` passes L-04 with no re-pin.
- **Do not land canon fixes on a change mid-flight where avoidable.** Fixing `gate.py`/`accept.py`/
  hooks/skills on the base while this change is open forces a rebase that rewrites every SHA. If it
  is unavoidable, rebase the branch and re-tag `baseline/<context>-NNN`, but **do not re-pin the
  verdict**: `accept.py` L-04 anchors freshness to the *tree identity* of the change's attested
  files (T10d), so a rebase that preserves the code + criteria keeps the verdict fresh with no
  evaluator re-run. A re-pin is needed only when a change file actually changed.
- **Any FAIL** → send `verdict.md` (with the concrete failure) back to a new **implementer**
  dispatch (step 2). A CONTRACT-CHANGE instead returns to step 1.
- **Full-cycle ceiling: 3 passes.** After the third pass still not all-green, write/expect the
  `ESCALATE` file and hand off to the human — the loop does not silently churn.
- The main-session Stop hook (T06) will not let this turn end while `criteria.md` has any `[ ]`,
  `verdict.md` is missing, or an `ESCALATE` file exists — the last resolves only by a human turn.
- **The `ESCALATE` is a commit, and clearing it is a commit too (§5.3/E-08).** The hook writes the
  file **and commits it**, scoped to that one path — an untracked lock is invisible to `gate.py`
  and to any acceptance run in a fresh worktree, so committing it is what makes "only a human
  removes it" a rule instead of a sentence. Consequences for this loop: `gate.py` goes **RED**
  (`integrity.escalate-intact`) if that committed file later disappears, and `accept.py` denies
  both while it stands and after it was deleted. So the human clears a lock in two steps —
  remove the file, commit **that deletion alone**, then move the baseline over it:

  ```bash
  uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" red-check --change <context>/NNN --clear-escalate
  ```

  It is deliberately narrower than `--rebaseline` (§2): it refuses unless a committed `ESCALATE`
  is now gone, **every** commit since the baseline touches nothing but that path, and no ac-marked
  test disappeared — so no criteria flip, `change.md` edit or dropped test can ride along. Hence
  "the deletion alone": clear the lock **before** committing anything else. In a real escalation
  that holds by construction, since the implementer commits `src/**` only on green and an escalated
  change never got there. Never `git tag -f` by hand.

Everything for this change — red tests, code, verdict — lives on the change branch; `main`
receives it only later, green, through `accept.py` (S9).
