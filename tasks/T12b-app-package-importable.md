# T12b — The app the cycle ships must be importable the way it is run

## Goal
`users/002` shipped a working FastAPI app that **is not an installable package**. Its
`pyproject.toml` declares dependencies but carries no `[build-system]` and no package configuration
at all, so `src/agentic_development_workflow/` is not on the import path. `gate.py` injects
`PYTHONPATH` itself (`gate.py:379-381`, `:992`), which is why the gate is GREEN — and why running
`uvicorn` by hand fails with `ModuleNotFoundError`, as both the implementer and the evaluator hit
mid-run.

This is an **A4 finding**: *"does the gate actually construct/run the artifact, or only type-check
and lint it?"* The gate constructs the app under an import path that only the gate provides. The
real deployment mode is never exercised, and the symptom (uvicorn failing by hand) is the gate
telling us so. It is the same shape as the `create_app()` defect A4 was written for: green
toolchain, broken construction.

Ownership is clean under D4/F1: `pyproject.toml` is the **test-author's** pre-baseline deps commit.
So the remedy lands in the slot T12 created — but the *canon question* below has to be settled first.

## The canon question (settle before coding)
This repo's `pyproject.toml` is **shared** between the meta layer (`.claude/` tooling) and the
target app maintained under `src/`. Its own header says so. Two readings:

- **(a)** The repo is one package: add `[build-system]` + package config, target app importable
  without `PYTHONPATH`, and `gate.py` stops injecting it.
- **(b)** The shared `pyproject.toml` is a dev-environment artifact, the target app is not meant to
  be installable *in this repo*, and `PYTHONPATH=src` is the sanctioned contract — in which case it
  must be documented in `conventions` (C7: derivation has one home) and the A4 gap closed by making
  the gate's construct-smoke run the app the way a consumer project would.

**(b) is not obviously wrong** — this repo is the workflow's own build-out, not a consumer project,
and a consumer project's app *will* be a plain `uv init` package where the question dissolves. Pick
consciously; do not default.

## Depends on
T12 (agents own deps and the app shell), T04 (`gate.py`'s construct-smoke + PYTHONPATH injection),
T03 (the Interface sketch that the test-author derives the deps commit from).

## Read first
- `pyproject.toml` — the header comment on shared meta/target ownership, and the absent
  `[build-system]`.
- `.claude/tools/gate.py:370-390`, `:985-1000` — the PYTHONPATH injection.
- `.claude/skills/conventions/SKILL.md` — the substrate + relational-bootstrap derivation; where a
  `PYTHONPATH` contract would have to live if reading (b) wins.
- `PRINCIPLES.md` A4, C7, D4, F1.
- `workflow_v3_spec.md §5.1` (construct-smoke), `§9`.

## Deliverables
Depends on which reading wins. Under **(a)**: `pyproject.toml` package config, `gate.py` injection
removed, a gate case asserting the app imports with no `PYTHONPATH` set. Under **(b)**: the contract
documented in `conventions`, and a `gate.py` construct-smoke that exercises the app under the
consumer-project import mode rather than the injected one.

Either way: **a gate case that fails if the app can only be imported via a path the gate itself
provides.** That is the finding; the packaging decision is the remedy.

## Verification
- `uv run .claude/tools/gate.py` GREEN on `change/users-002`'s tree (post-rebase) with the new case.
- `uv run pytest .claude/tools/test_gate.py` green.
- Under (a): `python -c "import agentic_development_workflow"` succeeds with `PYTHONPATH` unset.
- The new gate case demonstrably fails against the pre-fix tree.

## Out of scope / Escalate if
- Do NOT touch `change/users-002` in flight. This is a canon fix; it lands on the base branch and
  the change rebases (or a later change picks it up).
- Do NOT "fix" this by teaching the agents to export `PYTHONPATH`. That entrenches the papered-over
  failure mode — exactly what A4 forbids.
- Settling the canon question is an **escalation to the author**, not a builder judgment call. Bring
  both readings with a recommendation; do not resolve it silently (this is the T10d mistake).
