---
name: domain-repository-protocol
description: Apply when a spec needs a repository interface for an aggregate root. Produces one `typing.Protocol` module named `i_<noun>_repository.py` with `I<Noun>Repository` containing async CRUD-shaped methods. Does not implement the protocol — infrastructure does that via `infra-sqlalchemy-repository`. Defers package mechanics to `general-python-package`.
---

# Domain Repository Protocol

Produces one protocol module: the collection-style data-access interface for a single aggregate root. Infrastructure implements it structurally (no explicit inheritance).

## When to use vs. neighbours

- Aggregate-root data access (CRUD + aggregate-specific reads) → this skill.
- A single-action capability that doesn't fit "collection of an aggregate" (file rendering, token verification, blob storage) → `domain-capability-protocol`.
- The concrete implementation in `infrastructure/postgres/repositories/` → `infra-sqlalchemy-repository`.

## File location and naming

- Path: `src/<root>/domain/<subdomain>/i_<aggregate_snake>_repository.py`
- Class name: `I<Aggregate>Repository` (PascalCase, `I` prefix).
- One protocol per module. The `i_` prefix is mandatory.

## Template

```python
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from .foo import Foo
from .foo_list_filter import FooListFilter

__all__ = ["IFooRepository"]

class IFooRepository(Protocol):
    async def list(self, *, filter: FooListFilter) -> Sequence[Foo]: ...
    async def count(self, *, filter: FooListFilter) -> int: ...
    async def get_by_id(self, id: UUID) -> Foo: ...
    async def get_by_name(self, name: str) -> Foo | None: ...
    async def create(self, foo: Foo) -> None: ...
    async def update(self, foo: Foo) -> None: ...
    async def delete(self, id: UUID) -> None: ...
```

## Rules

1. **`class IName(Protocol)` from `typing`.** Never `abc.ABC`, never a concrete base class.
2. **Methods are async by default.** Sync only for pure-CPU operations (e.g. a JWT verification capability — but that belongs in `domain-capability-protocol`, not here). Repository methods always touch IO when implemented, so they are always `async`.
3. **Method bodies are `...` (ellipsis), one line.** No docstrings. No default implementations.
4. **Return types are domain types or `None`.** `Foo`, `Sequence[Foo]`, `int`, `bool`, `Foo | None`, or `None`. Never SQLAlchemy rows, never Pydantic models.
5. **Use keyword-only arguments (`*,`) for `list` / `count` and any multi-parameter method.** Positional arguments belong only on single-parameter lookups (`get_by_id(id)`).
6. **Return shape contract:**
   - `get_by_id` raises `NotFoundError` when missing (no `Foo | None`).
   - `get_by_<other>` is allowed to return `Foo | None` when "not found" is a non-error outcome.
   - `list` returns `Sequence[Foo]` (immutable view).
   - `create` / `update` / `delete` return `None`.
7. **No `@runtime_checkable`** unless the codebase actually does `isinstance(x, IFooRepository)`. Default off.
8. **No explicit inheritance in infrastructure.** This is enforced via structural subtyping; the infra adapter does not import this module to inherit from it.

## Inlined typing / import rules

- Stdlib only (`typing`, `collections.abc`, `uuid`, `datetime`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `Sequence[T]` (from `collections.abc`) for read-only views.
- Full annotations on every parameter and return type.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to add `from .i_<aggregate>_repository import *` to the subpackage `__init__.py` and extend its `__all__`.

## Hard stops

- Spec lists more than ~3 single-action methods that don't share a collection mental model → stop, this is one or more `domain-capability-protocol`s, not a repository.
- Spec asks for SQL or framework types on a method signature → stop, those are infrastructure concerns.
- Spec asks the protocol to inherit from an `ABC` or a concrete base → stop, this codebase uses `typing.Protocol` only.
