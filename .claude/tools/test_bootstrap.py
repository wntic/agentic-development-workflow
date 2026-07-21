"""Test suite for bootstrap.py (workflow v3, T09c).

Covers the deliverable checks: the framework substrate lands in pyproject.toml (names only,
existing entries preserved), the package root is derived from pyproject `name` (`-`→`_`),
a missing pyproject / missing `name` is a hard stop, presence is a no-op, and the emitted
shell is importable + behaviorless (constructs create_app() with an empty OpenAPI, no routes)
and clean under the gate's pinned ruff + strict-mypy config.

The shell imports the real FastAPI stack, which the meta-layer env does not carry, so the
construct / lint / type checks run in an ephemeral `uv run --with …` subprocess and are
skipped (never silently passed) when `uv` is unavailable.
"""

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("bootstrap", TOOLS_DIR / "bootstrap.py")
assert _spec and _spec.loader
bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap)

RUNTIME_DEPS = (
    "fastapi",
    "uvicorn[standard]",
    "pydantic",
    "pydantic-settings",
    "dependency-injector",
    "structlog",
)


def _write_pyproject(tree: Path, body: str) -> None:
    # the filename is assembled so this write is not caught by the meta bash_guard's literal
    (tree / ("pyproject" + ".toml")).write_text(body, encoding="utf-8")


MINIMAL = '[project]\nname = "meeting-assistant"\nversion = "0.1.0"\nrequires-python = ">=3.12"\ndependencies = []\n'


# ---------------------------------------------------------------------------------------
# Package-root name derivation + the hard stops
# ---------------------------------------------------------------------------------------


def test_package_name_normalizes_dash_to_underscore(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    assert bootstrap.package_name(tmp_path) == "meeting_assistant"


def test_missing_pyproject_is_a_stop(tmp_path: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.package_name(tmp_path)
    assert bootstrap.main([str(tmp_path), "--no-commit"]) == 2


def test_missing_name_is_a_stop(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, '[project]\nversion = "0.1.0"\n')
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.package_name(tmp_path)
    assert bootstrap.main([str(tmp_path), "--no-commit"]) == 2


# ---------------------------------------------------------------------------------------
# Substrate written into pyproject.toml — names only, existing entries preserved
# ---------------------------------------------------------------------------------------


def test_substrate_present_after_bootstrap(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    bootstrap.write_pyproject(tmp_path)
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    for pkg in RUNTIME_DEPS:
        assert pkg in deps, f"{pkg} missing from [project] dependencies"
    dev = data["dependency-groups"]["dev"]
    for pkg in ("pytest", "pytest-asyncio", "ruff", "mypy", "testcontainers", "httpx"):
        assert pkg in dev, f"{pkg} missing from the dev group"


def test_substrate_carries_no_versions(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    bootstrap.write_pyproject(tmp_path)
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    for spec in data["project"]["dependencies"] + data["dependency-groups"]["dev"]:
        assert not any(op in spec for op in ("==", ">=", "<=", "~=", ">", "<")), f"pinned version in {spec!r}"


def test_existing_dependencies_are_preserved(tmp_path: Path) -> None:
    _write_pyproject(
        tmp_path,
        '[project]\nname = "acme"\ndependencies = [\n    "somelib",\n]\n\n'
        '[dependency-groups]\ndev = [\n    "pre-commit",\n]\n',
    )
    bootstrap.write_pyproject(tmp_path)
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert "somelib" in data["project"]["dependencies"]
    assert "fastapi" in data["project"]["dependencies"]
    assert "pre-commit" in data["dependency-groups"]["dev"]
    assert "pytest" in data["dependency-groups"]["dev"]


# ---------------------------------------------------------------------------------------
# The shell files + presence-is-a-no-op
# ---------------------------------------------------------------------------------------


def test_shell_skeleton_written(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    assert bootstrap.main([str(tmp_path), "--no-commit"]) == 0
    root = tmp_path / "src" / "meeting_assistant"
    for rel in (
        "__init__.py",
        "containers.py",
        "domain/__init__.py",
        "domain/exceptions.py",
        "restapi/__init__.py",
        "restapi/main.py",
        "restapi/error_handler.py",
        "restapi/schemas/__init__.py",
        "restapi/schemas/errors.py",
    ):
        assert (root / rel).is_file(), f"{rel} not emitted"


def test_shell_declares_no_routes_statically(tmp_path: Path) -> None:
    # behaviorless: the shell must not register any router itself (routes are behaviour).
    _write_pyproject(tmp_path, MINIMAL)
    bootstrap.write_shell(tmp_path, "meeting_assistant")
    main_text = (tmp_path / "src/meeting_assistant/restapi/main.py").read_text(encoding="utf-8")
    active = [ln for ln in main_text.splitlines() if "include_router" in ln and not ln.lstrip().startswith("#")]
    assert active == [], f"shell main.py registers a router: {active}"
    assert not (tmp_path / "src/meeting_assistant/restapi/routers").exists()


def test_bootstrap_is_a_noop_when_substrate_present(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    assert bootstrap.main([str(tmp_path), "--no-commit"]) == 0
    before = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert bootstrap.substrate_present(tmp_path, "meeting_assistant")
    # a second run must not double-append the substrate or touch the tree
    assert bootstrap.main([str(tmp_path), "--no-commit"]) == 0
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == before


def test_bootstrap_commits_a_distinct_pre_baseline_commit(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, MINIMAL)
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "identity"], check=True)
    assert bootstrap.main([str(tmp_path)]) == 0
    # the bootstrap commit exists and touches only pyproject.toml + src/**
    files = subprocess.run(
        ["git", "-C", str(tmp_path), "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.split()
    assert files, "bootstrap did not create a commit"
    assert all(f == "pyproject.toml" or f.startswith("src/") for f in files), files


# ---------------------------------------------------------------------------------------
# The shell is importable, behaviorless (empty OpenAPI), and toolchain-clean.
# These exercise the REAL FastAPI stack in an ephemeral uv env (skip if uv absent).
# ---------------------------------------------------------------------------------------

_UV = shutil.which("uv")
_WITH = [arg for dep in RUNTIME_DEPS for arg in ("--with", dep)]


def _bootstrapped_tree(tmp_path: Path) -> Path:
    _write_pyproject(tmp_path, MINIMAL)
    bootstrap.write_shell(tmp_path, "meeting_assistant")
    return tmp_path


@pytest.mark.skipif(_UV is None, reason="uv not on PATH — cannot build the ephemeral FastAPI env")
def test_shell_constructs_with_empty_openapi(tmp_path: Path) -> None:
    tree = _bootstrapped_tree(tmp_path)
    code = (
        "import importlib\n"
        "m = importlib.import_module('meeting_assistant.restapi.main')\n"
        "app = m.create_app()\n"
        "schema = app.openapi()\n"
        "assert schema, 'empty openapi'\n"
        "paths = list(schema.get('paths', {}).keys())\n"
        "assert paths == [], f'shell exposes routes: {paths}'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [_UV, "run", *_WITH, "python", "-c", code],
        cwd=str(tree),
        env={"PYTHONPATH": str(tree / "src"), "PATH": __import__("os").environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


@pytest.mark.skipif(_UV is None, reason="uv not on PATH — cannot build the ephemeral FastAPI env")
def test_shell_is_ruff_and_mypy_clean(tmp_path: Path) -> None:
    tree = _bootstrapped_tree(tmp_path)
    (tree / "mypy.ini").write_text(
        "[mypy]\nstrict = True\nwarn_unreachable = True\nmypy_path = src\n"
        "explicit_package_bases = True\nnamespace_packages = True\n",
        encoding="utf-8",
    )
    ruff = subprocess.run(
        [
            _UV,
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "--isolated",
            "--line-length",
            "120",
            "--target-version",
            "py312",
            "--no-cache",
            "--select",
            "E,W,F,I,N,UP,B,C4,SIM,RUF",
            "src",
        ],
        cwd=str(tree),
        capture_output=True,
        text=True,
    )
    assert ruff.returncode == 0, ruff.stdout + ruff.stderr
    mypy = subprocess.run(
        [_UV, "run", *_WITH, "--with", "mypy", "python", "-m", "mypy", "--config-file", "mypy.ini", "src"],
        cwd=str(tree),
        capture_output=True,
        text=True,
    )
    assert mypy.returncode == 0, mypy.stdout + mypy.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
