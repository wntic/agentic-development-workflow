"""Unit tests for the import-resolution pass (codegen/generator/imports.py).

The point under test: a type token resolves to its import by introspecting a small ordered list
of stdlib modules (not a hand-written token→import map that rots), with a qualified-name escape
hatch for unscanned modules and lenient handling of the non-type tokens a signature string yields.
"""

from codegen.generator.imports import (
    dataclass_domain_import_block,
    import_lines,
    resolve_import,
    type_tokens,
)


def test_resolve_current_stdlib_types_unchanged() -> None:
    # Regression guard: every type the old hand-written `_STDLIB` map covered must resolve
    # byte-identically via the module scan, so generated imports do not shift.
    assert resolve_import("UUID") == ("uuid", "UUID")
    assert resolve_import("datetime") == ("datetime", "datetime")
    assert resolve_import("date") == ("datetime", "date")
    assert resolve_import("Decimal") == ("decimal", "Decimal")
    assert resolve_import("Sequence") == ("collections.abc", "Sequence")
    assert resolve_import("AsyncIterator") == ("collections.abc", "AsyncIterator")
    assert resolve_import("Any") == ("typing", "Any")


def test_resolve_new_stdlib_type_without_editing_codegen() -> None:
    # The point of the scan: a type never seen in a manifest resolves for free — no codegen edit.
    assert resolve_import("Counter") == ("collections", "Counter")
    assert resolve_import("deque") == ("collections", "deque")
    assert resolve_import("timedelta") == ("datetime", "timedelta")
    assert resolve_import("Path") == ("pathlib", "Path")
    assert resolve_import("Mapping") == ("collections.abc", "Mapping")


def test_builtins_need_no_import() -> None:
    for token in ("str", "int", "bool", "float", "list", "dict", "tuple", "set", "frozenset", "bytes", "None"):
        assert resolve_import(token) is None


def test_qualified_name_becomes_a_plain_module_import() -> None:
    # The escape hatch for a module the scan does not cover: import the module; the annotation
    # keeps the dotted form verbatim (no signature rewriting).
    assert resolve_import("zoneinfo.ZoneInfo") == ("zoneinfo", "")
    assert resolve_import("collections.abc.Callable") == ("collections.abc", "")


def test_signature_noise_and_unscanned_bare_resolve_to_nothing() -> None:
    # The non-type tokens a signature string yields, plus an unqualified exotic type, emit no
    # import (lenient — the reference-integrity gate is the loud catch for a truly undefined type).
    for token in ("self", "update", "async", "def", "query_embedding"):
        assert resolve_import(token) is None
    assert resolve_import("ZoneInfo") is None  # exotic + unqualified → no import (must be qualified)


def test_reexport_is_not_misresolved() -> None:
    # `uuid` does `from enum import Enum`, so `hasattr(uuid, "Enum")` is True — but `Enum.__module__`
    # is "enum", so the scan must NOT resolve it to uuid. This is why the scan checks `__module__`.
    assert resolve_import("Enum") is None


def test_type_tokens_keeps_a_qualified_name_whole() -> None:
    assert type_tokens("dict[str, collections.Counter]") == {"dict", "str", "collections.Counter"}


def test_import_lines_orders_plain_before_from() -> None:
    lines = import_lines({"uuid": {"UUID"}, "zoneinfo": set(), "datetime": {"date", "datetime"}})
    assert lines == ["import zoneinfo", "from datetime import date, datetime", "from uuid import UUID"]


def test_block_imports_a_scanned_type_for_free() -> None:
    block = dataclass_domain_import_block(["UUID", "Counter"], subdomain="x", domain_subdomains={}, has_post_init=False)
    assert "from collections import Counter" in block  # resolved by the scan, no codegen edit
    assert "from uuid import UUID" in block
