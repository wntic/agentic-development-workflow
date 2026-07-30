---
name: domain-exception
description: The house form for the project's single error catalog, `domain/exceptions.py` — a `DomainError` root carrying `code: str` + `http_status: int` and a `(message, context=None)` constructor every subclass inherits unchanged, plus one bare subclass per named error.
when_to_use: Adding a new domain error class, or laying the exceptions catalog for the first time.
paths: src/**/domain/**
---

# Domain Exception

The whole project uses a single error catalog: `src/<root>/domain/exceptions.py`. It holds the `DomainError` root plus one bare subclass per declared exception — every error the domain can raise lives in this one file, so the catalogue stays auditable.

The `DomainError` root is **always present**: it is the base every subclass inherits. Each named error is a
subclass that overrides only `code` and `http_status`.

## When to use vs. neighbours

- A new named error is needed to express a domain rule violation → this skill gives its shape. **First
  confirm no existing class already serves the rule** (scan `__all__` for a semantic match, read the candidate's body); if one fits, reuse it rather than minting a near-duplicate.
- A spec needs to map a low-level library exception to a domain exception inside a repository → `infra-sqlalchemy-repository` (which references this skill for the target class name).
- A spec needs to advertise an error on a REST route → `restapi-error-responses` (which references the new `code`).

## File shape (the contract every entry obeys)

`domain/exceptions.py` is the **only** sanctioned exception to "one class per module" — exception classes are small and belong together so the catalogue stays auditable.

- `__all__` at the top, alphabetized.
- `DomainError` is the root. **It defines `code: str` and `http_status: int` with type annotations and defaults, plus the `__init__` that accepts `(message, context=None)` and stores `self.context`.**
- Every subclass declares `code` and `http_status` as **bare class attributes** (no type annotation — the type is inherited from `DomainError`'s annotation).
- **No subclass overrides `__init__`.** Every subclass automatically accepts `(message, context=None)` because it inherits from `DomainError`.
- A subclass may inherit from another subclass when it's a refinement (e.g. `InUseError(ConflictError)`), in which case it also inherits `http_status` unless explicitly overridden.
- Order: `__all__` (alphabetized), then `DomainError`, then direct subclasses, then refinements of subclasses (e.g. `InUseError(ConflictError)` after `ConflictError`).

## Catalog file shape (illustrative)

A populated `domain/exceptions.py` — the `DomainError` root plus the common errors a typical catalog
carries. Which subclasses actually appear depends on the errors the domain needs; the shapes below are
the form each takes.

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

## How one error renders

Each named error is a bare subclass of `DomainError` — or of the most specific existing parent, when one
is a semantic match (a refinement inherits `http_status` unless it differs):

```python
class FooConflictError(ConflictError):
    code = "FOO_NAME_TAKEN"
    http_status = 409  # omit this line when it equals the parent's value
```

That's the entire class body. No `__init__`, no fields, no methods — the `(message, context=None)` constructor is inherited.

## How a custom subclass is raised (reference — not produced by this skill)

Custom exceptions still carry `context`. The raise site (in `infrastructure/` or `application/`) passes a `context` dict whose keys express the structured detail:

```python
raise FooConflictError(
    "foo name already exists",
    {"name": foo.name},
)
```

The skill does not enforce the keys — the raise site and its test agree on them (e.g. the repository's `IntegrityError` translation in `infra-sqlalchemy-repository._map_integrity_error` and the handler test assert the same `context` keys).

## Rules

1. **Never define exceptions outside `domain/exceptions.py`.** Not in `application/`, not in `infrastructure/`, not in `restapi/`. New classes are added to this file or not at all.
2. **Never inherit from bare `Exception` or stdlib exceptions.** Inherit from `DomainError` or one of its subclasses.
3. **`code` is a stable contract.** Once shipped, never rename or reassign a `code` — API clients depend on it. If the meaning changes, add a new class with a new `code` and deprecate the old one in a separate spec.
4. **Subclasses don't override `__init__`.** The base accepts `(message, context=None)`. If a subclass needs structured detail, the caller populates `context={...}` at the raise site.
5. **Subclass class attributes use bare assignment.** `code = "X"`, not `code: str = "X"`. The annotation lives on `DomainError`; subclasses just override the value.
6. **`http_status` is inherited from the parent unless explicitly overridden.** Only set it when it differs from the parent's value.
7. **`code` values are `SCREAMING_SNAKE_CASE`.** Keep them consistent — the public catalog and dashboards depend on the format.
8. **Every `code` is unique** across the catalog — two classes never share a `code`.

## Inlined typing / import rules

- Stdlib-only — no third-party imports. No `from __future__ import annotations`.
- `DomainError`'s class attributes carry annotations (`code: str = ...`, `http_status: int = ...`); subclasses do not re-annotate.
- `DomainError.__init__` is fully annotated, including `-> None`.

## Hard stops

- The spec asks to raise a new exception type from outside `domain/exceptions.py` → stop, define it here first.
- The spec asks to log the error at the raise site → stop, logging happens centrally (`general-logging` for the rule; `restapi-error-responses` for HTTP).
- The new class would duplicate an existing one's semantics → stop and recommend reuse.
- The spec asks the subclass to override `__init__` or carry extra fields → stop, structured detail goes through the inherited `context` dict at the raise site.
