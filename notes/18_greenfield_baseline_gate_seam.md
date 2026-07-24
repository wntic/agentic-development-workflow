# 18 — The greenfield baseline/gate seam (the users/001 ESCALATE)

`/implement users/001` (the greenfield first change of the `users` context) burned all three
implementer passes and ESCALATEd. The failing gate checks were `toolchain.mypy` and
`toolchain.ruff-check` — and **every** failing item was in `tests/**`, the implementer's blocked
lane (D4). The implementer behaved correctly: it got its own `src/**` fully green, diagnosed that
the residual red was 100% test-side, held at the SubagentStop gate rather than fabricating green,
and enumerated the fixes. The ceiling → ESCALATE was the correct outcome for the state it was in —
the defect was the workflow, not the agent.

## Root cause — one mechanism

`red_check.py` screens the RED baseline against a tree where **`src/` does not exist**; `gate.py`
judges the *same* test files against a tree where **`src/` exists**. Any toolchain check whose
verdict depends on `src`'s presence disagrees between the two, and because the disagreement lands
in `tests/**`, it is unfixable by the implementer and guarantees an ESCALATE.

Two src-dependent classes bit us, plus one universal-config gap:

1. **ruff `I001` (own-package import grouping).** Under `ruff --isolated`, isort auto-detects
   first-party packages from what is on disk. At baseline `src/agentic_development_workflow` is
   absent → the own package sorts as third-party → the test-author's import block is clean and
   `red_check` blesses it. At gate time the package exists → it sorts first-party → the same block
   is `I001`.
2. **mypy `attr-defined` on `object`-typed conftest fixtures.** With no src to name at author time,
   the conftest annotated fixtures `-> object`; strict mypy at gate time (src now present) rejects
   attribute access on `object`. Screenable only after src exists; fixable only by the test-author.
3. **Universal config gap (not src-dependent).** `str → SecretStr` (pydantic-settings) and the
   `testcontainers` missing-stubs import are hard errors under strict mypy for *every* app on this
   stack. `red_check` deliberately skips mypy (greenfield imports a not-yet-written package), so the
   test-author gets no signal; `gate.py` then enforces it over `tests/**` with no plugin/override.

## Fixes

**Fix 1 — gate.py mypy config (universal-stack altitude, C6/C7).** Added `plugins = pydantic.mypy`
and `[mypy-testcontainers.*] ignore_missing_imports = True` to `MYPY_CONFIG`. These are universal
facts of the pydantic-settings + testcontainers stack, so they live in the one config home, never as
per-app `# type: ignore` (which the grep gate bans anyway). Reproduced: clears both classes; the
users/001 mypy count dropped 14 → 11 (the 11 remaining are the class-2 `object` fixtures).

**Fix 2a — pin isort known-first-party (kills the ruff drift).** `gate.ruff_common(tree)` now pins
`lint.isort.known-first-party=[<project package>]`, derived from `pyproject [project].name`.
Classification is now explicit and src-independent, so baseline and gate agree by construction.
`red_check.lint_tests` calls the same helper (C7: one home for ruff config), so the baseline screen
now catches an ungrouped own-package import at author time instead of letting it drift to the gate.
`red_check.project_package` was collapsed to delegate to `gate.project_package`.

**Fix 3 — orchestration handback for a tests-localized red (the structural fix; subsumes 2b).**
`gate.py` now emits `red_localized_to: "tests"` in the verdict when a RED gate's failures are
entirely the static toolchain over `tests/**` — confirmed by re-running mypy + ruff over `src/`
*alone* and finding it clean (so a src bug, a pytest/behaviour failure, or an integrity breach is
never mis-routed). On that signal the SubagentStop hook releases the implementer immediately — no
block, no counter, no ESCALATE — and `/implement` returns to step 1 with a fresh test-author to fix
`tests/**` (re-type the conftest against the now-existing package, re-sort own-package imports). It
consumes one of the 3 full-cycle passes, so a change bouncing between the lanes still ESCALATEs
rather than looping forever. This is the decision on 2b (the class-2 `object` fixtures): keep strict
mypy over `tests/**`, and route the fix to the lane that owns it rather than relax the gate.

## Design-canon follow-up (not yet done)

`workflow_v3_spec.md` / `PRINCIPLES.md` should note that mypy-over-`tests/**` is a gate-time-only
contract with a test-author handback (the S8 completion for this seam), and that the red-localization
signal is the deterministic fact `/implement` branches on (S4). Flagged for the human — agents do not
edit design canon.

## Tests

- `test_red_check.py::test_e2e_greenfield_own_package_import_ungrouped_refused_at_baseline` — locks
  in that the baseline screen now refuses the drift-prone import grouping (Fix 2a).
- `test_gate.py::test_red_localized_to_tests_when_only_tests_static_toolchain_red` and
  `::test_red_localized_to_none_when_src_is_static_toolchain_red` — the localization signal fires
  only for a genuinely tests-confined static red (Fix 3).
