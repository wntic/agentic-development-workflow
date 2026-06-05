---
name: test-domain-service
description: Apply when adding or modifying a unit test for one domain service — either an orchestrator that takes injected protocols (uniqueness check, existence guard, signing capability) or a pure-logic service with no injected dependencies (canonicalizer, validator). Produces one test file at `tests/unit/domain/<subdomain>/test_<service_snake>_service.py` (orchestrator) or `tests/unit/domain/<subdomain>/test_<service_snake>.py` (pure-logic). Orchestrator tests inject a minimal inline class implementing only the protocol methods the service actually calls (not a `Fake*Repository`); pure-logic tests construct the service once at module scope and assert against literal expected outputs plus a `test_idempotent` for canonicalizers. Does not produce entity tests (use `test-domain-entity`), value-object tests (use `test-domain-value-object`), enum tests (use `test-domain-enum`), or integration tests.
---

# Test — Domain Service

Produces one unit-test file for one domain service. Two flavors: orchestrators (with injected protocols — uniqueness checks, existence guards) and pure-logic services (no dependencies — URL canonicalizers, hash transformers). Stdlib + `pytest` + `<root>.domain.*` only. No fixtures, no mocks, no fakes from `tests/unit/fakes/`, no IO outside the inline protocol stub.

## When to use vs. neighbours

- A domain service class (with or without injected protocols) → this skill.
- An entity → `test-domain-entity`.
- A value object → `test-domain-value-object`.
- An enum → `test-domain-enum`.
- The infrastructure adapter that implements the protocol the service depends on → not a domain test; `test-repository-contract`.
- The application handler that *uses* the service → end-to-end through the API; `test-restapi-endpoint`.

## Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<service_snake>_service.py        # orchestrator
└── test_<service_snake>.py                # pure-logic (no `_service` suffix)
```

### Orchestrator — minimal inline-class stub

```python
import pytest

from myapp.domain.exceptions import FooConflictError
from myapp.domain.foos import FooUniquenessService

def _service(existing_keys: list[str] | None = None) -> FooUniquenessService:
    class _MinimalRepo:
        def __init__(self, keys: list[str]) -> None:
            self._keys = set(keys)

        async def exists_by_canonical_key(self, canonical_key: str) -> bool:
            return canonical_key in self._keys

    return FooUniquenessService(repo=_MinimalRepo(existing_keys or []))

async def test_assert_available_raises_when_present() -> None:
    service = _service(["abc"])
    with pytest.raises(FooConflictError):
        await service.assert_available("abc")

async def test_assert_available_passes_when_absent() -> None:
    service = _service([])
    await service.assert_available("abc")  # does not raise
```

### Pure-logic service

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import UrlCanonicalizer

c = UrlCanonicalizer()

def test_strips_trailing_slash() -> None:
    assert c.canonicalize("https://example.com/path/") == "https://example.com/path"

def test_drops_default_port() -> None:
    assert c.canonicalize("https://example.com:443/path") == "https://example.com/path"

def test_idempotent() -> None:
    samples = ["https://example.com/", "https://example.com/path/?b=2&a=1"]
    for s in samples:
        assert c.canonicalize(c.canonicalize(s)) == c.canonicalize(s)

def test_rejects_non_http() -> None:
    with pytest.raises(ValidationError):
        c.canonicalize("ftp://example.com")
```

## Rules

1. **Orchestrators use a minimal inline class, not a fake from `tests/unit/fakes/`.** The class implements only the protocol methods the service actually calls. This makes the service's true dependency surface visible — a service that "needs the whole repo" is probably an entity method in disguise.
2. **The `_service(...)` factory returns the constructed service.** Hides the inline-class plumbing from the body of each test.
3. **One `test_*` per behavior of each service method.** Naming follows the rule: `test_assert_available_raises_when_present`, `test_assert_available_passes_when_absent`. The test name **is** the spec line.
4. **Async tests are `async def test_*`** when the service method is async; `pytest-asyncio` runs in auto mode — never add `@pytest.mark.asyncio`.
5. **Pure-logic services construct one instance at module scope.** The service is stateless; per-test construction is wasted ceremony.
6. **Canonicalizers always include `test_idempotent`.** Loop a few representative inputs and assert `f(f(x)) == f(x)`. Idempotence is part of the canonicalization contract; forgetting it is the most common bug class.
7. **Pair every happy-path test with a rejection test.** `with pytest.raises(ValidationError):` for the negative case. Single-direction tests are incomplete.
8. **No mocks.** The inline class is a hand-written stub, not a `MagicMock`. Using mocks defeats the purpose of making the dependency surface visible.
9. **No `@pytest.fixture`.** The `_service(...)` factory is a module-level `def`.
10. **Assert literal expected values.** Don't re-implement the canonicalization in the test.

## Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Full annotations on the `_service(...)` factory and on the inline `_MinimalRepo`.
- Tests are `def test_*() -> None` (sync) or `async def test_*() -> None` (async).
- No `from __future__ import annotations`.

## Hard stops

- Spec asks to import a fake from `tests/unit/fakes/` → stop, that directory is gone; use a minimal inline class scoped to the `_service(...)` factory.
- Spec uses `MagicMock` / `AsyncMock` for the protocol stub → stop, hand-write the inline class so the dependency surface stays visible.
- Spec adds methods to the inline class that the service does not call → stop, the inline class implements exactly the called surface, no more.
- Spec adds `@pytest.mark.asyncio` → stop, auto mode handles async.
- Spec asks the test to touch a real database / HTTP endpoint → stop, that's `test-repository-contract` / `test-restapi-endpoint`.
- Pure-logic service test omits `test_idempotent` for a canonicalizer → stop, idempotence is part of the contract.
- Spec re-implements the rule in the test to compute the expected value → stop, assert literal values.
