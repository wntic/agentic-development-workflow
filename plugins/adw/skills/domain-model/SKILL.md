---
name: domain-model
description: "House style for the domain data model, all pure Python with zero third-party deps: entities (mutable `@dataclass`, identity equality, `__post_init__` invariants), value objects (frozen, value equality, the tunable-threshold variant), enums (`StrEnum`), filter records (frozen parameter bags with `frozenset` defaults), and the single `domain/exceptions.py` catalog."
when_to_use: Producing or editing a domain entity, value object, enum, filter, or exception class.
---
# Domain model — entities, value objects, enums, filters, exceptions

This merged skill covers 5 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


## Domain Entity

Produces one entity class in the domain layer. Out of scope: value objects, enums, protocols, repositories, policies, persistence, tests, package wiring (defer to `architecture` §Python Package Structure).

### Template

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

### Rules

1. **Form:** `@dataclass` (mutable). Never `frozen=True` on an entity — entities have a lifecycle. Frozen-by-value belongs to §Domain Value Object below.
2. **Identity equality is mandatory.** Override `__eq__` and `__hash__` to compare by `id` only. Never compare by all fields.
3. **`__post_init__` is the only place for invariants.** Raise `ValidationError(message, {"field": "<field>"})` — one raise per rule. Omit the method when there are no invariants.
4. **Cross-aggregate rules don't go here.** Uniqueness, authorization, "does referenced X exist" → `domain-ports` §Domain Service. Tunable thresholds (max size, quotas) → the tunable-VO variant in §Domain Value Object below. This skill only handles invariants the entity checks from its own fields.
5. **No inheritance.** No base classes, no `ABC`. Compose by holding other domain objects.

### Inlined typing / import rules (the only ones an entity needs)

- Stdlib only (`dataclasses`, `datetime`, `enum`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party libraries. No Pydantic. No SQLAlchemy. No `from __future__ import annotations`.
- `X | None` (never `Optional[X]`). `frozenset[T]` / `tuple[T, ...]` for collection fields on an entity (never `set` / `list`).
- Full annotations on every field and every method signature, including `-> None` on `__post_init__`.
- Default to no comments. Only add one when the *why* is non-obvious. One short line max — never multi-paragraph docstrings.

### Package wiring

After writing the module, follow `architecture` §Python Package Structure to add the subpackage `__init__.py` re-export line and append to its `__all__`.

### Hard stops

- Spec asks for behavior that needs another aggregate's state → stop, use `domain-ports` §Domain Service.
- Spec asks for a frozen object defined by content → stop, use §Domain Value Object below.
- Spec asks for repository methods or persistence → stop, use `domain-ports` §Domain Repository Protocol / `infra-persistence` `repository.md`.


## Domain Value Object

Produces one immutable value object in the domain layer. Two value objects are equal iff all their fields are equal. They never carry an identity field.

### When to use vs. neighbours

- The thing has a UUID and a lifecycle → §Domain Entity above.
- The thing is a closed set of named values → §Domain Enum below.
- The thing is a read-side parameter bag for repository queries → §Domain Filter Record below.
- Everything else that is "defined by its content" → this skill.

### Template — standard case (value equality across all fields)

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

### Template — escape hatch (normalized + raw form)

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

### Rules

1. **Form:** `@dataclass(frozen=True)`. Always frozen — a mutable value object is almost always a mistake (invariants checked in `__post_init__` no longer hold after mutation).
2. **No identity field.** No `id: UUID`. If the spec includes one, this is an entity — use §Domain Entity above instead.
3. **Value equality.** Use dataclass-generated equality. Override `__eq__` / `__hash__` only for the normalized-form escape hatch above.
4. **Invariants in `__post_init__`.** Raise `ValidationError(message, {"field": "<field>"})`. Omit the method when there are none.
5. **No inheritance.** Compose, don't inherit.
6. **No cross-aggregate logic.** Anything that needs another aggregate's state is a `domain-ports` §Domain Service, not a value-object invariant.

### Variant — tunable value object (configuration consumed by the domain)

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

- Sourced from `infra-integration` `settings.md` at the DI layer — the provider wires `FooExportTunable(max_rows=export_settings.provided.max_rows)`.
- Injected into domain services and application handlers, never into entities. Entities don't read tunables; services do.
- Same rules as any value object apply: frozen, no methods, primitive or VO fields only, never `float` for money/time.

Use this variant only when the value carries no domain semantics beyond "this is a knob to turn." If the value participates in the ubiquitous language (an `OrderTotal`, a `RetentionWindow` with behavior), it's an ordinary value object, not a tunable.

### Inlined typing / import rules

- Stdlib only (`dataclasses`, `datetime`, `decimal`, `enum`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None` (never `Optional[X]`). Collections on a value object are `frozenset[T]` / `tuple[T, ...]` (never `set` / `list`).
- Full annotations on every field and every method signature, including `-> None` on `__post_init__`.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `architecture` §Python Package Structure to register the module in the subpackage `__init__.py`.

### Hard stops

- Spec includes `id: UUID` and field mutation over time → stop, use §Domain Entity above.
- Spec describes a closed set of named string constants → stop, use §Domain Enum below.
- Spec needs cross-aggregate validation → stop, use `domain-ports` §Domain Service.


## Domain Enum

Produces one enum module in the domain layer. Use whenever the spec describes a fixed, closed set of named values — never reach for bare string constants or `class Status: ACTIVE = "active"`.

### When to use vs. neighbours

- Closed set of string-valued names → this skill (`StrEnum`).
- Closed set of non-string values → this skill (`Enum`).
- Open-ended sets, lookup tables, anything coming from a database row → not an enum; model as a value object or entity.

### Template — `StrEnum` (default, for string-valued sets)

```python
from enum import StrEnum

__all__ = ["Foo"]

class Foo(StrEnum):
    A = "A"
    B = "B"
    C = "C"
```

### Template — `StrEnum` with a pure-logic method

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

### Template — `Enum` (non-string values)

```python
from enum import Enum

__all__ = ["Foo"]

class Foo(Enum):
    A = 1
    B = 2
    C = 3
```

### Rules

1. **Pick the right base.** `StrEnum` for string-valued sets (almost always). `Enum` for integer or other non-string values. Never `IntEnum` for codes that look like strings.
2. **Member names are `SCREAMING_SNAKE_CASE`.** Values are usually identical to the name for `StrEnum`; do not invent lowercased values unless the wire format requires them.
3. **One enum per module.** Module name is the class in snake_case.
4. **Methods only when pure.** Anything touching another aggregate, IO, or external state is not an enum method — that's a domain service or a handler. Methods receive `self` and other enum values only.
5. **No inheritance from a custom base.** Inherit from `StrEnum` or `Enum` directly. Do not build "abstract enum" hierarchies.
6. **No constants pretending to be enums.** `class Status: ACTIVE = "active"` is banned even outside the domain layer; use `StrEnum`.

### Inlined typing / import rules

- Stdlib only (`enum`, `collections.abc`, `typing`). No third-party. No `from __future__ import annotations`.
- Methods carry full annotations, including `-> bool` / `-> None`.
- No comments unless the meaning of a member or method is non-obvious; one short line max.

### Package wiring

Follow `architecture` §Python Package Structure to register the module in the subpackage `__init__.py` and append to its `__all__`.

### Hard stops

- Spec asks for runtime-extensible values (load from a config file or DB) → stop, this isn't an enum; use a value object plus a lookup repository.
- Spec asks for behavior that needs another aggregate's state → stop, use `domain-ports` §Domain Service.
- Spec asks for persistence of enum values to a SQL column → still produces the enum here; the column type and SA mapping live in `infra-persistence` `table.md`.


## Domain Filter Record

Produces one frozen dataclass that aggregates the parameters of a read-side repository call. Filter records are domain objects: pure data, value equality, no IO, no Pydantic.

### When to use vs. neighbours

- Read-side params bag passed into a repository `list`/`count` call → this skill.
- A value held inside an entity → §Domain Value Object above.
- A closed set of sort keys → §Domain Enum above (and then referenced here).
- A query DTO crossing the application boundary → `application` `query.md`. The filter record may be reused there; the query DTO wraps it plus authorization context.

### Template

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

### Rules

1. **Frozen dataclass, value equality.** `@dataclass(frozen=True)`. Generated `__eq__` / `__hash__` — never override.
2. **Multi-valued filters are `frozenset[T]`.** Never `set[T]` or `list[T]`. Use `field(default_factory=frozenset)` so the default is a fresh empty frozenset, not shared state.
3. **Scalar filters use `T | None = None`.** `None` means "no constraint on this field". Never use sentinel strings or `-1`.
4. **Sort is an enum reference.** Never a bare string. The enum lives in its own module (see §Domain Enum above).
5. **Pagination shape is explicit.** Either `limit: int` + `offset: int` with sane defaults, or a `cursor: str | None`. Pick one — never both. If the spec doesn't say which, ask.
6. **No methods.** A filter record is a passive data bag. Anything computed (e.g. translating a sort key to a SQL column) belongs in the repository adapter.
7. **No business invariants.** A repository receives whatever the caller passed; range / authorization checks live in the query handler. The only validation acceptable here is that `limit > 0` and similar self-consistency rules — and even those are usually better placed in the application query DTO. Default to no `__post_init__`.

### Inlined typing / import rules

- Stdlib only (`dataclasses`, `datetime`, `decimal`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `frozenset[T]` / `tuple[T, ...]` for collections.
- Full annotations on every field.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `architecture` §Python Package Structure to register the module in the subpackage `__init__.py` and append to its `__all__`.

### Hard stops

- Spec asks the filter record to validate cross-aggregate state → stop, that's the query handler's job.
- Spec asks for a method that translates the filter to SQL → stop, that's the repository adapter's job (use `infra-persistence` `repository.md`).
- Spec needs both `limit/offset` and `cursor` → stop, pick one with the user.


## Domain Exception

The whole project uses a single error catalog: `src/<root>/domain/exceptions.py`. It holds the `DomainError` root plus one bare subclass per declared exception — every error the domain can raise lives in this one file, so the catalogue stays auditable.

The `DomainError` root is **always present**: it is the base every subclass inherits, not a declared entry. Each `domain.exceptions` entry is a subclass that overrides only `code` and `http_status`.

### When to use vs. neighbours

- A spec needs a new named error to express a domain rule violation → declare it as a `domain.exceptions` entry; this skill gives its shape. **First confirm no existing class already serves the rule** (scan `__all__` for a semantic match, read the candidate's body); if one fits, reuse it rather than minting a near-duplicate.
- A spec needs to map a low-level library exception to a domain exception inside a repository → `infra-persistence` `repository.md` (which references this skill for the target class name).
- A spec needs to advertise an error on a REST route → `restapi` `error-responses.md` (which references the new `code`).

### File shape (the contract every entry obeys)

`domain/exceptions.py` is the **only** sanctioned exception to "one class per module" — exception classes are small and belong together so the catalogue stays auditable.

- `__all__` at the top, alphabetized.
- `DomainError` is the root. **It defines `code: str` and `http_status: int` with type annotations and defaults, plus the `__init__` that accepts `(message, context=None)` and stores `self.context`.**
- Every subclass declares `code` and `http_status` as **bare class attributes** (no type annotation — the type is inherited from `DomainError`'s annotation).
- **No subclass overrides `__init__`.** Every subclass automatically accepts `(message, context=None)` because it inherits from `DomainError`.
- A subclass may inherit from another subclass when it's a refinement (e.g. `InUseError(ConflictError)`), in which case it also inherits `http_status` unless explicitly overridden.
- Order: `__all__` (alphabetized), then `DomainError`, then direct subclasses, then refinements of subclasses (e.g. `InUseError(ConflictError)` after `ConflictError`).

### Catalog file shape (illustrative)

A populated `domain/exceptions.py` — the `DomainError` root plus the common errors a typical catalog declares. Which subclasses actually appear is determined by the app's declared set of exceptions; the shapes below are the form each takes.

```python
__all__ = [
    "ConflictError",
    "DomainError",
    "ForbiddenError",
    "InUseError",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationError",
]

class DomainError(Exception):
    code: str = "DOMAIN_ERROR"
    http_status: int = 500

    def __init__(self, message: str, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, object] = context if context is not None else {}

class NotFoundError(DomainError):
    code = "NOT_FOUND"
    http_status = 404

class ConflictError(DomainError):
    code = "CONFLICT"
    http_status = 409

class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    http_status = 422

class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    http_status = 403

class UnauthorizedError(DomainError):
    code = "UNAUTHORIZED"
    http_status = 401

class InUseError(ConflictError):
    code = "IN_USE"
    http_status = 409
```

### How one declared exception renders

Each `domain.exceptions` entry is a bare subclass of `DomainError` — or of the most specific existing parent, when a subclass is a semantic match (a refinement inherits `http_status` unless it differs):

```python
class FooConflictError(ConflictError):
    code = "FOO_NAME_TAKEN"
    http_status = 409  # omit this line when it equals the parent's value
```

That's the entire class body. No `__init__`, no fields, no methods — the `(message, context=None)` constructor is inherited.

### How a custom subclass is raised (reference — not produced by this skill)

Custom exceptions still carry `context`. The raise site (in `infrastructure/` or `application/`) passes a `context` dict whose keys express the structured detail:

```python
raise FooConflictError(
    "foo name already exists",
    {"name": foo.name},
)
```

The skill does not enforce the keys — the raise site and its test agree on them (e.g. the repository's `IntegrityError` translation in `infra-sqlalchemy-repository._map_integrity_error` and the handler test assert the same `context` keys).

### Rules

1. **Never define exceptions outside `domain/exceptions.py`.** Not in `application/`, not in `infrastructure/`, not in `restapi/`. New classes are added to this file or not at all.
2. **Never inherit from bare `Exception` or stdlib exceptions.** Inherit from `DomainError` or one of its subclasses.
3. **`code` is a stable contract.** Once shipped, never rename or reassign a `code` — API clients depend on it. If the meaning changes, add a new class with a new `code` and deprecate the old one in a separate spec.
4. **Subclasses don't override `__init__`.** The base accepts `(message, context=None)`. If a subclass needs structured detail, the caller populates `context={...}` at the raise site.
5. **Subclass class attributes use bare assignment.** `code = "X"`, not `code: str = "X"`. The annotation lives on `DomainError`; subclasses just override the value.
6. **`http_status` is inherited from the parent unless explicitly overridden.** Only set it when it differs from the parent's value.
7. **`code` values are `SCREAMING_SNAKE_CASE`.** Keep them consistent — the public catalog and dashboards depend on the format.
8. **Every `code` is unique** across the catalog — two classes never share a `code`.

### Inlined typing / import rules

- Stdlib-only — no third-party imports. No `from __future__ import annotations`.
- `DomainError`'s class attributes carry annotations (`code: str = ...`, `http_status: int = ...`); subclasses do not re-annotate.
- `DomainError.__init__` is fully annotated, including `-> None`.

### Hard stops

- The spec asks to raise a new exception type from outside `domain/exceptions.py` → stop, define it here first.
- The spec asks to log the error at the raise site → stop, logging happens centrally (`python-style` §Logging for the rule; `restapi` `error-responses.md` for HTTP).
- The new class would duplicate an existing one's semantics → stop and recommend reuse.
- The spec asks the subclass to override `__init__` or carry extra fields → stop, structured detail goes through the inherited `context` dict at the raise site.
