---
name: test-principles
description: The testing constitution every other test skill consults — the pyramid and per-layer speed targets, the conftest hierarchy and which fixtures live where, the fixture-versus-builder rule, when parametrize is allowed, AAA structure, the no-mocks contract, and naming.
when_to_use: Writing any test, as the shared groundwork beneath the skill that owns the specific test file.
paths: tests/**
---

# Test — Principles (reference)

Every other `test-*` skill consults this one. The rules here are the **catalog-level testing constitution**; the producer skills (`testing-unit-domain`, `test-application-handler`, `testing-contract`, `test-restapi-endpoint`, …) restate only the slices that apply to writing their specific artifact.

## When to use vs. neighbours

- Adding or modifying a test → consult this skill **and** the matching producer skill.
- Producing one test file from a spec → the matching producer skill (this one is reference-only, no file output).
- The grep-firewall architectural rule that enforces a principle → `test-architecture-rule`.
- A producer skill's rule contradicts something here → fix the producer skill; this is the source of truth.

## Moving a rule that a defect paid for

A rule distilled from a real defect travels **verbatim** when it is moved, merged or reworded across these skills — copy the sentence rather than restate it. What carries such a rule is one distinctive phrase or code pattern, the part a plausibly-wrong rewrite would never reproduce by accident; a paraphrase keeps the topic and drops exactly that, so the rule survives as a heading and stops changing anyone's behaviour. If the wording around it has to change, keep that phrase intact inside the new wording.

## The testing pyramid

| Layer | Skill | Touches IO? | Target speed (per test) | What it catches |
|-------|-------|-------------|-------------------------|-----------------|
| Domain unit | `testing-unit-domain` | No | < 10 ms | Identity equality, `__post_init__` invariants, enum values, pure-logic services, single-rule policies |
| Application handler unit | `test-application-handler` (+ `test-fake-repository`) | No (in-memory fakes) | < 50 ms | Handler orchestration, PATCH semantics, normalization, domain-exception propagation, compensating-tx undo |
| App construct smoke | `test-discovery-invariants` | No (constructs the app, no DB) | < 100 ms | Construct-time wiring + framework deps the type/lint/unit layers miss (e.g. `python-multipart`), OpenAPI schema build |
| Repository contract | `testing-contract` | Real Postgres via testcontainers, transaction-rollback isolation | < 500 ms | `IntegrityError` translation, constraint-name map, cascades, `onupdate=`, `get_by_*` semantics |
| REST endpoint | `test-restapi-endpoint` | Real app + real Postgres via ASGI | < 1 s | Routing, DI wiring, auth (when declared), request/response validation, tenancy/authorization scoping (when the app declares multi-tenancy) |
| Discovery invariants | `test-discovery-invariants` | Real app, no DB calls | < 500 ms | Global properties (every protected route 401s; every code in OpenAPI matches `error_responses(...)`; CORS; 413) |
| Architecture | `test-architecture-rule` | None (greps the source tree) | < 100 ms | Static "no X in layer Y" invariants |

The shape is the goal: **fast layers run on every save; slow layers run on every commit; the slowest layers run in CI.** If a domain unit test starts touching IO or a repository test starts depending on the FastAPI app, the layer is leaking and the speed budget is gone.

## The conftest hierarchy

```
tests/
├── conftest.py                                  # empty; pytest-asyncio mode lives in pyproject.toml
├── helpers/
│   └── jwt.py                                   # sign_token(...) — auth apps only
├── unit/
│   ├── fakes/
│   │   └── fake_<aggregate>_repository.py       # no __init__.py, no conftest, direct import
│   ├── domain/                                  # domain unit tests
│   ├── application/                             # handler unit tests
│   ├── restapi/                                 # test_app_constructs.py — construct smoke, no DB (test-discovery-invariants)
│   └── test_architecture.py                     # grep firewalls
└── integration/
    ├── conftest.py                              # OWNED BY test-integration-isolation
    │                                            #   - postgres_container (session) — relational apps
    │                                            #   - db_settings (session) — relational apps
    │                                            #   - _migrated_db, _guard_against_real_db, _engine (session) — relational apps
    │                                            #   - _outer_connection, sf (function) — relational apps
    │                                            #   - real_app (function) — consumes jwt_settings from down-tree WHEN the app has auth
    │                                            #   - minio_container, storage_settings (session) — blob-store apps only
    │                                            #   - s3_prefix (function), _cleanup_bucket_at_session_end — blob-store apps only
    ├── postgres/                                # repository contract tests; uses `sf` only
    │   └── test_<aggregate>_repository.py
    └── api/
        ├── conftest.py                          # OWNED BY test-integration-authed-client (auth apps only)
        │                                        #   - rsa_keypair (session) — auth apps only
        │                                        #   - jwt_settings (session) — consumed by real_app; auth apps only
        │                                        #   - authed_client (function; consumes real_app) — auth apps only
        ├── test_unauth_returns_401.py           # OWNED BY test-discovery-invariants
        ├── test_openapi_advertises_error_codes.py
        ├── test_cors.py
        ├── test_request_size_limit.py
        ├── test_info.py
        └── <resource>/
            ├── conftest.py                      # per-resource fixtures (make_foo, foo_id, bar_id)
            │                                    # owned by the team adding the resource;
            │                                    # not by any single skill
            └── test_<verb>_<noun>.py            # one file per endpoint
```

Two coupling points are deliberate and load-bearing:

1. **A fixture may consume a setting defined down-tree** — the canonical case being `real_app` (in `tests/integration/conftest.py`) consuming `jwt_settings` from down-tree `tests/integration/api/conftest.py`, **when the app declares auth**. Pytest's fixture resolution walks the conftest hierarchy from the *consuming test* outward, so a test under `tests/integration/api/` resolves the down-tree `jwt_settings` before pytest binds it into `real_app`. The down-tree-resolution mechanism is the universal, load-bearing point; the `jwt_settings` instance is **conditional** — an auth-less app has no such fixture and `real_app` does not consume or override it (see `testing-integration-setup`). Either way **`real_app` is only usable from tests under `tests/integration/api/`** — repository contract tests don't need it.
2. **No `tests/unit/fakes/__init__.py` and no `__all__`** — handler tests import fakes via the full path (`from tests.unit.fakes.fake_foo_repository import FakeFooRepository`). This is deliberate: fakes never leak into the production import graph.

## Fixture vs. builder

| | Builder (module-level `def`) | Fixture (`@pytest.fixture`) |
|--|------------------------------|------------------------------|
| Use for | Constructing one domain object with sensible defaults | Shared infrastructure or mutable factories that touch real state |
| Lives in | The same test module that uses it, or a per-resource conftest | A conftest at the appropriate level of the hierarchy |
| Examples | `_make_foo(**overrides) -> Foo`, `_foo(name="alpha") -> Foo`, `_policy(existing_keys=...)` | `sf`, `real_app`, `authed_client`, `make_foo` (per-resource factory that hits the real DB) |
| Why | Builders are pure-Python; calling them in a fixture adds ceremony without value. Fixtures live in conftests; importing a builder across files duplicates plumbing. | Fixtures handle setup/teardown lifecycle (sessions, transactions, ASGI transports) — that's what they're for. |

**Rule:** if the thing you're constructing has no setup or teardown beyond its `__init__`, write a module-level `def`, not a fixture. The producer skills (`testing-unit-domain`, `test-application-handler`) require this — see their rule lists.

## Fixture scope rules

- **Session-scoped fixtures** — the expensive, stateless-across-tests ones the app's features require: the postgres container + engine + test-DB guard + migration autouse (relational apps), the minio container (blob-store apps), the RSA keypair + JWT settings (auth apps). Anything expensive to construct and stateless across tests; a feature the app doesn't have contributes none of these.
- **Function-scoped fixtures** — everything else. `sf`, `real_app`, `authed_client`, all row factories (`make_foo`, `make_org`, …), `s3_prefix`. Per-test rows are non-negotiable: rollback isolation requires them.
- **No `module`-scoped or `class`-scoped fixtures** in this project. The two scopes that exist (session, function) are sufficient and easier to reason about.
- **No autouse fixtures except**: the session-scoped DB guard, the session-scoped migration runner, the session-end bucket cleanup, and (optionally) a per-test `_reset_captured_singletons` if `containers.py` snapshots settings at construction time. Each autouse is documented; no one ever adds a "convenience" autouse.

## Naming conventions

- **Test file**: mirror the source file with a `test_` prefix. `application/foos/create_foo_handler.py` → `tests/unit/application/test_create_foo_handler.py`.
- **Test function**: `test_<rule_being_pinned>` in snake_case. `test_assigns_uuid_and_stores`, `test_duplicate_name_raises_conflict`, `test_partial_update_leaves_unspecified_fields_untouched`. The name **is** the spec line — reading the file's `def test_*` list reads as a list of behaviors.
- **Builders**: `_make_<entity>(**overrides)` or `_<entity>(name="alpha")` for the short form. Underscore prefix marks them as file-private.
- **Inline failure-injection subclasses**: `_Raise<X>Repo(FakeFooRepository)` at module scope, underscore-prefixed, overriding exactly the method that should fail.

## The acceptance-criteria marker

A test that pins an observable acceptance criterion carries `@pytest.mark.ac("<criterion-slug>")`,
where the slug is the criterion's own identifier — lowercase, hyphen-separated, naming the behaviour
the criterion states rather than the code that implements it:

```python
@pytest.mark.ac("duplicate-name-rejected")
async def test_duplicate_name_raises_conflict(sf: async_sessionmaker[AsyncSession]) -> None:
    ...
```

Rules for it:

- **One marker per criterion, on the test that proves it.** A criterion proven by two tests carries the
  marker on both; a test that pins no criterion carries none.
- **The marker is not a category.** It does not replace the file's placement or its name — it records
  *which stated criterion this test is the evidence for*, so a reader can go from a criterion to its proof
  and back.
- **Register it** in `pyproject.toml` under `[tool.pytest.ini_options] markers` — an unregistered marker
  is a `PytestUnknownMarkWarning`, and warnings are errors here (`-W error`, Reliability rule 9), so it
  fails the run.
- **`pytest -m ac` selects every criterion-pinning test**, which is what makes the marker worth carrying.
  The selection spans the whole suite, tests written long ago included, and that is the intended reach:
  every value is a phrase that says what it stands for, so a particular criterion is looked up by its
  own slug and the answer does not depend on which tests happen to be selected alongside it.

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

## Reliability rules (local-vs-CI parity)

1. **All persistent state is ephemeral.** Postgres and MinIO come from testcontainers in dev and CI alike. No "developer's local Postgres" mode.
2. **Per-test rollback isolation.** Every integration test starts with an empty DB; nothing leaks between tests. Tests can assert exact counts.
3. **Tests don't depend on execution order.** Each test constructs its own state. Running the suite with `-p no:randomly` and with random ordering must produce the same result.
4. **No `time.sleep`.** If a test "needs to wait", it needs the right `await` instead.
5. **Datetimes asserted with `>=`, not `==`.** Postgres `now()` can return identical timestamps within a transaction; clock-based equality flakes.
6. **UUIDs used in assertions are constructed inside the test**, not pulled from `uuid.uuid4()` at module scope (except `_CALLER` which is conventional and irrelevant to assertion shape).
7. **No environment-dependent values.** Tests must not read `os.environ` or check `os.getenv("CI")` to alter behavior. The isolation skill handles the local/CI fork once, in `postgres_container`.
8. **`@pytest.mark.integration` / `@pytest.mark.asyncio` are never used.** Path-based collection separates unit from integration; `pytest-asyncio` runs in auto mode (declared once in `pyproject.toml`).
9. **A warning is a failure, not a line in the tail of the output.** `[tool.pytest.ini_options]` carries `filterwarnings` with `"error"` as its first entry — the same table that already holds `asyncio_mode` and `markers` — so a warning raised anywhere in the run turns the suite red. This is part of what "green" means: no extra command, no second run, nothing anyone has to remember to read.
   The price is that a deprecation from a library the project cannot fix reddens the suite too, so an exception is written as one narrow entry after `"error"` — `"ignore:<message>:<Category>:<module>"`, scoped as tightly as the warning allows — and it carries its reason beside it in a comment: whose warning it is, why the project cannot remove it at the source, and what will retire the entry. An exception without a reason is the rule switched off. A warning raised from the project's own `src/` never goes on that list; it gets fixed. Same watershed `conventions` draws around `# noqa`: a suppression is legal at someone else's boundary, never on your own content.

## Hard stops

- A test imports from `myapp.infrastructure.*` from `tests/unit/` → stop, unit tests use fakes; reach for `tests/integration/` if the real adapter is what's under test.
- A test imports `myapp.restapi.*` from `tests/unit/` → stop, the HTTP surface is integration-only.
- A test uses `MagicMock` / `AsyncMock` / `patch` → stop, use a fake or an inline subclass.
- A test adds `@pytest.mark.integration` or `@pytest.mark.asyncio` → stop, neither is used.
- A test reads `os.environ` to fork behavior → stop, the isolation fixture handles environment differences once.
- A test asserts `len(items) == N + 1` "to account for the test's own row plus seed rows" → stop, rollback isolation drops everything; exact equality is correct.
- A test uses `uuid4().hex[:4]` or `[:5]` natural-key suffixes "to avoid collisions" → stop, rollback isolation makes the DB empty; fixed values like `"alpha"` are fine.
- A "convenience" autouse fixture is proposed → stop, the autouse list is closed (DB guard, migration, bucket cleanup, optional singleton reset). New autouse fixtures cause spooky-action-at-a-distance.
- A producer skill says something this skill forbids → stop, the producer skill is wrong; fix it. This skill is the source of truth.
