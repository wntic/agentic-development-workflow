---
name: testing-unit
description: "House style for fast, no-IO unit tests and the whole unit tier's constitution: domain entity / value-object / enum / service tests, application handler tests with in-memory fakes, the fake-repository pattern (stores and returns copies with an updated log, honours every param, a missing fake is a stop not an improvisation), the seven assert-strength recipes, the `@pytest.mark.ac(\"AC-n\")` criteria marker, and the grep-firewall architecture rule. Carries the testing pyramid, conftest hierarchy, fixture-vs-builder rule, no-mocks contract and per-layer speed targets."
when_to_use: Writing a unit test for a domain object, an application handler, a fake repository, or a static architecture invariant.
---
# Testing — unit tier

This theme covers 7 test artifacts, each carried by its own topic file next to this one, plus the
unit-tier constitution below — the rules that govern every unit test whatever the artifact. A topic
file holds the full *When to use / Template(s) / Rules / Hard stops* body for its artifact; this
router only routes. Read the constitution and the topic file for what you are writing.

## When to use vs. neighbours

- Testing a new or modified application handler against in-memory fakes →
  **read `handler.md` now**.
- Writing the in-memory fake a handler test needs — a repository or capability stand-in →
  **read `fake.md` now**.
- Testing a domain entity — identity equality and every `__post_init__` invariant →
  **read `entity.md` now**.
- Testing a domain value object → **read `value-object.md` now**.
- Testing a domain enum's member values → **read `enum.md` now**.
- Testing a domain service, orchestrator or pure-logic → **read `domain-service.md` now**.
- Adding a static "no X in layer Y" grep firewall to `tests/unit/test_architecture.py` →
  **read `architecture-rule.md` now**.
- Anything under `tests/integration/` — a real store, the real app, testcontainers →
  `testing-integration`, not this theme.

## The unit testing constitution (shared)

These rules govern the whole unit tier and are the catalog-level testing constitution. The integration-specific half — the conftest hierarchy, fixture scope, and reliability rules — lives in `testing-integration`.

## The testing pyramid

| Layer | Topic | Touches IO? | Target speed (per test) | What it catches |
|-------|-------|-------------|-------------------------|-----------------|
| Domain unit | `entity.md`, `value-object.md`, `enum.md`, `domain-service.md` | No | < 10 ms | Identity equality, `__post_init__` invariants, enum values, pure-logic services, single-rule policies |
| Application handler unit | `handler.md` (+ `fake.md`) | No (in-memory fakes) | < 50 ms | Handler orchestration, PATCH semantics, normalization, domain-exception propagation, compensating-tx undo |
| App construct smoke | `test-discovery-invariants` | No (constructs the app, no DB) | < 100 ms | Construct-time wiring + framework deps the type/lint/unit layers miss (e.g. `python-multipart`), OpenAPI schema build |
| Repository contract | `test-repository-contract` | Real Postgres via testcontainers, transaction-rollback isolation | < 500 ms | `IntegrityError` translation, constraint-name map, cascades, `onupdate=`, `get_by_*` semantics |
| REST endpoint | `test-restapi-endpoint` | Real app + real Postgres via ASGI | < 1 s | Routing, DI wiring, auth (when declared), request/response validation, tenancy/authorization scoping (when the app declares multi-tenancy) |
| Discovery invariants | `test-discovery-invariants` | Real app, no DB calls | < 500 ms | Global properties (every protected route 401s; every code in OpenAPI matches `error_responses(...)`; CORS; 413) |
| Architecture | `architecture-rule.md` | None (greps the source tree) | < 100 ms | Static "no X in layer Y" invariants |

The shape is the goal: **fast layers run on every save; slow layers run on every commit; the slowest layers run in CI.** If a domain unit test starts touching IO or a repository test starts depending on the FastAPI app, the layer is leaking and the speed budget is gone.

## Fixture vs. builder

| | Builder (module-level `def`) | Fixture (`@pytest.fixture`) |
|--|------------------------------|------------------------------|
| Use for | Constructing one domain object with sensible defaults | Shared infrastructure or mutable factories that touch real state |
| Lives in | The same test module that uses it, or a per-resource conftest | A conftest at the appropriate level of the hierarchy |
| Examples | `_make_foo(**overrides) -> Foo`, `_foo(name="alpha") -> Foo`, `_policy(existing_keys=...)` | `sf`, `real_app`, `authed_client`, `make_foo` (per-resource factory that hits the real DB) |
| Why | Builders are pure-Python; calling them in a fixture adds ceremony without value. Fixtures live in conftests; importing a builder across files duplicates plumbing. | Fixtures handle setup/teardown lifecycle (sessions, transactions, ASGI transports) — that's what they're for. |

**Rule:** if the thing you're constructing has no setup or teardown beyond its `__init__`, write a module-level `def`, not a fixture. The producer skills (`entity.md`, `handler.md`) require this — see their rule lists.

## Naming conventions

- **Test file**: mirror the source file with a `test_` prefix. `application/foos/create_foo_handler.py` → `tests/unit/application/test_create_foo_handler.py`.
- **Test function**: `test_<rule_being_pinned>` in snake_case. `test_assigns_uuid_and_stores`, `test_duplicate_name_raises_conflict`, `test_partial_update_leaves_unspecified_fields_untouched`. The name **is** the spec line — reading the file's `def test_*` list reads as a list of behaviors.
- **Builders**: `_make_<entity>(**overrides)` or `_<entity>(name="alpha")` for the short form. Underscore prefix marks them as file-private.
- **Inline failure-injection subclasses**: `_Raise<X>Repo(FakeFooRepository)` at module scope, underscore-prefixed, overriding exactly the method that should fail.

## When to parametrize — and when not to

**Use `@pytest.mark.parametrize`** when:

- The parameter set is **discovered from the running system** — every protected route in `app.routes`, every operation in `app.openapi()`. `test-discovery-invariants` is the canonical example.
- The test is **input-domain coverage**: a single behavior verified against many inputs (10 invalid emails, 20 valid date formats). The behavior is one thing; the inputs vary.
- Adding a new parameter would extend, not duplicate, an existing test set.

**Do not parametrize** when:

- Each case is a distinct rule whose **name forms part of the spec**. `test_assigns_uuid_and_stores` and `test_duplicate_name_raises_conflict` are different behaviors; collapsing them into `@pytest.mark.parametrize("scenario, expected", [...])` hides the spec lines in tuples.
- The case differs in setup or assertions, not just input values.
- The test is in `tests/unit/domain/` covering `__post_init__` invariants — those are individual rules.

The rule of thumb: if you can read the parametrize ids out loud and they sound like a list of behaviors, parametrize is fine. If you can't (because the ids would be `0`, `1`, `2`), the cases are different rules and want different `def test_*` names.

## AAA structure (Arrange / Act / Assert)

Every test follows three visually-separated blocks:

```python
async def test_assigns_uuid_and_stores() -> None:
    # Arrange
    repo = FakeFooRepository()
    handler = CreateFooHandler(repo=repo)

    # Act
    foo_id = await handler.execute(CreateFooCommand(caller_id=_CALLER, name="alpha"))

    # Assert
    stored = await repo.get_by_id(foo_id)
    assert stored.name == "alpha"
```

Rules:

1. **Blank lines separate the three blocks.** Comments (`# Arrange`, `# Act`, `# Assert`) are optional once the pattern is established, but the blank lines are not.
2. **One Act per test.** If a test has two `handler.execute(...)` calls, the second one is part of Arrange (setup) for an assertion about the first. When in doubt, split into two tests.
3. **One assertion subject per test.** Multiple `assert` statements that all check the same returned object are fine (`assert stored.name == "alpha"; assert stored.created_at >= ...`). Multiple assertions across different objects often means two tests in one.
4. **Arrange constructs valid state.** Don't write defensive `try/except` in Arrange — if the setup fails, the test fails, and that's the right outcome.

## No-mocks rule

| Tool | Forbidden? | Notes |
|------|-----------|-------|
| `unittest.mock.MagicMock` | yes | always |
| `unittest.mock.AsyncMock` | yes | always |
| `unittest.mock.patch` | yes | always |
| `pytest.MonkeyPatch.setattr` (`monkeypatch.setattr`) | yes | never patch handler dependencies |
| `monkeypatch.setenv` | conditional | only inside env-parsing tests (`tests/unit/infrastructure/test_*_settings.py`); never used to drive handler tests |
| Hand-written fakes (`FakeFooRepository`) | preferred | the canonical substitution mechanism |
| Inline `_RaiseXxxRepo(FakeFooRepository)` subclass | preferred | one-off failure injection at the test module scope |

The rationale: mocks describe *what was called*; fakes describe *what state would result*. The state-based assertion catches whole classes of bug the call-based assertion can't. Mocks also encode interface details that drift independently of the protocol — a refactor that adds a parameter to `repo.create(...)` silently breaks no `MagicMock` test, but a hand-written fake fails compile-time.

The single sanctioned exception is `monkeypatch.setenv` inside settings-parsing tests (which exercise the env-reading code itself). Everywhere else, the answer is a fake.

## Testing hard stops (tier-wide)

- A test imports from `myapp.infrastructure.*` from `tests/unit/` → stop, unit tests use fakes; reach for `tests/integration/` if the real adapter is what's under test.
- A test imports `myapp.restapi.*` from `tests/unit/` → stop, the HTTP surface is integration-only.
- A test uses `MagicMock` / `AsyncMock` / `patch` → stop, use a fake or an inline subclass.
- A test adds `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- A test reads `os.environ` to fork behavior → stop, the isolation fixture handles environment differences once.
- A test asserts `len(items) == N + 1` "to account for the test's own row plus seed rows" → stop, rollback isolation drops everything; exact equality is correct.
- A test uses `uuid4().hex[:4]` or `[:5]` natural-key suffixes "to avoid collisions" → stop, rollback isolation makes the DB empty; fixed values like `"alpha"` are fine.
- A "convenience" autouse fixture is proposed → stop, the autouse list is closed (DB guard, migration, bucket cleanup, optional singleton reset). New autouse fixtures cause spooky-action-at-a-distance.
- A producer skill says something this skill forbids → stop, the producer skill is wrong; fix it. This skill is the source of truth.


## The `@pytest.mark.ac` criteria marker

Every acceptance criterion in a change's `criteria.md` is pinned by at least one test carrying its marker: `@pytest.mark.ac("AC-2")` on the test function. This is the convention the change cycle cross-checks — a criterion may be ticked only when a **passed** `ac`-marked test for it exists in the run's junit report. Put the marker on the test that most directly exercises the criterion's observable behaviour; one criterion may have several marked tests. A criterion no test can physically pin is a candidate for the manual `[m]` state, flagged explicitly rather than left silently unmarked.

## A missing fake is a stop, not an improvisation

When a handler test needs a fake repository or fake capability that does not yet exist, **stop and author the fake first** (following the fake-repository rules in `fake.md` — copy the real adapter's exception contract, store and return copies with an updated log, honour every constructor param). Never improvise a half-fake inline, and never reach for the production adapter body to stand in. (Harvested from notes/16 C4.)
