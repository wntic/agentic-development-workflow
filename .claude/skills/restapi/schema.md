<!-- merged from restapi-schema -->

# REST API Schema

Produces one resource's schema module — the Pydantic models that define the HTTP wire format. Schemas are the boundary between FastAPI/JSON and the domain: domain entities never cross the wire, schemas never cross into application/domain code.

## When to use vs. neighbours

- Per-resource Pydantic schemas (request/response) → this skill.
- Cross-cutting `ErrorResponse` / `error_responses()` → `error-responses.md`.
- A cross-cutting request schema that **already exists** elsewhere (e.g. an auth login schema in `restapi/schemas/auth.py` when the app has auth, or a shared collection-reorder body when some resource has a reorder endpoint) → reuse it, don't re-declare it per resource. These are **feature-conditional**, not always present: an app with no auth has no `auth.py`, and an app with no reorderable resource has no `ReorderRequest` — don't assume either exists.
- The route that consumes these schemas → `endpoint.md`.

## File location

```
src/<root>/restapi/schemas/<module>.py        # the resource's schemas
src/<root>/restapi/schemas/__init__.py        # update to re-export
```

Sub-resource schemas live **in the same file as the parent** when they are only used through the parent router (e.g. `BarResponse` in `foos.py` if `bars` are nested under `/foos/{id}/bars`).

## Template

```python
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "FooCreateRequest",
    "FooListResponse",
    "FooResponse",
    "FooUpdateRequest",
]

class FooResponse(BaseModel):
    id: UUID
    name: str
    sort_order: int
    usage_count: int = 0

# This shows the OFFSET pagination shape. A resource whose domain-filter chose
# cursor paging (domain-filter Rule 5) instead carries `items`, `next_cursor:
# str | None`, `limit` — match whichever shape the filter declared (Rule 7).
class FooListResponse(BaseModel):
    items: Sequence[FooResponse]
    total: int
    limit: int
    offset: int

class FooCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    sort_order: int = 0

class FooUpdateRequest(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    sort_order: int | None = None
```

## Naming (exhaustive — do not invent alternates)

| Schema | Purpose |
|--------|---------|
| `<Resource>Response` | Single-entity GET / POST / PATCH response |
| `<Resource>ListResponse` | List GET response — `items` + the resource's pagination fields (offset: `total`/`limit`/`offset`; cursor: `next_cursor`/`limit`), matching `domain-filter` |
| `<Resource>CreateRequest` | POST body |
| `<Resource>UpdateRequest` | PATCH body — every field `T \| None = None` |
| `<Resource>WithXResponse` | Single-entity response that embeds a sub-resource collection |

Do **not** introduce alternates (`Dto`, `Schema`, `In`, `Out`). The five names above cover the wire surface.

## Rules

### Class form

1. **Every schema inherits directly from `pydantic.BaseModel`.** No shared base classes for "common fields" — repetition is fine; schemas should read top-to-bottom as the wire format.
2. **Order in the file:** `Response`, `ListResponse`, `CreateRequest`, `UpdateRequest`, then sub-resource variants. Reads above writes; single above list.

### Validation

3. **Validators live on `*Request` schemas only.** Use `Annotated[T, Field(min_length=..., max_length=..., ge=..., le=..., pattern=...)]`. Responses don't need validators — the data already passed domain invariants.
4. **`pydantic.Field` enforces input *shape* (length, range, pattern), not business rules.** Domain invariants belong on entities and policies, never here.

### PATCH semantics

5. **Every field on `*UpdateRequest` is `T | None = None`.** The handler interprets `None` as "leave unchanged"; an explicit value as "set to this". Non-negotiable — the command DTO encodes the same partial-update contract.
6. **`*CreateRequest` lists required fields without `None`** and uses defaults (`sort_order: int = 0`) for genuinely optional inputs.

### `*ListResponse`

7. **`*ListResponse` carries the resource's pagination shape — whichever one its `domain-filter` declared** (`domain-filter` Rule 5 picks exactly one), never a third:
   - **offset paging** → `items: Sequence[<Resource>Response]`, `total: int`, `limit: int`, `offset: int`.
   - **cursor paging** → `items: Sequence[<Resource>Response]`, `next_cursor: str | None`, `limit: int`.
   The route `endpoint.md` builds constructs whichever shape the filter uses, so the schema must match it (see `endpoint.md`'s cursor-list note). Don't mix the two.

### `__all__`

8. **Immediately after imports, before the first class.** List every public schema **alphabetically**, one symbol per line, trailing comma. The wildcard re-export depends on this — anything missing is invisible to routers.

### Imports

9. **Allowed:** `pydantic`, stdlib (`uuid`, `collections.abc`, `datetime`, `decimal`, `typing`), and **domain enums or value-object types only** (`FooCategory`, `Role`).
10. **Forbidden:** domain entities, dataclasses, repositories, application handlers, infrastructure types. Routers map field-by-field; the schema must not know about `Foo` the entity.
11. **No `from __future__ import annotations`** (project rule plus Pydantic needs runtime annotations).
12. **No `Optional[...]`** — `T | None`.

## What never goes in a schema file

- **No domain types beyond enums.** `FooResponse` does not import the `Foo` entity.
- **No business logic, computed properties, or `@validator`s that encode rules.** Use Pydantic's built-in `Field` constraints for shape; domain rules go elsewhere.
- **No persistence concerns.** No ORM mode, no `from_orm`, no SQLAlchemy types.
- **No shared base classes beyond `BaseModel`.**

## Package wiring

After writing the module, update `restapi/schemas/__init__.py`:

```python
from . import foos  # alphabetized with siblings
from .foos import *  # noqa: F403

__all__ = (
    foos.__all__
    # + sibling.__all__ ...
)
```

Both lines must be present — the wildcard import makes symbols reachable, and the package's own `__all__` advertises them. Routers `from ..schemas import (...)` only works because of these re-exports.

## Hard stops

- Spec asks `*Response` to validate input → stop, responses don't validate. The data already passed domain invariants.
- Spec asks `*CreateRequest` to allow all fields as `None` → stop, that's a `*UpdateRequest`.
- Spec asks for a shared base class to deduplicate fields across resources → stop, schemas are wire contracts; repetition is intentional.
- Spec asks to import a domain entity into the schema file → stop, mapping happens in the route.
