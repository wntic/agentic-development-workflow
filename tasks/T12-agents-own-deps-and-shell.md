# T12 — Agents own dependencies and the app shell (dissolve bootstrap AND the template)

## Goal

Eliminate the greenfield-substrate problem at its root instead of moving it. bootstrap.py was
removed (5e559a8, approach A) and briefly replaced by a planned external scaffold **TEMPLATE** —
but a template that ships `fastapi`/`uvicorn`/a shell just re-encodes the *prediction* the workflow
must not do (human ruling: "dependencies are ALWAYS added by an agent; no 'add sqlalchemy in case'").
This task makes that true: the **test-author owns the change's dependencies** (declared from the
Interface sketch, in a pre-baseline commit) and the **implementer writes the app shell** (`create_app`
+ DI container + error handler + exceptions + error schemas) as ordinary `src/**` work from the
skills. A brand-new project then needs nothing but `uv init` + the installed workflow plugin; there is
no bootstrap script and no scaffold template. The workflow generates no code (D1/A3).

The problem bootstrap/the template solved is shown to be **self-inflicted** by two rules; this task
relaxes exactly the minimum:
1. **greenfield collection-error is not a real red** — `red_check` can't see `@pytest.mark.ac`
   markers when the target module isn't written yet (import fails at collection → the marked tests
   never register → check "every AC has a marked test" fails). Fixed with a static (AST) marker
   fallback that also treats the collection failure as RED.
2. **who lands the framework substrate at baseline** — the test-author, in a **pre-baseline commit**
   (not the tests-only baseline commit), from the Interface sketch. No script, no template, no
   prediction: the deps are exactly the ones the change's tests and code import.

**Explicitly NOT needed (design refinement over the first sketch):** narrowing `gate.py`'s
whole-`pyproject.toml` freeze. Because the test-author lands deps in a commit *before* the tagged
baseline, `pyproject.toml` is unchanged from baseline through evaluation, so the freeze never bites
legitimately — and keeping it whole-file preserves the eval-env==baseline-env reproducibility
guarantee. **gate.py is untouched by this task** (do not weaken the trust anchor without a reason a
gate check can't already cover — S8).

## Depends on

- [x] T04 (gate.py), [x] T05 (accept.py), [x] T09/T09b (cycle agents + tests-only baseline),
  and the bootstrap removal (commit 5e559a8) — all already done.

## Read first

- `workflow_v3_spec.md` §5.1 (gate inventory / integrity), §6 step 1 (red baseline), §9 (greenfield /
  substrate — already rewritten for approach A; this task re-aligns it again). **Canon — do not edit
  it yourself; propose the patch, the human applies it (see Steps).**
- `PRINCIPLES.md` — F1 (brownfield primary), S8 (hooks vs trust), D3/D4 (anti-collusion, tests-vs-src
  ownership), A3 (determinism in verification, not authoring). C6 (no scope-overclaim — why the
  template must not carry a store).
- `.claude/tools/red_check.py` — the whole file. Note: `RED_OUTCOMES = {"failed","error"}` (line ~47)
  already accepts errors; the gap is that a **collection** failure means the marked items are never
  collected, so the AST fallback is about *finding the markers*, not reclassifying outcomes. Note the
  tests-only baseline check (~line 16-20) — it inspects the tagged commit only, so a *prior*
  pre-baseline deps commit is legal.
- `.claude/agents/test-author.md` and `.claude/agents/implementer.md` — the `disallowedTools`
  frontmatter. test-author is NOT blocked from `pyproject.toml`; implementer IS (keep it that way).
- `.claude/commands/implement.md` — step 0.5 (brownfield precondition) and step 1 (test-author / red
  baseline).
- The `conventions` skill (framework substrate §D list) and `restapi` / `architecture` /
  `domain-model` / `infra-integration` skills (the app-shell house style the implementer writes from).
- Memory: `greenfield-first-change-blockers` and `plugin-packaging-plan`.
- The removed `bootstrap.py` (git history, commit aa80f7b / its parent) — its `shell_files()` is the
  reference for exactly which shell modules the implementer must produce, and `FRAMEWORK_SUBSTRATE` /
  `DEV_SUBSTRATE` are the reference dep lists (now owned by the test-author, not a script).

## Deliverables (exact paths)

1. `.claude/tools/red_check.py` — greenfield collection-error fallback (see Step 2).
2. `.claude/tools/test_red_check.py` — a test proving a greenfield module-absent collection error
   yields "all ACs present + RED", and that a genuinely broken brownfield test is still caught.
3. `.claude/agents/test-author.md` — document dependency ownership: the test-author declares the
   change's runtime + dev dependencies (from the Interface sketch / conventions §D) in a
   **pre-baseline commit** (`pyproject.toml` + a committed `uv.lock`), separate from the tests-only
   baseline commit. Owns neither `src/**` nor the shell.
4. `.claude/agents/implementer.md` — document that on a **first change** the implementer writes the
   behaviorless app shell (`create_app` + container + error handler + `domain/exceptions.py` +
   `restapi/schemas/errors.py`) from the skills, in addition to the change's behaviour. Still blocked
   from `pyproject.toml`: a genuinely unforeseen dependency is a **CONTRACT-CHANGE** back to the
   test-author, never a silent `uv add`.
5. `.claude/commands/implement.md` — rewrite step 0.5 + step 1: no bootstrap, no template; the
   test-author's pre-baseline deps commit → tests-only red baseline → red_check (with the greenfield
   fallback). A brand-new project is set up once with `uv init` (built-in) + the installed plugin —
   documented, not a workflow step.
6. `workflow_v3_spec.md` §9 — **propose** the canon patch (uv init + agents own deps/shell; drop the
   external-template idea). Deliver it as a diff in the task report; the human applies it.
7. `CLAUDE.md` + `PRINCIPLES.md` F1 — align the prose (substrate is agent-owned per change, not a
   template precondition; project setup is `uv init`).
8. `tasks/INDEX.md` — mark **TEMPLATE = DROPPED (superseded by T12)** and **T09d = RESOLVED by T12**
   (conditional deps are the test-author's pre-baseline concern, per change, from the Interface
   sketch — never predicted); tick T12 when Verification passes.

## Steps

1. **test-author owns deps (pre-baseline commit).** Update `test-author.md` + `implement.md` step 1
   so the test-author, before committing the tests-only baseline, commits `pyproject.toml` (framework
   substrate §D that this change's tests/code import + the dev deps the tests need) **and** a
   `uv lock`-refreshed `uv.lock`, as a distinct pre-baseline commit. (This is the honest fix for the
   old "bootstrap left uv.lock dirty" finding too — the dep-owner locks and commits.) The tests-only
   baseline commit stays tests-only, so `red_check`'s anti-collusion check is unaffected.
2. **red_check greenfield fallback.** When a test module fails to import at collection because the
   module under construction does not exist yet (greenfield first change), `red_check` must still
   (a) discover the `@pytest.mark.ac("AC-n")` markers — a static AST scan of the change's test files
   as a fallback when pytest collection errored — and (b) count that collection failure as RED for
   those ACs. **Guard it tightly:** the fallback applies only when the failing import targets the
   app package that does not exist yet (`src/<pkg>/` or the specific target module absent), NOT to a
   test that errors for any other reason (a real import typo in brownfield must still fail red_check).
   If a clean discriminator between "greenfield module-not-written" and "broken test" cannot be built
   deterministically, **STOP and escalate** — do not ship a fallback that masks broken tests.
3. **implementer writes the shell.** Update `implementer.md`: first change ⇒ the implementer produces
   the behaviorless shell from the skills (reference the removed `bootstrap.py` `shell_files()` for
   the exact module set) plus the change's route. Keep it blocked from `pyproject.toml`; unforeseen
   dep ⇒ CONTRACT-CHANGE. (Depends on the shell being emittable gate-clean — coordinate with the
   open **SKILL-GATE** task: the restapi/architecture skill templates must pass the gate's RUFF_SELECT.)
4. **Canon + prose.** Propose the `workflow_v3_spec.md` §9 patch (report it, human applies). Edit
   `CLAUDE.md` + `PRINCIPLES.md` F1 to match. Update `tasks/INDEX.md` (drop TEMPLATE, resolve T09d).
5. **Confirm gate.py is untouched** and still green — this task must not modify the trust anchor.

## Verification

- `uv run python -m pytest .claude/tools/ -q` — full meta suite green (currently 162), including the
  new `test_red_check.py` cases (greenfield collection-error ⇒ RED + all ACs; brownfield broken test
  ⇒ still fails red_check).
- `git diff --stat` shows **no change to `.claude/tools/gate.py`** and **no change to `test_gate.py`**.
- **Human/e2e (T11-style, not builder-runnable):** in a throwaway `uv init` project with the plugin
  installed, run `/spec platform` (GET /health) → `/implement platform/001` and confirm it reaches a
  GREEN gate with NO bootstrap and NO template: test-author lands `fastapi`+deps pre-baseline + writes
  red tests (red_check green via the fallback), implementer writes the shell + route to green,
  evaluator flips. Record it in the T11 runbook / defect log (the notes/pipeline_dryrun honesty
  discipline).

## Out of scope / Escalate if

- **Do NOT touch `gate.py` / its freeze.** If you find a real case where the whole-`pyproject.toml`
  freeze blocks a legitimate agent action even with deps landing pre-baseline, STOP and escalate — do
  not weaken the trust anchor on your own judgment.
- **Do NOT relax the tests-only baseline or the tests-vs-src ownership** (D3/D4) — the deps commit is
  a *separate, earlier* commit, and the baseline commit stays tests-only.
- **Do NOT build a scaffold template or any code-emitting script** — that is the mistake this task
  closes. `uv init` + skills + agents only.
- Escalate if the greenfield red_check discriminator (Step 2) cannot be made deterministic, or if the
  restapi/architecture skills cannot emit a gate-clean shell (that is the SKILL-GATE dependency).
