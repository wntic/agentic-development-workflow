---
name: test-domain-entity
description: Apply when adding or modifying a unit test for one domain entity. Produces one test file at `tests/unit/domain/<subdomain>/test_<entity>_entity.py` with the identity-equality block (entity equality is by id only; `hash` agrees with `eq`), a module-level `_make_<entity>(**overrides)` builder for many-field entities, and one `test_*` function per `__post_init__` invariant using the `with pytest.raises(ValidationError) as exc: assert exc.value.context["field"] == "<field>"` pattern. Stdlib + `pytest` + `<root>.domain.*` only — no fixtures, no mocks, no fakes, no IO. Does not produce value-object tests (use `test-domain-value-object`), enum tests (use `test-domain-enum`), service tests (use `test-domain-service`), or any integration test (use `test-restapi-endpoint` / `test-repository-contract`).
---

# Test — Domain Entity

Produces one unit-test file for one domain entity. Sync `def` tests; entities have no IO. Asserts identity equality and every `__post_init__` invariant. Nothing else.

## When to use vs. neighbours

- A `@dataclass` entity with UUID identity → this skill.
- A frozen `@dataclass(frozen=True)` value object → `test-domain-value-object`.
- A `StrEnum` / `Enum` member set → `test-domain-enum`.
- A domain service (orchestrator with injected protocols, or pure-logic service) → `test-domain-service`.
- A grep-firewall architectural rule → `test-architecture-rule`.

## Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<entity_snake>_entity.py
```

### Standard template

```python
import uuid

import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import Foo

def _make_foo(**overrides) -> Foo:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        name="Test",
    )
    defaults.update(overrides)
    return Foo(**defaults)

def test_equality_by_id() -> None:
    shared_id = uuid.uuid4()
    a = Foo(id=shared_id, name="alpha")
    b = Foo(id=shared_id, name="beta")
    c = Foo(id=uuid.uuid4(), name="alpha")

    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert hash(a) != hash(c)

def test_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        _make_foo(name="")
    assert exc.value.context["field"] == "name"
```

The builder spreads **only the entity's real declared fields** (`id` + its domain fields). Two things it must NOT carry: `created_at`/`updated_at` (audit timestamps are a DB-managed table convention, never entity fields — the validator forbids them as reserved names, so constructing `Foo(created_at=...)` fails), and any `import datetime` that exists only to feed them. `datetime` enters this file **only** if a specific entity genuinely declares a datetime domain field. If the entity has a computed property/method, add one `test_*` per Rule 7 (an entity without one needs no such test).

### Few-field entity (skip the builder)

```python
import uuid

import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import Foo

def test_equality_by_id() -> None:
    shared_id = uuid.uuid4()
    assert Foo(id=shared_id, name="a") == Foo(id=shared_id, name="b")

def test_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        Foo(id=uuid.uuid4(), name="")
    assert exc.value.context["field"] == "name"
```

## Rules

1. **The four-line identity-equality block is the contract.** Entity equality is by id only; `hash` agrees with `eq`. Don't paraphrase.
2. **`_make_<entity>(**overrides)` is a module-level `def`** — never a `@pytest.fixture`. Defaults must be valid; no-override construction must succeed.
3. **No conditional logic in the builder.** Dumb spreader. Computations belong in tests.
4. **One `test_*` per `__post_init__` invariant.** Pattern: `with pytest.raises(ValidationError) as exc:` then `assert exc.value.context["field"] == "<field>"`.
5. **Group multiple failure modes of the same invariant in one test.** Several `with pytest.raises(...)` blocks under one `test_*` named after the invariant.
6. **Don't test what `@dataclass` gives for free.** No tests for field equality on frozen dataclasses, hashability, immutability — those are guaranteed by Python's data model. Test only `__post_init__`, computed properties, and methods.
7. **Computed properties / methods get their own `test_*`** named after the rule — but only when the entity actually declares one (e.g. an entity with a computed `is_active` → `test_<entity>_is_active_when_...`). Don't add a lifecycle/archive test to an entity that has no such property; that is a per-aggregate feature, not a default.
8. **Assert against literal expected values.** Never re-implement the entity's logic to compute the expected value — that hides bugs where both sides have the same mistake.

## Inlined typing / import rules

- Stdlib (`uuid`, `datetime`) + `pytest` + `myapp.domain.*` only. No infrastructure, no application, no restapi, no pydantic, no SQLAlchemy.
- Full annotations on `_make_<entity>`; tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks the test to touch the database / an HTTP endpoint / S3 → stop, use `test-repository-contract` or `test-restapi-endpoint`.
- Spec asks to use `MagicMock` / `AsyncMock` / `monkeypatch` → stop, domain has no IO; mocks have no place here.
- Spec asks for the builder as a `@pytest.fixture` → stop, builders are module-level `def`.
- Spec asks to test `dataclass`-given equality / hash / immutability → stop, Python's data model already guarantees it; assert on `__post_init__` and methods only.
- Spec re-implements the invariant in the test ("compute expected slug from name, then assert") → stop, assert literal values.
- Spec asserts on log output / `caplog` → stop, entities don't log.
- Spec puts `created_at` / `updated_at` in the builder or treats them as entity fields → stop, audit timestamps are a DB-managed table convention the validator forbids on an entity; the builder spreads only the entity's real domain fields.
