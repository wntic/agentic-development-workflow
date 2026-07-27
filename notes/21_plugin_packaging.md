# 21 — Packaging: what ships, how it is released, and where a trial lives (T15)

The workflow is a **Claude Code plugin named `adw`**, and **this repository is the marketplace that
ships it** — `adw`'s assets live in `plugins/adw/`, while the repository root is its *installation*
root (§5c). This note is the packaging
reference: the layout, the platform facts it rests on (all measured on Claude Code 2.1.220 — none of
it inferred from documentation), the release procedure, and the questions answered in prose rather
than in code.

Companion notes: `notes/20_consumer_trial_venue.md` (the symlink venue, which is deliberately *not*
the plugin) and `tasks/T18-what-protects-the-installed-plugin.md` (what the installed artifact
does *not* protect — the open trust question this layout exposes).

**History, so the reasoning is not re-derived:** until 2026-07-27 the plugin root was `.claude/`
and a release was a `git subtree split --prefix=.claude` into a second repository. That satisfied
the self-hash anchor (§5) but demanded one repo per plugin. §5a records the measurements that made
the root the *installation* root; §5c records the ones that then allowed the assets to move back
into `plugins/adw/` without weakening the anchor.

---

## 1. The layout: the repo is the MARKETPLACE, every plugin's assets live in `plugins/<name>/`

```
.claude-plugin/marketplace.json <- the catalog: `adw` from THIS repo as a whole-repo source
.claude-plugin/plugin.json      <- adw's manifest. Belongs to the INSTALLATION root (= the repo
                                   root) and NAMES the asset paths; no `version` — §5a
agents -> plugins/adw/agents    <- platform-forced symlinks (§5c): an agent loads from the
hooks  -> plugins/adw/hooks        installation root's `agents/` and from NO custom path, and
                                   `hooks/hooks.json` is the default home. Relative, or the
                                   install drops them
.claude/settings.json           <- the hook wiring for a CHECKED-OUT load ($CLAUDE_PROJECT_DIR)
.claude/{skills,commands,agents,hooks}  <- SYMLINKS to the real dirs, so that load finds components
plugins/adw/                    <- THE PLUGIN: every asset of the workflow
  bin/adw.py                    <-   the one invocation form for the tools
  hooks/hooks.json              <-   the hook wiring for an INSTALLED load (${CLAUDE_PLUGIN_ROOT})
  hooks/*.py                    <-   the four hooks
  commands/ agents/ skills/ templates/ tools/
plugins/<next>/                 <- a future plugin: its own .claude-plugin/plugin.json and a
                                   RELATIVE source; it runs no gate, so no self-hash to satisfy
```

Two roots, and keeping them apart is what the rest of this note is about:

| | what it is | how code finds it |
|---|---|---|
| **installation root** | what `${CLAUDE_PLUGIN_ROOT}` expands to; where the platform looks for a manifest, `agents/` and `hooks/hooks.json` | the repository root |
| **plugin root** | where the workflow's own files live | `plugin_root()` = the parent of `tools/` = `plugins/adw` |

What the move cost, precisely — three things that were literally true before and are derived now:

- `gate.py`'s `PROTECTED_PATHS` split in two: the project's paths stay literals
  (`.claude/settings.json`, `pyproject.toml`), and the plugin's own trees are computed by
  `protected_paths()` from the plugin root, contributing nothing when the plugin lives outside the
  tree. Naming them `tools`/`hooks` as literals would protect a **consumer's** unrelated `tools/`
  and fail its changes for touching its own code;
- `bash_guard`'s `PROTECTED_FRAGMENTS` likewise, plus a grammar addition: a leading slash marks a
  **root-anchored** fragment, because these fragments match at any depth and `tools/` at depth
  belongs to whoever's project it is. Measured in both directions (A5), including the pre-fix
  failure: with the old `.claude/tools` fragment, `rm tools/gate.py` in the moved layout was
  **ALLOWED** — the whole enforcement tree had silently stopped being guarded;
- `check_self_hash` needed no path arithmetic change (it computes `relative_to(<git toplevel>)` at
  runtime), but the three files that decide WHICH components are wired now sit above the plugin
  root, so `ABOVE_ROOT_ANCHOR_GLOBS` anchors them from the git toplevel instead (§5c).

### The ship rule — everything ships, and the roles differ

**Every file in the repository ships**, because the plugin is fetched as a whole repository (§5a).
The by-location rule is gone; what remains is a rule by ROLE: a file that *instructs* an agent
(`plugins/adw/{commands,agents,skills,templates}/`) must use the `/adw:<name>` command form, while
`tasks/`, `notes/`, the design docs and `CLAUDE.md` are a dev record that ships physically and is
never loaded (a plugin-root `CLAUDE.md` is not read as project context) and keeps the bare names.

Consequences, accepted deliberately:

- `tasks/`, `notes/`, both design docs, `CLAUDE.md`, `PRINCIPLES.md`, `README.md`, `pyproject.toml`
  and any trial app in `src/`/`tests/` now land in the plugin cache too. They are **inert** — the
  platform loads components from `skills/`, `commands/`, `agents/`, `hooks/hooks.json` and nowhere
  else — so the cost is disk and a consumer's puzzlement, not behaviour. The `/adw:` sweep is
  therefore scoped to the *instructing* directories rather than to a path prefix, and
  `test_no_shipped_file_invokes_a_tool_by_its_checked_out_path` is scoped the same way.
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
| Does `env` in `settings.json` reach the Bash tool? | **Yes**, verbatim — with **no** variable expansion inside the value (`$CLAUDE_PROJECT_DIR/.claude` stays literal), and `CLAUDE_PROJECT_DIR` is not in that shell either. Hence the dev value is the relative `.` (the installation root). |
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
- checked out → nothing expands it, and the shell does, from `env.CLAUDE_PLUGIN_ROOT = "."`
  in `.claude/settings.json`. That is not a workaround dressed as configuration: the repository
  root **is** the plugin root here, and the setting states it.
- `bin/adw.py` resolves the tools directory from `CLAUDE_PLUGIN_ROOT` first and from its own
  location (`__file__`) second, so it also works when the variable is unset, relative to a moved
  cwd, or plain wrong. It adds no flags and parses no tool arguments — `gate.py --help` is still
  the documentation.
- `uv run` is load-bearing: it puts the tool in the **project's** environment, which is where the
  toolchain must live (`sys.executable -m mypy|ruff|pytest` has to see the app's code).

Guarded by `tools/test_plugin_packaging.py`: no INSTRUCTING Markdown may name a tool by a raw
`tools/<x>.py` path (which, with the plugin root at a repository root, would resolve inside the
*consumer's* tree), every sub-command must name an existing tool, and the dev half of the form
must be declared in `.claude/settings.json`.

---

## 4. Two homes for one hook wiring — and a guard, not a comment

Because a plugin cannot ship hooks in `settings.json`, the wiring exists twice:

| Home | Read when | Root |
|---|---|---|
| `.claude/settings.json` | the workflow is checked out (this repo) | `$CLAUDE_PROJECT_DIR/hooks/` |
| `hooks/hooks.json` | the workflow is installed as a plugin | `${CLAUDE_PLUGIN_ROOT}/hooks/` |

The duplication is forced by the platform, so it is held by a test rather than by a plea (S4):
`test_the_two_wirings_are_one_substitution_apart` maps one form onto the other **string for
string** and fails on any other difference, and `test_every_hook_is_wired_in_both_homes` fails if a
hook is added to one home only. An entry in `settings.json` that names no script under the plugin's
`hooks/` (this repo wires a local graph-index hint) is project-local dev tooling and takes no part.

---

## 5. Release: whole-repo source, never a subdirectory source

```bash
# the whole release, since the plugin root became the repository root
git push origin main
```

That is the entire procedure: the repository a consumer adds as a marketplace is the repository
Claude Code clones as the plugin, so publishing is a push. **Superseded (2026-07-27):** a release
used to be `git subtree split --prefix=.claude -b adw-plugin` into a second repository — the price
of a `.claude/` plugin root, and the thing §5a's layout removes.

**Never a `git-subdir` source.** This is a correctness requirement, not taste, and both directions
are measured:

- whole-repo clone → the cache keeps `.git` → `integrity.self-hash` **PASS**;
- a subdirectory source is a *content copy* with no `.git` → `check_self_hash` returns
  *"the workflow's own files (…) are not inside a git repository — self-integrity is unverifiable"*
  (T18 reworded it to name the directory and the remedy) → **GATE: RED on every run in every
  consumer**. Reproduced verbatim on a `.git`-stripped copy of the split repo.

The obvious packaging choice is the broken one. It is also the failure with the worst shape: the
gate is red for a reason that has nothing to do with the consumer's code.

### 5a. The marketplace catalog (2026-07-27)

**This repository is the marketplace AND the `adw` plugin.** The catalog and the manifest share
`.claude-plugin/`, and the catalog names *this very repository* as `adw`'s source — a whole-repo
form, which is what puts a `.git` in the plugin cache:

```json
{ "name": "wntic-adw", "owner": { "name": "…" },
  "plugins": [ { "name": "adw", "source": { "source": "url",
    "url": "https://github.com/wntic/agentic-development-workflow.git" } } ] }
```

The self-reference is legal because the catalog and the plugin are fetched independently: one clone
under `plugins/marketplaces/<name>/`, one under `plugins/cache/<name>/<plugin>/<sha>/`. Future
plugins live in `plugins/<name>/` with an ordinary relative source — **they** have no self-hash to
satisfy, so the subdirectory restriction below binds `adw` alone.

Consumer side: `claude plugin marketplace add wntic/agentic-development-workflow` →
`claude plugin install adw@wntic-adw` → `/reload-plugins`.

Four measured facts decided this, all on Claude Code 2.1.220. First, a probe plugin installed three
ways, then the cache directory listed:

| plugin `source` form | cache copy holds | consequence |
|---|---|---|
| `"./sub"` (relative path) | no `.git` | `integrity.self-hash` unverifiable → **GATE RED** |
| `"./"` (the marketplace root itself) | no `.git` | same — and note the source dir *had* a `.git` |
| `{"source":"url"\|"github", …}` | `.git`, `.in_use` | a real clone → **self-hash PASS** |

So §5's rule extends further than `git-subdir`: **every relative-path source is a content copy**,
including `./` pointing at the marketplace root. A plugin that must be a git checkout therefore has
to *be* a whole repository — which, with one repo, means being the repository root.

Second, the anchor that would have rescued a subdirectory layout does not exist: an installed
marketplace's clone under `plugins/marketplaces/<name>/` **is** a git checkout, but a **shallow**
one (`rev-parse --is-shallow-repository` → `true`, one commit of history). It advances on every
marketplace refresh and cannot vouch for the commit a plugin was installed at — the same reason T19
rejected comparing against a release tag (`notes/20` F-02).

Third: **a catalog next to `plugin.json` shadows the plugin's own validation.** Given a directory
holding both manifests, `claude plugin validate` validates the *marketplace* and reports nothing
about the plugin, with a green exit code. Here that colocation is forced (the catalog's only legal
home is `<marketplace root>/.claude-plugin/`), so the release check validates a marketplace-less
copy to see the plugin half:

```bash
claude plugin validate .                                    # the catalog
T=$(mktemp -d); cp -R . "$T/plug"; rm "$T/plug/.claude-plugin/marketplace.json"
claude plugin validate "$T/plug"                             # the plugin + its skills
```

The class of defect that half once caught — unparseable `SKILL.md` frontmatter (§8) — has had its
own guard since T13b (`test_skill_format.py::test_every_skill_frontmatter_parses_as_yaml`), which is
why the cost is affordable rather than silent. Pinned by
`test_the_catalog_shares_the_plugin_root_and_that_costs_the_plugins_own_validation`.

Fourth: **`version` is gone from `plugin.json`.** Version resolution is `plugin.json` → marketplace
entry → the source's commit SHA; a version *string* pins the plugin, so pushing commits leaves
installed copies stale and `/plugin update` answers *"already at the latest version"*. Bump-on-release
is a rule with nothing enforcing it and a silent failure (S4), so the workflow versions by commit SHA
— the cache directory is then the short SHA (`…/adw/0e50b724513a`). Cost, accepted: the plugin half
of `claude plugin validate --strict` fails on the lone *"No version specified"* warning, so that
check is read for its warnings rather than its exit code.

Auto-update is **off by default for third-party marketplaces** (only Anthropic's are on), so each
machine needs `/plugin` → *Marketplaces* → *Enable auto-update* once, or a periodic
`/plugin marketplace update wntic-adw && /plugin update adw`. Updates land after session start with
a random delay of up to 10 minutes and prompt for `/reload-plugins`.

### 5c. Where the assets may live, and the two the platform pins down (2026-07-27)

The layout above exists because "one repo, plugins in `plugins/<name>/`" and "the plugin must be a
git checkout" pull in opposite directions. What resolved it: the **installation root** (whole repo,
so `.git` reaches the cache) and the **plugin root** (`plugins/adw/`) are allowed to differ, with the
manifest naming the paths. What each component supports was measured by installing a probe plugin
whose assets sat in `plugins/p1/` and reading `claude plugin details`:

| component | custom path in `marketplace.json` | custom path in `plugin.json` | root symlink into the nested tree |
|---|---|---|---|
| `skills` | **loads** | **loads** | not needed |
| `commands` | **loads** | **loads** | not needed |
| `hooks` | validates, loads **nothing** | **loads** | **loads** (default home) |
| `agents` | validates (file form only), loads **nothing** | loads **nothing** | **loads** |

Two consequences, and both are pinned by tests rather than by this table:

1. `agents` has no working custom path at all. A **directory** value fails validation outright
   (`plugins.0.agents: Invalid input`) and, in `plugin.json`, breaks the plugin's load; a **file**
   value validates and then loads nothing. So `agents/` must be at the installation root, and the
   layout reaches it with a relative symlink — which the install preserves (the runtime documents
   that a symlink resolving inside the plugin's own directory is kept, and the probe confirmed the
   agent behind it loads). `hooks` joins it for symmetry: `hooks/hooks.json` is its default home, so
   the manifest needs no key for it either.
2. An absolute symlink, or one escaping the plugin, is **skipped** by the install for security. The
   two root symlinks are therefore relative, and a test asserts it.

The gate needed one change for the split roots: `plugin.json`, `marketplace.json` and
`.claude/settings.json` all live at the installation root, i.e. ABOVE the plugin root, where a
plugin-root-relative anchor glob cannot see them — and they are exactly the files that decide which
components are wired at all. `ABOVE_ROOT_ANCHOR_GLOBS` + `_anchors_above_the_plugin_root()` anchor
them from the git toplevel, skipping any that turn out to be *inside* the plugin root so the count
the verdict prints cannot be inflated (in the `.claude/`-rooted layout every gate fixture builds,
`.claude/settings.json` is inside it).

### The marketplace rehearsal, end to end (2026-07-27)

Rehearsed first on the pre-move layout (`git subtree split --prefix=.claude` → a standalone clone →
a rehearsal catalog whose plugin source is `file://<that clone>`), which established the shape:

1. `claude plugin marketplace add <catalog dir>` → `claude plugin install adw@adw-rehearsal` →
   installed at `~/.claude/plugins/cache/adw-rehearsal/adw/0e50b724513a`, **`.git` present**.
2. `CLAUDE_PLUGIN_ROOT=<that dir> uv run "<that dir>/bin/adw.py" gate` →
   **`[PASS] integrity.self-hash — all 13 enforcement anchor(s) match git HEAD (E-02)`**, GATE: GREEN.
3. `file://` is accepted as a **plugin** source and rejected as a **marketplace** source, which is
   why the marketplace-add half cannot be rehearsed locally against a git URL.

### 5b. The same rehearsal on the root layout (2026-07-27)

No `subtree split`: a clone of THIS repo *is* the plugin, and a rehearsal catalog points at it with
a `file://` `url` source (the catalog's own `name` bumped so it cannot squat the real one).

1. `claude plugin marketplace add <catalog dir>` → `claude plugin install adw@adw-rehearsal2` →
   installed at `~/.claude/plugins/cache/adw-rehearsal2/adw/c1410764d7e5` — the version directory is
   the **commit SHA**, and the copy holds **`.git`**. The whole repo is there, `notes/` and `tasks/`
   included, and the `.claude/` symlinks survived the copy as relative symlinks (which the runtime
   documents: a symlink resolving inside the plugin's own directory is preserved).
2. `CLAUDE_PLUGIN_ROOT=<cache dir> uv run "<cache dir>/bin/adw.py" gate` →
   **`[PASS] integrity.self-hash — all 14 enforcement anchor(s) match git HEAD (E-02)`**, GATE: GREEN.
3. The consumer-safety half, read off the INSTALLED gate: `protected_paths(<any tree>)` →
   `('.claude/settings.json', 'pyproject.toml')`. The plugin's own trees are absent, so a consumer's
   `tools/` is its own. From a checked-out gate the same call returns
   `(…, 'tools', 'hooks')` for this repo and the two-element form for a foreign tree — the
   derivation measured in both directions.
4. Both manifests validate: the catalog cleanly, the plugin half (marketplace-less copy) with two
   warnings — the accepted `version` one, and *"CLAUDE.md at the plugin root is not loaded as project
   context"*, which is the runtime confirming §1's claim about the dev record shipping inert.

Still not exercised, because it needs the published remote: `claude plugin marketplace add
wntic/agentic-development-workflow` over the network, and the `url` source resolving that repo for a
consumer. Local `file://` covers the plugin half only.

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
tests under `plugins/adw/tools/` — and the other two live where they belong: the consumer's toolchain
in the *consumer's* `pyproject.toml` (`conventions` block D), and a trial app's substrate in the
trial's own project (§6).

The acceptance test is blunt: **delete `src/` and `pytest plugins/adw/tools/` must still pass.** It did
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
