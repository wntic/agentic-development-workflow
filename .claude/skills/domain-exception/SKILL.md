---
name: domain-exception
description: Apply when a spec requires `domain/exceptions.py` (bootstrap) or a new error class added to it. The file is the single error catalog for the whole project — one `DomainError` root with `code: str` + `http_status: int` class attributes and a `(message, context=None)` constructor that every subclass inherits unchanged. Subclasses use bare `code = "..."` / `http_status = ...` assignments and add nothing else. Does not handle raising — use `infra-sqlalchemy-repository` or `pattern-compensating-tx`. Does not handle HTTP translation — use `restapi-error-responses`.
---

# Domain Exception

The whole project uses a single error catalog: `src/<root>/domain/exceptions.py`. This skill has two modes:

- **Bootstrap** — the file doesn't exist yet. Create it with `DomainError` + the standard subclass set.
- **Extend** — the file exists. Insert one new class with a stable `code` (and `http_status` only when it differs from the parent).

Both modes operate on the same file and obey the same shape: classes inherit from `DomainError` (or a `DomainError` subclass), override only the two class attributes, and **inherit the `(message, context=None)` constructor unchanged**.

## When to use vs. neighbours

- A new project / first error class → bootstrap mode of this skill.
- A spec needs a new named error to express a domain rule violation → extend mode.
- A spec needs to map a low-level library exception to a domain exception inside a repository → `infra-sqlalchemy-repository` (which references this skill for the target class name).
- A spec needs to advertise an error on a REST route → `restapi-error-responses` (which references the new `code`).

## File shape (the contract every entry obeys)

`domain/exceptions.py` is the **only** sanctioned exception to "one class per module" — exception classes are small and belong together so the catalogue stays auditable.

- `__all__` at the top, alphabetized.
- `DomainError` is the root. **It defines `code: str` and `http_status: int` with type annotations and defaults, plus the `__init__` that accepts `(message, context=None)` and stores `self.context`.**
- Every subclass declares `code` and `http_status` as **bare class attributes** (no type annotation — the type is inherited from `DomainError`'s annotation).
- **No subclass overrides `__init__`.** Every subclass automatically accepts `(message, context=None)` because it inherits from `DomainError`.
- A subclass may inherit from another subclass when it's a refinement (e.g. `InUseError(ConflictError)`), in which case it also inherits `http_status` unless explicitly overridden.

## Bootstrap template — full `domain/exceptions.py`

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

Order: `__all__` (alphabetized), then `DomainError`, then direct subclasses, then refinements of subclasses (e.g. `InUseError(ConflictError)` after `ConflictError`).

## Extend template — adding one class

```python
class FooConflictError(ConflictError):
    code = "FOO_NAME_TAKEN"
    http_status = 409  # omit this line when it equals the parent's value
```

That's the entire class body. No `__init__`, no fields, no methods — the `(message, context=None)` constructor is inherited.

## How a custom subclass is raised (reference — not produced by this skill)

Custom exceptions still carry `context`. The raise site (in `infrastructure/` or `application/`) passes a `context` dict whose keys are agreed in the spec:

```python
raise FooConflictError(
    "foo name already exists",
    {"name": foo.name},
)
```

The skill does not enforce the keys — but the spec author should list them in `expected_context_keys` so downstream code (test assertions, `infra-sqlalchemy-repository._map_integrity_error`) populates the same keys.

## Rules

### Procedure — bootstrap mode

1. Confirm the file does not exist.
2. Create `src/<root>/domain/exceptions.py` using the bootstrap template above.
3. Pick the subclass set from `initial_subclasses`. Always include `DomainError`. Standard set covers most needs: `NotFoundError`, `ConflictError`, `ValidationError`, `ForbiddenError`, `UnauthorizedError`, `InUseError`.

### Procedure — extend mode

1. Read `domain/exceptions.py` in full.
2. Confirm no existing class already serves the spec's rule (search `__all__` for similar names; read candidate class bodies). If reuse is possible, **stop and recommend reuse**.
3. Pick the most specific existing parent. Direct inheritance from `DomainError` is only correct when no subclass is a semantic match.
4. Insert the new class in a position that respects inheritance order (parents above children). Place it next to siblings of the same parent so the file stays readable.
5. Insert `<ClassName>` into `__all__` in alphabetical order.
6. Verify the new `code` does not collide with any existing `code` in the file (every `code` must be unique across the catalog).

### Constraints

1. **Never define exceptions outside `domain/exceptions.py`.** Not in `application/`, not in `infrastructure/`, not in `restapi/`. New classes are added to this file or not at all.
2. **Never inherit from bare `Exception` or stdlib exceptions.** Inherit from `DomainError` or one of its subclasses.
3. **`code` is a stable contract.** Once shipped, never rename or reassign a `code` — API clients depend on it. If the meaning changes, add a new class with a new `code` and deprecate the old one in a separate spec.
4. **Subclasses don't override `__init__`.** The base accepts `(message, context=None)`. If a subclass needs structured detail, the caller populates `context={...}` at the raise site.
5. **Subclass class attributes use bare assignment.** `code = "X"`, not `code: str = "X"`. The annotation lives on `DomainError`; subclasses just override the value.
6. **`http_status` is inherited from the parent unless explicitly overridden.** Only set it when it differs from the parent's value.
7. **`code` values are `SCREAMING_SNAKE_CASE`.** Keep them consistent — the public catalog and dashboards depend on the format.

## Inlined typing / import rules

- Stdlib-only — no third-party imports. No `from __future__ import annotations`.
- `DomainError`'s class attributes carry annotations (`code: str = ...`, `http_status: int = ...`); subclasses do not re-annotate.
- `DomainError.__init__` is fully annotated, including `-> None`.

## Hard stops

- The spec asks to raise a new exception type from outside `domain/exceptions.py` → stop, define it here first.
- The spec asks to log the error at the raise site → stop, logging happens centrally (`general-logging` for the rule; `restapi-error-responses` for HTTP).
- The new class would duplicate an existing one's semantics → stop and recommend reuse.
- The spec asks the subclass to override `__init__` or carry extra fields → stop, structured detail goes through the inherited `context` dict at the raise site.
