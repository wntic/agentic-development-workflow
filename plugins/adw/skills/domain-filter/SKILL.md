---
name: domain-filter
description: Apply when a spec asks for a read-side parameter object passed to a repository `list`/`count` call (paging, sort, multi-valued filters). Produces one `@dataclass(frozen=True)` filter record with `frozenset` defaults, sort enum, and optional pagination fields. Does not produce repositories, query handlers, or schemas — each is a separate skill. Defers package mechanics to `general-python-package`.
---

# Domain Filter Record

Produces one frozen dataclass that aggregates the parameters of a read-side repository call. Filter records are domain objects: pure data, value equality, no IO, no Pydantic.

## When to use vs. neighbours

- Read-side params bag passed into a repository `list`/`count` call → this skill.
- A value held inside an entity → `domain-value-object`.
- A closed set of sort keys → `domain-enum` (and then referenced here).
- A query DTO crossing the application boundary → `application-query`. The filter record may be reused there; the query DTO wraps it plus authorization context.

## Template

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

1. **Frozen dataclass, value equality.** `@dataclass(frozen=True)`. Generated `__eq__` / `__hash__` — never override.
2. **Multi-valued filters are `frozenset[T]`.** Never `set[T]` or `list[T]`. Use `field(default_factory=frozenset)` so the default is a fresh empty frozenset, not shared state.
3. **Scalar filters use `T | None = None`.** `None` means "no constraint on this field". Never use sentinel strings or `-1`.
4. **Sort is an enum reference.** Never a bare string. The enum lives in its own module (use `domain-enum`).
5. **Pagination shape is explicit.** Either `limit: int` + `offset: int` with sane defaults, or a `cursor: str | None`. Pick one — never both. If the spec doesn't say which, ask.
6. **No methods.** A filter record is a passive data bag. Anything computed (e.g. translating a sort key to a SQL column) belongs in the repository adapter.
7. **No business invariants.** A repository receives whatever the caller passed; range / authorization checks live in the query handler. The only validation acceptable here is that `limit > 0` and similar self-consistency rules — and even those are usually better placed in the application query DTO. Default to no `__post_init__`.

## Inlined typing / import rules

- Stdlib only (`dataclasses`, `datetime`, `decimal`, `uuid`, `collections.abc`, `typing`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `frozenset[T]` / `tuple[T, ...]` for collections.
- Full annotations on every field.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to register the module in the subpackage `__init__.py` and append to its `__all__`.

## Hard stops

- Spec asks the filter record to validate cross-aggregate state → stop, that's the query handler's job.
- Spec asks for a method that translates the filter to SQL → stop, that's the repository adapter's job (use `infra-sqlalchemy-repository`).
- Spec needs both `limit/offset` and `cursor` → stop, pick one with the user.
