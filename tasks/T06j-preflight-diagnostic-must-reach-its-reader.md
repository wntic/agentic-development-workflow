# T06j — The toolchain preflight's sentence never reaches the one who must act on it

## Goal
T12b gave `gate.py` a preflight that aborts with a usable sentence when the project's environment
lacks `mypy` / `ruff` / `pytest` / `alembic`:

```
error: toolchain missing from this project's environment (…/.venv/bin/python): mypy, ruff, pytest
```

**Two entry points throw that sentence away.**

1. **`subagent_stop.run_gate` discards the gate's stdout/stderr** and reads only
   `.gate/verdict.json`. An aborted run therefore surfaces to the implementer as
   `gate produced no verdict.json` — **three times** — and then writes `ESCALATE`. The terminal state
   is correct (a human must install the toolchain; no `src/**` edit can fix it), but the agent burns
   its whole iteration ceiling on a message that would have ended the confusion at once. This is the
   T09f deadlock shape a third time: an implementer held on a RED outside its lane.
2. **`red_check.py` has no preflight at all.** It runs the baseline lint as
   `sys.executable -m ruff` (T09f), so a consumer missing `ruff` gets a raw `No module named ruff`
   at *baseline* time — before the gate is ever reached. On a project's first change that is the
   very first script the workflow runs.

Both were found by T12b (its findings 1 and 2) and correctly left out of its scope.

The underlying rule is worth stating once and applying to both: **a precondition failure must be
legible to whoever can act on it.** A diagnostic that exists but is swallowed is the same defect as
no diagnostic — and in the `subagent_stop` case it is strictly worse than a crash, because the agent
retries.

## Depends on
T12b (which built the preflight and found both gaps), T06 (the hook lane), T09f (`red_check`'s
baseline lint, the code that needs the second preflight), T06c (`subagent_stop` scope).

## Read first
- `.claude/tools/gate.py` — `required_toolchain` / `missing_toolchain` / `preflight_toolchain`, and
  the exit-2 contract (no `verdict.json` written; `resolve_context()` deletes any stale one first).
  **Reuse these; do not write a second toolchain list** (C7).
- `.claude/hooks/subagent_stop.py` — `run_gate`, what it captures, and how it distinguishes
  "gate ran and said RED" from "gate could not run". The ESCALATE ceiling logic.
- `.claude/tools/red_check.py` — the `sys.executable -m ruff` invocation and its surroundings; note
  `red_check` deliberately does **not** run mypy at baseline time (T09f), so its required set is
  smaller than the gate's.
- `notes/20_consumer_trial_venue.md` — a consumer's first-run experience, which is the case this
  fixes.
- `PRINCIPLES.md` S4, S8; `tasks/T09f-*.md` for why an implementer held on an unfixable RED is a
  known-expensive failure.

## Deliverables
- `.claude/hooks/subagent_stop.py` — distinguish **"the gate could not run"** (exit 2, no verdict)
  from **"the gate ran and it is RED"**. A could-not-run must surface the gate's own message to the
  human and must **not** consume an iteration of the implementer's ceiling — retrying a missing
  interpreter module three times helps nobody. Whether that means an immediate ESCALATE with the
  message, or a release-with-systemMessage in the shape T09f's TESTS-HANDBACK uses, is yours to
  choose — state which and why.
- `.claude/tools/red_check.py` — the same preflight before the baseline lint, importing the gate's
  helper rather than restating the tool list; its required set is `ruff` only (plus whatever it
  actually invokes), not the gate's full set.
- Tests: `test_subagent_stop.py` — an exit-2 gate does not consume a ceiling iteration and its
  message reaches the output; `test_red_check.py` — a missing `ruff` aborts with the sentence, not a
  traceback.

## Verification
- `uv run pytest .claude/tools .claude/hooks` (or the suites covering the three files) green.
- Both new cases demonstrably behave differently against pre-fix code: today the `subagent_stop`
  path reports `gate produced no verdict.json` three times, and `red_check` raises.
- **End to end in a real project**: in a throwaway `uv init --package` project with no dev deps,
  `red_check` and the `subagent_stop` path each produce the actionable sentence once. T12b left one
  such project at `…/scratchpad/consumer-demo`; rebuild it if it is gone.
- The T16 venue (`~/Projects/adw-consumer-probe`, toolchain present) is unaffected: gate GREEN,
  `red_check` behaviour unchanged.

## Out of scope / Escalate if
- Do NOT make the preflight a `GATES`/check row. T12b chose abort-with-exit-2 deliberately: with a
  tool absent there is no GREEN/RED to report, and a check row would be a verdict about the code.
- Do NOT widen `red_check`'s required set to the gate's. It runs before `src/` exists and
  deliberately skips mypy (T09f); demanding the full toolchain there would resurrect that deadlock.
- Do NOT install anything automatically. The workflow declares the substrate (`conventions` block D)
  and the test-author lands it in the deps commit; a script that runs `uv add` behind the human is
  the prediction F1 forbids.
- **Escalate if** `subagent_stop` cannot tell exit-2 from a crashed gate without changing the gate's
  exit-code contract — that contract is shared with `/implement` and `accept.py`, so widening it is
  a canon-adjacent call, not a hook detail.
