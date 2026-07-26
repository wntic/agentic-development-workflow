# T15 — Split the shipped plugin from the trial harness

## Goal
`pyproject.toml` at the repo root wears **three hats at once**, and only one of them ever ships:

1. **the trial app's runtime deps** (`fastapi`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, …) —
   an artifact of whatever change is currently being trialled here; transient by nature (T02 purged
   `src/`, `users/002` recreated it);
2. **the toolchain a consumer legitimately needs** (`pytest`, `pytest-asyncio`, `ruff`, `mypy`,
   `testcontainers`, `httpx`) — this one is *correct* where it is and must stay in the consumer's
   own project: `gate.py` invokes `sys.executable -m mypy|ruff|pytest`, so the tools must live in the
   environment that can see the project's code. A plugin with an isolated env could not type-check
   or test the app it is installed next to. Already declared in `conventions` block D;
3. **the meta layer's own test environment** — `pytest` for the 297 tests under `.claude/tools/`,
   which test `gate.py`/`accept.py`/`red_check.py` themselves and ship nowhere.

Hat 3 is the one with no home: the workflow's own dependencies live outside the workflow, mixed into
a file that also serves a disposable trial app. And there is **no `.claude-plugin/plugin.json`** yet
— the packaging has never been started, so nothing has forced the question.

This task separates what ships from what is scaffolding for testing it.

## Depends on
T12b (the consumer-facing packaging facts — land those first so this task moves code, not decisions).
Do **not** start before T11's e2e probe has at least been designed: the probe is the only thing that
exercises the shipped artifact in a real consumer project, and it is the acceptance test for this
split.

## Read first
- `.claude/settings.json` — every hook path as it is written today (these become
  `${CLAUDE_PLUGIN_ROOT}`-relative).
- `.claude/tools/gate.py`, `accept.py`, `red_check.py` — how each locates the repo root and its own
  siblings; `gate.py`'s self-hash (E-02) in particular, which must keep working once the tools are
  installed rather than checked out.
- `.claude/hooks/bash_guard.py` — `_repo_root()` (`CLAUDE_PROJECT_DIR` or the git toplevel): the
  distinction between *plugin root* and *project root* becomes load-bearing here.
- `pyproject.toml` — its header already documents the shared meta/target ownership.
- `CLAUDE.md`'s two-layer table (Meta vs Target) — this task makes that table physical.
- `PRINCIPLES.md` A1 (layer separation), C6, C7, F1.

## Deliverables
Shape to be decided as part of the task, but it must answer all four:

- **The plugin manifest** — `.claude-plugin/plugin.json`, and hook/tool paths reparented to
  `${CLAUDE_PLUGIN_ROOT}` so they resolve when installed rather than checked out.
- **A home for hat 3** — the meta layer's own test environment, independent of whether a trial app
  exists in the tree. The acceptance test is blunt: **delete `src/` entirely and
  `uv run pytest .claude/tools/` must still pass.** Today it would not survive T12b's rejected
  `[build-system]`, and the coupling is exactly what this fixes.
- **A decision on the trial app** — does a trialled change live at the repo root (as `users/002`
  does), in a sibling directory, or in a throwaway project outside the repo entirely? This is the
  substantive design call; it determines whether the trial is *packaging-faithful* to a consumer
  project. Today it is not, which is how T12b's A4 hole survived unnoticed.
- **What is excluded from the shipped plugin** — `tasks/`, `notes/`, `workflow_v3_spec.md`,
  `codegen_workflow_spec.md`, the trial app, and the meta layer's tests are all dev artifacts. State
  the rule, not just the list, so a new file lands on the right side by default.

## Verification
- `uv run pytest .claude/tools` green throughout.
- **`src/` deleted → `uv run pytest .claude/tools/` still green.** The decoupling, stated as a test.
- The plugin installs into a fresh `uv init --package` project and `/orient` resolves its skills,
  agents, commands, hooks and tools with no path fixups. (Overlaps T11 — coordinate rather than
  duplicating the probe.)
- Hooks fire correctly from the installed location: at minimum `bash_guard` still denies a non-owner
  write to the *project's* protected tree while ignoring the *plugin's* own files.
- `gate.py`'s self-hash (E-02) still passes when the tools are installed, not checked out.

## Out of scope / Escalate if
- Do NOT move the toolchain out of the consumer's project (hat 2). It is where it must be; the
  reasoning is in the Goal, and getting this backwards would break every gate run in every consumer.
- Do NOT change what any gate checks. This moves files and fixes paths; a behavioural change to
  `gate.py`/`accept.py` riding along in this task would be invisible in the diff noise.
- **Escalate before writing code** with a proposed layout. This is a repository restructure with
  several defensible shapes, and it touches the hook paths that every enforcement guarantee rests on
  — the wrong call is expensive to unwind. Bring the trial-app decision explicitly; it is the one
  that determines whether future trials test the real artifact.
