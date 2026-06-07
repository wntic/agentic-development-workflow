---
name: domain-service
description: Apply when a business rule needs context an entity can't see — uniqueness across the collection, "does referenced X exist", a hash/sign/canonicalize transformation, or anything that requires a repository or capability protocol. Produces one plain class module that takes injected protocols and exposes async/sync methods following the `assert_*` / `is_*` / verb convention. For tunable thresholds (max size, quotas) use `domain-value-object` (the tunable-VO pattern). Defers package mechanics to `general-python-package`.
---

# Domain Service

Produces one domain service: a stateless class that orchestrates a domain rule using injected protocols. Domain services live next to the aggregate they primarily concern. In DDD terms this is a *domain service*; the codebase uses the `*Service` suffix to mark it.

## When to use vs. neighbours

- Rule enforceable from one entity's own fields → not a service; use `__post_init__` on the entity (see `domain-entity`).
- Rule needs to query other aggregates or a domain capability → this skill.
- Rule is a numeric/boolean threshold (max rows, retention days) → not a service; model as a tunable value object via `domain-value-object`.
- Orchestrating a use case across multiple aggregates → that's a command/query handler, not a service (see `application-command`).

## File location and naming

- Path: `src/<root>/domain/<subdomain>/<class_snake>.py`. The filename always ends in `_service.py`.
- Class name: `<Concern>Service` (e.g. `FooUniquenessService`, `FooQuotaService`).

## Template

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

## Rules

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

## What a domain service is not

- Not an application handler — services don't know commands, queries, or transactions.
- Not a single-entity validator — that's `__post_init__`.
- Not an infrastructure adapter — depends on protocols, not on concrete clients.
- Not a dumping ground for unrelated helpers.

## Inlined typing / import rules

- Stdlib only plus relative domain imports. No third-party. No `from __future__ import annotations`.
- `X | None`. Full annotations on `__init__`, every method, and every parameter.
- No comments unless a non-obvious *why*; one short line max.

## Package wiring

Follow `general-python-package` to register the module in the subpackage `__init__.py` and append to its `__all__`. The DI provider that constructs this service is the responsibility of `infra-di-provider`, not this skill.

## Hard stops

- Method count grows past ~4–5 distinct rules → split into multiple services grouped by concern.
- The class needs to call a SQLAlchemy session directly → stop, model the access as a protocol method on the existing repository and depend on the protocol.
- The class needs to read settings → stop, wrap the relevant settings in a tunable value object (see `domain-value-object`) and inject that.
