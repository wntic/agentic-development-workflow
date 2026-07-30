---
name: domain-ports
description: The house forms for the two `typing.Protocol` interfaces the domain owns and infrastructure implements by structural subtyping — a repository protocol (`I<Noun>Repository`, async CRUD-shaped, one per aggregate root) and a capability protocol (`ICan<Verb>`, one or two paired methods, for an action that is not a collection).
when_to_use: Producing or editing the interface an aggregate's data access or a single external action must satisfy.
paths: src/**/domain/**
---

# Domain Ports

The domain's outbound interfaces. Both are `typing.Protocol` modules holding method signatures and
nothing else; infrastructure satisfies them **structurally**, without importing them to inherit.

Two shapes, and the split is about mental model rather than size: a **repository** is the collection of
one aggregate root, a **capability** is a single action the domain needs but cannot perform itself.

## When to use vs. neighbours

- Aggregate-root data access — CRUD plus aggregate-specific reads → **repository protocol**.
- A single action that does IO or talks to an external system — file rendering, token verification, blob
  storage, a third-party gateway call → **capability protocol**.
- A pure-CPU operation such as JWT signature verification → **capability protocol**, with a sync method
  instead of async.
- The entity, value object, enum or filter record the signatures mention → `domain-model`.
- A rule needing cross-aggregate state, which *consumes* these protocols → `domain-service`.
- The concrete implementation → `infra-persistence` (a relational store) or `infra-store-repository` (a
  client-style store) for a repository; `infra-capability-adapter` for a capability. The protocol itself
  is store-agnostic; the choice is made by store profile (`conventions` block C).

## File location and naming

| | Path | Class |
|---|---|---|
| Repository | `src/<root>/domain/<subdomain>/i_<aggregate_snake>_repository.py` | `I<Aggregate>Repository` |
| Capability | `src/<root>/domain/<subdomain>/i_can_<verb_snake>.py` | `ICan<Verb>` |

One protocol per module. Both prefixes are mandatory: `i_` marks a port, and `i_can_` distinguishes a
capability from a repository at a glance.

Place a capability where its primary input lives. Cross-cutting ones — auth, observability — go in their
own subdomain package (`domain/auth/`, `domain/observability/`).

## Template(s)

### Repository protocol

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

### Capability protocol — async (the default)

```python
from collections.abc import Sequence
from typing import Protocol

from .foo_export_row import FooExportRow

__all__ = ["ICanExportFoosXlsx"]

class ICanExportFoosXlsx(Protocol):
    async def export(self, rows: Sequence[FooExportRow]) -> bytes: ...
```

### Capability protocol — sync (pure CPU only)

```python
from typing import Protocol

from .foo_token import FooToken

__all__ = ["ICanVerifyFooToken"]

class ICanVerifyFooToken(Protocol):
    def verify(self, token: str) -> FooToken: ...
```

## Rules

### Both shapes

1. **`class IName(Protocol)` from `typing`.** Never `abc.ABC`, never a concrete base class.
2. **Method bodies are `...` on one line.** No docstrings, no default implementations.
3. **Parameters and return types are domain types or primitives.** Never SQLAlchemy rows, never SDK
   types, never Pydantic models.
4. **No `@runtime_checkable`** unless the codebase genuinely does `isinstance(x, IFoo)`. Default off.
5. **No explicit inheritance in infrastructure.** Satisfaction is structural; the adapter does not import
   this module to inherit from it.
6. **No class-level state and no helper methods.** Those belong in the adapter.

### Repository protocol

1. **Methods are always `async`.** A repository method touches IO once implemented, without exception.
2. **Keyword-only arguments (`*,`) for `list` / `count` and any multi-parameter method.** Positional
   arguments belong only on single-parameter lookups such as `get_by_id(id)`.
3. **Return-shape contract:**
   - `get_by_id` raises `NotFoundError` when missing — never returns `Foo | None`.
   - `get_by_<other>` may return `Foo | None` when "not found" is a non-error outcome.
   - `list` returns `Sequence[Foo]`, an immutable view.
   - `create` / `update` / `delete` return `None`.

### Capability protocol

1. **One method is the default; two is the maximum**, and only when tightly paired — `upload` plus
   `delete` on the same key. Three or more means splitting into several `ICan…` protocols, or that this
   is really a repository.
2. **Async unless the operation is pure CPU.** Anything that may do IO is `async`; sync is reserved for
   cryptographic, parsing and encoding helpers.

## Inlined typing / import rules

- Stdlib only — `typing`, `collections.abc`, `uuid`, `datetime` — plus relative domain imports. No
  third-party. No `from __future__ import annotations`.
- `X | None`. `Sequence[T]` from `collections.abc` for read-only views.
- Full annotations on every parameter and every return type.
- No comments unless a non-obvious *why*; one short line at most.

## Package wiring

Follow `general-python-package` to add `from .i_<name> import *` to the subdomain's `__init__.py` and
extend its `__all__`.

## Hard stops

- Spec lists more than about three single-action methods that share no collection mental model → stop,
  that is one or more capability protocols, not a repository.
- A capability's method count would grow past two → stop, split the protocol or model it as a repository.
- Spec asks for SQL, SDK or framework types on a signature → stop, those are infrastructure concerns.
- Spec asks the protocol to inherit from an `ABC` or a concrete base → stop, this codebase uses
  `typing.Protocol` only.
- Spec asks for a default implementation on the protocol → stop, that is behaviour leaking into a domain
  interface; it belongs in the adapter.
