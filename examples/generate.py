#!/usr/bin/env python3
"""Run the forward generator on a manifest and print what it produced.

Usage (from the repo root):

    uv run python examples/generate.py examples/helpdesk_manifest.yaml --package hdk
    uv run python examples/generate.py examples/vector_rag_manifest.yaml --package vrag

Output goes to examples/generated/<package>/ (the package) plus
examples/generated/tests/. The whole examples/generated/ tree is disposable —
re-run any time. (Migrations are not generated — Alembic owns the chain; see
the storage redesign.)
"""

import argparse
import shutil
import sys
from pathlib import Path

# Make the src/ layout importable so `codegen` resolves when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from codegen.generator import Generator  # noqa: E402
from codegen.generator.drift import check_schema_drift  # noqa: E402
from codegen.generator.references import check_references  # noqa: E402
from codegen.manifest.validator import load_and_validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate code from a manifest.")
    parser.add_argument("manifest", help="path to the epic manifest YAML")
    parser.add_argument("--package", default="demo", help="import root for the generated package")
    parser.add_argument("--out", default="examples/generated", help="output directory")
    parser.add_argument("--uc-dir", default=None, help="UC dir (enables sources resolution)")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    pkg_root = out / args.package
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text("")

    uc_dir = Path(args.uc_dir) if args.uc_dir else None
    print(f"→ validating {args.manifest} ...")
    manifest, report = load_and_validate(args.manifest, uc_dir=uc_dir)

    for finding in report.findings:
        print(f"   [{finding.severity}] {finding.code}: {finding.message}")
    if not report.ok:
        print("✗ manifest did not pass validation — nothing generated.")
        return 1
    print(f"✓ form + graph valid (epic: {manifest.meta.epic})")

    written = Generator(manifest, pkg_root, package=args.package).generate_all(
        tests_root=out / "tests",
    )

    print(f"\n→ generated {len(written)} files under {out}/:\n")
    for path in sorted(written):
        print(f"   {path.relative_to(out)}")

    # Post-gen schema-drift: every freshly scaffolded table is unfilled, so this lists the
    # tables awaiting the implementer (the deterministic §4 trigger). After a brownfield
    # delta it would instead flag the specific columns a migration must add.
    drift = check_schema_drift(manifest, pkg_root)
    if drift.warnings:
        print("\n→ schema-drift (tables awaiting the implementer):")
        for f in drift.warnings:
            print(f"   [{f.code}] {f.message}")

    # Reference integrity: every first-party import in the generated tree must resolve, and no
    # undefined names — a generator bug (not the implementer's) fails loudly here, before any
    # implementer spawns. (The §6 manifest validator's analog for generated OUTPUT.)
    refs = check_references(out, args.package)
    if refs.errors:
        print("\n✗ reference-integrity errors (generator emitted a broken reference):")
        for f in refs.errors:
            print(f"   [{f.code}] {f.message}")
    else:
        print("\n✓ reference integrity: all first-party imports resolve")

    print(
        "\nInspect the result, e.g.:\n"
        f"   find {pkg_root} -name '*.py' | sort\n"
        f"   cat {pkg_root}/restapi/routers/*.py\n"
        "   # lint (generated package is first-party for its own imports):\n"
        f"   uv run ruff check --config 'lint.isort.known-first-party=[\"{args.package}\"]' {out}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
