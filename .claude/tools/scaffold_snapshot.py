#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Scaffold baseline snapshot + implementer-diff — the attribution record for the scaffold tail.

The scaffolder (spec §3) writes every body as `raise NotImplementedError`; the implementer (§4) then
overwrites those bodies IN PLACE. Because the generated tree is disposable + git-ignored, the moment a
body is filled the scaffolder's original state is gone — so a convention slip (e.g. an import reaching
into a submodule instead of the package re-export) can no longer be attributed to scaffolder vs
implementer. This tool freezes the baseline so every implementer edit is a reviewable diff.

Two subcommands, stdlib-only (no git, no deps — ships bare in a plugin):
  * `snapshot <root>`  — copy `<root>` → `<root>.scaffold/` ONCE, at the end of scaffolding when every
                         body is still `raise NotImplementedError`. Idempotent: refuses to clobber an
                         existing baseline unless `--force` (a re-snapshot after implementers ran would
                         destroy the very record it exists to keep).
  * `diff <root>`      — unified diff of `<root>` vs the frozen `<root>.scaffold/` baseline, restricted
                         to source (`*.py` + `pyproject.toml`). Every changed file is implementer work;
                         a changed file that was NOT a dispatched body scaffold is an overreach
                         (declarative/glue is the scaffolder's — §4) and the diff makes it auditable.

Usage:
  uv run .claude/tools/scaffold_snapshot.py snapshot <generated-package-root> [--force]
  uv run .claude/tools/scaffold_snapshot.py diff <generated-package-root>
"""

import argparse
import difflib
import shutil
import sys
from pathlib import Path

# Caches / build droppings / the lockfile — not part of the authored baseline.
_IGNORE = shutil.ignore_patterns(
    ".venv",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.egg-info",
    ".git",
    "uv.lock",
    "*.scaffold",
)

# Files whose content we attribute (source the agents author).
_DIFFABLE_SUFFIX = (".py",)
_DIFFABLE_NAME = ("pyproject.toml",)


def _baseline(root: Path) -> Path:
    return root.parent / (root.name + ".scaffold")


def _diffable(root: Path) -> dict[str, Path]:
    """Relative-path → file, for every authored source file under root (skipping the ignore set)."""
    out: dict[str, Path] = {}
    skip = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # check the path RELATIVE to root — the baseline's own dir name ends in ".scaffold"
        # and must not disqualify the files inside it.
        rel_parts = p.relative_to(root).parts
        if any(part in skip or part.endswith((".egg-info", ".scaffold")) for part in rel_parts):
            continue
        if p.suffix in _DIFFABLE_SUFFIX or p.name in _DIFFABLE_NAME:
            out[p.relative_to(root).as_posix()] = p
    return out


def cmd_snapshot(root: Path, force: bool) -> int:
    dest = _baseline(root)
    if dest.exists():
        if not force:
            print(f"baseline already exists: {dest} (leaving it — use --force to re-take)")
            return 0
        shutil.rmtree(dest)
    shutil.copytree(root, dest, ignore=_IGNORE)
    n = len(_diffable(dest))
    print(f"snapshot taken: {root} → {dest}  ({n} source files frozen as the scaffold baseline)")
    return 0


def cmd_diff(root: Path) -> int:
    dest = _baseline(root)
    if not dest.is_dir():
        sys.exit(f"error: no baseline at {dest} — run `snapshot {root}` right after scaffolding")

    base = _diffable(dest)
    cur = _diffable(root)
    base_keys, cur_keys = set(base), set(cur)

    added = sorted(cur_keys - base_keys)
    removed = sorted(base_keys - cur_keys)
    changed: list[str] = []
    chunks: list[str] = []
    for rel in sorted(base_keys & cur_keys):
        b = base[rel].read_text().splitlines(keepends=True)
        c = cur[rel].read_text().splitlines(keepends=True)
        if b != c:
            changed.append(rel)
            chunks.append("".join(difflib.unified_diff(b, c, fromfile=f"scaffold/{rel}", tofile=f"current/{rel}")))

    if not (added or removed or changed):
        print("no changes vs the scaffold baseline — nothing has been filled yet, or every edit reverted.")
        return 0

    print("=== implementer diff vs scaffold baseline ===")
    print(f"changed: {len(changed)} · added: {len(added)} · removed: {len(removed)}\n")
    for rel in changed:
        print(f"  ~ {rel}")
    for rel in added:
        print(f"  + {rel}   (NEW — the implementer must not create files; investigate, §4)")
    for rel in removed:
        print(f"  - {rel}   (DELETED — the implementer must not delete files; investigate, §4)")
    print()
    for chunk in chunks:
        print(chunk)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold baseline snapshot + implementer diff.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("snapshot", help="freeze the scaffold baseline (run right after scaffolding)")
    ps.add_argument("root", type=Path)
    ps.add_argument("--force", action="store_true", help="re-take even if a baseline exists (destroys the record)")
    pd = sub.add_parser("diff", help="unified diff of current source vs the frozen baseline")
    pd.add_argument("root", type=Path)
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        sys.exit(f"error: package root not found: {args.root}")
    if args.cmd == "snapshot":
        return cmd_snapshot(args.root, args.force)
    return cmd_diff(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
