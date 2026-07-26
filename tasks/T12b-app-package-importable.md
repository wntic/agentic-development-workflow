# T12b — The app must be startable in a consumer project, and the gate must say so

> **Rewritten 2026-07-26** after the first dispatch ESCALATEd. The original framing ("make this
> repo's `pyproject.toml` installable") was wrong and is now explicitly forbidden below — see
> *Out of scope*. Everything here is consumer-facing: what the shipped plugin requires of the
> project it is installed into, and what the gate checks there.

## Goal
`users/002` produced a working FastAPI app that **cannot be started**: `uvicorn` dies with
`ModuleNotFoundError`, while `gate.py` reports GREEN across 22 checks. The gate injects
`PYTHONPATH=src` itself (`gate.py:376-381`, `:1030-1033`; a third site in `red_check.py`), so it
constructs the app under an import path only the gate provides. That is the **A4** violation the
principle exists for — the gate is not exercising the real failure mode, it is supplying the
conditions that hide it.

The fix does **not** belong in this repository. Three facts settle that, all verified:

1. `[build-system]` + an absent `src/<pkg>/` makes `uv` hard-fail *every* command
   (`× Failed to build … ╰─▶ Expected a Python module at: src/demo_pkg/__init__.py`, uv 0.11.6).
2. This repo's `src/` is **transient** — T02 purged it, `users/002` recreated it, the next trial
   will churn it again. Declaring `[build-system]` here would couple the meta layer's own test
   environment to the presence of a trial app: purge the trial, and `uv run pytest .claude/tools/`
   stops working.
3. This `pyproject.toml` is a dev artifact of the trial harness wearing three hats at once (trial
   app deps · the toolchain a consumer legitimately needs · the meta layer's own test env). Untangling
   that is the plugin split — **T15**, not this task.

So: fix what the plugin tells a consumer project, and make the gate verify it *there*.

## Depends on
T12 (agents own deps and the shell), T04 (`gate.py`), T10f (the undetermined-input rule — the new
checks must obey it).

## Read first
- The first dispatch's findings are the specification; they are summarised in this file, but the
  reasoning behind items 1–3 above came from probing `uv` directly — re-probe if you doubt any of it.
- `.claude/skills/conventions/SKILL.md` **block D** (the substrate list; note line ~186, `Dev
  (always present)`, already carries `pytest`/`ruff`/`mypy`/`testcontainers`/`httpx`) and **block E**
  (which defers toolchain commands to `gate.py`, C7).
- `.claude/tools/gate.py` — the `sys.executable -m mypy|ruff|pytest|alembic` invocations and both
  `PYTHONPATH` injection sites; `.claude/tools/red_check.py` — the third injection site.
- `.claude/tools/test_gate.py` — the fixture tree (`[project] name = "fixture-app"` shipping
  `src/app/`, never installed into any environment) — see the fixture note under Deliverables.
- `PRINCIPLES.md` A4, C6, C7, F1; `workflow_v3_spec.md §9`.

## Deliverables

**1. `[build-system]` becomes a substrate fact.** `.claude/skills/conventions/SKILL.md` block D —
add it alongside the existing `Dev (always present)` line, in the test-author's lane like every
other substrate entry. Backend: **`uv_build`**, because a consumer scaffolded by `uv init --package`
receives exactly that; note in the text that its `>=x,<y` pin is the one sanctioned exception to
block D's no-versions rule *because uv itself emits it*, so an author does not read it as drift.

**2. A toolchain preflight in `gate.py`.** There is **none today** (verified: zero matches for any
presence check). A consumer whose project lacks `ruff` or `mypy` gets a raw `ModuleNotFoundError`
out of a subprocess instead of a sentence telling them what to install. Check the tools the gate is
about to invoke are importable and fail with the missing names and the fix; this is a precondition,
so it may abort like T10f's base resolution rather than occupy a `GATES` row — state which you chose.

**3. An import check with the injection stripped.** Run `import <project package>` in a subprocess
**without** the gate's `src` injection. **FAIL** when the project declares itself installable
(`[build-system]` present) but the import fails. **Loud SKIP**, naming the reason, when it does not
declare itself installable — this repo's permanent case. Never silent.

**Do not remove the injections.** The editable install's `.pth` holds an *absolute* path to one
tree's `src`; the injections are what make each gate run hermetic to its own tree, and
`collect_baseline_inventory` depends on one to point pytest at the extracted baseline tree. Removing
them would trade an A4 hole for an integrity hole.

**Fixture note.** `test_gate.py`'s fixtures are never installed into any environment, so they are
correctly the SKIP case for deliverable 3 — that is the shape that makes this cheap. Do not build
per-fixture virtualenvs.

## Verification
- `uv run pytest .claude/tools/test_gate.py` green, plus a case per deliverable; each new check
  demonstrably behaves differently against pre-fix `gate.py`.
- `uv run pytest .claude/tools` — whole meta suite green.
- **On this repo**: `uv run .claude/tools/gate.py` stays GREEN, with deliverable 3 emitting its
  loud SKIP. If it FAILs here, the SKIP condition is wrong.
- **On the `users/002` tree**: same, via a detached worktree (`git worktree add --detach <path>
  change/users-002`) — read-only, do not touch the branch or its tag.
- Deliverable 2 demonstrated: a project missing a tool produces the new message, not a traceback.

## Out of scope / Escalate if
- **Do NOT add `[build-system]` to this repository's `pyproject.toml`.** Reasons 1–3 in the Goal.
  This repo stays deliberately non-installable; deliverable 3's SKIP is the honest, permanent report
  of that, not a bug to fix later.
- **Do NOT do the plugin split** (`.claude-plugin/plugin.json`, `${CLAUDE_PLUGIN_ROOT}`, separating
  the meta layer's env from the trial app's) — that is **T15**.
- **Do NOT edit `workflow_v3_spec.md`.** §9 says a new project is «просто `uv init`», and `uv init`
  demonstrably creates neither `src/<pkg>/` nor `[build-system]` (uv 0.11.6: it emits `main.py` at
  the root) — so the package root §9 calls "derived" is never created by the command §9 names. The
  correction to `uv init --package` is **the author's to make**; design canon is never edited by
  agents. Write deliverable 1 so it is consistent with that correction, and flag in your report if
  it has not landed yet.
- **Escalate if** deliverable 3 cannot distinguish "declares itself installable" cheaply — guessing
  wrong turns a permanent SKIP into a permanent FAIL on this repo and would block every gate run.
