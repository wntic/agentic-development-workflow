#!/usr/bin/env python3
"""adw.py — the one invocation form for the workflow's tools (T15/D4).

Every shipped file (commands, agents) names a tool exactly once and identically, whether the
workflow is INSTALLED as a plugin or loaded from a project's own `.claude/`:

    uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" gate --change <context>/NNN

Why that single form works in both places (measured on Claude Code 2.1.220):

  * installed — Claude Code expands `${CLAUDE_PLUGIN_ROOT}` in a command/agent file's text
    before the Bash tool ever sees it, to the plugin's absolute directory. (`$CLAUDE_PLUGIN_ROOT`
    without braces is NOT expanded, and no `CLAUDE_PLUGIN_*` variable exists in the Bash tool's
    environment, so a `${VAR:-default}` form would silently take the default — do not use one.)
  * checked out (the workflow's own repo, or a consumer with `.claude/` symlinked) — no plugin
    is loaded, nothing expands the placeholder, and the shell expands it from `env` in
    `.claude/settings.json`, which sets `CLAUDE_PLUGIN_ROOT=.claude`. That is a statement of
    fact, not a workaround: `.claude/` IS the plugin root here — the plugin is this directory.

`uv run` is what keeps the toolchain in the PROJECT's environment (hat 2): the tools shell out
to `sys.executable -m mypy|ruff|pytest`, which must be the interpreter that can see the app's
code. `uv run <abs path outside the project>.py` still runs under the project's venv with the
project as cwd — measured — so the tools do not care where the plugin lives.

The tools directory is resolved from `CLAUDE_PLUGIN_ROOT` first and from this file's own
location second, so the shim works when the variable is unset, wrong, or relative to a cwd
that has moved. Both routes name the same directory in every sane layout; the fallback is what
makes the shim usable by absolute path from anywhere.

This is a locator, not a wrapper: it adds no flags, parses no tool arguments, and passes
argv through untouched, so `gate.py --help` remains the documentation for `adw.py gate`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DESCRIBE = "adw.py: locates and runs one of the workflow's tools (gate | accept | red-check | criteria-lint | drift)."

# Sub-command -> the tool it runs. The names are the vocabulary the commands/agents use; the
# file names stay the tools' own (gate.py's identity is load-bearing for its self-hash, E-02).
TOOLS = {
    "gate": "gate.py",
    "accept": "accept.py",
    "red-check": "red_check.py",
    "criteria-lint": "criteria_lint.py",
    "drift": "drift.py",
}


def tools_dir(argv0: str | None = None) -> Path:
    """Where the workflow's tools live: `$CLAUDE_PLUGIN_ROOT/tools`, else `<this file>/../tools`.

    The environment wins only when it actually names a tools directory — a stale, relative, or
    foreign value must not defeat the fallback, which is always right for a shim invoked at its
    real path.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        candidate = Path(env).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if (candidate / "tools").is_dir():
            return (candidate / "tools").resolve()
    return (Path(argv0 or __file__).resolve().parent.parent / "tools").resolve()


def usage() -> str:
    return (
        "usage: adw.py <" + " | ".join(TOOLS) + "> [tool arguments...]\n"
        "       run it through the project's environment: "
        'uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" gate --change <context>/NNN\n'
    )


def main(argv: list[str]) -> int:
    if argv[:1] == ["--describe"]:
        print(DESCRIBE)
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(usage(), end="")
        return 0 if argv else 2
    name, rest = argv[0], argv[1:]
    if name not in TOOLS:
        print(f"adw.py: unknown tool {name!r}\n{usage()}", end="", file=sys.stderr)
        return 2
    tool = tools_dir() / TOOLS[name]
    if not tool.is_file():
        print(
            f"adw.py: {tool} not found — the workflow's tools directory could not be located.\n"
            "Set CLAUDE_PLUGIN_ROOT to the plugin directory, or run the shim by its real path.\n",
            end="",
            file=sys.stderr,
        )
        return 2
    # sys.executable, not `python3`: under `uv run` this is the PROJECT's interpreter, which is
    # the whole point of hat 2 — the tools then find mypy/ruff/pytest and the app's own code.
    return subprocess.run([sys.executable, str(tool), *rest]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
