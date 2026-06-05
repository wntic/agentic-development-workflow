---
name: general-typing-conventions
description: Apply when writing or modifying any type annotation anywhere in the codebase (domain, application, infrastructure, entrypoints). Enforces `X | None` over `Optional[X]`, the prohibition on `from __future__ import annotations`, the `Any`-only-at-raw-external-boundaries rule, `TypeAlias` for repeated complex types, immutable collection types in domain (`frozenset` / `tuple` over `set` / `list`), full annotation coverage on every signature, and selective `@runtime_checkable` use on protocols.
---

# Typing Conventions

Project-wide typing rules. They apply to every layer — domain, application, infrastructure, restapi — and are stricter than CPython's defaults to keep runtime introspection cheap and the type-checker honest.

## When to use vs. neighbours

- Writing or modifying any type annotation anywhere in the codebase → consult this skill.
- Package mechanics (one class per module, `__all__`, re-exports) → `general-python-package`.
- Import shape (relative vs absolute, collapsed imports) → `general-imports-conventions`.
- Layer boundaries (what each layer may import) → `general-layered-architecture`.
- Domain object collection types (`frozenset` vs `set`) — same rules; this skill is referenced by `domain-entity`, `domain-value-object`, `domain-filter`.

## Core rules

### `X | None`, not `Optional[X]`

```python
# yes
name: str | None = None
def find(id: UUID) -> User | None: ...

# no
from typing import Optional
name: Optional[str] = None
```

PEP 604 union syntax is the project default. `Union[A, B]` is also banned — write `A | B`. This applies at every layer, including Pydantic models in `restapi/schemas/`.

### Never `from __future__ import annotations`

Do not add this import to any module. The project relies on **runtime annotation introspection** (Pydantic's validation, `dependency-injector`'s providers, dataclass `__post_init__` checks). Stringified annotations break those tools silently. Python 3.10+ is the runtime, so PEP 604 syntax already works without the future import.

If a third-party tool tells you to add it, the right fix is to change the annotation, not silence the runtime.

### Full coverage on every signature

Every function, method, and `__init__` parameter is fully annotated, including the return type. `-> None` is required for procedures. Lambdas inside business logic are forbidden (use named functions); lambdas inside `dataclasses.field(default_factory=...)` are fine because they don't carry annotations.

### `Any` only at raw external boundaries

`typing.Any` is permitted only where data has not yet been parsed:

- raw deserialized JSON before Pydantic validation
- third-party SDK return types we haven't yet narrowed
- `dict[str, Any]` for `context: dict[str, object] = ...` in `ErrorResponse`-style payloads — note this codebase uses `object`, not `Any`, when collecting heterogeneous values, because `object` requires explicit narrowing at consumption time

Inside `domain/`, `application/`, and the body of any handler, `Any` is forbidden. If a type is hard to express, introduce a `TypeAlias` or a small dataclass; do not reach for `Any`.

### `TypeAlias` for repeated complex types

```python
from typing import TypeAlias
FooKey: TypeAlias = tuple[UUID, int]
```

Use a `TypeAlias` whenever the same composite (`tuple[..., ...]`, `dict[str, frozenset[UUID]]`, callable signatures) appears in more than one signature. Place the alias at the top of the module that owns the concept, after imports and before classes. Re-export it via `__all__` if it crosses module boundaries.

For module-internal one-shot types, write the type out directly — premature aliases hide intent.

## Domain-layer collection types

Domain code uses **immutable** collection types so entities and value objects can hash/compare safely and so frozen dataclasses don't expose mutable state.

| Mutable (avoid in domain) | Immutable (use in domain) |
|--------------------------|---------------------------|
| `list[T]` | `tuple[T, ...]` for ordered, `Sequence[T]` for read-only views |
| `set[T]` | `frozenset[T]` |
| `dict[K, V]` | `Mapping[K, V]` for read-only views, frozen dataclass for fixed-shape records |

```python
# domain — frozen dataclass with immutable collections
@dataclass(frozen=True)
class Foo:
    id: UUID
    bar_ids: frozenset[UUID]
    items: tuple[Item, ...]
```

When a command DTO accepts collections from the entrypoint, the route converts on the boundary: `bar_ids=frozenset(payload.bar_ids)`, `items=tuple(item_inputs)`. The schema layer can hold `list[...]` (Pydantic's natural shape); the domain stores the frozen form.

`Sequence[T]` and `Mapping[K, V]` (from `collections.abc`) are the right return-type annotations for read-only views — they accept both `list`/`tuple` and `dict`/`MappingProxyType` at runtime.

Application and infrastructure code may use mutable collections **internally** (loop accumulators, building rows), but anything that crosses into a domain object is converted to its immutable counterpart.

## Protocols

- Use `typing.Protocol` for all interfaces (see `domain-protocols`).
- Apply `@runtime_checkable` **only** when `isinstance(x, IProtocol)` is genuinely needed. Avoid runtime checks against protocols in hot paths — they walk the protocol's `__protocol_attrs__` on every call.
- Protocol method signatures carry full annotations like any other function. Do not write `...` as a parameter default; the protocol body is `...` for the **method body**, not the parameters.

## Pydantic and FastAPI specifics

- `BaseModel` field types use the same `X | None` and PEP 585 generic forms (`list[int]`, `dict[str, str]`) — not `List[int]`, `Dict[str, str]`.
- `Annotated[T, Field(...)]` and `Annotated[T, Query(...)]` are the canonical form for adding constraints. Don't use the legacy `field: int = Field(default=...)` shape when there is no default — write `field: Annotated[int, Field(ge=1)]`.
- Schemas live in `restapi/schemas/` and never import from domain entities (see `restapi-schema`).

## Collections from `collections.abc`

Prefer `collections.abc` over `typing` for runtime-checkable abstract types:

| Use | Not |
|-----|-----|
| `collections.abc.Sequence` | `typing.Sequence` (deprecated alias) |
| `collections.abc.Mapping` | `typing.Mapping` |
| `collections.abc.Iterable` | `typing.Iterable` |
| `collections.abc.AsyncIterator` | `typing.AsyncIterator` |
| `collections.abc.Callable` | `typing.Callable` |

`typing.*` aliases for these are deprecated since 3.9; using `collections.abc` keeps imports consistent and avoids unnecessary `typing` imports.

## Hard stops

- `from __future__ import annotations` anywhere → stop, runtime annotation introspection (Pydantic, `dependency-injector`, dataclass `__post_init__`) breaks silently with stringified annotations.
- `Optional[X]` or `Union[A, B]` → stop, use `X | None` / `A | B`.
- Bare `Any` outside the documented external-boundary cases → stop, introduce a `TypeAlias` or a small dataclass; do not let `Any` spread.
- Untyped `**kwargs` / `*args` in domain or application code → stop, you're likely missing a dataclass.
- `cast(...)` to silence a type error → stop, fix the type. `cast` is acceptable only for narrowing after a runtime guard the checker can't follow (rare).
- `# type: ignore` without a reason → stop, use `# type: ignore[<rule>]` with a brief explanation.
- `TYPE_CHECKING`-only imports purely to break a circular import → stop, the cycle is usually a layering violation (see `general-layered-architecture`); fix the structure, not the import.
