"""Import-resolution pass (spec §9): imports are graph edges in Python syntax.

A generated module references types (entity/VO fields, protocol method signatures,
handler deps/returns). Each referenced type resolves to a module via the graph; this
module groups those into import lines. Same-subdomain domain types use a relative
`.module` import; cross-subdomain ones a relative `..subdomain` import; stdlib types
their canonical import. Builtins need none.

The "symbol table" passed around as `domain_subdomains` maps every *named domain type*
(entity, enum, value object) → the subdomain package that owns it. That is the single
lookup that turns a bare type token in a field/signature into an import edge.
"""

import re

from .naming import snake_case

# token → (module, symbol)
_STDLIB: dict[str, tuple[str, str]] = {
    "UUID": ("uuid", "UUID"),
    "datetime": ("datetime", "datetime"),
    "date": ("datetime", "date"),
    "Decimal": ("decimal", "Decimal"),
    "Any": ("typing", "Any"),
    "Protocol": ("typing", "Protocol"),
    "Sequence": ("collections.abc", "Sequence"),
    "AsyncIterator": ("collections.abc", "AsyncIterator"),  # streaming return (e.g. RAG token stream)
}


def type_tokens(text: str) -> set[str]:
    """Identifier tokens in a type or signature string."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))


def _render(groups: list[dict[str, set[str]]]) -> str:
    blocks: list[str] = []
    for group in groups:
        if not group:
            continue
        lines = [f"from {module} import {', '.join(sorted(names))}" for module, names in sorted(group.items())]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _relative_module(name: str, owner: str, current: str) -> str:
    """A relative import path to a domain type: `.module` within the same subdomain,
    `..subdomain` across subdomains (re-exported by that subdomain's `__init__`)."""
    return f".{snake_case(name)}" if owner == current else f"..{owner}"


def _local_domain_imports(
    referenced: set[str],
    *,
    subdomain: str,
    domain_subdomains: dict[str, str],
) -> dict[str, set[str]]:
    local: dict[str, set[str]] = {}
    for token in referenced:
        owner = domain_subdomains.get(token)
        if owner is not None:
            module = _relative_module(token, owner, subdomain)
            local.setdefault(module, set()).add(token)
    return local


def _stdlib_imports(referenced: set[str], seed: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    stdlib: dict[str, set[str]] = {k: set(v) for k, v in (seed or {}).items()}
    for token in referenced:
        if token in _STDLIB:
            module, symbol = _STDLIB[token]
            stdlib.setdefault(module, set()).add(symbol)
    return stdlib


def dataclass_domain_import_block(
    field_types: list[str],
    *,
    subdomain: str,
    domain_subdomains: dict[str, str],
    has_post_init: bool,
) -> str:
    """Imports for an entity or value object: `dataclass`, the stdlib types its fields
    reference, the sibling domain types (enums/VOs/entities) they reference, and
    `ValidationError` when a scaffolded `__post_init__` will raise it."""
    referenced = {t for ft in field_types for t in type_tokens(ft)}
    stdlib = _stdlib_imports(referenced, {"dataclasses": {"dataclass"}})
    local = _local_domain_imports(referenced, subdomain=subdomain, domain_subdomains=domain_subdomains)
    if has_post_init:
        local.setdefault("..exceptions", set()).add("ValidationError")
    return _render([stdlib, local])


def dto_import_block(
    field_types: list[str],
    *,
    package: str,
    domain_subdomains: dict[str, str],
) -> str:
    """Imports for an application DTO (command/query/result).

    Stdlib types via their canonical import; domain types via absolute import through
    the subpackage (`from <package>.domain.<subdomain> import X`), per the
    application-layer rule that cross-layer imports are absolute.
    """
    referenced = {t for ft in field_types for t in type_tokens(ft)}
    stdlib = _stdlib_imports(referenced, {"dataclasses": {"dataclass"}})
    local: dict[str, set[str]] = {}
    for token in referenced:
        owner = domain_subdomains.get(token)
        if owner is not None:
            local.setdefault(f"{package}.domain.{owner}", set()).add(token)
    return _render([stdlib, local])


def protocol_import_block(
    method_signatures: list[str],
    *,
    subdomain: str,
    domain_subdomains: dict[str, str],
) -> str:
    """Imports for a `typing.Protocol` (repository or capability): `Protocol`, stdlib
    types in the signatures, and the domain types they reference (relative)."""
    referenced = {t for sig in method_signatures for t in type_tokens(sig)}
    stdlib = _stdlib_imports(referenced, {"typing": {"Protocol"}})
    local = _local_domain_imports(referenced, subdomain=subdomain, domain_subdomains=domain_subdomains)
    return _render([stdlib, local])
