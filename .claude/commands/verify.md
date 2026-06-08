---
description: "Scaffold tail — fill scaffolded bodies via the implementer agent until mypy/ruff/tests are green (spec §4, §9, §11, §12)"
argument-hint: "[manifest] [package-root] | <node-or-file> | (empty)"
---

You are the **runner** for the verification loop (spec §4, §11, §12). The scaffolder has laid the
tree; your job is to drive **implementer** subagents to fill the scaffolded bodies until the
toolchain and the canonical tests are green — deterministically triggered, ordered by the DAG, the
implementer doing the per-file judgement. You orchestrate; you never write a body yourself.

`$ARGUMENTS` is one of: empty (verify the whole scaffolded epic) · a single node/file substring
(verify just that one) · explicit `<manifest> <package-root>` paths.

## 1. Resolve the target

- **Manifest + package root.** If `$ARGUMENTS` names them, use them. Otherwise discover: the
  manifest is the epic under `specs/epics/<NN>-slug/manifest.yaml` (or, while the pipeline is
  pre-build, the fixture `.claude/tools/fixtures/helpdesk_manifest.yaml`); the package root is the
  matching disposable tree under `examples/generated/<pkg>/`. If discovery is ambiguous (several
  generated packages, no obvious epic), **stop and ask** which manifest + root to verify — do not
  guess.
- If `$ARGUMENTS` is a single token that is not a path, treat it as a `--node` filter (single-node
  mode, step 4) against the discovered manifest + root.

## 2. Pre-flight (deterministic, no agents)

1. `uv run .claude/tools/validate_manifest.py <manifest>` — must be `ok`. A form/graph error or a
   §16 presence-gap is the **architect's** to fix; stop and report, do not scaffold or implement on
   an invalid manifest.
2. `uv run .claude/tools/plan_implementation.py <manifest> <root> --json` (add `--node <X>` in
   single-node mode). This is the **deterministic trigger + DAG ordering**: it returns the pending
   files (each still carrying `raise NotImplementedError` or a column-less table), the producer skill
   per file, the canonical test + its kind (`flat` | `manual` | `none`), and a `dag_level`.
   - If `count == 0`, every body is filled — skip to step 5 (final gate).

## 3. Dispatch implementers, level by level (§11)

Process the worklist in **ascending `dag_level`**. Within a level, the items are independent — each
is a different file with a different owner — so dispatch them **in parallel**: one `implementer`
subagent per item, all in a single message (multiple Agent tool calls). Finish a level before
starting the next (a higher level may depend on a body filled in a lower one).

For each item, the `implementer` invocation prompt carries **only**:
- the **scaffold file** path (`item.file`) — the one file it edits and owns;
- the **producer skill** to apply (`item.skill`, e.g. `application-command`) — it reads
  `.claude/skills/<skill>/SKILL.md` itself;
- the **source UC** when the file's `CONTRACT —` comment cites one (else "none").

**Never pass the test path or any test content to the implementer** — anti-collusion (§9). The
implementer's contract is the `CONTRACT —` comment already in the scaffold + the skill + the UC. It
*runs* tests; it must not *read* them.

After each implementer returns, run the **per-file toolchain check** (commands from `conventions`
block E):
- `uv run mypy src/<package>` — green;
- `uv run ruff check <item.file>` then `uv run ruff format <item.file>` — clean;
- if `item.test_kind == "flat"`: `uv run pytest <item.test>` — green (red→green is the proof).

**Iterate to acceptance, ≤ N = 3 rounds per file.** If a check is red, re-dispatch the **same**
`implementer` on the same file with the failing mypy/ruff/test output appended to the prompt (still
no test source). After 3 red rounds, **stop on that file and escalate** to the human with the output
— an unbreakable red is a review signal, not something to brute-force.

**Acceptance is two-shaped (§9):**
- `flat` items → accepted when mypy + ruff clean **and** the flat test is green.
- `manual` / `none` items (auth/multi-dep handlers, repositories, capability adapters, endpoints,
  middlewares, the table) → there is no executable assert at unit time. Accepted when mypy + ruff are
  clean and the implementer reports faithful skill/contract conformance; **record these in the review
  tail** — do not present them as proven.

## 4. Single-node mode

When `$ARGUMENTS` is a node/file substring: run the planner with `--node <X>`, expect one item,
dispatch one `implementer`, run that file's toolchain check, iterate ≤3, report. Same anti-collusion
and acceptance rules.

## 5. Final gate + report

Once the worklist is drained (or you have escalations), run the **whole-tree** toolchain from the
package root:
- `uv run mypy src/<package>` · `uv run ruff check src tests` · `uv run ruff format src tests` ·
  `uv run pytest` (flat tests green; `_manual` stubs stay skipped — expected, their asserts are a
  deferred step, §9).
- **No-silenced-imports gate (deterministic).** `grep -rn "# noqa: F401" src` must return **nothing**.
  An inline `# noqa: F401` on a content module is never sanctioned (only the project-wide
  `__init__.py` F403/F405 per-file ignore in `pyproject.toml` is) — a hit means the scaffolder
  over-imported and silenced ruff, or an implementer left a dead import. Surface it loudly as a defect
  and have the owner delete the import (not the `# noqa`). This is what keeps ruff F401 armed on the
  imports most prone to contract drift (spec §0-P3).

Then produce the **attribution diff** against the scaffold baseline the scaffolder froze:
- `uv run .claude/tools/scaffold_snapshot.py diff <package-root>`. Every changed file is implementer
  work; **a changed file that was NOT a dispatched body scaffold — any declarative/glue file
  (`__init__.py`, `containers.py`, a DTO, a schema, `pyproject.toml`), or an `added`/`removed` file —
  is an overreach** (the implementer must touch only its dispatched body, §4): surface it loudly.
  Also eyeball the body diffs for convention slips the toolchain can't catch (e.g. an import reaching
  into a submodule instead of the package re-export). If no baseline exists (`<package-root>.scaffold/`
  missing), say so — attribution is unavailable for this run (the scaffolder snapshots it; a tree
  scaffolded before that step has none).

Report:
- files filled (count) · flat tests now green (count) ·
- **review tail**: the `manual` / `none` / table files accepted on mypy+ruff only — list them
  explicitly as needing human review (the §9 irreducible surface);
- **attribution**: changed-file count vs the baseline + any overreach (a touched glue/declarative file)
  or convention slip the diff surfaced;
- escalations: any file still red after 3 rounds, with its output;
- toolchain final: mypy / ruff / pytest pass-fail.

## Notes

- The implementer is dispatched, never self-selected; you (the runner) own which file and when (the
  planner's trigger + DAG). Parallelism is across files within a level, never within one file
  (a router with several endpoints is one file = one dispatch).
- You do not author tests, manual-stub asserts, or migrations, and you do not edit declarative/glue —
  if a body cannot go green without that, it is contract drift or a manifest gap → escalate to the
  architect, do not patch around it.
- The automated, human-out-of-the-loop runner is a later build-plan step; this command is the
  interim driver.
