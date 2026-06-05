---
name: test-domain-enum
description: Apply when adding or modifying a unit test for one domain enum. Produces one test file at `tests/unit/domain/<subdomain>/test_<enum_snake>_enum.py` that pins every enum member's string value the database / API depends on and asserts that constructing the enum with an unknown value raises `ValueError`. When the enum defines pure-logic methods (e.g. `Role.satisfies(other)`), one additional `test_*` per method asserts the truth table. Stdlib + `pytest` + `<root>.domain.*` only. Does not produce entity tests (use `test-domain-entity`), value-object tests (use `test-domain-value-object`), service tests (use `test-domain-service`), or integration tests.
---

# Test — Domain Enum

Produces one unit-test file for one domain enum. Pins each member's value (typically a string the DB / wire format depends on), asserts unknown values are rejected, and covers any pure-logic methods on the enum.

## When to use vs. neighbours

- A `StrEnum` / `Enum` with closed-set members → this skill.
- An entity → `test-domain-entity`.
- A value object → `test-domain-value-object`.
- A service → `test-domain-service`.
- A grep-firewall rule → `test-architecture-rule`.

## Template(s)

```
tests/unit/domain/<subdomain>/
└── test_<enum_snake>_enum.py
```

### Standard template — values + rejection

```python
import pytest

from myapp.domain.foos import FooStatus

def test_values() -> None:
    assert FooStatus.ALPHA == "ALPHA"
    assert FooStatus.BETA == "BETA"

    with pytest.raises(ValueError):
        FooStatus("GAMMA")
```

### With a pure-logic method

```python
import pytest

from myapp.domain.auth import Role

def test_values() -> None:
    assert Role.SUPER_ADMIN == "SUPER_ADMIN"
    assert Role.ADMIN == "ADMIN"
    assert Role.COLLABORATOR == "COLLABORATOR"

    with pytest.raises(ValueError):
        Role("ROOT")

def test_satisfies() -> None:
    assert Role.SUPER_ADMIN.satisfies(Role.ADMIN) is True
    assert Role.ADMIN.satisfies(Role.ADMIN) is True
    assert Role.COLLABORATOR.satisfies(Role.ADMIN) is False
    assert Role.COLLABORATOR.satisfies(Role.COLLABORATOR) is True
```

## Rules

1. **Pin every member with an explicit assertion.** `assert FooStatus.ALPHA == "ALPHA"` — one line per member. The DB / wire format depends on these strings; a silent rename must break the test.
2. **Don't loop over members.** `for m in FooStatus: assert m.value == m.name` masks the bug it's supposed to catch — a renamed value still passes. Explicit asserts only.
3. **Always include the unknown-value rejection.** `with pytest.raises(ValueError): FooStatus("<unknown>")` proves the enum is closed.
4. **One `test_*` per pure-logic method on the enum.** Name the test after the method (`test_satisfies`, `test_is_terminal`). Inside, assert every relevant input/output pair with `is True` / `is False` for boolean returns — `==` may accidentally compare `int(1)` to `True`.
5. **No fixtures, no builders.** Enums are constants.
6. **No mocks.** Enums have no IO.

## Inlined typing / import rules

- Stdlib + `pytest` + `myapp.domain.*` only.
- Tests are `def test_*() -> None`.
- No `from __future__ import annotations`.

## Hard stops

- Spec proposes looping over members → stop, write explicit asserts.
- Spec asks the test to touch infrastructure → stop, enums have no IO.
- Spec asks for the test to import from `application` / `infrastructure` / `restapi` → stop, domain layer only.
- Spec asks to use `==` instead of `is` for boolean enum-method returns → stop, `is True` / `is False` prevents truthy-but-not-True bugs.
- The enum has no members listed in the spec → stop, members must be enumerated explicitly.
