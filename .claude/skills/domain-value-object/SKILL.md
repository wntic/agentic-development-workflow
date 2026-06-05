---
name: domain-value-object
description: Apply when a spec asks for a domain value object — an immutable type defined by its content, not by an identity (e.g. a money amount, a normalized email, a coordinate). Produces one `@dataclass(frozen=True)` module with value equality, optional `__post_init__` invariants, and the standard `__all__`. Does not produce entities, enums, filters, protocols, or tests — each is a separate skill. Defers package mechanics to `general-python-package`.
---

# Domain Value Object

Produces one immutable value object in the domain layer. Two value objects are equal iff all their fields are equal. They never carry an identity field.

## When to use vs. neighbours

- The thing has a UUID and a lifecycle → `domain-entity`.
- The thing is a closed set of named values → `domain-enum`.
- The thing is a read-side parameter bag for repository queries → `domain-filter`.
- Everything else that is "defined by its content" → this skill.

## Template — standard case (value equality across all fields)

```python
from dataclasses import dataclass

from ..exceptions import ValidationError

__all__ = ["Foo"]

@dataclass(frozen=True)
class Foo:
    field_a: str
    field_b: int

    def __post_init__(self) -> None:
        if self.field_b < 0:
            raise ValidationError("field_b must be non-negative", {"field": "field_b"})
```

The `@dataclass(frozen=True)`-generated `__eq__` / `__hash__` compare all fields. Do not override them in the standard case.

## Template — escape hatch (normalized + raw form)

When the value object stores both a raw input and a normalized form (e.g. an email with both the user-typed string and the canonical lowercased version), equality must compare by the **canonical** field only — otherwise two semantically equal values compare unequal.

```python
from dataclasses import dataclass

__all__ = ["Foo"]

@dataclass(frozen=True)
class Foo:
    raw: str
    canonical: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Foo):
            return NotImplemented
        return self.canonical == other.canonical

    def __hash__(self) -> int:
        return hash(self.canonical)
```

## Rules

1. **Form:** `@dataclass(frozen=True)`. Always frozen — a mutable value object is almost always a mistake (invariants checked in `__post_init__` no longer hold after mutation).
2. **No identity field.** No `id: UUID`. If the spec includes one, this is an entity — use `domain-entity` instead.
3. **Value equality.** Use dataclass-generated equality. Override `__eq__` / `__hash__` only for the normalized-form escape hatch above.
4. **Invariants in `__post_init__`.** Raise `ValidationError(message, {"field": "<field>"})`. Omit the method when there are none.
5. **No inheritance.** Compose, don't inherit.
6. **No cross-aggregate logic.** Anything that needs another aggregate's state is a `domain-service`, not a value-object invariant.

## Variant — tunable value object (configuration consumed by the domain)

A value object can also serve as the domain-shaped view of an environment-tunable threshold (max upload size, max export rows, retention days). The form is identical — a frozen dataclass with primitive fields and no methods — but the file is named `*_tunable.py` (or `*_limits.py`) and the suffix on the class is `<Concern>Tunable` (e.g. `FooExportTunable`, `FooQuotaTunable`).

```python
from dataclasses import dataclass

__all__ = ["FooExportTunable"]

@dataclass(frozen=True)
class FooExportTunable:
    max_rows: int
    retention_days: int = 30
```

Distinguishing characteristics:

- Sourced from `infra-settings` at the DI layer — the provider wires `FooExportTunable(max_rows=export_settings.provided.max_rows)`.
- Injected into domain services and application handlers, never into entities. Entities don't read tunables; services do.
- Same rules as any value object apply: frozen, no methods, primitive or VO fields only, never `float` for money/time.

Use this variant only when the value carries no domain semantics beyond "this is a knob to turn." If the value participates in the ubiquitous language (an `OrderTotal`, a `RetentionWindow` with behavior), it's an ordinary value object, not a tunable.

## Inlined typing / import rules

- Stdlib only (`dataclasses`, `datetime`, `decimal`, `enum`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None` (never `Optional[X]`). Collections on a value object are `frozenset[T]` / `tuple[T, ...]` (never `set` / `list`).
- Full annotations on every field and every method signature, including `-> None` on `__post_init__`.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to register the module in the subpackage `__init__.py`.

## Hard stops

- Spec includes `id: UUID` and field mutation over time → stop, use `domain-entity`.
- Spec describes a closed set of named string constants → stop, use `domain-enum`.
- Spec needs cross-aggregate validation → stop, use `domain-service`.
