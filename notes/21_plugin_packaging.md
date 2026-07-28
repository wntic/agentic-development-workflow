# 21 — Packaging: what ships, how it is released, and where a trial lives (T15)

The workflow is a **Claude Code plugin named `adw`**, and **this repository is a marketplace that
ships it like any other plugin** — everything `adw` owns lives in `plugins/adw/`. This note is the
packaging reference: the layout, the platform facts it rests on (all measured on Claude Code
2.1.220 — none of it inferred from documentation), the release procedure, and the questions
answered in prose rather than in code.

Companion notes: `notes/20_consumer_trial_venue.md` (the symlink venue) and
`tasks/T18-what-protects-the-installed-plugin.md` (what the installed artifact protects).

**History, so the reasoning is not re-derived.** The layout took two wrong turns before this one,
both forced by the same thing — `check_self_hash` verifying the enforcement layer against *git*
HEAD, which an installed plugin has no `.git` for:

1. until 2026-07-27 the plugin root was `.claude/` and a release was a `git subtree split` into a
   second repository. Satisfied the anchor; demanded one repo per plugin.
2. then the repository root became the *installation* root (whole-repo source → `.git` reaches the
   cache). Satisfied the anchor with one repo; scattered `agents/`, `hooks/`, `tools/` across a
   root shared with the marketplace, and — since no custom path loads an agent (§5c) — needed
   symlinks there.
3. now: **the anchor stopped requiring git** (§5b). `plugins/adw/` is an ordinary plugin directory
   with an ordinary relative source, and the repository root carries nothing of the plugin.

## 1. The layout: a marketplace, and one ordinary plugin inside it

```
.claude-plugin/marketplace.json <- the catalog: one entry per plugin, ordinary relative sources
.claude/settings.json           <- the hook wiring for a CHECKED-OUT load ($CLAUDE_PROJECT_DIR)
.claude/{skills,commands,agents,hooks}  <- SYMLINKS into plugins/adw/, so that load finds components
plugins/adw/                    <- THE PLUGIN. Its root; every component at its DEFAULT location
  .claude-plugin/plugin.json    <-   its manifest: no `version` (§5a), no component paths
  .claude-plugin/anchors.json   <-   the anchor digest E-02 falls back to without git (§5b)
  bin/adw.py                    <-   the one invocation form for the tools
  hooks/hooks.json              <-   the hook wiring for an INSTALLED load (${CLAUDE_PLUGIN_ROOT})
  hooks/*.py  commands/ agents/ skills/ templates/ tools/
plugins/<next>/                 <- a future plugin: the same shape, one more catalog entry
notes/ tasks/ *.md              <- the dev record; NOT shipped (a relative source copies
                                   plugins/adw/ and nothing else)
```

The plugin root and the installation root are the same directory again — `plugins/adw/` — which is
what lets the manifest declare nothing and the repository root own nothing. `${CLAUDE_PLUGIN_ROOT}`
expands to it; the checked-out load says so too (`env.CLAUDE_PLUGIN_ROOT = "plugins/adw"` in
`.claude/settings.json`).

### The ship rule — by location

**A file ships iff it lives under `plugins/adw/`.** No list, no manifest of exclusions: a new file
lands on the right side by where its author puts it. `tasks/`, `notes/`, both design docs,
`CLAUDE.md`, `PRINCIPLES.md`, `pyproject.toml` and any trial app are dev artifacts a consumer never
receives — which is why they keep the bare command names while everything under `plugins/adw/`
refers to commands as `/adw:<name>`.

Consequences, accepted deliberately:

- the meta layer's own `test_*.py` and `fixtures/` **do** ship (~250 KB). Accepted: it lets a
  consumer re-verify the enforcement scripts, and excluding them would separate the tests from the
  code they test.
- `commands/build-task.md` and `agents/v3-builder.md` ship too, though they are dev-only (they
  drive *this* build-out and read `tasks/`, which a consumer does not have). Same for
  `commands/orient.md`, which reads the design canon. They are inert-but-visible in a consumer;
  the alternative (a hand-maintained exclusion list) is the thing the ship rule exists to avoid.

What the enforcement layer carries for it: `gate.py`'s `protected_paths()` and `bash_guard`'s
plugin-tree fragments are DERIVED from the plugin root rather than written as literals, because
`plugins/adw/tools` is a path only this repository has — in a consumer the plugin lives outside the
tree and contributes nothing. `bash_guard`'s fragments are additionally **root-anchored** (a
leading slash), since its fragments match at any depth and `tools/` at depth belongs to whoever's
project it is. Both directions measured (A5), including the pre-fix failure: with the old
`.claude/tools` literal, `rm tools/gate.py` in the moved layout was **ALLOWED**.

---

## 2. Measured platform facts (Claude Code 2.1.220)

| Question | Answer, measured |
|---|---|
| Does `${CLAUDE_PLUGIN_ROOT}` expand inside `commands/*.md`? | **Yes** — substituted into the text before the Bash tool sees it. Same inside `agents/*.md`. |
| `$CLAUDE_PLUGIN_ROOT` (no braces)? | **No** — reaches the shell unexpanded and is empty there. |
| `${CLAUDE_PLUGIN_ROOT:-fallback}`? | **Not** substituted — bash then takes the fallback. So a `:-` default form is silently wrong when installed. Do not use one. |
| Is `CLAUDE_PLUGIN_ROOT` in the Bash tool's environment? | **No.** It is in a **hook's** environment (together with `CLAUDE_PROJECT_DIR`). |
| Does `env` in `settings.json` reach the Bash tool? | **Yes**, verbatim — with **no** variable expansion inside the value (`$CLAUDE_PROJECT_DIR/.claude` stays literal), and `CLAUDE_PROJECT_DIR` is not in that shell either. Hence the dev value is the relative `plugins/adw`. |
| What `agent_type` does a plugin-shipped agent report? | **`<plugin>:<agent>`** — e.g. `probeplug:probe-agent`, so `adw:implementer` here. On PreToolUse *and* SubagentStop. This is the whole reason D1 exists. |
| Can a plugin ship hooks in `settings.json`? | **No** — a plugin's `settings.json` honours only `agent` / `subagentStatusLine`. Hooks must be in `hooks/hooks.json`. |
| Does a bare `/spec` resolve in a consumer? | **No** — `Unknown command`. Only `/adw:spec` resolves. |
| `uv run <abs path outside the project>/x.py`? | Runs under the **project's** venv with the project as cwd — so the tools keep seeing the app's code (hat 2) wherever the plugin lives. |

Two consequences worth stating out loud:

1. **Do not enable both loads at once.** With the workflow checked out *and* installed as a plugin,
   every hook is wired twice and **fires twice**. This repo loads via project config only.
2. **`${CLAUDE_PLUGIN_ROOT}` is a session fact, not a shell fact.** A human at a plain terminal has
   no such variable: the human-facing form is `uv run plugins/adw/bin/adw.py gate` (which is what
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
- checked out → nothing expands it, and the shell does, from
  `env.CLAUDE_PLUGIN_ROOT = "plugins/adw"` in `.claude/settings.json`. That is not a workaround
  dressed as configuration: the plugin IS that directory, here as much as in a consumer's cache.
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

## 5. Release

```bash
git push origin main            # the whole procedure
```

The repository a consumer adds as a marketplace is the repository that carries the plugin, so
publishing is a push. Consumer side:

```
claude plugin marketplace add wntic/agentic-development-workflow
claude plugin install adw@wntic-adw
/reload-plugins
```

**Superseded twice, both recorded above:** a release used to be `git subtree split --prefix=.claude`
into a second repository, and then (briefly) a whole-repo source with the assets at the repository
root. Both were the shape `check_self_hash`'s git requirement forced; §5b removed the requirement.

The release check is two validations, because the two manifests live in different directories:

```bash
claude plugin validate .              # the catalog
claude plugin validate plugins/adw    # the plugin and its skills; read the warnings, see §5a
uv run plugins/adw/bin/adw.py anchors # the digest must be current — §5b
```

### 5a. The catalog, and versioning by commit SHA (2026-07-27)

```json
{ "name": "wntic-adw", "owner": { "name": "…" },
  "plugins": [ { "name": "adw", "source": "./plugins/adw" } ] }
```

An ordinary relative source, like every other plugin here. **`version` is gone from
`plugin.json`**: version resolution is `plugin.json` → marketplace entry → the source's commit SHA,
and a version *string* pins the plugin, so pushing commits leaves installed copies stale while
`/plugin update` answers *"already at the latest version"*. Bump-on-release is a rule with nothing
enforcing it and a silent failure (S4), so the workflow versions by commit SHA — the cache
directory is then the short SHA (`…/adw/0a3c831dbd1b`). Cost, accepted: `claude plugin validate
plugins/adw --strict` fails on the lone *"No version specified"* warning, so that check is read for
its warnings rather than its exit code.

Auto-update is **off by default for third-party marketplaces** (only Anthropic's are on), so each
machine needs `/plugin` → *Marketplaces* → *Enable auto-update* once, or a periodic
`/plugin marketplace update wntic-adw && /plugin update adw`. Updates land after session start with
a random delay of up to 10 minutes and prompt for `/reload-plugins`.

One layout fact worth keeping even though it no longer binds: **a catalog next to `plugin.json`
shadows the plugin's own validation.** Given a directory holding both manifests, `claude plugin
validate` validates the *marketplace* one and reports nothing about the plugin, with a green exit
code (measured). While the plugin root was the repository root that colocation was forced and the
release check had to validate a marketplace-less copy; now the two are in different directories and
the two commands above each see their own half. Pinned by
`test_both_manifests_validate_separately_because_they_no_longer_share_a_directory`.

### 5b. E-02's second anchor: the shipped digest (2026-07-27)

An installed plugin is a content copy with no `.git` — measured, in every source form that copies
rather than clones:

| plugin `source` form | cache copy holds |
|---|---|
| `"./plugins/adw"` (relative path) | no `.git` |
| `"./"` (the marketplace root itself) | no `.git` — and the source dir *had* one |
| `git-subdir` | no `.git` |
| `{"source":"url"\|"github", …}` | `.git`, `.in_use` — a real clone |

For a long time that read as "the source must be a whole repository", and the layout was bent
around it twice. It was the wrong conclusion: what E-02 needs is a *content* anchor, and git was
merely the hash store that happened to be there. `plugins/adw/.claude-plugin/anchors.json` — sha256
per anchored file, written by `adw.py anchors --write` at release — is the second anchor, so
`check_self_hash` now has two modes and **names the one it used** in the verdict:

- inside a git checkout (this repo) → verify against HEAD, unchanged, strongest;
- otherwise (every install) → verify against the digest.

What it is worth, so nobody over-reads it. It catches what the git anchor catches: an edited tool
or hook — the agent that patched the checker instead of the code, the hand-fix to an installed copy
that then diverges. That matters because **nothing else notices**: `bash_guard` is anchored to the
CONSUMER's root and deliberately does not fire on a write outside it (T06e), so
`~/.claude/plugins/cache/.../tools/gate.py` is writable by any agent with a shell. What it is not:
a defence against someone who understands it — editing a tool and its digest line defeats it,
exactly as editing a tool and committing defeats the git anchor (`notes/20` F-02). Two steps either
way; the digest simply needs no `.git`, which is what lets `plugins/adw/` be an ordinary directory.

Fail-closed at every turn, each pinned by a test: a missing digest, an unreadable one, a foreign
schema, an empty anchor map, a file the digest does not list, a listed file that is gone, and a
stale digest in the repo (the last is a dev-repo guard, so a release cannot forget to regenerate).

Also measured, and the reason no *third* mode was attempted: an installed marketplace's clone under
`plugins/marketplaces/<name>/` **is** a git checkout, but a **shallow** one
(`rev-parse --is-shallow-repository` → `true`, one commit). It advances on every marketplace refresh
and cannot vouch for the commit a plugin was installed at — the same reason T19 rejected comparing
against a release tag.

### 5c. Where the assets may live — kept because it constrains any FUTURE layout (2026-07-27)

Nothing here binds the current layout (every component sits at its default location). It is kept
because it is expensive to re-measure and it is what makes a nested-assets layout unattractive:
measured by installing a probe plugin whose assets sat in `plugins/p1/` and reading
`claude plugin details`,

| component | custom path in `marketplace.json` | custom path in `plugin.json` | root symlink into the nested tree |
|---|---|---|---|
| `skills` | **loads** | **loads** | not needed |
| `commands` | **loads** | **loads** | not needed |
| `hooks` | validates, loads **nothing** | **loads** | **loads** (default home) |
| `agents` | validates (file form only), loads **nothing** | loads **nothing** | **loads** |

Read it as: **if a plugin's assets are ever not at its own root, its agents cannot follow.** A
**directory** value in `agents` fails validation outright (`plugins.0.agents: Invalid input`) and,
in `plugin.json`, breaks the plugin's load; a **file** value validates and then loads nothing. The
only mechanism that works is an `agents/` at the installation root — a relative symlink into the
nested tree does the job, since the install preserves a symlink resolving inside the plugin's own
directory (an absolute one, or one escaping the plugin, is skipped for security).

So the middle layout needed two symlinks at a shared root, plus a manifest naming the other paths,
plus (because `plugin.json` and the catalog then sat ABOVE the plugin root, out of reach of a
plugin-root-relative anchor glob) a separate mechanism to anchor the files that decide which
components are wired. All three are gone with the assets back at the plugin's own root; what
remains of that episode is this table and the rehearsal in §5d.

### 5d. The install rehearsals (2026-07-26 → 2026-07-27)

Each layout was installed for real before it was believed, from a clone through a rehearsal
catalog (`file://` plugin source; the catalog's `name` bumped so it cannot squat the real one).
`file://` is accepted as a *plugin* source and **rejected as a marketplace** source, which is why
the marketplace-add half can only be rehearsed by path.

**Current layout — `plugins/adw/`, relative source, digest anchor.**

1. Installed at `~/.claude/plugins/cache/adw-plain-rehearsal/adw/71b6c1e4e64c`. The cache holds
   `plugins/adw/`'s content and **nothing else** — no `notes/`, no `tasks/`, no `.git` — which is
   the ship rule visible on disk.
2. `claude plugin details adw` → **Skills (21)** (14 skills + 7 commands), **Agents (4)**,
   **Hooks (3)** events covering all four scripts. Every one from its default location: no
   symlinks, no declared paths.
3. The gate from that copy:
   `[PASS] integrity.self-hash — all 13 enforcement anchor(s) match .claude-plugin/anchors.json
   (E-02; no git here, so the shipped digest is the anchor)`, GATE: GREEN.
4. Then the case the anchor exists for, run for real: `echo '# patched' >> <cache>/tools/gate.py`
   → `[FAIL] integrity.self-hash — tools/gate.py: content differs from the digest — the
   enforcement layer was modified`, GATE: RED.

**Whole-repo source, assets at the repository root (superseded).** Installed at
`~/.claude/plugins/cache/adw-rehearsal3/adw/0a3c831dbd1b` — version directory named by the commit
SHA, `.git` present, both root symlinks preserved as relative symlinks; `claude plugin details`
reported 21 skills (14 + 7 commands), **4 agents** through the `agents` symlink, and all four hook
scripts across three events; the gate from that copy: `[PASS] integrity.self-hash — all 14
enforcement anchor(s) match git HEAD`. This is the run that proved the symlink mechanism works —
and the layout it proved is the one §5b made unnecessary.

**`.claude/`-rooted plugin, split repo (superseded).** `git subtree split --prefix=.claude` → a
standalone clone → install → `[PASS] integrity.self-hash — all 13 enforcement anchor(s)`, GATE
GREEN. Established the shape the other two inherited.

Still not exercised, because it needs the published remote: `claude plugin marketplace add
wntic/agentic-development-workflow` over the network.

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
