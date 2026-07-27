# 21 — Packaging: what ships, how it is released, and where a trial lives (T15)

The workflow is a **Claude Code plugin named `adw`**, and its root is `.claude/` itself. This note
is the packaging reference: the ship rule, the platform facts the layout rests on (all measured on
Claude Code 2.1.220, 2026-07-26 — none of it is inferred from documentation), the release
procedure, and the two questions T15 had to answer in prose rather than in code.

Companion notes: `notes/20_consumer_trial_venue.md` (the symlink venue, which is deliberately *not*
the plugin) and `tasks/T18-what-protects-the-installed-plugin.md` (what the installed artifact
does *not* protect — the open trust question this layout exposes).

---

## 1. The layout: `.claude/` IS the plugin root, and nothing moved

```
.claude/                        <- the plugin root; `git subtree split --prefix=.claude` releases it
  .claude-plugin/plugin.json    <- the manifest (name `adw`)
  bin/adw.py                    <- the one invocation form for the tools
  hooks/hooks.json              <- the hook wiring for an INSTALLED load (${CLAUDE_PLUGIN_ROOT})
  hooks/*.py                    <- the four hooks
  settings.json                 <- the hook wiring for a CHECKED-OUT load ($CLAUDE_PROJECT_DIR);
                                   ships, but is inert for a consumer
  commands/ agents/ skills/ templates/ tools/
```

Not one file moved to make this work, and that is the point:

- `gate.py`'s `PROTECTED_PATHS` (`.claude/tools`, `.claude/hooks`, `.claude/settings.json`) and
  `bash_guard`'s `PROTECTED_FRAGMENTS` stay **literally true and unedited**;
- the new `hooks/hooks.json` lands inside an already-protected tree for free;
- `check_self_hash` needed no change *for the layout*: it computes `relative_to(<git toplevel>)` at
  runtime, so `tools/gate.py` in the split repo verifies exactly as `.claude/tools/gate.py` does here
  — and against the *published* commit, which is a strictly stronger anchor. **(T18, 2026-07-26: its
  file SET did change — the anchors are now plugin-root-relative globs covering every tool, hook and
  manifest, not gate.py + criteria_lint.py. The path arithmetic is untouched, and the split repo is
  still verified as-is.)**

### The ship rule — by location

**A file ships iff it lives under `.claude/`.** No list, no manifest of exclusions, no per-file
decision: a new file lands on the right side by where its author puts it.

Consequences, accepted deliberately:

- `tasks/`, `notes/`, `workflow_v3_spec.md`, `codegen_workflow_spec.md`, `CLAUDE.md`,
  `PRINCIPLES.md`, `README.md`, `pyproject.toml`, and any trial app in `src/`/`tests/` do **not**
  ship. A consumer reads nothing outside `.claude/` — which is why the `/adw:` rename sweep is
  scoped to `.claude/**` and every document outside it keeps the bare command names.
- the meta layer's own `test_*.py` and `fixtures/` **do** ship (~250 KB). Accepted: it lets a
  consumer re-verify the enforcement scripts, and excluding them would separate the tests from the
  code they test.
- `commands/build-task.md` and `agents/v3-builder.md` ship too, though they are dev-only (they
  drive *this* build-out and read `tasks/`, which a consumer does not have). Same for
  `commands/orient.md`, which reads the design canon. They are inert-but-visible in a consumer;
  the alternative (a hand-maintained exclusion list) is the thing the ship rule exists to avoid.

---

## 2. Measured platform facts (Claude Code 2.1.220)

| Question | Answer, measured |
|---|---|
| Does `${CLAUDE_PLUGIN_ROOT}` expand inside `commands/*.md`? | **Yes** — substituted into the text before the Bash tool sees it. Same inside `agents/*.md`. |
| `$CLAUDE_PLUGIN_ROOT` (no braces)? | **No** — reaches the shell unexpanded and is empty there. |
| `${CLAUDE_PLUGIN_ROOT:-fallback}`? | **Not** substituted — bash then takes the fallback. So a `:-` default form is silently wrong when installed. Do not use one. |
| Is `CLAUDE_PLUGIN_ROOT` in the Bash tool's environment? | **No.** It is in a **hook's** environment (together with `CLAUDE_PROJECT_DIR`). |
| Does `env` in `settings.json` reach the Bash tool? | **Yes**, verbatim — with **no** variable expansion inside the value (`$CLAUDE_PROJECT_DIR/.claude` stays literal), and `CLAUDE_PROJECT_DIR` is not in that shell either. Hence the dev value is the relative `.claude`. |
| What `agent_type` does a plugin-shipped agent report? | **`<plugin>:<agent>`** — e.g. `probeplug:probe-agent`, so `adw:implementer` here. On PreToolUse *and* SubagentStop. This is the whole reason D1 exists. |
| Can a plugin ship hooks in `settings.json`? | **No** — a plugin's `settings.json` honours only `agent` / `subagentStatusLine`. Hooks must be in `hooks/hooks.json`. |
| Does a bare `/spec` resolve in a consumer? | **No** — `Unknown command`. Only `/adw:spec` resolves. |
| `uv run <abs path outside the project>/x.py`? | Runs under the **project's** venv with the project as cwd — so the tools keep seeing the app's code (hat 2) wherever the plugin lives. |

Two consequences worth stating out loud:

1. **Do not enable both loads at once.** With the workflow checked out *and* installed as a plugin,
   every hook is wired twice and **fires twice**. This repo loads via project config only.
2. **`${CLAUDE_PLUGIN_ROOT}` is a session fact, not a shell fact.** A human at a plain terminal has
   no such variable: the human-facing form is `uv run .claude/bin/adw.py gate` (which is what
   `CLAUDE.md` documents). Inside a session either Claude Code (installed) or `settings.json`'s
   `env` (checked out) supplies it.

---

## 3. One invocation form for the tools

Every shipped file names a tool exactly one way:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" gate --change <context>/NNN
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" accept <context>/NNN
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" red-check --change <context>/NNN
uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" criteria-lint <path>
```

- installed → Claude Code expands the placeholder to the plugin's absolute path;
- checked out → nothing expands it, and the shell does, from `env.CLAUDE_PLUGIN_ROOT = ".claude"`
  in `.claude/settings.json`. That is not a workaround dressed as configuration: `.claude/` **is**
  the plugin root here, and the setting states it.
- `bin/adw.py` resolves the tools directory from `CLAUDE_PLUGIN_ROOT` first and from its own
  location (`__file__`) second, so it also works when the variable is unset, relative to a moved
  cwd, or plain wrong. It adds no flags and parses no tool arguments — `gate.py --help` is still
  the documentation.
- `uv run` is load-bearing: it puts the tool in the **project's** environment, which is where the
  toolchain must live (`sys.executable -m mypy|ruff|pytest` has to see the app's code).

Guarded by `.claude/tools/test_plugin_packaging.py`: no shipped Markdown may say
`uv run .claude/tools/<x>.py`, every sub-command must name an existing tool, and the dev half of
the form must be declared in `settings.json`.

---

## 4. Two homes for one hook wiring — and a guard, not a comment

Because a plugin cannot ship hooks in `settings.json`, the wiring exists twice:

| Home | Read when | Root |
|---|---|---|
| `.claude/settings.json` | the workflow is checked out (this repo, or a consumer with `.claude/` symlinked) | `$CLAUDE_PROJECT_DIR/.claude/hooks/` |
| `.claude/hooks/hooks.json` | the workflow is installed as a plugin | `${CLAUDE_PLUGIN_ROOT}/hooks/` |

The duplication is forced by the platform, so it is held by a test rather than by a plea (S4):
`test_the_two_wirings_are_one_substitution_apart` maps one form onto the other **string for
string** and fails on any other difference, and `test_every_hook_is_wired_in_both_homes` fails if a
hook is added to one home only. An entry in `settings.json` that names no script under the plugin's
`hooks/` (this repo wires a local graph-index hint) is project-local dev tooling and takes no part.

---

## 5. Release: whole-repo source, never a subdirectory source

```bash
# from the workflow repo, on the branch being released
git subtree split --prefix=.claude -b adw-plugin
git push <plugin-remote> adw-plugin:main
```

The split repo's root is `.claude/`'s content, so `.claude-plugin/plugin.json` lands exactly where
a plugin manifest belongs. Consumers then add it as a **`github` / `url` marketplace source (a
whole repository)**.

**Never a `git-subdir` source.** This is a correctness requirement, not taste, and both directions
are measured:

- whole-repo clone → the cache keeps `.git` → `integrity.self-hash` **PASS**;
- a subdirectory source is a *content copy* with no `.git` → `check_self_hash` returns
  *"the workflow's own files (…) are not inside a git repository — self-integrity is unverifiable"*
  (T18 reworded it to name the directory and the remedy) → **GATE: RED on every run in every
  consumer**. Reproduced verbatim on a `.git`-stripped copy of the split repo.

The obvious packaging choice is the broken one. It is also the failure with the worst shape: the
gate is red for a reason that has nothing to do with the consumer's code.

### The release rehearsal, end to end (2026-07-26)

1. `git subtree split --prefix=.claude` → clone the split branch into a standalone repo;
   `claude plugin validate --strict` → **passed**.
2. Fresh consumer: `uv init --package consumer`, `uv add --dev pytest ruff mypy`, `uv add pydantic`
   (the framework substrate of `conventions` block D covers this in a real app).
3. `CLAUDE_PLUGIN_ROOT=<split repo> uv run "<split repo>/bin/adw.py" gate` → **GATE: GREEN**, with
   `[PASS] integrity.self-hash` from the *installed* location (since T18 the line reads
   `all <n> enforcement anchor(s) match git HEAD (E-02)`).
4. A live `claude -p --plugin-dir <split repo>` session in that consumer: all 7 commands and 4
   agents resolve under the `adw:` namespace, `/adw:orient` runs, and `echo probe > tests/probe.py`
   is **denied** by `bash_guard` — fired through `hooks/hooks.json` from the installed location —
   with the file never created.

One wrinkle found in step 2: with only `pytest`/`ruff`/`mypy` declared, `toolchain.mypy` FAILs with
`Error importing plugin "pydantic.mypy": No module named 'pydantic'`. `conventions` block D always
declares `pydantic` for a real app, so this bites only a minimal project — but the gate's
toolchain preflight (T12b) checks that mypy/ruff/pytest *exist*, not that mypy's pinned **plugins**
are importable, so the message a bare project gets is a config error rather than a sentence.

---

## 6. Where a trialled change lives

**Outside this repository.** A trial runs in a packaging-faithful consumer project — the venue of
`notes/20_consumer_trial_venue.md` (`~/Projects/adw-consumer-probe`, `.claude/` symlinked) or, for
questions about the *installed* artifact, a fresh project with the split plugin loaded.

Why not at this repo's root, which is where `platform/001`, `health/001` and `users/002` ran:

- plugin root == project root there, so **no consumer-facing branch of any script executes** —
  which is how T12b's A4 hole survived unnoticed for as long as it did;
- the trial's runtime deps would land in the meta layer's `pyproject.toml`, coupling
  `pytest .claude/tools/` to a trial app being present (see §7);
- `src/` becomes transient in a repo whose own suite must not depend on it.

**Honest caveat, unresolved as of 2026-07-26:** the rule is not yet fully true. `change/users-002`
and `backup/users-002-prerebase` still exist in this repo and are neither accepted nor abandoned;
this repo's `.venv` still carries their substrate, and that leftover is the only reason a
`users/002` worktree can be gated from here at all. Nothing was deleted — the branches are
somebody's decision, not a builder's — but until they are resolved, "trials live elsewhere"
describes the intent, not the whole tree.

---

## 7. Hat 3: the meta layer's own environment

The root `pyproject.toml` wore three hats. It now wears one — the environment that runs the ~390
tests under `.claude/tools/` — and the other two live where they belong: the consumer's toolchain
in the *consumer's* `pyproject.toml` (`conventions` block D), and a trial app's substrate in the
trial's own project (§6).

The acceptance test is blunt: **delete `src/` and `pytest .claude/tools/` must still pass.** It did
before T15 — but only thanks to a `.venv` still holding the `users/002` substrate, which no file
recorded. Measured in a venv holding *only* the declared set, in a tree with no `src/`:

| declared set | result |
|---|---|
| pytest, ruff, mypy | **30 failures** — `gate.py`'s pinned mypy config declares `plugins = pydantic.mypy`, so every fixture gate run needs pydantic importable |
| + pydantic | **1 failure** — a `red_check` fixture reproduces the `health/001` lint-dirty conftest verbatim, `import httpx` included, and pytest must be able to collect it |
| + httpx | **392 passed** |

Both are now declared with the reason inline, and the guard is an **allowlist** (`META_ENV` in
`test_plugin_packaging.py`) rather than a blacklist of app names: a new dependency has to come
through the test, which is where "meta layer's, or a trial app's?" gets asked. `[build-system]`, a
non-empty `dependencies`, `[project.scripts]` and the unambiguous app-substrate names stay
forbidden outright.

---

## 8. What T15 did **not** answer

- **What protects the plugin's own files once installed** — almost nothing. `bash_guard` anchors to
  the consumer root, so a write to the plugin's `tools/`/`hooks/`/`plugin.json` resolves *outside*
  it and is allowed (by design, T06e); `integrity.protected-trees` diffs paths that do not exist in
  the consumer tree and passes **vacuously**. All that remains is `check_self_hash`, covering
  `gate.py` + `criteria_lint.py` alone. Verified live against the installed plugin. That is
  **T18** — a trust-model decision about which files are anchors, not a packaging one.
  **ANSWERED 2026-07-26 (T18):** `check_self_hash` now anchors the whole enforcement layer —
  `tools/*.py`, `hooks/*.py|json`, `bin/*.py`, `.claude-plugin/*.json`, `settings.json` (12 files
  when T18 landed, 13 since `tools/drift.py` — T17), as globs so a new tool or hook is covered by
  construction, which is exactly what happened when the next tool arrived. The other two protections are
  unchanged and still blind in a consumer; what closes the chain is that `accept.py` re-runs the gate
  in-process, so **nothing merges while an anchor differs from HEAD**. The anchor set, the two hooks
  that have *no* post-hoc backstop (`subagent_stop`, `session_stop`) and the local-`HEAD` limit are
  written up in `notes/20_consumer_trial_venue.md` F-02.
- **The namespace is stripped, not validated.** Both hooks read the role as
  `agent_type.rsplit(":", 1)[-1]`, so a foreign plugin's `other:test-author` is read as this
  workflow's test-author. The widening only ever grants a role its *own* tree and the gate
  backstops it (S8), but it is pinned as deliberate rather than left to be discovered.
- **The skills' frontmatter had never parsed.** Nine of fourteen `SKILL.md` files carried an
  unquoted `description:` whose text contained `": "`, which YAML reads as a nested mapping;
  `claude plugin validate --strict` reports the runtime consequence — *"at runtime this skill loads
  with empty metadata (all frontmatter fields silently dropped)"*. So auto-invocation by
  `description`/`when_to_use` never worked for them, here as much as in a consumer. Fixed by
  quoting (no wording changed). `test_skill_catalog.py` greps bodies by content signature and
  never parses frontmatter, which is why this survived three audit rounds — a frontmatter-parse
  guard belongs with the catalog tests, and there is none.
