"""Guards for the shipped artifact's shape (workflow v3, T15).

The workflow ships as a Claude Code plugin whose root is `.claude/` itself — the ship rule is
**by location**: a file ships iff it lives under `.claude/`. Nothing moved when the plugin was
introduced, so `gate.py`'s `PROTECTED_PATHS` and `bash_guard`'s `PROTECTED_FRAGMENTS` stay
literally true, and this suite pins the three facts that layout makes fragile:

  1. **the manifest** — `.claude/.claude-plugin/plugin.json` exists and carries the metadata
     `claude plugin validate --strict` demands (an absent `author` alone fails it);
  2. **two homes for one hook wiring** — a plugin cannot ship hooks in `settings.json` (the
     runtime honours only `agent` / `subagentStatusLine` there), so the wiring is written twice:
     `.claude/settings.json` for a checked-out load (`$CLAUDE_PROJECT_DIR`) and
     `.claude/hooks/hooks.json` for an installed one (`${CLAUDE_PLUGIN_ROOT}`). The duplication
     is forced by the platform, so it gets a guard rather than a comment (S4): the test maps one
     form onto the other and FAILs on any drift, including a new hook wired in only one file;
  3. **one invocation form** — every shipped file reaches a tool through `bin/adw.py`, never
     through a `.claude/tools/...` path that does not exist in a consumer.

Plus the meta layer's own environment (hat 3): the root `pyproject.toml` is the workflow's test
environment and nothing else. It must never grow the trial app's substrate, because that would
make `pytest .claude/tools/` depend on a trial app being present in the tree.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = TOOLS_DIR.parent  # .claude/ IS the plugin root (T15, layout C)
HOOKS_DIR = PLUGIN_ROOT / "hooks"
MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
SETTINGS = PLUGIN_ROOT / "settings.json"
HOOKS_JSON = HOOKS_DIR / "hooks.json"
SHIM = PLUGIN_ROOT / "bin" / "adw.py"

PLUGIN_NAME = "adw"

# The two roots, and the substitution that turns one wiring into the other.
PLUGIN_FORM = "${CLAUDE_PLUGIN_ROOT}/hooks/"
PROJECT_FORM = "$CLAUDE_PROJECT_DIR/.claude/hooks/"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _hook_scripts() -> set[str]:
    """Every hook the plugin ships — the set both wirings must cover exactly."""
    return {p.name for p in HOOKS_DIR.glob("*.py")}


# =======================================================================================
# The manifest
# =======================================================================================


def test_manifest_exists_and_names_the_plugin() -> None:
    data = _manifest()
    assert data["name"] == PLUGIN_NAME, "the namespace every /adw:<command> reference depends on"
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"]), data["version"]
    assert data["description"].strip()


def test_manifest_carries_an_author() -> None:
    # `claude plugin validate --strict` fails on a missing author, and a release is tagged
    # off the manifest — so this is not decoration.
    author = _manifest()["author"]
    assert isinstance(author, dict) and author.get("name"), author


def test_manifest_declares_no_component_paths() -> None:
    # Components are auto-discovered from the plugin root (commands/, agents/, skills/,
    # hooks/hooks.json). Declaring them again would be a second source of truth for a layout
    # the directory itself states (C7) — and the first one to drift.
    for key in ("commands", "agents", "skills", "hooks"):
        assert key not in _manifest(), f"{key} is discovered by location, not declared"


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

# Every shipped Markdown that INSTRUCTS someone — commands, agents, skills, templates. The
# fixtures under tools/ are test data (a recorded change spec, quoted verbatim), not instructions.
SHIPPED_MARKDOWN = sorted(p for p in PLUGIN_ROOT.rglob("*.md") if "fixtures" not in p.parts)
RAW_TOOL_INVOCATION = re.compile(r"uv run\s+\S*\.claude/tools/")


@pytest.mark.parametrize("doc", SHIPPED_MARKDOWN, ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_no_shipped_file_invokes_a_tool_by_its_checked_out_path(doc: Path) -> None:
    # `.claude/tools/gate.py` does not exist in a consumer with the plugin installed. The one
    # form that works in both layouts is the shim; a file that spells the path out sends the
    # agent at a file that is not there.
    hits = RAW_TOOL_INVOCATION.findall(doc.read_text(encoding="utf-8"))
    assert not hits, f"{doc}: invoke tools through bin/adw.py, not {hits}"


def test_the_dev_half_of_the_invocation_form_is_declared() -> None:
    # Checked out, nothing expands `${CLAUDE_PLUGIN_ROOT}` in a command file, so the shell must:
    # settings.json states the fact that `.claude/` is the plugin root here.
    env = json.loads(SETTINGS.read_text(encoding="utf-8")).get("env", {})
    assert env.get("CLAUDE_PLUGIN_ROOT") == ".claude", env


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


def _shim():  # noqa: ANN202 — the shim module, imported for its pure helpers
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

REPO_ROOT = PLUGIN_ROOT.parent

# The meta layer's environment, exactly — measured, not assumed: in a venv holding only these,
# in a tree with no `src/`, the whole suite passes; drop `pydantic` and 30 tests fail (gate.py's
# pinned mypy config declares `plugins = pydantic.mypy`), drop `httpx` and 1 does (a red_check
# fixture's conftest imports it and pytest must collect it). Before T15 both were undeclared and
# satisfied only by a leftover trial-app venv — the acceptance test passed by luck.
# An allowlist rather than a blacklist: adding a dependency has to come through here, which is
# where the "is this the meta layer's, or a trial app's?" question gets asked.
META_ENV = frozenset({"pytest", "ruff", "mypy", "pydantic", "httpx", "pre-commit"})

# Names of the app substrate a trial change installs. None of them may reach the meta layer's
# environment: `pytest .claude/tools/` must pass in a tree with no `src/` at all.
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
    # `pytest .claude/tools/` starts needing a trial app to exist.
    declared = [d for d in _declared_dependencies(_meta_pyproject()) if d.lower().startswith(name)]
    assert not declared, f"{name} belongs to a trial app, not to the meta layer's test environment"


def test_meta_layer_tests_import_nothing_from_the_app() -> None:
    # The blunt acceptance test of T15 is "delete src/ and `pytest .claude/tools/` still passes".
    # This is its static half: no test here reaches into the app's package.
    for test in sorted(TOOLS_DIR.glob("test_*.py")):
        text = test.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import src", "from src")), f"{test}: {stripped}"
