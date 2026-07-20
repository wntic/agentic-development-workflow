---
name: domain-ports
description: House style for domain contracts and services: repository protocols (`IFooRepository`, async CRUD-shaped), capability protocols (`ICan<Verb>`, single-action), and stateless domain services that take injected protocols to enforce rules needing cross-aggregate state.
when_to_use: Producing a domain repository protocol, a capability protocol, or a domain service — the ports the application depends on and infrastructure implements by structural subtyping.
---
# Domain ports — protocols & services

This merged skill covers 3 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from domain-repository-protocol -->

## Domain Repository Protocol

Produces one protocol module: the collection-style data-access interface for a single aggregate root. Infrastructure implements it structurally (no explicit inheritance).

### When to use vs. neighbours

- Aggregate-root data access (CRUD + aggregate-specific reads) → this skill.
- A single-action capability that doesn't fit "collection of an aggregate" (file rendering, token verification, blob storage) → `domain-capability-protocol`.
- The concrete implementation → `infra-sqlalchemy-repository` (relational store, `infrastructure/postgres/repositories/`) or `infra-store-repository` (client-style store — qdrant/redis/…, `infrastructure/<store-kind>/repositories/`); the protocol itself is store-agnostic, the choice is the infra decision dispatched by store profile (`conventions` block C).

### File location and naming

- Path: `src/<root>/domain/<subdomain>/i_<aggregate_snake>_repository.py`
- Class name: `I<Aggregate>Repository` (PascalCase, `I` prefix).
- One protocol per module. The `i_` prefix is mandatory.

### Template

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

### Rules

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

### Inlined typing / import rules

- Stdlib only (`typing`, `collections.abc`, `uuid`, `datetime`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `Sequence[T]` (from `collections.abc`) for read-only views.
- Full annotations on every parameter and return type.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `general-python-package` to add `from .i_<aggregate>_repository import *` to the subpackage `__init__.py` and extend its `__all__`.

### Hard stops

- Spec lists more than ~3 single-action methods that don't share a collection mental model → stop, this is one or more `domain-capability-protocol`s, not a repository.
- Spec asks for SQL or framework types on a method signature → stop, those are infrastructure concerns.
- Spec asks the protocol to inherit from an `ABC` or a concrete base → stop, this codebase uses `typing.Protocol` only.


<!-- merged from domain-capability-protocol -->

## Domain Capability Protocol

Produces one protocol module: a narrow, action-shaped interface that infrastructure implements structurally. One method is the norm; two is acceptable when they are tightly paired (e.g. `upload` / `delete` on a blob store).

### When to use vs. neighbours

- Aggregate-root CRUD → `domain-repository-protocol`, not this skill.
- Single action that does IO or talks to an external system → this skill.
- Pure-CPU operation (e.g. JWT signature verification) → this skill, with a sync method instead of async.

### File location and naming

- Path: `src/<root>/domain/<subdomain>/i_can_<verb_snake>.py`
- Class name: `ICan<Verb>` (PascalCase, `ICan` prefix).
- One protocol per module. The `i_can_` prefix is mandatory and distinguishes a capability from a repository.

### Template — async (default)

```python
from collections.abc import Sequence
from typing import Protocol

from .foo_export_row import FooExportRow

__all__ = ["ICanExportFoosXlsx"]

class ICanExportFoosXlsx(Protocol):
    async def export(self, rows: Sequence[FooExportRow]) -> bytes: ...
```

### Template — sync (pure CPU only)

```python
from typing import Protocol

from .foo_token import FooToken

__all__ = ["ICanVerifyFooToken"]

class ICanVerifyFooToken(Protocol):
    def verify(self, token: str) -> FooToken: ...
```

### Rules

1. **`class ICanX(Protocol)` from `typing`.** Never `abc.ABC`.
2. **One method is the default; two is the maximum** and only when they are tightly paired (e.g. `upload` + `delete` on the same key). Three or more → split into multiple `ICan...` protocols or model it as a repository.
3. **Method bodies are `...`, one line.** No docstrings, no default implementations.
4. **Async unless the operation is pure CPU.** Anything that may do IO is `async`. Sync is reserved for cryptographic/parsing/encoding helpers.
5. **Parameters and return types are domain types or primitives.** Never SDK types, never Pydantic models.
6. **Place the protocol where its primary input lives.** Cross-cutting (auth, observability) capabilities go in their own subdomain package (`domain/auth/`, `domain/observability/`).
7. **No `@runtime_checkable`** unless `isinstance(x, ICanX)` is genuinely needed.
8. **No explicit inheritance in infrastructure.** Structural subtyping; infra adapter does not import this module to inherit.

### Inlined typing / import rules

- Stdlib only (`typing`, `collections.abc`, `uuid`, `datetime`) plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. `Sequence[T]` (from `collections.abc`) for read-only views.
- Full annotations on every parameter and return type.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `general-python-package` to add `from .i_can_<verb> import *` to the subpackage `__init__.py` and extend its `__all__`.

### Hard stops

- Method count would grow past two → stop, split the protocol or model it as a repository.
- The protocol carries class-level state or helper methods → stop, those belong in the adapter.
- Spec asks for a default implementation in the protocol → stop, that's behavior leaking into the domain interface.


<!-- merged from domain-service -->

## Domain Service

Produces one domain service: a stateless class that orchestrates a domain rule using injected protocols. Domain services live next to the aggregate they primarily concern. In DDD terms this is a *domain service*; the codebase uses the `*Service` suffix to mark it.

### When to use vs. neighbours

- Rule enforceable from one entity's own fields → not a service; use `__post_init__` on the entity (see `domain-entity`).
- Rule needs to query other aggregates or a domain capability → this skill.
- Rule is a numeric/boolean threshold (max rows, retention days) → not a service; model as a tunable value object via `domain-value-object`.
- Orchestrating a use case across multiple aggregates → that's a command/query handler, not a service (see `application-command`).

### File location and naming

- Path: `src/<root>/domain/<subdomain>/<class_snake>.py`. The filename always ends in `_service.py`.
- Class name: `<Concern>Service` (e.g. `FooUniquenessService`, `FooQuotaService`).

### Template

```python
from ..exceptions import FooConflictError
from .i_can_canonicalize_key import ICanCanonicalizeKey
from .i_foo_repository import IFooRepository

__all__ = ["FooUniquenessService"]

class FooUniquenessService:
    def __init__(
        self,
        repo: IFooRepository,
        canonicalizer: ICanCanonicalizeKey,
    ) -> None:
        self._repo = repo
        self._canonicalizer = canonicalizer

    def canonicalize(self, raw_key: str) -> str:
        return self._canonicalizer.canonicalize(raw_key)

    async def assert_available(self, canonical_key: str) -> None:
        if await self._repo.exists_by_canonical_key(canonical_key):
            raise FooConflictError("key already exists")

    async def is_taken(self, canonical_key: str) -> bool:
        return await self._repo.exists_by_canonical_key(canonical_key)
```

**Two forms.** An *orchestrator* service has collaborators: injected protocols on `__init__`, async
methods that touch them (the form above). A *pure* service has none: no `__init__` parameters, only
sync transformation methods (`canonicalize`, `derive_*`). The form follows directly from whether the
service has collaborators to inject.

### Rules

1. **Plain class, no dataclass decorator.** Domain services are not data — they're behavior with dependencies.
2. **Constructor takes only domain protocols, other services, or value objects.** Never concrete adapters. Never settings classes directly (settings flow through tunable value objects).
3. **Store dependencies on `_`-prefixed attributes.** No public attributes. No mutation outside `__init__`.
4. **Method-name convention:**
   - `assert_*` → raises a domain exception when the rule is violated, returns `None`.
   - `is_*` / `can_*` → returns `bool`, lets the caller decide.
   - Imperative verbs (`canonicalize`, `derive_*`, `hash_*`) for pure transformations.
5. **Async iff the method touches IO via an injected protocol.** Pure transformations are sync.
6. **Raise domain exceptions directly.** Don't catch and rewrap; the central error handler does that.
7. **No state beyond constructor dependencies.** No caches, no counters, no mutable attributes.
8. **No transport, persistence, or framework code.** The only IO is through the injected protocols.

### What a domain service is not

- Not an application handler — services don't know commands, queries, or transactions.
- Not a single-entity validator — that's `__post_init__`.
- Not an infrastructure adapter — depends on protocols, not on concrete clients.
- Not a dumping ground for unrelated helpers.

### Inlined typing / import rules

- Stdlib only plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. Full annotations on `__init__`, every method, and every parameter.
- No comments unless a non-obvious *why*; one short line max.

### Package wiring

Follow `general-python-package` to register the module in the subpackage `__init__.py` and append to its `__all__`. The DI provider that constructs this service is the responsibility of `infra-di-provider`, not this skill.

### Hard stops

- Method count grows past ~4–5 distinct rules → split into multiple services grouped by concern.
- The class needs to call a SQLAlchemy session directly → stop, model the access as a protocol method on the existing repository and depend on the protocol.
- The class needs to read settings → stop, wrap the relevant settings in a tunable value object (see `domain-value-object`) and inject that.
