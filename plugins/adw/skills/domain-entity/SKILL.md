---
name: domain-entity
description: Apply when a spec asks for a new domain entity — a thing with a UUID identity and a lifecycle. Produces exactly one mutable `@dataclass` with identity equality, optional `__post_init__` invariants, and the standard `__all__`. Does not produce value objects, enums, protocols, repositories, or tests — each is a separate skill. Defers package mechanics (file placement, `__init__.py` re-exports) to `general-python-package`.
---

# Domain Entity

Produces one entity class in the domain layer. Out of scope: value objects, enums, protocols, repositories, policies, persistence, tests, package wiring (defer to `general-python-package`).

## Template

```python
from dataclasses import dataclass
from uuid import UUID

from ..exceptions import ValidationError

__all__ = ["Foo"]

@dataclass
class Foo:
    id: UUID
    # required fields first; `field: T | None = None` after

    def __post_init__(self) -> None:
        # one block per invariant; omit method entirely if no invariants
        if not self.name:
            raise ValidationError("name must be non-empty", {"field": "name"})

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Foo):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
```

## Rules

1. **Form:** `@dataclass` (mutable). Never `frozen=True` on an entity — entities have a lifecycle. Frozen-by-value belongs to `domain-value-object`.
2. **Identity equality is mandatory.** Override `__eq__` and `__hash__` to compare by `id` only. Never compare by all fields.
3. **`__post_init__` is the only place for invariants.** Raise `ValidationError(message, {"field": "<field>"})` — one raise per rule. Omit the method when there are no invariants.
4. **Cross-aggregate rules don't go here.** Uniqueness, authorization, "does referenced X exist" → `domain-service`. Tunable thresholds (max size, quotas) → the tunable-VO variant in `domain-value-object`. This skill only handles invariants the entity checks from its own fields.
5. **No inheritance.** No base classes, no `ABC`. Compose by holding other domain objects.

## Inlined typing / import rules (the only ones an entity needs)

- Stdlib only (`dataclasses`, `datetime`, `enum`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party libraries. No Pydantic. No SQLAlchemy. No `from __future__ import annotations`.
- `X | None` (never `Optional[X]`). `frozenset[T]` / `tuple[T, ...]` for collection fields on an entity (never `set` / `list`).
- Full annotations on every field and every method signature, including `-> None` on `__post_init__`.
- Default to no comments. Only add one when the *why* is non-obvious. One short line max — never multi-paragraph docstrings.

## Package wiring

After writing the module, follow `general-python-package` to add the subpackage `__init__.py` re-export line and append to its `__all__`.

## Hard stops

- Spec asks for behavior that needs another aggregate's state → stop, use `domain-service`.
- Spec asks for a frozen object defined by content → stop, use `domain-value-object`.
- Spec asks for repository methods or persistence → stop, use `domain-repository-protocol` / `infra-sqlalchemy-repository`.
