# SKILL-GATE — the skill templates must emit gate-clean code

## Goal

The knowledge layer (skills) instructs agents how to write the app's code; the enforcement layer
(`gate.py`) rejects code that fails its pinned `ruff` selection. Today these disagree: several skill
templates were written against an older, narrower ruff select, so the code an agent writes *by
faithfully following the skill* is rejected by the gate's broad `RUFF_SELECT` (see `gate.py` — cite
it, do not restate the list here, C7). Surfaced live on the platform/001 probe (T09c finding F2:
`F403` / `F841` / `RUF022` fired on shell code the skills prescribe). This task makes the
skill-prescribed code pass the gate, so the implementer writing a module or the app shell from a
skill lands green instead of fighting the linter.

This is a **T12 dependency**: T12 has the implementer write the behaviorless app shell from the
`restapi` / `architecture` / `domain-model` skills, and that shell must be gate-clean.

## Depends on

- [x] T04 / T04c (gate.py + its ruff selection), [x] T08 (skill catalog merged to its current shape).

## Read first

- `gate.py` — `RUFF_SELECT`, `check_ruff` / `toolchain.ruff-check` (the exact selection and how it is
  invoked: `ruff check --no-cache --select <RUFF_SELECT>`). This is the definition of "clean"; cite it.
- `.claude/skills/architecture/SKILL.md` — the **re-export contract** (`from . import <module>` +
  `from .module import *` + `__all__ = module.__all__` / `+`-joined). This is the primary source of
  `F403` ("import *") and `F405` ("may be undefined, from star imports") under the gate's `F` rules.
  Note the carve-outs (entrypoint packages, routers) already there.
- `.claude/skills/restapi/SKILL.md`, `domain-model/SKILL.md`, `python-style/SKILL.md` — other code
  the shell/first modules come from (error schemas, `__all__` lists, exceptions catalog).
- The removed `bootstrap.py` (git history, ~aa80f7b) — its `shell_files()` shows the exact shell the
  implementer must now write; it already carried `from .exceptions import *  # noqa: F403` and an
  `__all__ = ["MIDDLEWARE_ERRORS", "ErrorResponse", "error_responses"]` (unsorted → `RUF022`). These
  are the concrete reds to reproduce.
- `PRINCIPLES.md` S4 (a must-hold rule lives in a gate), S8 (don't weaken the gate to launder), C7
  (derivation has one home). Memory: `greenfield-first-change-blockers` (T09c F2), `skill-altitude-audit`.

## Deliverables (exact paths)

1. Edits to the offending skill templates — at minimum `.claude/skills/architecture/SKILL.md` (the
   re-export idiom) and `.claude/skills/restapi/SKILL.md` (error-schema `__all__` ordering), plus any
   other skill whose prescribed code reproduces a gate ruff finding.
2. A deterministic **guard** that the skill-prescribed code stays gate-clean (see Steps 3 — pick the
   feasible form; escalate if none is clean).
3. If — and only if — the re-export idiom cannot be made clean at the skill level, a **proposed**
   `gate.py` change (a scoped `--per-file-ignore` for `__init__.py`: `F403`/`F405`) delivered as a
   diff + rationale for the human to rule on. Do NOT change `gate.py` unilaterally (S8).

## Steps

1. **Reproduce the reds.** Materialize, in a scratch tree, the exact modules the skills prescribe —
   the app shell (`bootstrap.py`'s `shell_files()` set: `containers.py`, `domain/__init__.py`,
   `domain/exceptions.py`, `restapi/main.py`, `restapi/error_handler.py`, `restapi/schemas/__init__.py`,
   `restapi/schemas/errors.py`) plus one representative multi-module re-export package built to the
   architecture skill's contract. Run the gate's ruff exactly (`ruff check --no-cache --select
   <RUFF_SELECT from gate.py>`). Record every finding with its rule code and the skill line that
   produced it.
2. **Fix at the skill level, cheapest principled form.** For each finding:
   - `RUF022` (unsorted `__all__`) → sort the literal `__all__` in the template (and teach the skill
     to emit sorted `__all__`).
   - `F841` (unused local) / other mechanical rules → fix the template snippet.
   - `F403`/`F405` (the star re-export) → this is the load-bearing one. The idiom is intentional
     (mypy needs the `from . import <module>` + the wildcard). Decide the policy: (a) the skill's
     `__init__` template carries a correct, minimal `# noqa: F403` on each wildcard line (note: the
     gate grep-gates only `# noqa: F401`, so `F403` noqa is allowed) — verify F405 does not then fire
     on the `__all__ = module.__all__` reference; OR (b) if noqa-per-line is unworkable/ugly at scale,
     escalate a scoped `gate.py` `--per-file-ignore` (`__init__.py: F403,F405`) as a human decision
     (Deliverable 3). Prefer (a) if it is clean; (b) is a gate change and needs a ruling.
3. **Guard.** Add a regression that a later reword can't silently re-break: extend
   `test_skill_catalog.py` (or a new `test_skill_shell_ruff.py`) to materialize the shell / a
   representative re-export package from the skill-prescribed content and assert `ruff check --select
   <RUFF_SELECT>` is clean. If a faithful, low-noise materialization can't be built (skill snippets
   are illustrative fragments, not whole modules), say so and fall back to verifying against the T11
   e2e (the implementer's real shell passes the gate) — but call that out explicitly, don't pretend a
   guard exists.

## Verification

- The materialized shell + representative re-export package pass `uv run ruff check --no-cache
  --select <RUFF_SELECT from gate.py>` with zero findings.
- `uv run python -m pytest .claude/tools/ -q` green (including the new guard, if Step 3 landed one).
- If a `gate.py` per-file-ignore was needed, `test_gate.py` covers it and the change is a separate,
  human-approved commit (not folded in silently).

## Out of scope / Escalate if

- **Do NOT widen or narrow `RUFF_SELECT` to hide a real defect.** The re-export `F403`/`F405` case is
  a legitimate idiom (a scoped per-file-ignore is defensible); any *other* rule firing is a real
  finding to fix in the template, not to silence.
- **Do NOT touch `gate.py` unilaterally** — Deliverable 3 is a *proposal* for the human.
- Escalate if fixing a template to satisfy ruff would contradict a house-style rule the skill exists
  to enforce (e.g. mypy needs the star re-export) — that is the F403 tension; surface it with the
  concrete trade-off rather than picking silently.
