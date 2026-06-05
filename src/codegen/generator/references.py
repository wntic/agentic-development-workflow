"""Generated-tree reference integrity — a post-generation gate (the §6 manifest validator's
analog for OUTPUT).

The manifest validator catches broken edges BEFORE generation; this catches broken references
the GENERATOR ITSELF emitted: an import of a symbol the target module does not export, or an
undefined name in a declarative file. These are generator bugs (not implementer bugs), of the
kind a test fixture's shape can hide — the vector_rag probe surfaced three (a settings
collision, a no-auth `UnauthorizedError` import, a cross-resource schema reference). The check
is deterministic and cheap: run it right after `generate` and in the verify loop, BEFORE any
implementer spawns.

Why a dedicated check and not just the existing tooling:
  * `py_compile` misses these — imports are not resolved at compile time.
  * `ruff` misses unresolved imports — it is a linter, not a type checker (F401 flags an
    UNUSED import, never "this name does not exist in the target module").
So the first-party import resolution here is its unique value (zero-dep, no installed
third-party packages, no filled bodies). Undefined-name detection (the cross-resource schema
class) delegates to `ruff --select F821` when ruff is on PATH. mypy, once wired into the loop
(spec §17), subsumes most of this — this stays the fast pre-mypy smoke + a generator-regression
guard runnable on every fixture without a full environment.
"""

import ast
import json
import shutil
import subprocess
from pathlib import Path

from ..manifest.validator import ValidationReport


def _module_file(import_root: Path, module: str) -> Path | None:
    """The file backing a dotted module under the import root (a `.py` or a package `__init__`)."""
    base = import_root.joinpath(*module.split("."))
    if base.with_suffix(".py").exists():
        return base.with_suffix(".py")
    if (base / "__init__.py").exists():
        return base / "__init__.py"
    return None


def _abs_module(node: ast.ImportFrom, file_path: Path, import_root: Path) -> str | None:
    """Resolve an `ImportFrom` to an absolute dotted module (handles relative `.`/`..`)."""
    if node.level == 0:
        return node.module
    pkg_parts = list(file_path.relative_to(import_root).parts[:-1])  # this file's package
    climb = node.level - 1
    if climb:
        pkg_parts = pkg_parts[:-climb] if climb <= len(pkg_parts) else []
    if node.module:
        pkg_parts += node.module.split(".")
    return ".".join(pkg_parts) or None


def _exported(file_path: Path, import_root: Path, seen: frozenset[Path]) -> set[str]:
    """Names a module makes importable: its top-level defs/classes/assignments + imported
    bindings, plus (recursively) everything a `from .x import *` re-exports. An over-
    approximation by design — it never reports a real binding as missing (no false positives)."""
    if file_path in seen:
        return set()
    seen = seen | {file_path}
    names: set[str] = set()
    for node in ast.parse(file_path.read_text()).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = _abs_module(node, file_path, import_root)
            for a in node.names:
                if a.name == "*":
                    tf = _module_file(import_root, target) if target else None
                    if tf is not None:
                        names |= _exported(tf, import_root, seen)
                else:
                    names.add(a.asname or a.name)
    return names


def check_references(import_root: str | Path, package: str) -> ValidationReport:
    """Verify every FIRST-PARTY import in the generated package resolves to a real export
    (+ ruff F821 undefined names when ruff is available). Errors block — a generator that
    references what it did not generate must fail loudly, before the implementer is spawned."""
    root = Path(import_root)
    report = ValidationReport()
    for f in sorted((root / package).rglob("*.py")):
        where = f.relative_to(root)
        for node in ast.parse(f.read_text()).body:
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _abs_module(node, f, root)
            if not target or not (target == package or target.startswith(f"{package}.")):
                continue  # first-party only; stdlib/third-party are mypy/ruff's concern
            target_file = _module_file(root, target)
            if target_file is None:
                report.add("error", "unresolved_import", f"{where}: imports from missing module {target!r}")
                continue
            exported = _exported(target_file, root, frozenset())
            for a in node.names:
                if a.name == "*" or a.name in exported:
                    continue
                # `from pkg.x import y` where pkg.x.y is itself a module = a submodule import (valid)
                if _module_file(root, f"{target}.{a.name}") is not None:
                    continue
                report.add("error", "unresolved_import", f"{where}: {a.name!r} is not exported by {target!r}")

    _check_undefined_names(root / package, report)
    return report


def _check_undefined_names(pkg_dir: Path, report: ValidationReport) -> None:
    """Undefined module-level names (a referenced-but-unimported schema type) via ruff F821.
    Skipped silently when ruff is not on PATH — the import resolver above still runs."""
    ruff = shutil.which("ruff")
    if ruff is None:
        return
    proc = subprocess.run(
        [ruff, "check", "--select", "F821", "--isolated", "--output-format", "json", str(pkg_dir)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 or not proc.stdout.strip():
        return
    try:
        items = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return
    for item in items:
        report.add("error", "undefined_name", f"{item.get('filename', '?')}: {item.get('message', 'undefined name')}")
