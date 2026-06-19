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
- **Multi-context app (block F).** When the tree was scaffolded from several sibling context
  manifests into ONE package (a `specs/**/epics/<NN>-slug/manifest.yaml` with siblings under the same
  epics dir), there is no single "target" manifest whose nodes cover the whole tree — every other
  context's body would map `UNMAPPED`. Set `<epics-dir>` to the shared parent and pass `--app
  <epics-dir>` to **both** pre-flight commands (step 2) so the registry is the union over all
  contexts. Pick any one of the manifests as the positional `<manifest>`; `--app` adds the siblings.

## 2. Pre-flight (deterministic, no agents)

1. `uv run .claude/tools/validate_manifest.py <manifest>` — must be `ok` (add `--app <epics-dir>` in
   multi-context mode so cross-epic refs resolve). A form/graph error or a §16 presence-gap is the
   **architect's** to fix; stop and report, do not scaffold or implement on an invalid manifest.
2. `uv run .claude/tools/plan_implementation.py <manifest> <root> --json` (add `--node <X>` in
   single-node mode; add `--app <epics-dir>` in multi-context mode so every context's bodies map and
   none is left `UNMAPPED`). This is the **deterministic trigger + DAG ordering**: it returns the
   pending files (each still carrying `raise NotImplementedError` or a column-less table), the
   producer skill per file, the canonical test + its kind (`flat` | `manual` | `none`), and a
   `dag_level`.
   - If `count == 0`, every body is filled — skip to step 5 (final gate).
   - A residual `UNMAPPED` item is a defect, not a body to fill — a scaffolder gap (e.g. a
     `NotImplementedError` connection factory the scaffolder should have rendered complete, F-011) or
     a missing `--app`. Stop and report it; do not dispatch an implementer against it.

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
- `uv run mypy src tests` — green;
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
- **`infrastructure.tables` node — add a metadata-import smoke.** A `Table(...)` can pass mypy + ruff
  yet raise at **construct** time (a functional `Index("ix", "lower(email)")` whose bare string reads
  as a missing column → `ConstraintColumnNotFoundError`); the per-file toolchain misses it because a
  table has no executable test. After mypy/ruff clean, run `uv run python -c "from <pkg>.infrastructure.postgres
  import metadata"` — the cheapest exercise that actually constructs every `Table` in the shared
  `MetaData`. A red here is the table body's defect (a bare-string functional index → wrap the
  expression in `text(...)`, see `infra-sqlalchemy-table`); iterate it like any other red.

## 4. Single-node mode

When `$ARGUMENTS` is a node/file substring: run the planner with `--node <X>`, expect one item,
dispatch one `implementer`, run that file's toolchain check, iterate ≤3, report. Same anti-collusion
and acceptance rules.

## 5. Final gate + report

Once the worklist is drained (or you have escalations), run the **whole-tree** toolchain from the
package root:
- `uv run mypy src tests` · `uv run ruff check src tests` · `uv run ruff format src tests` ·
  `uv run pytest` (flat tests green; `_manual` stubs stay skipped — expected, their asserts are a
  deferred step, §9).
  - **The testcontainers integration suite is Docker-gated.** `tests/integration/` (the discovery
    invariants, the `postgres/` repository-contract tests, and the `api/<resource>/` REST-endpoint tests)
    needs a running Docker daemon; without one those tests **error with `DockerException` — expected, not
    a failure** of this Docker-less loop. Run `uv run pytest tests/unit` for the loop's green bar, and run
    the full `tests/integration/` suite under a daemon (a session event loop is configured — F-D) as the
    deeper gate: it is the only layer that exercises the real SQL round-trip, the `IntegrityError`→domain
    constraint-name map, and the full HTTP→handler→repo→DB path (all review-tail in the Docker-less loop).
  - **App-construction smoke is part of this `pytest` run.** `tests/unit/restapi/test_app_constructs.py`
    (from `test-discovery-invariants`) constructs `create_app(container=Container())` and renders
    `app.openapi()` with no database. It is the only gate that catches **construct-time** failures the
    type/lint/unit layers miss — a missing framework dependency FastAPI imports at app-build time
    (`python-multipart` for a multipart route, …), broken middleware wiring, or a route whose schema
    won't build. A red here on a freshly scaffolded tree is usually an upstream dependency-derivation
    gap (`conventions` block D / the scaffolder's `pyproject`), not an implementer's body — escalate it
    as a meta-layer defect, don't patch the generated tree.
- **No-silenced-imports gate (deterministic).** `grep -rn "# noqa: F401" src` must return **nothing**.
  An inline `# noqa: F401` on a content module is never sanctioned (only the project-wide
  `__init__.py` F403/F405 per-file ignore in `pyproject.toml` is) — a hit means the scaffolder
  over-imported and silenced ruff, or an implementer left a dead import. Surface it loudly as a defect
  and have the owner delete the import (not the `# noqa`). This is what keeps ruff F401 armed on the
  imports most prone to contract drift (spec §0-P3).
- **No-silenced-types gate (deterministic).** `grep -rn "# type: ignore" src` must return **nothing**.
  An inline `# type: ignore` on a content module is never sanctioned (`conventions` block E — only the
  project-wide `[[tool.mypy.overrides]] ignore_missing_imports` for a stub-less SDK is); a hit means
  mypy is "clean" only because a real error was suppressed. Surface it as a defect and fix at the
  source: an `[attr-defined]` ignore is a leaked-out type (carry the value on a typed wrapper, not a
  stashed function attribute), a `[no-any-return]` is a raw-boundary value (`cast(<type>, …)` at the
  boundary). `tests/` may keep a narrowly-scoped ignore only where a fake deliberately violates a
  Protocol — never `src`.
- **No-future-annotations gate (deterministic).** `grep -rn "from __future__ import annotations" src`
  must return **nothing**. `general-typing-conventions` forbids it project-wide: this stack introspects
  annotations at runtime (Pydantic / pydantic-settings, `dependency-injector`, dataclass `__post_init__`,
  FastAPI), and PEP 563 stringifies them so that introspection breaks silently. The toolchain does **not**
  catch it — the ruff select (`E, F, I, B006, B904`) has no rule for it, and in a runtime-harmless module
  (e.g. `domain/exceptions.py`) mypy/ruff/unit/construct all stay green, so the violation is invisible
  without this grep. A hit is almost always the scaffolder reflexively emitting the modern-module header
  against its own skill instruction (`domain-exception` / `general-typing-conventions` both ban it) —
  surface it as a defect and delete the line at the source, never keep it.

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
