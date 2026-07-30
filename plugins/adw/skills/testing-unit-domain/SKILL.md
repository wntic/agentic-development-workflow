---
name: testing-unit-domain
description: The house forms for the domain layer's unit tests — an entity (identity equality plus one test per `__post_init__` invariant), a value object (canonical equality, skipped entirely when there is nothing custom), an enum (every member's value pinned, unknown value rejected), and a domain service (a minimal inline protocol stub, or a module-scope instance for pure logic). Stdlib plus pytest plus the domain, nothing else.
when_to_use: Writing or changing the unit test for a domain entity, value object, enum or service.
paths: tests/**
---

# Testing — Domain Unit

The four kinds of test the domain layer takes. They share one constitution — no IO, no mocks, no
fixtures, stdlib plus `pytest` plus `myapp.domain.*` and nothing else — which is why they live together;
the differences are per-kind and small.

The broader testing constitution — the pyramid, the conftest hierarchy, speed targets — is
`test-principles`.

## When to use vs. neighbours

Inside this skill, by what is under test:

- A `@dataclass` entity with UUID identity → **Entity**.
- A frozen value object **with** `__post_init__` invariants or a canonicalization rule → **Value object**.
  With neither, **write no file at all**: Python's data model already guarantees frozen-dataclass
  equality, and a test for it is maintenance with no defect-detection value.
- A `StrEnum` / `Enum` member set → **Enum**.
- A domain service, with injected protocols or without → **Domain service**.

Outside it:

- An application command or query handler → `test-application-handler`.
- An in-memory fake under `tests/unit/fakes/` → `test-fake-repository`.
- A grep-firewall architectural rule → `test-architecture-rule`.
- The infrastructure adapter implementing a protocol a service depends on → `testing-contract`.
- The handler that *uses* a service, end to end → `test-restapi-endpoint`.

## Template(s)

File placement, and note the two suffix asymmetries:

| Under test | File |
|---|---|
| Entity | `tests/unit/domain/<subdomain>/test_<entity_snake>_entity.py` |
| Value object | `tests/unit/domain/<subdomain>/test_<vo_snake>.py` — no `_value_object` suffix |
| Enum | `tests/unit/domain/<subdomain>/test_<enum_snake>_enum.py` |
| Domain service — orchestrator | `tests/unit/domain/<subdomain>/test_<service_snake>_service.py` |
| Domain service — pure logic | `tests/unit/domain/<subdomain>/test_<service_snake>.py` — no `_service` suffix |

### Entity — standard

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

The builder spreads **only the entity's real declared fields** — `id` plus its domain fields. Two things
it must not carry: `created_at` / `updated_at`, because audit timestamps are a DB-managed table
convention and never entity fields, so `Foo(created_at=...)` fails; and any `import datetime` that exists
only to feed them. `datetime` enters the file **only** when the entity genuinely declares a datetime
domain field.

### Entity — few fields, so no builder

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

### Value object — canonical-form equality plus an invariant

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

### Value object — invariants only, no canonicalization

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

### Enum — values plus rejection

```python
import pytest

from myapp.domain.foos import FooStatus

def test_values() -> None:
    assert FooStatus.ALPHA == "ALPHA"
    assert FooStatus.BETA == "BETA"

    with pytest.raises(ValueError):
        FooStatus("GAMMA")
```

### Enum — with a pure-logic method

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

### Domain service — orchestrator, with a minimal inline stub

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

### Domain service — pure logic

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
    with pytest.raises(ValidationError) as exc:
        c.canonicalize("ftp://example.com")
```

## Rules

### All four kinds

1. **Sync `def test_*() -> None`**, except where the method under test is async — then `async def`.
   `pytest-asyncio` runs in auto mode; **never** add `@pytest.mark.asyncio`.
2. **No mocks.** No `MagicMock`, no `AsyncMock`, no `monkeypatch`. The domain has no IO to stub, and where
   a stub is needed (a service's injected protocol) it is hand-written so the dependency surface stays
   visible.
3. **No `@pytest.fixture`.** A builder or a factory is a module-level `def`.
4. **Assert against literal expected values.** Never re-implement the rule under test to compute the
   expected value — that hides the defect where both sides make the same mistake.
5. **Do not test what `@dataclass` gives for free** — field equality on a frozen dataclass, hashability,
   immutability. Python's data model guarantees them. Test `__post_init__`, computed properties and
   methods only.
6. **One `test_*` per invariant**, with the pattern `with pytest.raises(ValidationError) as exc:` then
   `assert exc.value.context["field"] == "<field>"`. Several failure modes of the *same* invariant group
   under one test named after that invariant.

### Entity

7. **The four-line identity-equality block is the contract**: equality by id only, and `hash` agreeing
   with `eq`. Do not paraphrase it.
8. **`_make_<entity>(**overrides)` is a module-level `def`** whose defaults are valid, so construction
   with no overrides succeeds. **No conditional logic in it** — it is a dumb spreader, and computation
   belongs in the tests.
9. **A computed property or method gets its own `test_*`** named after the rule — but only when the entity
   actually declares one. Do not add a lifecycle or archive test to an entity that has no such property;
   that is a per-aggregate feature, not a default.

### Value object

10. **Write no file when the VO has no `__post_init__` and no custom `__eq__`.**
11. **A canonical-form equality test pins the rule, not Python's `==`**: two instances with the same
    `canonical` must be equal even when their `raw` fields differ, and `hash` must agree.
12. **No builder.** Value objects are small — pass the fields directly.

### Enum

13. **Pin every member with an explicit assertion**, one line each. The database and the wire format
    depend on these strings, so a silent rename must break the test.
14. **Never loop over members.** `for m in FooStatus: assert m.value == m.name` masks the very bug it
    looks like it catches — a renamed value still passes.
15. **Always include the unknown-value rejection**:
    `with pytest.raises(ValueError): FooStatus("<unknown>")` proves the enum is closed.
16. **One `test_*` per pure-logic method**, named after the method, asserting every relevant
    input/output pair with `is True` / `is False` for booleans — `==` may accidentally compare `int(1)` to
    `True`.

### Domain service

17. **An orchestrator uses a minimal inline class, not a fake from `tests/unit/fakes/`.** The class
    implements only the protocol methods the service actually calls. That makes the true dependency
    surface visible: a service that "needs the whole repository" is probably an entity method in disguise.
    The fakes directory exists and is real (`test-fake-repository`) — it is for *handler* tests, where the
    fake stands in for a whole adapter.
18. **The `_service(...)` factory returns the constructed service**, hiding the inline-class plumbing from
    each test body.
19. **One `test_*` per behaviour of each method**, named so the test name *is* the spec line —
    `test_assert_available_raises_when_present`, `test_assert_available_passes_when_absent`.
20. **A pure-logic service constructs one instance at module scope.** It is stateless; per-test
    construction is ceremony.
21. **A canonicalizer always has `test_idempotent`** — loop a few representative inputs and assert
    `f(f(x)) == f(x)`. Idempotence is part of the canonicalization contract, and forgetting it is the most
    common bug in this class of code.
22. **Pair every happy path with a rejection test.** Single-direction tests are incomplete.

## Inlined typing / import rules

Identical for all four kinds:

- Stdlib (`uuid`, and `datetime` only when genuinely needed) plus `pytest` plus `myapp.domain.*`. No
  infrastructure, no application, no restapi, no Pydantic, no SQLAlchemy.
- Full annotations on a builder or factory and on an inline stub class. Tests are
  `def test_*() -> None` or `async def test_*() -> None`.
- No `from __future__ import annotations`.

## Hard stops

- Spec asks a test here to touch a database, an HTTP endpoint or blob storage → stop, that is
  `testing-contract` or `test-restapi-endpoint`.
- Spec asks for `MagicMock` / `AsyncMock` / `monkeypatch` → stop, the domain has no IO, and a service's
  stub is hand-written.
- Spec asks for a builder or factory as a `@pytest.fixture` → stop, they are module-level `def`s.
- Spec asks to test dataclass-given equality, hash or immutability → stop, Python guarantees it.
- Spec re-implements the rule in the test to compute the expected value → stop, assert literal values.
- Spec asserts on log output or `caplog` → stop, the domain does not log.
- Asked to put `created_at` / `updated_at` in an entity builder, or to treat them as entity fields → stop,
  audit timestamps are a DB-managed table convention.
- The value object has no `__post_init__` and no custom `__eq__` → stop, produce no file.
- Spec proposes looping over enum members → stop, write explicit asserts.
- Spec uses `==` instead of `is` for a boolean enum-method return → stop, `is True` / `is False` prevents
  truthy-but-not-`True` bugs.
- An enum's members are not enumerated in the spec → stop, they must be listed explicitly.
- Spec adds methods to a service's inline stub that the service never calls → stop, the stub implements
  exactly the called surface.
- Spec adds `@pytest.mark.asyncio` → stop, auto mode handles async.
- A pure-logic canonicalizer's test omits `test_idempotent` → stop, idempotence is part of the contract.
