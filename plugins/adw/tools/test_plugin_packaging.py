"""Guards for the shipped artifact's shape (workflow v3, T15; relaid by the marketplace move).

**This repository is at once the marketplace and the `adw` plugin.** The plugin root is the
repository root — `skills/`, `commands/`, `agents/`, `tools/`, `hooks/`, `bin/`, `templates/` sit
there, the catalog and the manifest share `.claude-plugin/`, and `.claude/` is left holding only
what a *project* needs: `settings.json` plus symlinks for the checked-out load. Everything in the
repo therefore ships, and the reason for that shape is one measured fact: a plugin installed from
a SUBDIRECTORY source is a content copy with no `.git`, so `integrity.self-hash` cannot verify
E-02 and the gate is RED in every consumer. A whole-repo source clones, `.git` included — and the
only way to be a whole repo is to be one (notes/21 §5a).

What this suite pins:

  1. **the manifest** — `.claude-plugin/plugin.json` exists and carries the metadata
     `claude plugin validate` demands (an absent `author` alone fails `--strict`);
  2. **the catalog** — `.claude-plugin/marketplace.json` names this repo as `adw`'s source, as a
     whole-repo form, and nothing pins a `version` (else pushed commits never reach a machine);
  3. **two homes for one hook wiring** — a plugin cannot ship hooks in `settings.json` (the
     runtime honours only `agent` / `subagentStatusLine` there), so the wiring is written twice:
     `.claude/settings.json` for a checked-out load (`$CLAUDE_PROJECT_DIR`) and `hooks/hooks.json`
     for an installed one (`${CLAUDE_PLUGIN_ROOT}`). The duplication is forced by the platform, so
     it gets a guard rather than a comment (S4): the test maps one form onto the other and FAILs on
     any drift, including a new hook wired in only one file;
  4. **one invocation form** — every instructing file reaches a tool through `bin/adw.py`, never
     through a raw `tools/...` path (which resolves to the CONSUMER's tree once installed).

Plus the meta layer's own environment (hat 3): the root `pyproject.toml` is the workflow's test
environment and nothing else. It must never grow the trial app's substrate, because that would
make `pytest tools/` depend on a trial app being present in the tree.
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = TOOLS_DIR.parent  # plugins/adw — where the workflow's own files live
REPO_ROOT = TOOLS_DIR.parents[2]  # the repository: the marketplace AND the installation root
HOOKS_DIR = PLUGIN_ROOT / "hooks"
# Both manifests belong to the INSTALLATION root, which is the repository root — a manifest
# inside `plugins/adw/` would not be read at all (and would be a second source of truth).
MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
# The hook wiring of the CHECKED-OUT load lives in project configuration, not in the plugin's own
# `settings.json` (which the runtime would read for `agent` keys only).
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
HOOKS_JSON = HOOKS_DIR / "hooks.json"
SHIM = PLUGIN_ROOT / "bin" / "adw.py"

PLUGIN_NAME = "adw"

# The directories the platform discovers at the plugin root, and the one directory that stays
# project configuration. `.claude/` may hold symlinks to the first group (the checked-out load
# reads components from there) but never a second copy of them.
COMPONENT_DIRS = ("skills", "commands", "agents", "hooks", "templates", "tools", "bin")
# The components the platform loads from the INSTALLATION root only, reached by a relative
# symlink there. Measured: `agents` loads from no custom path at all (a directory value even
# fails the plugin), and a root symlink into the nested tree does load; `hooks/hooks.json` is
# the default home, and the checked-out wiring of THIS session reached it that way.
ROOT_SYMLINKS = ("agents", "hooks")

# The two roots, and the substitution that turns one wiring into the other.
PLUGIN_FORM = "${CLAUDE_PLUGIN_ROOT}/plugins/adw/hooks/"
PROJECT_FORM = "$CLAUDE_PROJECT_DIR/plugins/adw/hooks/"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _marketplace() -> dict:
    """The release catalog, or skip — a consumer's installed copy is not the marketplace."""
    if not (MARKETPLACE.is_file() and (REPO_ROOT / "workflow_v3_spec.md").is_file()):
        pytest.skip("not the workflow's own repo — the marketplace catalog belongs to that repo alone")
    return json.loads(MARKETPLACE.read_text(encoding="utf-8"))


def _entry() -> dict:
    """The catalog's entry for this plugin."""
    entries = [p for p in _marketplace()["plugins"] if p.get("name") == PLUGIN_NAME]
    assert len(entries) == 1, _marketplace()["plugins"]
    return entries[0]


def _hook_scripts() -> set[str]:
    """Every hook the plugin ships — the set both wirings must cover exactly."""
    return {p.name for p in HOOKS_DIR.glob("*.py")}


# =======================================================================================
# The manifest
# =======================================================================================


def test_manifest_exists_and_names_the_plugin() -> None:
    data = _manifest()
    assert data["name"] == PLUGIN_NAME, "the namespace every /adw:<command> reference depends on"
    assert data["description"].strip()


def test_manifest_carries_an_author() -> None:
    # `claude plugin validate --strict` fails on a missing author, and a release is tagged
    # off the manifest — so this is not decoration.
    author = _manifest()["author"]
    assert isinstance(author, dict) and author.get("name"), author


def test_the_manifest_declares_where_the_components_are() -> None:
    """The one place that says the assets are NOT at the installation root.

    The opposite of what this suite demanded before the nesting: with `plugins/adw/` holding the
    assets, discovery-by-location would find nothing, so the manifest's paths are the ONLY source
    of truth rather than a second one (C7 is satisfied by there being exactly one).

    `agents` is deliberately absent, and that is measured, not an oversight: on Claude Code
    2.1.220 an agent loads from the plugin root's `agents/` and from no custom path at all —
    a directory value in `agents` fails the plugin outright, a file value validates and then
    loads nothing. The root symlink below is the mechanism that stands in for it.
    """
    manifest = _manifest()
    for key in ("skills", "commands"):
        declared = manifest[key]
        paths = [declared] if isinstance(declared, str) else declared
        for path in paths:
            assert path.startswith("./plugins/adw/"), f"{key}: {path} does not point into the plugin's tree"
            assert (REPO_ROOT / path).exists(), f"{key}: {path} does not exist"
    for key in ("agents", "hooks"):
        assert key not in manifest, f"{key} is reached through the root symlink, not a declared path"


# =======================================================================================
# The layout: assets under plugins/adw/, the installation root holds only what must be there
# =======================================================================================


@pytest.mark.parametrize("name", COMPONENT_DIRS)
def test_every_component_directory_sits_in_the_plugins_own_tree(name: str) -> None:
    assert (PLUGIN_ROOT / name).is_dir(), f"{name}/ must live in plugins/adw/"


@pytest.mark.parametrize("name", ROOT_SYMLINKS)
def test_the_platform_forced_symlinks_exist_and_point_into_the_plugin(name: str) -> None:
    """The narrow exception to "assets live under plugins/adw/", and why it is narrow.

    A relative symlink whose target resolves inside the plugin's own directory is preserved by
    the install (measured: it survives the copy into `~/.claude/plugins/cache/…` and the agent
    behind it loads). An absolute one, or one escaping the plugin, is skipped for security — so
    the symlink must stay relative.
    """
    link = REPO_ROOT / name
    assert link.is_symlink(), f"{name} must be a symlink at the installation root"
    assert not Path(os.readlink(link)).is_absolute(), f"{name} must be RELATIVE or the install drops it"
    assert link.resolve() == (PLUGIN_ROOT / name).resolve(), f"{name} points outside plugins/adw/"


def test_the_installation_root_carries_no_stray_component_directory() -> None:
    # Anything else with a component's name at the installation root would be a second copy the
    # platform might load instead of the one under plugins/adw/ — and hooks wired twice fire twice.
    for name in COMPONENT_DIRS:
        entry = REPO_ROOT / name
        if name in ROOT_SYMLINKS:
            continue
        assert not entry.exists(), f"{name} at the installation root shadows plugins/adw/{name}"


def test_dot_claude_holds_project_configuration_and_never_a_second_copy() -> None:
    """`.claude/` may point AT the components; it must not contain a fork of them.

    The checked-out load reads components from `.claude/`, so symlinks live there — and a real
    directory there would be a second copy of a skill or command, drifting from the first the
    moment either is edited. `settings.json` is the one real file: the hook wiring of that load.
    """
    dot = REPO_ROOT / ".claude"
    assert (dot / "settings.json").is_file(), "the checked-out load's hook wiring"
    for entry in sorted(dot.iterdir()):
        if entry.name in {"settings.json", "settings.local.json"} or entry.name.startswith("."):
            continue
        assert entry.is_symlink(), f".claude/{entry.name} must be a symlink to the real directory, not a copy"
        assert entry.resolve() == (PLUGIN_ROOT / entry.name).resolve(), f".claude/{entry.name} points elsewhere"


# =======================================================================================
# The marketplace catalog
# =======================================================================================

# The two `source` forms whose install is a git CLONE into the plugin cache, so the cache copy
# keeps its `.git` — measured 2026-07-27, see the whole-repo rule below.
WHOLE_REPO_SOURCES = frozenset({"github", "url"})


def test_marketplace_catalog_exists_and_lists_this_plugin() -> None:
    data = _marketplace()
    # Both names show up in `plugin@marketplace`, so they must not be the same word.
    assert data["name"] and data["name"] != PLUGIN_NAME, data["name"]
    assert data["owner"]["name"].strip()
    assert _entry()["source"], "an entry without a source cannot be installed"


def test_the_catalog_names_this_very_repository_as_the_plugins_source() -> None:
    """The self-reference this layout rests on: the marketplace repo IS the plugin repo.

    Claude Code fetches the catalog and the plugin independently — one clone under
    `plugins/marketplaces/<name>/`, one under `plugins/cache/<name>/<plugin>/<sha>/` — so a
    repository may legally be both. What that buys is the only whole-repo source available
    without a second repository, and therefore a `.git` in the cache (see the test below).
    What it costs is that a wrong URL here installs somebody else's code under this name, so
    the URL is checked against the actual remote rather than trusted.
    """
    source = _entry()["source"]
    url = source.get("url") or source.get("repo", "")
    rc = subprocess.run(["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"], capture_output=True, text=True)
    if rc.returncode != 0:
        pytest.skip("no origin remote to compare the catalog against")

    def _slug(text: str) -> str:  # owner/repo, however the URL spells it
        return text.strip().removesuffix(".git").replace("git@github.com:", "").replace("https://github.com/", "")

    assert _slug(url) == _slug(rc.stdout), f"catalog names {_slug(url)!r}, origin is {_slug(rc.stdout)!r}"


def test_the_catalog_shares_the_plugin_root_and_that_costs_the_plugins_own_validation() -> None:
    """A catalog beside `plugin.json` shadows the plugin half of `claude plugin validate`.

    Measured on 2026-07-27: given a directory holding both manifests, the CLI validates the
    MARKETPLACE one and reports nothing about the plugin — silently, with a green exit code. In
    this layout that colocation is forced (the catalog's only legal home is
    `<marketplace root>/.claude-plugin/`, and the marketplace root is the plugin root), so the
    release check validates a marketplace-less COPY of the tree to see the plugin half
    (notes/21 §5a). The class of defect that half once caught — unparseable `SKILL.md`
    frontmatter — has its own guard since T13b, which is why the cost is affordable rather than
    silent: `test_skill_format.py::test_every_skill_frontmatter_parses_as_yaml`.
    """
    assert MARKETPLACE.parent == MANIFEST.parent, "both manifests share `.claude-plugin/` in this layout"
    guard = TOOLS_DIR / "test_skill_format.py"
    assert "def test_every_skill_frontmatter_parses_as_yaml" in guard.read_text(encoding="utf-8"), (
        "the frontmatter guard that replaces the shadowed validation is gone — restore it or "
        "stop colocating the catalog"
    )


def test_marketplace_fetches_the_plugin_as_a_whole_repository() -> None:
    """The load-bearing one: a subdirectory source makes the gate RED in every consumer.

    Measured on Claude Code 2.1.220 (2026-07-27) by installing the same plugin three ways and
    listing the cache directory:

      | source form                          | cache copy holds        |
      |--------------------------------------|-------------------------|
      | `"./sub"` (relative path)            | no `.git`               |
      | `"./"`    (the marketplace root)     | no `.git`               |
      | `{"source": "url", ...}` whole repo  | `.git` (a real clone)   |

    Without `.git`, `check_self_hash` reports the enforcement layer as *not inside a git
    repository* and E-02 cannot be verified — GATE: RED on every run, for a reason that has
    nothing to do with the consumer's code. `git-subdir` is the same content copy (notes/21 §5).
    So the obvious packaging choice (marketplace repo with the plugin in a subdirectory) is the
    broken one, and this test is what stands between a refactor and that failure.
    """
    source = _entry()["source"]
    assert isinstance(source, dict), (
        f"a string source is a relative path — its cache copy has no .git and the gate goes RED: {source!r}"
    )
    assert source["source"] in WHOLE_REPO_SOURCES, (
        f"{source['source']!r} does not clone the whole repository: {source!r}"
    )
    assert "path" not in source, "a subdirectory of a repo is a content copy, not a clone"


def test_nothing_pins_a_version_so_every_commit_reaches_every_machine() -> None:
    # Version resolution: `plugin.json` wins over the marketplace entry, and the git commit SHA
    # is the fallback when BOTH are unset. A `version` string therefore pins the plugin — pushing
    # commits without bumping it leaves installed copies stale and `/plugin update` answers
    # "already at the latest version". Bumping-on-release is a rule with nothing enforcing it
    # (S4), and its failure is silent, so the workflow versions by commit SHA instead.
    # Cost, accepted and measured: `claude plugin validate <plugin> --strict` now fails on the
    # "No version specified" warning, so the release check is the non-strict form, read for its
    # warnings (notes/21 §5). The frontmatter class of defect that --strict once caught has its
    # own guard in the catalog tests since T13b.
    assert "version" not in _manifest(), "a pinned version silently strands every installed copy"
    assert "version" not in _entry(), "same pin, one file over"


# =======================================================================================
# Two homes for one hook wiring (D3)
# =======================================================================================


def _wiring(path: Path) -> dict[tuple[str, str, str], str]:
    """{(event, matcher, script): command} for every entry naming one of the plugin's hooks.

    An entry that names no script under the plugin's `hooks/` is project-local dev tooling
    (this repo wires a graph-index hint into `settings.json`); it is not part of the shipped
    plugin and takes no part in the equivalence.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = _hook_scripts()
    out: dict[tuple[str, str, str], str] = {}
    for event, groups in data.get("hooks", {}).items():
        for group in groups:
            for entry in group.get("hooks", []):
                command = entry.get("command", "")
                named = [s for s in scripts if f"/hooks/{s}" in command]
                if not named:
                    continue
                assert len(named) == 1, command
                out[(event, group.get("matcher", ""), named[0])] = command
    return out


def test_every_hook_is_wired_in_both_homes() -> None:
    settings, plugin = _wiring(SETTINGS), _wiring(HOOKS_JSON)
    assert set(settings) == set(plugin), "a hook wired in only one home fires in only one layout"
    wired = {script for _, _, script in settings}
    assert wired == _hook_scripts(), "every hook script must be wired (or deleted), in both homes"


def test_the_two_wirings_are_one_substitution_apart() -> None:
    # The whole content of the duplication: the same interpreter, the same script, the same
    # event/matcher — only the root differs. Anything else is drift, and drift here means the
    # installed and the checked-out workflow enforce different things.
    settings, plugin = _wiring(SETTINGS), _wiring(HOOKS_JSON)
    for key, plugin_command in plugin.items():
        assert PLUGIN_FORM in plugin_command, (key, plugin_command)
        assert plugin_command.replace(PLUGIN_FORM, PROJECT_FORM) == settings[key], (key, plugin_command)


def test_settings_hooks_use_the_project_root_only() -> None:
    for key, command in _wiring(SETTINGS).items():
        assert PROJECT_FORM in command, (key, command)
        assert "CLAUDE_PLUGIN_ROOT" not in command, (key, command)


# =======================================================================================
# One invocation form (D4)
# =======================================================================================

# Every Markdown that INSTRUCTS someone — commands, agents, skills, templates. Scoped to those
# directories rather than to the plugin root, which is now the whole repository: `notes/` and
# `tasks/` are a dev record, and a note may quote whatever invocation it is describing. The
# fixtures under tools/ are test data (a recorded change spec, quoted verbatim), not instructions.
INSTRUCTING_DIRS = ("commands", "agents", "skills", "templates")
SHIPPED_MARKDOWN = sorted(
    p for d in INSTRUCTING_DIRS for p in (PLUGIN_ROOT / d).rglob("*.md") if "fixtures" not in p.parts
)
# A raw tools path in an instructing file is doubly wrong once the plugin root is a repository
# root: `tools/gate.py` does not merely fail to exist in a consumer, it names a directory in the
# CONSUMER's tree — so the agent is sent at somebody else's file rather than at nothing.
RAW_TOOL_INVOCATION = re.compile(r"uv run\s+\S*(?:\.claude/)?tools/\w+\.py")


def test_there_are_instructing_files_to_check() -> None:
    # `parametrize` over an empty list is a green no-op — the vacuity rule (notes/19).
    assert len(SHIPPED_MARKDOWN) > 10, SHIPPED_MARKDOWN


@pytest.mark.parametrize("doc", SHIPPED_MARKDOWN, ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_no_shipped_file_invokes_a_tool_by_its_checked_out_path(doc: Path) -> None:
    # The one form that works in both layouts is the shim; a file that spells the path out sends
    # the agent at a file that is not there — or, worse, at the consumer's own `tools/`.
    hits = RAW_TOOL_INVOCATION.findall(doc.read_text(encoding="utf-8"))
    assert not hits, f"{doc}: invoke tools through bin/adw.py, not {hits}"


def test_the_dev_half_of_the_invocation_form_is_declared() -> None:
    # Checked out, nothing expands `${CLAUDE_PLUGIN_ROOT}` in a command file, so the shell must:
    # settings.json states the fact that the repository root is the plugin root here.
    env = json.loads(SETTINGS.read_text(encoding="utf-8")).get("env", {})
    assert env.get("CLAUDE_PLUGIN_ROOT") == ".", env


# =======================================================================================
# The command namespace (D2)
# =======================================================================================

COMMANDS = sorted(PLUGIN_ROOT.glob("commands/*.md"))


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.stem)
def test_every_command_states_its_namespaced_name(command: Path) -> None:
    # In a consumer, a bare `/implement` is "Unknown command" — only `/adw:implement` resolves.
    # Every command therefore states both forms, so a reader typing one is never stuck; and a
    # command naming ANOTHER command uses the namespaced form throughout its body.
    text = command.read_text(encoding="utf-8")
    assert f"/{PLUGIN_NAME}:{command.stem}" in text, f"{command}: state the /{PLUGIN_NAME}: form of its own name"


def _shim():  # the shim module, imported for its pure helpers
    import importlib.util

    spec = importlib.util.spec_from_file_location("adw_shim", SHIM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_tool_the_shim_offers_exists() -> None:
    mod = _shim()
    for name, filename in mod.TOOLS.items():
        assert (PLUGIN_ROOT / "tools" / filename).is_file(), name


def test_shim_resolves_the_tools_dir_without_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # The added requirement of D4: uninstalled, the shim finds the tools from its own location.
    mod = _shim()
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert mod.tools_dir() == (PLUGIN_ROOT / "tools").resolve()


def test_shim_prefers_a_plugin_root_that_holds_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _shim()
    plugin = tmp_path / "adw"
    (plugin / "tools").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    assert mod.tools_dir() == (plugin / "tools").resolve()

    # ... and never lets an unusable value defeat the fallback
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "nowhere"))
    assert mod.tools_dir() == (PLUGIN_ROOT / "tools").resolve()


def test_shim_runs_a_tool_and_returns_its_exit_code() -> None:
    ok = subprocess.run([sys.executable, str(SHIM), "criteria-lint"], capture_output=True, text=True)
    assert ok.returncode != 0  # criteria_lint needs an argument — the tool's own complaint
    assert "usage" in (ok.stdout + ok.stderr).lower()

    unknown = subprocess.run([sys.executable, str(SHIM), "nope"], capture_output=True, text=True)
    assert unknown.returncode == 2
    assert "unknown tool" in unknown.stderr


# =======================================================================================
# Hat 3 — the meta layer's own environment (the root pyproject.toml)
# =======================================================================================


# The meta layer's environment, exactly — measured, not assumed: in a venv holding only these,
# in a tree with no `src/`, the whole suite passes; drop `pydantic` and 30 tests fail (gate.py's
# pinned mypy config declares `plugins = pydantic.mypy`), drop `httpx` and 1 does (a red_check
# fixture's conftest imports it and pytest must collect it). Before T15 both were undeclared and
# satisfied only by a leftover trial-app venv — the acceptance test passed by luck.
# An allowlist rather than a blacklist: adding a dependency has to come through here, which is
# where the "is this the meta layer's, or a trial app's?" question gets asked.
META_ENV = frozenset({"pytest", "ruff", "mypy", "pydantic", "httpx", "pre-commit"})

# Names of the app substrate a trial change installs. None of them may reach the meta layer's
# environment: `pytest tools/` must pass in a tree with no `src/` at all.
SUBSTRATE = (
    "fastapi",
    "starlette",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "psycopg",
    "aiosqlite",
    "dependency-injector",
    "testcontainers",
    "qdrant-client",
    "openai",
    "structlog",
)


def _meta_pyproject() -> dict:
    """The workflow repo's own pyproject.toml, or skip.

    Identified by the design canon sitting next to it — everywhere else (a consumer with the
    plugin installed, the split plugin repo) the file either belongs to somebody's app or does
    not exist, and this guard has nothing to say about it.
    """
    pyproject = REPO_ROOT / "pyproject.toml"
    canon = REPO_ROOT / "workflow_v3_spec.md"
    if not (pyproject.is_file() and canon.is_file()):
        pytest.skip("not the workflow's own repo — the root pyproject.toml here is not the meta layer's")
    with pyproject.open("rb") as fh:
        return tomllib.load(fh)


def _declared_dependencies(data: dict) -> list[str]:
    project = data.get("project", {})
    deps = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        deps += list(extra)
    for group in data.get("dependency-groups", {}).values():
        deps += [g for g in group if isinstance(g, str)]
    return deps


def test_meta_pyproject_declares_no_runtime_dependencies() -> None:
    data = _meta_pyproject()
    assert data["project"]["dependencies"] == [], "the meta layer runs on the stdlib + its test toolchain"


def test_meta_pyproject_is_not_a_package() -> None:
    # A `[build-system]` here would make `uv` hard-fail every command whenever the trial app's
    # `src/<pkg>/` is absent — which is its normal state (T12b). The app that IS installable is
    # the consumer's, declared in its own pyproject (`conventions` block D).
    data = _meta_pyproject()
    assert "build-system" not in data, "the workflow repo is not a distributable package"
    assert "scripts" not in data.get("project", {})


def test_meta_pyproject_declares_exactly_the_meta_environment() -> None:
    declared = {
        re.split(r"[<>=!~\[]", d, maxsplit=1)[0].strip().lower() for d in _declared_dependencies(_meta_pyproject())
    }
    assert declared == set(META_ENV), f"declared {sorted(declared)}, expected {sorted(META_ENV)}"


@pytest.mark.parametrize("name", SUBSTRATE)
def test_meta_pyproject_carries_no_app_substrate(name: str) -> None:
    # The coupling this forbids is concrete: declare the trial app's deps here and
    # `pytest tools/` starts needing a trial app to exist.
    declared = [d for d in _declared_dependencies(_meta_pyproject()) if d.lower().startswith(name)]
    assert not declared, f"{name} belongs to a trial app, not to the meta layer's test environment"


def test_meta_layer_tests_import_nothing_from_the_app() -> None:
    # The blunt acceptance test of T15 is "delete src/ and `pytest tools/` still passes".
    # This is its static half: no test here reaches into the app's package.
    for test in sorted(TOOLS_DIR.glob("test_*.py")):
        text = test.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import src", "from src")), f"{test}: {stripped}"
