---
name: domain-enum
description: The house form for a closed set of named values in the domain — a role, a status, a sort key. One `StrEnum` (string-valued) or `Enum` (non-string) with `SCREAMING_SNAKE_CASE` members and, optionally, pure-logic methods on the enum itself.
when_to_use: Producing or editing a domain enum.
paths: src/**/domain/**
---

# Domain Enum

Produces one enum module in the domain layer. Use whenever the spec describes a fixed, closed set of named values — never reach for bare string constants or `class Status: ACTIVE = "active"`.

## When to use vs. neighbours

- Closed set of string-valued names → this skill (`StrEnum`).
- Closed set of non-string values → this skill (`Enum`).
- Open-ended sets, lookup tables, anything coming from a database row → not an enum; model as a value object or entity.

## Template — `StrEnum` (default, for string-valued sets)

```python
from enum import StrEnum

__all__ = ["Foo"]

class Foo(StrEnum):
    A = "A"
    B = "B"
    C = "C"
```

## Template — `StrEnum` with a pure-logic method

Pure logic means: depends only on the enum's own value(s), no IO, no other aggregates. Common shapes are ordering, ranking, or membership tests.

```python
from enum import StrEnum

__all__ = ["Foo"]

_RANK: dict[str, int] = {"A": 1, "B": 2, "C": 3}

class Foo(StrEnum):
    A = "A"
    B = "B"
    C = "C"

    def satisfies(self, required: Foo) -> bool:
        return _RANK[self.value] >= _RANK[required.value]
```

Module-level constants like `_RANK` are allowed only when they encode pure mappings the enum uses. They are private (leading underscore) and excluded from `__all__`.

**`_RANK` is method-body logic, not part of the enum's declaration.** This Template shows the *filled* end state; `_RANK` (the rank-order map) exists only to serve `satisfies` and is written together with that method's body, distilled from its rule (e.g. "rank order ADMIN >= AGENT >= MEMBER"). It is not part of the type's public shape: the enum's declaration is its members + the method signature, while `_RANK` is implementation — a module-level helper that serves a single method's body belongs to that body, the same way a repository's `_map_integrity_error` or a module-level `logger` does.

## Template — `Enum` (non-string values)

```python
from enum import Enum

__all__ = ["Foo"]

class Foo(Enum):
    A = 1
    B = 2
    C = 3
```

## Rules

1. **Pick the right base.** `StrEnum` for string-valued sets (almost always). `Enum` for integer or other non-string values. Never `IntEnum` for codes that look like strings.
2. **Member names are `SCREAMING_SNAKE_CASE`.** Values are usually identical to the name for `StrEnum`; do not invent lowercased values unless the wire format requires them.
3. **One enum per module.** Module name is the class in snake_case.
4. **Methods only when pure.** Anything touching another aggregate, IO, or external state is not an enum method — that's a domain service or a handler. Methods receive `self` and other enum values only.
5. **No inheritance from a custom base.** Inherit from `StrEnum` or `Enum` directly. Do not build "abstract enum" hierarchies.
6. **No constants pretending to be enums.** `class Status: ACTIVE = "active"` is banned even outside the domain layer; use `StrEnum`.

## Inlined typing / import rules

- Stdlib only (`enum`, `collections.abc`, `typing`). No third-party. No `from __future__ import annotations`.
- Methods carry full annotations, including `-> bool` / `-> None`.
- No comments unless the meaning of a member or method is non-obvious; one short line max.

## Package wiring

Follow `general-python-package` to register the module in the subpackage `__init__.py` and append to its `__all__`.

## Hard stops

- Spec asks for runtime-extensible values (load from a config file or DB) → stop, this isn't an enum; use a value object plus a lookup repository.
- Spec asks for behavior that needs another aggregate's state → stop, use `domain-service`.
- Spec asks for persistence of enum values to a SQL column → still produces the enum here; the column type and SA mapping live in `infra-sqlalchemy-table`.
