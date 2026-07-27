# T15 — Split the shipped plugin from the trial harness

---

## ESCALATION RESOLVED — author's decisions, 2026-07-26

The first dispatch escalated with a measured layout proposal and five open decisions. **Layout C is
approved as proposed: `.claude/` *is* the plugin root, and not one file moves** — so `gate.py`'s
`PROTECTED_PATHS` and `bash_guard`'s `PROTECTED_FRAGMENTS` stay literally true and unedited, and the
new `hooks/hooks.json` lands inside an already-protected tree for free. Read the first dispatch's
probe table before starting; it is measured fact (Claude Code 2.1.220), not assumption.

**Distribution is a correctness requirement, not a preference (its finding 4).** Release by
`git subtree split --prefix=.claude` into a standalone plugin repo, and use a **whole-repo**
marketplace source (`github`/`url`) — **never `git-subdir`**. Measured: a whole-repo clone keeps
`.git` in the cache so `check_self_hash` passes; a subdirectory source is a content copy with no
`.git`, and E-02 then returns *"gate.py is not inside a git repository"* → **every gate run in every
consumer goes RED**. `check_self_hash` needs no change: it computes `relative_to(top)` at runtime, so
`tools/gate.py` in the split repo works exactly as `.claude/tools/gate.py` does here — and verifies
against the *published* commit, a strictly stronger anchor.

**D1 — namespaced `agent_type`: (a), fold into T15, in its own commit.** Verified in source:
`subagent_stop.py:55` pins `IMPLEMENTER_AGENT = "implementer"` and compares at `:173`; `bash_guard`'s
`ROLE_OWNED` (`:121-125`) is keyed on bare role names. Shipped as a plugin the payload carries
`adw:implementer`, so the implementer is **never held on a RED gate** (T06c dead) and all three cycle
roles **lose their owned-tree write path** (T06d dead) — both silently, invisible to every test here.
Shipping without this removes two enforcement guarantees, so it is not a follow-up. Fix: compare on
`agent_type.rsplit(":", 1)[-1]` in **both** hooks, and test **both** the bare and namespaced forms —
the bare form must keep working, because this repo loads via project config, not as a plugin.

**D2 — plugin name `adw`; the rename sweep is scoped to `.claude/**` and nothing else.** Measured:
a bare `/probe-cmd` is `Unknown command`; only `/<plugin>:<name>` resolves. So in a consumer the
commands are `/adw:spec`, `/adw:implement`, `/adw:accept-change`, `/adw:abandon`, `/adw:orient`.
By the ship-by-location rule below, **a consumer never reads anything outside `.claude/`** — so
`CLAUDE.md`, `tasks/`, `notes/` and both spec docs stay bare, and only cross-references *inside*
`.claude/**` (a command naming another command, an agent naming a command) get the namespaced form.
Where a shipped file must name a command, write it so both forms are legible to a reader
(`/adw:implement` — bare `/implement` when the workflow is loaded from project config, as in the
workflow's own repo). Do not attempt to make this repo load via the plugin as well: the first
dispatch is right that enabling both at once **double-fires every hook**.

**D3 — confirmed: two homes for the hook wiring, pinned by a test.** A plugin cannot ship hooks in
`settings.json` (it honours only `agent` / `subagentStatusLine`), so `.claude/settings.json` (dev,
`$CLAUDE_PROJECT_DIR`) and `.claude/hooks/hooks.json` (shipped, `${CLAUDE_PLUGIN_ROOT}`) must both
exist. The duplication is forced by the platform, so it gets a **guard, not a comment** (S4): a test
in `.claude/tools/` that maps one form onto the other and FAILs on drift.

**D4 — (b) the `bin/` shim, with one added requirement.** One invocation form, identical in dev and
installed, and it preserves hat 2 (the *project's* venv, so `sys.executable -m mypy` still sees the
app). It also sidesteps the unverified question of whether `${CLAUDE_PLUGIN_ROOT}` expands inside
`commands/*.md`. **Added requirement: the shim must work uninstalled**, i.e. when
`CLAUDE_PLUGIN_ROOT` is unset it resolves the tools directory from its own location (`$0`), so the
workflow's own repo keeps working. `subagent_stop.run_gate`'s hardcoded
`root/".claude"/"tools"/"gate.py"` becomes `CLAUDE_PLUGIN_ROOT`-first with the current path as
fallback, same rule.

**D5 — (a) filed as a follow-up (T18), not done here.** Once installed, the plugin lives outside the
consumer repo: `bash_guard` allows writes to it (targets resolve outside the root) and
`integrity.protected-trees` diffs paths that do not exist there, passing **vacuously**. The only
protection left is `check_self_hash`, which covers `gate.py` + `criteria_lint.py` **alone** —
`accept.py`, `red_check.py`, all four hooks and `plugin.json` itself (tamper with it and everything
unhooks) are unprotected. Extending `SELF_INTEGRITY_FILES` is a trust-model decision about which
files are anchors, not a packaging one, and this task's Out-of-scope forbids gate changes.

**Deliverable 2 (hat 3):** as proposed — the root `pyproject.toml` **stays** and becomes single-hat,
with a rewritten header and a **guard test** that FAILs if it grows `[build-system]`, a non-empty
`dependencies`, or any app-substrate name. The first dispatch is right that the acceptance test
("delete `src/` → `pytest .claude/tools/` green") passes today *by accident*; the deliverable is
turning that accident into an enforced rule. Rejecting `.claude/pyproject.toml` is accepted.

**Deliverable 3 (where a trial lives):** as proposed — **out of this repo entirely**, in T16's
sibling venue. Note honestly (its finding 9) that the rule is not fully honest until
`change/users-002` and `backup/users-002-prerebase` are accepted or abandoned; **state that in the
report, do not delete them.**

**Deliverable 4 (exclusion rule):** as proposed — **ship-by-location: the plugin root is `.claude/`,
a file ships iff it lives under it.** The meta layer's `test_*.py` + `fixtures/` therefore ship
(~250 KB, accepted: it lets a consumer re-verify the enforcement scripts, and excluding them would
separate the tests from the code they test). `.claude/settings.json` ships but is inert for a
consumer.

Also: the manifest must carry an `author` field — `claude plugin validate --strict` fails without it.

---

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
3. **the meta layer's own test environment** — `pytest` for the 300+ tests under `.claude/tools/`,
   which test `gate.py`/`accept.py`/`red_check.py` themselves and ship nowhere.

**A concrete symptom, measured (T12b finding 10):** this repo's `.venv` still carries the entire
`users/002` substrate — `fastapi`, `sqlalchemy`, `asyncpg`, `alembic`, `testcontainers` — even though
`markdown-specs`' `pyproject.toml` declares none of it (the deps commit lives on the change branch).
That leftover is the *only* reason a `users/002` worktree can be gated from here at all. So the
verification everyone has been running silently depends on stale environment state that no file
records. Any layout this task proposes has to say where a trial's runtime deps live, or the next
`uv sync` quietly breaks the ability to gate a change branch.

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
- **`notes/20_consumer_trial_venue.md` finding F-02 — measured, and it is this task's sharpest
  input.** In a consumer project the enforcement infrastructure is protected by **`check_self_hash`
  alone**. `bash_guard` anchors to the *consumer's* root and resolves targets, so a write to the
  plugin's own `.claude/tools|hooks|settings.json` — by absolute path **or** through the `.claude`
  symlink — is **ALLOWED**; and `gate.py`'s `integrity.protected-trees` diffs those same paths inside
  the consumer tree, where they do not exist, so it PASSes **vacuously**. Of the protected set, only
  `pyproject.toml` is genuinely covered in a consumer. Any layout this task proposes must say what
  protects the plugin's own files once it ships, and `self-hash` needs the plugin directory to be a
  git repository — which an installed plugin may not be.
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
  `gate.py`/`accept.py` riding along in this task would be invisible in the diff noise. **The one
  sanctioned exception is D1** — the namespace-tolerant `agent_type` comparison in the two hooks,
  which restores existing guarantees rather than adding a new check, and lands in its own commit.
- ~~**Escalate before writing code** with a proposed layout~~ — **discharged.** The layout and all
  five decisions are settled above. Do **not** escalate again on shape. Escalate only if a specific
  decision cannot be implemented as written, and say which and why.
- Do NOT extend `SELF_INTEGRITY_FILES` (that is T18) and do NOT delete `change/users-002` or
  `backup/users-002-prerebase` (report the caveat instead).
