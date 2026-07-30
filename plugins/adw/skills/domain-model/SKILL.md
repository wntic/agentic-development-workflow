---
name: domain-model
description: The house forms for the domain data model, all pure Python with no third-party imports — entities (mutable `@dataclass`, identity equality), value objects (frozen, value equality, plus the tunable-threshold variant), enums (`StrEnum`), and filter records (frozen parameter bags for repository reads).
when_to_use: Producing or editing a domain entity, value object, enum, or filter record. A single change usually touches several of them at once.
paths: src/**/domain/**
---

# Domain Model

The four data shapes of the domain layer. They share one substrate — stdlib only, no third-party
imports, full annotations — and a change that adds a capability usually adds several of them together,
which is why they live in one place.

Package mechanics (file placement, `__init__.py` re-exports) defer to `general-python-package`.

## When to use vs. neighbours

Inside this skill, pick by what the thing *is*:

- A thing with a UUID and a lifecycle → **Entity**.
- An immutable type defined by its content → **Value object**.
- A closed set of named values → **Enum**.
- A read-side parameter bag passed to a repository `list`/`count` → **Filter record**.
- An env-tunable threshold the domain consumes (max rows, retention days, quotas) → the **tunable
  variant** of a value object, not a service and not a settings class.

Outside it:

- The interface a repository or a capability must satisfy → `domain-ports`.
- A rule needing another aggregate's state, or a domain capability → `domain-service`.
- The single error catalog → `domain-exception`.
- A DTO crossing the application boundary → `application`. A filter record may be reused there; the
  query DTO wraps it plus authorization context.
- Persistence of any of these → `infra-persistence`.

## Template(s)

### Entity

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

### Value object — standard case (value equality across all fields)

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

The `@dataclass(frozen=True)`-generated `__eq__` / `__hash__` compare all fields. Do not override them
in the standard case.

### Value object — escape hatch (normalized plus raw form)

When the value object stores both a raw input and a normalized form — an email with the user-typed
string and the canonical lowercased version — equality must compare by the **canonical** field only,
otherwise two semantically equal values compare unequal.

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

### Value object — tunable variant (configuration the domain consumes)

A value object can serve as the domain-shaped view of an environment-tunable threshold (max upload
size, max export rows, retention days). The form is identical — frozen dataclass, primitive fields, no
methods — but the file is named `*_tunable.py` (or `*_limits.py`) and the class carries a
`<Concern>Tunable` suffix.

```python
from dataclasses import dataclass

__all__ = ["FooExportTunable"]

@dataclass(frozen=True)
class FooExportTunable:
    max_rows: int
    retention_days: int = 30
```

Distinguishing characteristics:

- Sourced from a settings class at the DI layer — the provider wires
  `FooExportTunable(max_rows=export_settings.provided.max_rows)`. See `infra-wiring`.
- Injected into domain services and application handlers, never into entities. Entities do not read
  tunables; services do.
- Every value-object rule still applies: frozen, no methods, primitive or VO fields only, never `float`
  for money or time.

Use this variant only when the value carries no domain meaning beyond "this is a knob to turn". If it
participates in the ubiquitous language — an `OrderTotal`, a `RetentionWindow` with behaviour — it is an
ordinary value object.

### Enum — `StrEnum` (the default, for string-valued sets)

```python
from enum import StrEnum

__all__ = ["Foo"]

class Foo(StrEnum):
    A = "A"
    B = "B"
    C = "C"
```

### Enum — `StrEnum` with a pure-logic method

Pure logic means it depends only on the enum's own values: no IO, no other aggregates. The common
shapes are ordering, ranking and membership tests.

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

A module-level constant like `_RANK` is allowed only when it encodes a pure mapping the enum uses. It
is private and excluded from `__all__`.

**`_RANK` is method-body logic, not part of the enum's declaration.** The template shows the *filled*
end state: `_RANK` exists only to serve `satisfies` and is written together with that method's body,
distilled from its rule ("rank order ADMIN >= AGENT >= MEMBER"). The type's public shape is its members
plus the method signature; `_RANK` is implementation, the same way a repository's
`_map_integrity_error` or a module-level `logger` is.

### Enum — `Enum` (non-string values)

```python
from enum import Enum

__all__ = ["Foo"]

class Foo(Enum):
    A = 1
    B = 2
    C = 3
```

### Filter record

```python
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from .foo_sort import FooSort

__all__ = ["FooListFilter"]

@dataclass(frozen=True)
class FooListFilter:
    parent_ids: frozenset[UUID] = field(default_factory=frozenset)
    created_from: date | None = None
    created_to: date | None = None
    sort: FooSort = FooSort.CREATED_AT_DESC
    limit: int = 50
    offset: int = 0
```

## Rules

### Entity

1. **Form:** `@dataclass`, mutable. Never `frozen=True` on an entity — entities have a lifecycle.
2. **Identity equality is mandatory.** Override `__eq__` and `__hash__` to compare by `id` only. Never
   compare by all fields.
3. **`__post_init__` is the only place for invariants.** Raise
   `ValidationError(message, {"field": "<field>"})`, one raise per rule. Omit the method when there are
   no invariants.
4. **Cross-aggregate rules do not go here.** Uniqueness, authorization, "does referenced X exist" → a
   domain service (`domain-service`). Tunable thresholds → the tunable variant above. An entity only
   checks invariants it can see from its own fields.
5. **No inheritance.** No base classes, no `ABC`. Compose by holding other domain objects.
6. **Audit timestamps are never entity fields.** `created_at` / `updated_at` are a DB-managed table
   convention. A read that needs them returns a read-model DTO projected from the row.

### Value object

1. **Form:** `@dataclass(frozen=True)`. Always frozen — a mutable value object is almost always a
   mistake, because invariants checked in `__post_init__` stop holding after mutation.
2. **No identity field.** No `id: UUID`. If one is called for, this is an entity.
3. **Value equality.** Use the dataclass-generated equality. Override `__eq__` / `__hash__` only for the
   normalized-form escape hatch.
4. **Invariants in `__post_init__`.** The same `ValidationError(message, {"field": ...})` shape as an
   entity. Omit the method when there are none.
5. **No inheritance.** Compose, do not inherit.
6. **No cross-aggregate logic.** Anything needing another aggregate's state is a domain service.

### Enum

1. **Pick the right base.** `StrEnum` for string-valued sets, which is almost always. `Enum` for integer
   or other non-string values. Never `IntEnum` for codes that look like strings.
2. **Member names are `SCREAMING_SNAKE_CASE`.** For a `StrEnum` the value is usually identical to the
   name; do not invent lowercased values unless the wire format requires them.
3. **One enum per module**, named after the class in snake_case.
4. **Methods only when pure.** Anything touching another aggregate, IO or external state is not an enum
   method. Methods receive `self` and other enum values only.
5. **No custom base class.** Inherit from `StrEnum` or `Enum` directly; no "abstract enum" hierarchies.
6. **No constants pretending to be enums.** `class Status: ACTIVE = "active"` is banned everywhere, not
   just in the domain.

### Filter record

1. **Frozen dataclass, value equality.** Generated `__eq__` / `__hash__` — never override.
2. **Multi-valued filters are `frozenset[T]`**, never `set[T]` or `list[T]`, with
   `field(default_factory=frozenset)` so the default is a fresh empty frozenset rather than shared
   state.
3. **Scalar filters use `T | None = None`.** `None` means "no constraint on this field". Never a
   sentinel string or `-1`.
4. **Sort is an enum reference**, never a bare string. The enum lives in its own module.
5. **One pagination shape, explicitly.** Either `limit: int` + `offset: int` with sane defaults, or
   `cursor: str | None`. Never both. If it is not stated which, ask.
6. **No methods.** A filter record is a passive data bag. Anything computed — translating a sort key to
   a SQL column, say — belongs in the repository adapter.
7. **No business invariants.** A repository receives whatever the caller passed; range and authorization
   checks live in the query handler. Default to no `__post_init__` at all.

## Inlined typing / import rules

These hold for all four shapes; the full rules are `python-style`.

- **Stdlib only**, plus relative domain imports. No third-party libraries — no Pydantic, no SQLAlchemy.
  The usable set is `dataclasses`, `datetime`, `decimal`, `enum`, `uuid`, `collections.abc`, `typing`;
  an enum module normally needs only `enum`.
- **No `from __future__ import annotations`**, anywhere in the project.
- `X | None`, never `Optional[X]`. Collection fields are `frozenset[T]` / `tuple[T, ...]`, never `set` /
  `list`.
- **Full annotations** on every field and every method signature, including `-> None` on
  `__post_init__`.
- Default to no comments. Add one only when the *why* is non-obvious, one short line — never a
  multi-paragraph docstring.

## Package wiring

After writing the module, follow `general-python-package` to add the subpackage `__init__.py` re-export
line and append to its `__all__`.

## Hard stops

- Spec asks for a frozen object defined by its content, with no identity → stop, that is a value object,
  not an entity. And the reverse: `id: UUID` plus mutation over time is an entity, not a value object.
- Spec asks for behaviour that needs another aggregate's state → stop, use `domain-service`.
- Spec asks for repository methods or persistence on any of these → stop, the interface is
  `domain-ports` and the adapter is `infra-persistence`.
- Spec asks for runtime-extensible "enum" values loaded from config or a database → stop, that is not an
  enum; model it as a value object plus a lookup repository.
- Spec asks for a filter-record method that translates the filter to SQL → stop, that is the repository
  adapter's job.
- Spec asks a filter record to validate cross-aggregate state, or to range-check its own fields → stop,
  that is the query handler's job (`application`).
- Spec needs both `limit`/`offset` and `cursor` on one filter → stop, pick one with the user.
- Spec puts `created_at` / `updated_at` on an entity → stop, audit timestamps are a DB-managed table
  convention; project them into a read-model DTO instead.
- Spec asks for enum values persisted to a SQL column → the enum still belongs here; the column type and
  its mapping live in `infra-persistence`.
