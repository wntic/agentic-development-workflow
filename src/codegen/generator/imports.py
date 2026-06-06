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

import builtins
import importlib
import re

from .naming import snake_case

# Bare names that need NO import: Python's builtins plus the keyword-constants. This is the
# LANGUAGE's own set, not a hand-picked list of the types our manifests happen to use, so it
# never rots the way a per-type stdlib map did.
_NO_IMPORT: frozenset[str] = frozenset(dir(builtins)) | {"None", "True", "False"}

# Ordered stdlib modules a BARE type token is resolved against by introspection. The first module
# whose OWN namespace defines the symbol wins — verified via `obj.__module__` so a RE-EXPORT does
# not mis-resolve (e.g. `uuid` re-exports `Enum`, which must NOT resolve to uuid). Precedence:
# collections.abc before typing, collections before typing (their `typing.*` aliases are
# deprecated). Each entry covers its module's WHOLE surface for free — Counter/deque (collections),
# timedelta (datetime), Path (pathlib), Mapping/Iterable (collections.abc) — so a new type never
# means editing this list. A type from an UNSCANNED module is reached via a QUALIFIED name
# (`zoneinfo.ZoneInfo` → `import zoneinfo`), so this list is never a coverage ceiling.
_STDLIB_SCAN: tuple[str, ...] = (
    "uuid",
    "datetime",
    "decimal",
    "collections.abc",
    "collections",
    "pathlib",
    "typing",
)


def type_tokens(text: str) -> set[str]:
    """Identifier tokens in a type or signature string. A QUALIFIED name (`collections.Counter`)
    is captured as ONE token, so its import is derivable from the dotted path; a bare name is one
    token."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", text))


def resolve_import(token: str) -> tuple[str, str] | None:
    """Resolve one token from a type or signature string to the import it needs:

      * a builtin (`list`, `str`, `int`, …) → None (no import);
      * a QUALIFIED name (`collections.Counter`) → (`collections`, "") → `import collections`
        (the annotation keeps the dotted form verbatim — no signature rewriting);
      * a BARE name defined in a scanned stdlib module → (`module`, `token`) →
        `from module import token`;
      * anything else → None (no import).

    The last case is intentionally LENIENT, not an error: a signature string also yields
    non-type tokens (`self`, the method name, parameter names, `async`/`def`), and a
    locally-declared name (domain type / sibling schema) is the caller's to import. An
    unqualified EXOTIC type that slips through here emits no import — caught downstream as an
    undefined name by the reference-integrity gate (ruff F821), the loud catch; the fix is to
    qualify it (`zoneinfo.ZoneInfo`) or declare it.
    """
    if token in _NO_IMPORT:
        return None
    if "." in token:
        return (token.rpartition(".")[0], "")  # `import <prefix>`; the annotation stays qualified
    for module_name in _STDLIB_SCAN:
        obj = getattr(importlib.import_module(module_name), token, None)
        if obj is not None and getattr(obj, "__module__", None) == module_name:
            return (module_name, token)
    return None


def import_lines(groups: dict[str, set[str]]) -> list[str]:
    """Render a {module: {symbols}} mapping to import lines, isort-ordered: plain `import module`
    (an empty symbol set — a qualified type) before `from module import a, b`."""
    plain = sorted(m for m, names in groups.items() if not names)
    froms = sorted(m for m, names in groups.items() if names)
    return [f"import {m}" for m in plain] + [f"from {m} import {', '.join(sorted(groups[m]))}" for m in froms]


def _render(groups: list[dict[str, set[str]]]) -> str:
    blocks: list[str] = []
    for group in groups:
        lines = import_lines(group)
        if lines:
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


def stdlib_import_groups(
    referenced: set[str],
    skip: frozenset[str] | set[str] | dict[str, str],
    seed: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    """The {module: {symbols}} import groups for the NON-local tokens in `referenced`: builtins are
    dropped, a qualified name becomes a plain `import module` (empty set), a bare name resolves to a
    stdlib `from`-import, and anything unresolvable is dropped (see `resolve_import`). `skip` is any
    `in`-container of locally-declared names the CALLER imports itself (domain types, sibling
    schemas) — they are passed over here, not resolved (so a domain type that happens to share a
    stdlib name is not mis-imported)."""
    groups: dict[str, set[str]] = {k: set(v) for k, v in (seed or {}).items()}
    for token in referenced:
        if token in skip:
            continue
        spec = resolve_import(token)
        if spec is None:
            continue
        module, symbol = spec
        groups.setdefault(module, set())
        if symbol:
            groups[module].add(symbol)
    return groups


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
    stdlib = stdlib_import_groups(referenced, domain_subdomains, seed={"dataclasses": {"dataclass"}})
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
    stdlib = stdlib_import_groups(referenced, domain_subdomains, seed={"dataclasses": {"dataclass"}})
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
    stdlib = stdlib_import_groups(referenced, domain_subdomains, seed={"typing": {"Protocol"}})
    local = _local_domain_imports(referenced, subdomain=subdomain, domain_subdomains=domain_subdomains)
    return _render([stdlib, local])
