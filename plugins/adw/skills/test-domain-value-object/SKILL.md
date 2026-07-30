---
name: test-domain-value-object
description: The house form for one value object's unit test — canonical-equality and one `test_*` per `__post_init__` invariant. Skip the file entirely when the VO is a plain frozen dataclass with no `__post_init__` and no custom equality: Python already guarantees that.
when_to_use: Writing or changing the unit test for a domain value object.
paths: tests/**
---

# Test — Domain Value Object

Produces one unit-test file for one domain value object — only when there is something custom to test. Stdlib + `pytest` + `<root>.domain.*` only.

## When to use vs. neighbours

- A frozen value object with `__post_init__` invariants or a canonicalization rule → this skill.
- A frozen value object with neither `__post_init__` nor custom equality → **do not invoke this skill**; Python guarantees the contract for free.
- An entity (UUID identity, mutable) → `test-domain-entity`.
- An enum → `test-domain-enum`.
- A service → `test-domain-service`.
- A grep-firewall rule → `test-architecture-rule`.

## Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<vo_snake>.py
```

(No `_value_object` suffix — `test_foo_key.py`, not `test_foo_key_value_object.py`.)

### Canonical-form equality + invariant

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.foos import FooKey

def test_canonical_equality() -> None:
    a = FooKey(raw="abc", canonical="ABC")
    b = FooKey(raw="ABC", canonical="ABC")

    assert a == b
    assert hash(a) == hash(b)

def test_rejects_empty() -> None:
    with pytest.raises(ValidationError) as exc:
        FooKey(raw="", canonical="")
    assert exc.value.context["field"] == "canonical"
```

### Invariant only (no canonicalization)

```python
import pytest

from myapp.domain.exceptions import ValidationError
from myapp.domain.amounts import Money

def test_amount_must_be_non_negative() -> None:
    with pytest.raises(ValidationError) as exc:
        Money(amount=-1, currency="USD")
    assert exc.value.context["field"] == "amount"

def test_currency_must_be_three_letters() -> None:
    with pytest.raises(ValidationError) as exc:
        Money(amount=1, currency="US")
    assert exc.value.context["field"] == "currency"
```

## Rules

1. **Skip the file entirely when the VO has no `__post_init__` and no custom `__eq__`.** Frozen-dataclass equality is given by Python's data model — testing it adds maintenance with no defect-detection value. The skill produces no file in this case.
2. **Canonical-form equality tests pin the rule, not Python's `==`.** Two instances with the same `canonical` field must be equal even when their `raw` fields differ. `hash` must agree.
3. **One `test_*` per `__post_init__` invariant.** Pattern: `with pytest.raises(ValidationError) as exc:` then `assert exc.value.context["field"] == "<field>"`.
4. **No `_make_*` builder.** Value objects are small — pass fields directly. Builders are for many-field entities (`test-domain-entity`).
5. **No `@pytest.fixture`.** Tests construct the VO directly.
6. **Assert literal canonical values.** `canonical="ABC"` — don't compute the expected canonical form in the test, or both sides may agree on a bug.

## Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

## Hard stops

- VO has no `__post_init__` and no custom `__eq__` → stop, no file is produced; the contract is Python's data model.
- Spec asks for the test to touch infrastructure → stop, value objects have no IO.
- Spec asks to mock anything → stop, no IO to stub.
- Spec re-implements the canonicalization rule in the test → stop, assert literal canonical values.
- Spec adds a builder → stop, VOs are constructed inline.
