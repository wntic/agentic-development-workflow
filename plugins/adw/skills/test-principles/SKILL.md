---
name: test-principles
description: The testing constitution every other test skill consults — the pyramid and per-layer speed targets, the conftest hierarchy and which fixtures live where, the fixture-versus-builder rule, when parametrize is allowed, AAA structure, the no-mocks contract, and naming.
when_to_use: Writing any test, as the shared groundwork beneath the skill that owns the specific test file.
paths: tests/**
---

# Test — Principles (reference)

Every other `test-*` skill consults this one. The rules here are the **catalog-level testing constitution**; the producer skills (`testing-unit-domain`, `test-application-handler`, `testing-contract`, `test-restapi-endpoint`, …) restate only the slices that apply to writing their specific artifact.

This skill also carries the **catalog's own guard**: a machine inventory of every hard-won lesson, so no reorganisation of the knowledge base can quietly lose one (see the next section).

## When to use vs. neighbours

- Adding or modifying a test → consult this skill **and** the matching producer skill.
- Producing one test file from a spec → the matching producer skill (this one is reference-only, no file output).
- The grep-firewall architectural rule that enforces a principle → `test-architecture-rule`.
- A producer skill's rule contradicts something here → fix the producer skill; this is the source of truth.
- A hard-won lesson (a phrase distilled from a real defect) is being moved, merged, or reworded across the catalog → the paid-fixes guard below must still find it afterwards.

## The catalog's paid-fixes guard

The knowledge base is a living document: skills get reworded, split, and merged. Every such move risks silently dropping a lesson that was expensive to learn — a defect surfaced once, its fix distilled into a distinctive sentence, and that sentence must never evaporate in an edit. Prose review ("I copied it all over, trust me") is not enough; the transfer is checked by a machine.

**The guard is `.claude/tools/test_skill_catalog.py`** — a pytest suite that, for each closed lesson, greps the *whole* catalog for the lesson's **content signature** (a distinctive phrase or code pattern), never its file path. Because the check is path-agnostic, a lesson may live in any skill and move to any other; the guard stays green as long as the phrase is carried over verbatim. If a phrase disappears, the matching test reds and names the lesson that was lost.

The families of lesson it inventories today (one test each, the test name citing the lesson's id) — described here as categories only, deliberately **without** quoting the grep phrases, so the exact signatures live in exactly one place, the producer skills, and this summary can never satisfy the guard by accident:

- **Persistence & handler correctness** — the conftest-import discipline, the sanctioned failure-state exception path, the compensating-undo shapes, the copy-and-log fake behaviour, the concrete-service substitution rule, and auth-derived field stamping.
- **Type & import fragility** — the re-export-hop import rule, the version-robust route-internals access, the future-annotations ban, and the settings-prefix altitude.
- **Assert strength** — the seven recipes that keep a handler/manual-stub assert strong at authoring time.
- **Feature-conditional templates** — the auth-optional and relational-optional two-sub-template idioms (a contingent feature is never frozen as universal).
- **Standing bans & disciplined exceptions** — the Core-only rule, the single-pagination-shape rule, the substrate version-pin discipline, the inline type-suppression ban, and the two enabled bugbear lint rules.

**How to extend it when a new paid lesson lands.** Every time a defect is closed and its fix distilled into the catalog, add **one** test to `test_skill_catalog.py`:

1. Pick the most distinctive phrase or code pattern the fix introduced — one a plausibly-wrong rewrite would not accidentally reproduce.
2. Write `test_<id>_<slug>` that asserts that phrase (and any co-load-bearing phrase) is present somewhere in the catalog, via the suite's `_present(...)` helper. Cite the lesson's id in the test name.
3. Never assert on a file path, and never weaken an existing signature to make room — one entry per closed lesson, append-only.

The guard is deliberately rewritten **before** any large catalog reorganisation, not during it: the watcher must not be re-authored by the same hand, in the same pass, that moves what it watches.

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
