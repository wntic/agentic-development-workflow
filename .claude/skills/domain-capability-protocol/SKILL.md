---
name: domain-capability-protocol
description: Apply when a spec needs a single-action capability interface that does not fit "collection of an aggregate" — file rendering, token verification, blob storage, third-party gateway calls. Produces one `typing.Protocol` module named `i_can_<verb>.py` with `ICan<Verb>` containing one or two closely related methods. Does not implement it — infrastructure does that. Defers package mechanics to `general-python-package`.
---

# Domain Capability Protocol

Produces one protocol module: a narrow, action-shaped interface that infrastructure implements structurally. One method is the norm; two is acceptable when they are tightly paired (e.g. `upload` / `delete` on a blob store).

## When to use vs. neighbours

- Aggregate-root CRUD → `domain-repository-protocol`, not this skill.
- Single action that does IO or talks to an external system → this skill.
- Pure-CPU operation (e.g. JWT signature verification) → this skill, with a sync method instead of async.

## File location and naming

- Path: `src/<root>/domain/<subdomain>/i_can_<verb_snake>.py`
- Class name: `ICan<Verb>` (PascalCase, `ICan` prefix).
- One protocol per module. The `i_can_` prefix is mandatory and distinguishes a capability from a repository.

## Template — async (default)

```python
from collections.abc import Sequence
from typing import Protocol

from .foo_export_row import FooExportRow

__all__ = ["ICanExportFoosXlsx"]

class ICanExportFoosXlsx(Protocol):
    async def export(self, rows: Sequence[FooExportRow]) -> bytes: ...
```

## Template — sync (pure CPU only)

```python
from typing import Protocol

from .foo_token import FooToken

__all__ = ["ICanVerifyFooToken"]

class ICanVerifyFooToken(Protocol):
    def verify(self, token: str) -> FooToken: ...
```

## Rules

1. **`class ICanX(Protocol)` from `typing`.** Never `abc.ABC`.
2. **One method is the default; two is the maximum** and only when they are tightly paired (e.g. `upload` + `delete` on the same key). Three or more → split into multiple `ICan...` protocols or model it as a repository.
3. **Method bodies are `...`, one line.** No docstrings, no default implementations.
4. **Async unless the operation is pure CPU.** Anything that may do IO is `async`. Sync is reserved for cryptographic/parsing/encoding helpers.
5. **Parameters and return types are domain types or primitives.** Never SDK types, never Pydantic models.
6. **Place the protocol where its primary input lives.** Cross-cutting (auth, observability) capabilities go in their own subdomain package (`domain/auth/`, `domain/observability/`).
7. **No `@runtime_checkable`** unless `isinstance(x, ICanX)` is genuinely needed.
8. **No explicit inheritance in infrastructure.** Structural subtyping; infra adapter does not import this module to inherit.

## Inlined typing / import rules

- Stdlib only (`typing`, `collections.abc`, `uuid`, `datetime`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `Sequence[T]` (from `collections.abc`) for read-only views.
- Full annotations on every parameter and return type.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to add `from .i_can_<verb> import *` to the subpackage `__init__.py` and extend its `__all__`.

## Hard stops

- Method count would grow past two → stop, split the protocol or model it as a repository.
- The protocol carries class-level state or helper methods → stop, those belong in the adapter.
- Spec asks for a default implementation in the protocol → stop, that's behavior leaking into the domain interface.
