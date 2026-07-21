#!/usr/bin/env python3
"""bootstrap.py — greenfield substrate + app shell, in a PRE-baseline commit (workflow v3).

Run as `/implement` **step 0.5** on a first change (when the framework substrate is absent),
BEFORE the test-author writes the red baseline. It is the fix for the greenfield-probe F2/F3
gap: the framework substrate (`pyproject.toml` deps) must already exist at baseline time
(pyproject is a gate-protected frozen tree, and the implementer is tool-blocked from it), yet
no role established it — v3 dropped the v2 scaffolder that owned bootstrap, and the §9-L
walkthrough wrongly reassigned bootstrap to the implementer.

So a deterministic step establishes, in its own commit BEFORE the red baseline:
  1. the conventions §D framework substrate in the root `pyproject.toml`;
  2. a minimal, BEHAVIORLESS, importable app shell — `create_app()` returns a bare FastAPI
     app with the DI container attached + the domain-error handler registered, and NO routes
     / behaviour (the implementer adds those on top, as behaviour, against the red tests);
  3. the package skeleton under `src/<pkg>/`, where `<pkg>` is the `pyproject.toml` `name`
     normalized `-`→`_` (single source of project identity — the human sets `name` as normal
     project setup; bootstrap only READS it. No `name` → a hard stop: declare identity first).

This keeps T09b's tests-only red baseline intact (bootstrap is a SEPARATE, earlier commit —
the baseline commit touches `tests/**` only) and keeps gate.py's frozen-pyproject integrity
check green (the substrate is pre-baseline and unchanged after). The test-author's greenfield
tests then import the shell and fail cleanly on missing behaviour — real red, not a
collection error.

This is a NARROW, deterministic first-change bootstrap — the substrate list is conventions
§D, the shell is the `restapi` bootstrap content. It is NOT a general per-component scaffolder
(that was the v2 mistake, PRINCIPLES D1): it emits no domain/application/route/store code.

Usage:
    bootstrap.py [tree] [--no-commit]

  tree         root of the change work tree (default: cwd). Its pyproject.toml supplies `name`.
  --no-commit  write the files but do not create the pre-baseline commit (tests / dry runs).

Exit codes: 0 done (or already present, a no-op); 2 a precondition could not be met (no
pyproject.toml, no `[project] name`) — a loud stop, never a silent skip.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True

# --------------------------------------------------------------------------------------
# The substrate (conventions §D — names only, never versions; `uv lock` resolves pins).
# Only the ALWAYS-present substrate: the relational/multipart/auth-test deps are conditional
# on the graph and land with the change that introduces the store / form route / auth (§D).
# --------------------------------------------------------------------------------------

FRAMEWORK_SUBSTRATE: tuple[str, ...] = (
    "fastapi",
    "uvicorn[standard]",
    "pydantic",
    "pydantic-settings",
    "dependency-injector",
    "structlog",
)

DEV_SUBSTRATE: tuple[str, ...] = (
    "pytest",
    "pytest-asyncio",
    "ruff",
    "mypy",
    "testcontainers",
    "httpx",
)


class BootstrapError(Exception):
    """A precondition could not be met; carries the loud detail."""


# --------------------------------------------------------------------------------------
# Package-root name — derived from pyproject `name`, normalized `-`→`_` (RULING 2026-07-21).
# --------------------------------------------------------------------------------------


def package_name(tree: Path) -> str:
    pyproject = tree / "pyproject.toml"
    if not pyproject.is_file():
        raise BootstrapError(
            f"no pyproject.toml at {pyproject} — declare the project identity ([project] name) "
            "before bootstrap; the package root src/<pkg>/ is derived from it."
        )
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BootstrapError(f"pyproject.toml does not parse: {exc}") from None
    name = data.get("project", {}).get("name")
    if not isinstance(name, str) or not name.strip():
        raise BootstrapError(
            "pyproject.toml has no [project] name — set it (the human declares project identity "
            "first); the package root src/<pkg>/ is name with '-' normalized to '_'."
        )
    return name.strip().replace("-", "_")


# --------------------------------------------------------------------------------------
# pyproject.toml — merge the substrate into [project] dependencies + [dependency-groups] dev.
# A surgical text edit (stdlib has no TOML writer): tomllib validates + reads the current
# arrays, then the array value is replaced in place (existing entries kept, substrate unioned).
# --------------------------------------------------------------------------------------


def _render_array(key: str, values: list[str]) -> str:
    if not values:
        return f"{key} = []"
    body = "".join(f'    "{v}",\n' for v in values)
    return f"{key} = [\n{body}]"


def _table_bounds(lines: list[str], table: str) -> tuple[int, int] | None:
    """Return [start, end) line indices of the body of `[table]` (header excluded), or None."""
    header = f"[{table}]"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        stripped = lines[j].lstrip()
        if stripped.startswith("[") and lines[j] == lines[j].lstrip():
            end = j
            break
    return start, end


def _find_array_span(lines: list[str], body_start: int, body_end: int, key: str) -> tuple[int, int] | None:
    """Line span [start, end) of `key = [ ... ]` (possibly multi-line) within a table body."""
    for i in range(body_start, body_end):
        stripped = lines[i].lstrip()
        if stripped.startswith(f"{key} =") or stripped.startswith(f"{key}="):
            # advance to the line whose running bracket balance returns to zero
            depth = 0
            for j in range(i, body_end):
                depth += lines[j].count("[") - lines[j].count("]")
                if depth <= 0:
                    return i, j + 1
            return i, body_end
    return None


def _merge(existing: list[str], additions: tuple[str, ...]) -> list[str]:
    merged = list(existing)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def render_pyproject(text: str, data: dict) -> str:
    lines = text.splitlines()

    # [project] dependencies
    existing_deps = list(data.get("project", {}).get("dependencies", []))
    deps = _merge(existing_deps, FRAMEWORK_SUBSTRATE)
    proj = _table_bounds(lines, "project")
    if proj is None:
        raise BootstrapError("pyproject.toml has no [project] table")
    span = _find_array_span(lines, proj[0], proj[1], "dependencies")
    new_deps_block = _render_array("dependencies", deps).splitlines()
    if span is not None:
        lines[span[0] : span[1]] = new_deps_block
    else:
        lines[proj[0] : proj[0]] = new_deps_block

    # [dependency-groups] dev
    existing_dev = list(data.get("dependency-groups", {}).get("dev", []))
    dev = _merge(existing_dev, DEV_SUBSTRATE)
    new_dev_block = _render_array("dev", dev).splitlines()
    grp = _table_bounds(lines, "dependency-groups")
    if grp is None:
        addition = ["", "[dependency-groups]", *new_dev_block]
        if lines and lines[-1].strip() != "":
            lines.append("")
            lines.extend(addition[1:])
        else:
            lines.extend(addition)
    else:
        span = _find_array_span(lines, grp[0], grp[1], "dev")
        if span is not None:
            lines[span[0] : span[1]] = new_dev_block
        else:
            lines[grp[0] : grp[0]] = new_dev_block

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def write_pyproject(tree: Path) -> None:
    pyproject = tree / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    pyproject.write_text(render_pyproject(text, data), encoding="utf-8")


# --------------------------------------------------------------------------------------
# The app shell + package skeleton (the `restapi` bootstrap content — public / auth-less,
# behaviorless: create_app() with the DI container + the DomainError handler, NO routes).
# --------------------------------------------------------------------------------------

_APP_ROOT_INIT = '__version__ = "0.1.0"\n'

_CONTAINERS = """\
from dependency_injector import containers

__all__ = ["Container"]


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["%%PKG%%.restapi"])
"""

_DOMAIN_INIT = """\
from . import exceptions
from .exceptions import *  # noqa: F403

__all__ = exceptions.__all__
"""

_EXCEPTIONS = """\
__all__ = ["DomainError"]


class DomainError(Exception):
    code: str = "DOMAIN_ERROR"
    http_status: int = 500

    def __init__(self, message: str, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, object] = context if context is not None else {}
"""

_RESTAPI_INIT = ""  # entrypoint package: minimal, re-exports nothing (architecture carve-out 2)

_MAIN = """\
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from %%PKG%%.containers import Container

from .error_handler import register_error_handlers

__all__ = ["create_app"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The bootstrap shell owns no long-lived disposable resource yet, so teardown is empty.
    # A later change that wires a store (relational engine / client) disposes it here.
    yield


def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container()

    app = FastAPI(title="%%TITLE%%", lifespan=_lifespan)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        # Allowed origins are deployment config, not a code constant — set them from the
        # app's settings/env. Empty default = no cross-origin until configured.
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[],
    )

    register_error_handlers(app)

    # Routers land here as behaviour, added by the change cycle (restapi-endpoint):
    #     from .routers.foos import router as foos_router
    #     app.include_router(foos_router)

    return app
"""

_ERROR_HANDLER = """\
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from %%PKG%%.domain.exceptions import DomainError

from .schemas.errors import ErrorResponse

__all__ = ["register_error_handlers"]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                code=exc.code,
                message=str(exc),
                context=exc.context,
            ).model_dump(),
        )
"""

_SCHEMAS_INIT = """\
from . import errors
from .errors import *  # noqa: F403

__all__ = errors.__all__
"""

_SCHEMAS_ERRORS = """\
from typing import Any

from pydantic import BaseModel, Field

from %%PKG%%.domain import exceptions as _domain_exceptions
from %%PKG%%.domain.exceptions import DomainError

__all__ = ["MIDDLEWARE_ERRORS", "ErrorResponse", "error_responses"]


class ErrorResponse(BaseModel):
    code: str
    message: str
    context: dict[str, object] = Field(default_factory=dict)


# Status codes emitted by middleware that have no DomainError class behind them.
# Empty by default — no middleware is presumed.
MIDDLEWARE_ERRORS: dict[str, int] = {}

_DESCR: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    422: "Unprocessable entity",
}


def _all_known_statuses() -> set[int]:
    domain_statuses: set[int] = set()
    for name in _domain_exceptions.__all__:
        cls = getattr(_domain_exceptions, name)
        if isinstance(cls, type) and issubclass(cls, DomainError):
            domain_statuses.add(cls.http_status)
    return domain_statuses | set(MIDDLEWARE_ERRORS.values())


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    known = _all_known_statuses()
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValueError(f"HTTP statuses not produced by any DomainError or middleware: {unknown}")
    out: dict[int | str, dict[str, Any]] = {
        c: {"model": ErrorResponse, "description": _DESCR.get(c, str(c))} for c in codes
    }
    return out
"""


def _title(pkg: str) -> str:
    return " ".join(part.capitalize() for part in pkg.split("_") if part) + " service"


def _render(template: str, pkg: str) -> str:
    return template.replace("%%PKG%%", pkg).replace("%%TITLE%%", _title(pkg))


def shell_files(pkg: str) -> dict[str, str]:
    """The relative-path → content map of the shell, rendered for the package `pkg`."""
    root = f"src/{pkg}"
    return {
        f"{root}/__init__.py": _APP_ROOT_INIT,
        f"{root}/containers.py": _render(_CONTAINERS, pkg),
        f"{root}/domain/__init__.py": _DOMAIN_INIT,
        f"{root}/domain/exceptions.py": _EXCEPTIONS,
        f"{root}/restapi/__init__.py": _RESTAPI_INIT,
        f"{root}/restapi/main.py": _render(_MAIN, pkg),
        f"{root}/restapi/error_handler.py": _render(_ERROR_HANDLER, pkg),
        f"{root}/restapi/schemas/__init__.py": _SCHEMAS_INIT,
        f"{root}/restapi/schemas/errors.py": _render(_SCHEMAS_ERRORS, pkg),
    }


def write_shell(tree: Path, pkg: str) -> list[str]:
    written: list[str] = []
    for rel, content in shell_files(pkg).items():
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)
    return written


# --------------------------------------------------------------------------------------
# Presence detection + commit
# --------------------------------------------------------------------------------------


def substrate_present(tree: Path, pkg: str) -> bool:
    """The shell already stands (the step is gated on 'substrate absent')."""
    return (tree / "src" / pkg / "restapi" / "main.py").is_file()


def _git(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)


def commit_bootstrap(tree: Path, pkg: str) -> str:
    if _git(tree, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise BootstrapError(f"{tree} is not a git work tree — bootstrap must land as a pre-baseline commit")
    add = _git(tree, "add", "pyproject.toml", f"src/{pkg}")
    if add.returncode != 0:
        raise BootstrapError(f"git add failed: {(add.stderr or add.stdout).strip()}")
    message = f"Bootstrap {pkg}: framework substrate + behaviorless app shell (pre-baseline)"
    commit = _git(tree, "commit", "-m", message)
    if commit.returncode != 0:
        raise BootstrapError(f"git commit failed: {(commit.stderr or commit.stdout).strip()}")
    return message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Greenfield substrate + app shell, in a pre-baseline commit.")
    parser.add_argument("tree", nargs="?", default=".")
    parser.add_argument("--no-commit", action="store_true", help="write the files but do not commit")
    args = parser.parse_args(argv)

    tree = Path(args.tree).resolve()
    try:
        pkg = package_name(tree)
        if substrate_present(tree, pkg):
            print(f"bootstrap: substrate already present (src/{pkg}/restapi/main.py exists) — no-op")
            return 0
        write_pyproject(tree)
        written = write_shell(tree, pkg)
    except BootstrapError as exc:
        print(f"bootstrap: STOP — {exc}", file=sys.stderr)
        return 2

    print(f"bootstrap: package {pkg}")
    print(f"  substrate: {', '.join(FRAMEWORK_SUBSTRATE)} (+ dev: {', '.join(DEV_SUBSTRATE)})")
    for rel in written:
        print(f"  wrote {rel}")

    if args.no_commit:
        print("bootstrap: --no-commit — files written, NOT committed")
        return 0
    try:
        message = commit_bootstrap(tree, pkg)
    except BootstrapError as exc:
        print(f"bootstrap: STOP — {exc}", file=sys.stderr)
        return 2
    print(f"bootstrap: committed pre-baseline — {message!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
