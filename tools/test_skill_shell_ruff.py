"""Guard: the code the skills prescribe passes the gate's pinned ruff selection (SKILL-GATE).

The knowledge layer (skills) tells an agent how to write the app's code; the enforcement
layer (`gate.py`) rejects code that fails its pinned `RUFF_SELECT`. These two must agree —
otherwise an implementer who *faithfully follows a skill* lands red at the gate (the live
T09c/platform-001 finding F2: `F403` on the star re-export idiom, `RUF022` on an unsorted
`__all__`). This suite is the regression that a later reword of a skill cannot silently
re-open that disagreement.

Two complementary guards:

1. `test_materialized_app_shell_and_reexport_package_are_gate_clean` — materialize the WHOLE
   modules the skills prescribe (the behaviorless app shell that T12's implementer writes from
   `restapi` / `architecture` / `domain-model`, plus a representative multi-module re-export
   package built to `architecture`'s re-export contract) and assert the gate's exact ruff
   invocation is clean. This exercises the real artifacts end to end, not illustrative
   fragments (skill snippets are often fragments with placeholders / undefined names, so
   extracting every fence and linting it is dominated by noise — see the task's Step 3 note).

2. `test_every_skill_wildcard_reexport_line_carries_noqa_f403` and
   `test_every_literal_all_list_in_skill_code_is_ruff_sorted` — tie the two specific reds back
   to the skill *text*: every `from .<module> import *` template line carries `# noqa: F403`,
   and every literal `__all__ = [...]` in a fenced code block is RUF022-sorted. A reword that
   drops the noqa or reorders a list reds here by name.

`RUFF_SELECT` / line-length / target-version are imported from `gate.py`, never restated (C7).
"""

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = TOOLS_DIR.parent / "skills"


def _load_gate():
    spec = importlib.util.spec_from_file_location("gate_for_skill_guard", TOOLS_DIR / "gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


_GATE = _load_gate()


def _ruff_check(targets: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ruff exactly as gate.py's `check_ruff` does (its pinned common flags + select)."""
    common = ["--isolated", "--line-length", _GATE.RUFF_LINE_LENGTH, "--target-version", _GATE.RUFF_TARGET]
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", *common, "--no-cache", "--select", _GATE.RUFF_SELECT, *targets],
        capture_output=True,
        text=True,
    )


# --- The whole modules the skills prescribe -------------------------------------------
# The behaviorless app shell (restapi / architecture / domain-model house style) + a
# representative multi-module re-export package (architecture's re-export contract). The
# star re-export lines carry a `noqa: F403` directive and `errors.py`'s `__all__` is RUF022-sorted,
# exactly as the skills now instruct.

_PKG = "myapp"

_SHELL: dict[str, str] = {
    f"src/{_PKG}/__init__.py": '__version__ = "0.1.0"\n',
    f"src/{_PKG}/containers.py": (
        "from dependency_injector import containers\n\n"
        '__all__ = ["Container"]\n\n\n'
        "class Container(containers.DeclarativeContainer):\n"
        f'    wiring_config = containers.WiringConfiguration(packages=["{_PKG}.restapi"])\n'
    ),
    f"src/{_PKG}/domain/__init__.py": (
        "from . import exceptions\nfrom .exceptions import *  # noqa: F403\n\n__all__ = exceptions.__all__\n"
    ),
    f"src/{_PKG}/domain/exceptions.py": (
        '__all__ = ["DomainError"]\n\n\n'
        "class DomainError(Exception):\n"
        '    code: str = "DOMAIN_ERROR"\n'
        "    http_status: int = 500\n\n"
        "    def __init__(self, message: str, context: dict[str, object] | None = None) -> None:\n"
        "        super().__init__(message)\n"
        "        self.context: dict[str, object] = context if context is not None else {}\n"
    ),
    f"src/{_PKG}/restapi/__init__.py": "",
    f"src/{_PKG}/restapi/main.py": (
        "from collections.abc import AsyncIterator\n"
        "from contextlib import asynccontextmanager\n\n"
        "from fastapi import FastAPI\n\n"
        f"from {_PKG}.containers import Container\n\n"
        "from .error_handler import register_error_handlers\n\n"
        '__all__ = ["create_app"]\n\n\n'
        "@asynccontextmanager\n"
        "async def _lifespan(app: FastAPI) -> AsyncIterator[None]:\n"
        "    yield\n\n\n"
        "def create_app(container: Container | None = None) -> FastAPI:\n"
        "    container = container or Container()\n"
        '    app = FastAPI(title="Myapp service", lifespan=_lifespan)\n'
        "    app.state.container = container\n"
        "    register_error_handlers(app)\n"
        "    return app\n"
    ),
    f"src/{_PKG}/restapi/error_handler.py": (
        "from fastapi import FastAPI, Request\n"
        "from fastapi.responses import JSONResponse\n\n"
        f"from {_PKG}.domain.exceptions import DomainError\n\n"
        "from .schemas.errors import ErrorResponse\n\n"
        '__all__ = ["register_error_handlers"]\n\n\n'
        "def register_error_handlers(app: FastAPI) -> None:\n"
        "    @app.exception_handler(DomainError)\n"
        "    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:\n"
        "        return JSONResponse(\n"
        "            status_code=exc.http_status,\n"
        "            content=ErrorResponse(code=exc.code, message=str(exc), context=exc.context).model_dump(),\n"
        "        )\n"
    ),
    f"src/{_PKG}/restapi/schemas/__init__.py": (
        "from . import errors\nfrom .errors import *  # noqa: F403\n\n__all__ = errors.__all__\n"
    ),
    f"src/{_PKG}/restapi/schemas/errors.py": (
        "from pydantic import BaseModel, Field\n\n"
        f"from {_PKG}.domain import exceptions as _domain_exceptions\n"
        f"from {_PKG}.domain.exceptions import DomainError\n\n"
        '__all__ = ["MIDDLEWARE_ERRORS", "ErrorResponse", "error_responses"]\n\n\n'
        "class ErrorResponse(BaseModel):\n"
        "    code: str\n"
        "    message: str\n"
        "    context: dict[str, object] = Field(default_factory=dict)\n\n\n"
        "MIDDLEWARE_ERRORS: dict[str, int] = {}\n\n\n"
        "def _all_known_statuses() -> set[int]:\n"
        "    domain_statuses: set[int] = set()\n"
        "    for name in _domain_exceptions.__all__:\n"
        "        cls = getattr(_domain_exceptions, name)\n"
        "        if isinstance(cls, type) and issubclass(cls, DomainError):\n"
        "            domain_statuses.add(cls.http_status)\n"
        "    return domain_statuses | set(MIDDLEWARE_ERRORS.values())\n\n\n"
        "def error_responses(*codes: int) -> dict[int | str, dict[str, object]]:\n"
        "    known = _all_known_statuses()\n"
        "    unknown = [c for c in codes if c not in known]\n"
        "    if unknown:\n"
        '        raise ValueError(f"HTTP statuses not produced by any DomainError or middleware: {unknown}")\n'
        '    return {c: {"model": ErrorResponse, "description": str(c)} for c in codes}\n'
    ),
    # A representative multi-module re-export package built to architecture's contract:
    # a domain subdomain with two class modules, its subpackage __init__, and the layer
    # __init__ that re-exports the subdomain (the `from . import <mod>` + `from .<mod>
    # import *` with a `noqa: F403` directive + `+`-joined __all__ idiom, one hop and two).
    f"src/{_PKG}/foos/__init__.py": (
        "from . import foo, foo_category\n"
        "from .foo import *  # noqa: F403\n"
        "from .foo_category import *  # noqa: F403\n\n"
        "__all__ = foo.__all__ + foo_category.__all__\n"
    ),
    f"src/{_PKG}/foos/foo.py": '__all__ = ["Foo"]\n\n\nclass Foo:\n    pass\n',
    f"src/{_PKG}/foos/foo_category.py": '__all__ = ["FooCategory"]\n\n\nclass FooCategory:\n    pass\n',
    f"src/{_PKG}/reexport_layer/__init__.py": (
        "from . import foos\nfrom .foos import *  # noqa: F403\n\n__all__ = foos.__all__\n"
    ),
    f"src/{_PKG}/reexport_layer/foos/__init__.py": (
        "from . import foo\nfrom .foo import *  # noqa: F403\n\n__all__ = foo.__all__\n"
    ),
    f"src/{_PKG}/reexport_layer/foos/foo.py": '__all__ = ["Foo"]\n\n\nclass Foo:\n    pass\n',
}


def test_materialized_app_shell_and_reexport_package_are_gate_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, content in _SHELL.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        result = _ruff_check([str(root / "src")])
    assert result.returncode == 0, (
        "the skill-prescribed app shell + re-export package fail the gate's ruff selection "
        f"({_GATE.RUFF_SELECT}):\n{result.stdout}\n{result.stderr}"
    )


# --- Tie the two reds to the skill text ------------------------------------------------

_WILDCARD_LINE = re.compile(r"^from \.[A-Za-z_][A-Za-z0-9_]* import \*(.*)$", re.MULTILINE)
_PY_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_ALL_LITERAL = re.compile(r"__all__\s*=\s*\[[^\]]*\]", re.DOTALL)


def _skill_files() -> list[Path]:
    files = sorted(SKILLS_DIR.rglob("SKILL.md"))
    assert files, f"no SKILL.md found under {SKILLS_DIR}"
    return files


def test_every_skill_wildcard_reexport_line_carries_noqa_f403() -> None:
    """A template `from .<module> import *` line (fenced, line-anchored) must suppress F403.

    The wildcard re-export is the intentional idiom (mypy needs it); the gate's `F` rules flag
    it as F403. The skill templates must carry the per-line `# noqa: F403` so an agent copying
    them lands clean. (`# noqa: F403` is permitted — the gate grep-gates only `# noqa: F401`.)
    """
    offenders: list[str] = []
    for f in _skill_files():
        for m in _WILDCARD_LINE.finditer(f.read_text(encoding="utf-8")):
            if "# noqa: F403" not in m.group(0):
                line_no = f.read_text(encoding="utf-8")[: m.start()].count("\n") + 1
                offenders.append(f"{f.parent.name}/SKILL.md:{line_no}: {m.group(0)}")
    assert not offenders, "wildcard re-export lines missing `# noqa: F403`:\n" + "\n".join(offenders)


def test_every_literal_all_list_in_skill_code_is_ruff_sorted() -> None:
    """Every literal `__all__ = [...]` in a fenced code block is RUF022-sorted.

    A reword that reorders a list (the platform-001 F2 case: `["ErrorResponse",
    "MIDDLEWARE_ERRORS", ...]`) reds here rather than at an implementer's gate run.
    """
    literals: list[str] = []
    for f in _skill_files():
        for fence in _PY_FENCE.finditer(f.read_text(encoding="utf-8")):
            literals.extend(_ALL_LITERAL.findall(fence.group(1)))
    assert literals, "found no literal __all__ lists in skill code fences — extraction broke"
    with tempfile.TemporaryDirectory() as tmp:
        paths: list[str] = []
        for i, lit in enumerate(literals):
            p = Path(tmp) / f"all_{i}.py"
            p.write_text(lit + "\n", encoding="utf-8")
            paths.append(str(p))
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--select", "RUF022", *paths],
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, "an `__all__` literal in a skill code fence is not RUF022-sorted:\n" + result.stdout
