#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Generate the manifest SHAPE skeleton from the validator's `SCHEMAS` (spec §5, R4).

The hand-maintained `manifest.template.yaml` and `MANIFEST_SCHEMA.md` drifted because nothing
checked them — a second source of truth for the manifest shape, kept in sync by hand. This script
removes that source: the shape is emitted FROM `validate_manifest.SCHEMAS` (the executable
contract), so it cannot drift. A golden-file test (`test_template_is_in_sync`) asserts the
committed template matches a fresh generation.

What it emits: every section, every artifact kind, every field — with its type, required/optional,
enum choices, and default as an inline comment. It is a STRUCTURAL reference, not a valid manifest
(placeholder values; cross-refs don't resolve). Semantics (why a field exists) live in the spec +
conventions, never here; a validated worked example is any fixture.

Usage:  uv run .claude/tools/gen_template.py            # write the template
        uv run .claude/tools/gen_template.py --check     # exit 1 if the committed file is stale
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_manifest as vm

_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "manifest.template.yaml"

_HEADER = """\
# ─────────────────────────────────────────────────────────────────────────────
# GENERATED — DO NOT EDIT.  Regenerate:  uv run .claude/tools/gen_template.py
# ─────────────────────────────────────────────────────────────────────────────
# This is the manifest SHAPE skeleton, emitted from the validator's `SCHEMAS`
# (validate_manifest.py — the single executable contract for the manifest form).
# It exists so the shape can be READ without drifting from what the validator enforces.
#
#   • It is NOT a valid manifest — values are type placeholders and cross-references
#     (handler deps → protocols, endpoint.handler → command, …) do not resolve.
#   • For a validated WORKED EXAMPLE, read a fixture:
#       .claude/tools/fixtures/helpdesk_manifest.yaml   (auth + tickets)
#       .claude/tools/fixtures/vector_rag_manifest.yaml (polyglot + non-CRUD)
#       .claude/tools/fixtures/label_manifest.yaml      (small CRUD)
#   • For field SEMANTICS (why a field exists, earn-its-place, derived-not-declared),
#     read codegen_workflow_spec.md §5 and the `conventions` skill — semantics live in
#     their canonical layer and are never restated here.
#
# Each line is annotated:  <field>: <placeholder>   # <type>, required|optional[, default ...]
"""

_SCALAR_PLACEHOLDER = {
    "str": '"<str>"',
    "int": "0",
    "bool": "false",
    "strlist": '["<str>"]',
    "intlist": "[0]",
    "map": "{}",
    "any": "<any>",
}

_SCALAR_TYPENAME = {
    "str": "str",
    "int": "int",
    "bool": "bool",
    "strlist": "list of str",
    "intlist": "list of int",
    "map": "free key→value map",
    "any": "any literal (validator never inspects)",
    "protocol_methods": 'list of "signature" | {signature, notes}',
}


def _describe(f: vm.F) -> str:
    """The inline comment for a field: type, required/optional, default."""
    kind = f.kind
    if isinstance(kind, tuple):
        tag, sub = kind
        base = f"list of {sub}" if tag == "list" else f"{sub} (mapping)"
    elif kind == "enum":
        base = "one of: " + ", ".join(f.choices)
    else:
        base = _SCALAR_TYPENAME.get(kind, str(kind))  # type: ignore[arg-type]
    parts = [base, "required" if f.required else "optional"]
    if not f.required and f.default not in (None, [], {}, False, 0):
        parts.append(f"default {f.default!r}")
    return ", ".join(parts)


def _line(prefix: str, text: str, comment: str) -> str:
    """One YAML line, padded so the `# comment` column lines up reasonably."""
    body = prefix + text
    return f"{body:<52}# {comment}" if comment else body


def _emit_mapping(schema_name: str, indent: int, lines: list[str], dash: bool = False) -> None:
    """Emit one mapping (a schema's fields) at `indent` (one level = 2 spaces). When `dash`, this
    mapping is a list element: the FIRST field carries the `- ` marker (sitting one level shallower)
    and continuation fields align under it — so callers pass the element's *content* indent and the
    dash is rendered half a step back. A YAML list of mappings is +2 levels from its key (dash +1)."""
    first = True
    for fname, f in vm.SCHEMAS[schema_name].items():
        prefix = "  " * (indent - 1) + "- " if (dash and first) else "  " * indent
        first = False
        kind = f.kind
        if isinstance(kind, tuple):
            tag, sub = kind
            lines.append(_line(prefix, f"{fname}:", _describe(f)))
            if tag == "obj":
                _emit_mapping(sub, indent + 1, lines)
            else:  # list → one example element, content +2 levels, dash +1
                _emit_mapping(sub, indent + 2, lines, dash=True)
        elif kind == "protocol_methods":
            lines.append(_line(prefix, f"{fname}:", _describe(f)))
            lines.append(_line("  " * (indent + 1), '- "async def method(self, arg: Type) -> ReturnType"', ""))
        else:
            placeholder = f.choices[0] if kind == "enum" and f.choices else _SCALAR_PLACEHOLDER.get(kind, '"<?>"')  # type: ignore[arg-type]
            lines.append(_line(prefix, f"{fname}: {placeholder}", _describe(f)))


def render() -> str:
    lines: list[str] = []
    # Walk the top-level Manifest fields (meta + the section containers) as blocks.
    for fname, f in vm.SCHEMAS["Manifest"].items():
        assert isinstance(f.kind, tuple) and f.kind[0] == "obj", "top-level fields are all objects"
        lines.append("")
        lines.append(_line("", f"{fname}:", _describe(f)))
        _emit_mapping(f.kind[1], 1, lines)
    return _HEADER + "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the manifest shape skeleton from SCHEMAS.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed template is stale")
    args = parser.parse_args(argv)

    generated = render()
    if args.check:
        current = _TEMPLATE.read_text() if _TEMPLATE.exists() else ""
        if current != generated:
            print(f"{_TEMPLATE} is STALE — regenerate with: uv run .claude/tools/gen_template.py")
            return 1
        print(f"{_TEMPLATE}: up to date")
        return 0
    _TEMPLATE.write_text(generated)
    print(f"wrote {_TEMPLATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
