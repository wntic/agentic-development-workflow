---
name: testing-integration
description: "House style for real-backend integration tests via testcontainers: repository contract tests (relational and client-style store), REST endpoint tests, discovery-invariant tests over `app.routes` / `app.openapi()`, capability-adapter tests, and the isolation / authed-client fixtures. Carries the testcontainers discipline, per-test rollback and per-namespace isolation, and the Docker-absence skip rule (a clean `pytest.skip`, never a fixture that raises)."
when_to_use: Writing an integration test that touches a real store, the real FastAPI app, or an external adapter — anything under `tests/integration/`.
---
# Testing — integration tier

This theme covers 7 test artifacts, each carried by its own topic file next to this one, plus the
integration-tier constitution below — the conftest hierarchy, fixture scope, reliability and
Docker-absence rules that govern every integration test. A topic file holds the full *When to use /
Template(s) / Rules / Hard stops* body for its artifact; this router only routes. Read the
constitution and the topic file for what you are writing.

## When to use vs. neighbours

- First-time scaffold of `tests/integration/conftest.py` — container lifecycle, migrations, and the
  per-test rollback `sf` (or per-namespace cleanup for a client-style store) →
  **read `isolation.md` now**.
- First-time scaffold of the JWT-minting `authed_client` factory and the keys it depends on →
  **read `authed-client.md` now**.
- Testing a relational repository adapter against real Postgres — constraint violations, cascades,
  the `IntegrityError` translator → **read `repository-contract.md` now**.
- Testing a client-style store repository against its real backend →
  **read `store-repository-contract.md` now**.
- Testing an HTTP endpoint end to end through the real app → **read `endpoint.md` now**.
- Testing a capability adapter against the real SDK or upstream →
  **read `capability-adapter.md` now**.
- A cross-cutting invariant over the running app — every protected route 401s, OpenAPI codes match
  `error_responses(...)`, CORS, the request-size cap, the construct smoke →
  **read `discovery.md` now**.
- A test that touches no IO — a domain object, a handler over in-memory fakes, the grep firewall →
  `testing-unit`, not this theme.

## The integration testing constitution (shared)

These rules govern the integration tier and are part of the catalog-level testing constitution. The pyramid, fixture-vs-builder, AAA, no-mocks and naming rules live in `testing-unit`.

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

1. **A fixture may consume a setting defined down-tree** — the canonical case being `real_app` (in `tests/integration/conftest.py`) consuming `jwt_settings` from down-tree `tests/integration/api/conftest.py`, **when the app declares auth**. Pytest's fixture resolution walks the conftest hierarchy from the *consuming test* outward, so a test under `tests/integration/api/` resolves the down-tree `jwt_settings` before pytest binds it into `real_app`. The down-tree-resolution mechanism is the universal, load-bearing point; the `jwt_settings` instance is **conditional** — an auth-less app has no such fixture and `real_app` does not consume or override it (see `isolation.md`). Either way **`real_app` is only usable from tests under `tests/integration/api/`** — repository contract tests don't need it.
2. **No `tests/unit/fakes/__init__.py` and no `__all__`** — handler tests import fakes via the full path (`from tests.unit.fakes.fake_foo_repository import FakeFooRepository`). This is deliberate: fakes never leak into the production import graph.

## Fixture scope rules

- **Session-scoped fixtures** — the expensive, stateless-across-tests ones the app's features require: the postgres container + engine + test-DB guard + migration autouse (relational apps), the minio container (blob-store apps), the RSA keypair + JWT settings (auth apps). Anything expensive to construct and stateless across tests; a feature the app doesn't have contributes none of these.
- **Function-scoped fixtures** — everything else. `sf`, `real_app`, `authed_client`, all row factories (`make_foo`, `make_org`, …), `s3_prefix`. Per-test rows are non-negotiable: rollback isolation requires them.
- **No `module`-scoped or `class`-scoped fixtures** in this project. The two scopes that exist (session, function) are sufficient and easier to reason about.
- **No autouse fixtures except**: the session-scoped DB guard, the session-scoped migration runner, the session-end bucket cleanup, and (optionally) a per-test `_reset_captured_singletons` if `containers.py` snapshots settings at construction time. Each autouse is documented; no one ever adds a "convenience" autouse.

## Reliability rules (local-vs-CI parity)

1. **All persistent state is ephemeral.** Postgres and MinIO come from testcontainers in dev and CI alike. No "developer's local Postgres" mode.
2. **Per-test rollback isolation.** Every integration test starts with an empty DB; nothing leaks between tests. Tests can assert exact counts.
3. **Tests don't depend on execution order.** Each test constructs its own state. Running the suite with `-p no:randomly` and with random ordering must produce the same result.
4. **No `time.sleep`.** If a test "needs to wait", it needs the right `await` instead.
5. **Datetimes asserted with `>=`, not `==`.** Postgres `now()` can return identical timestamps within a transaction; clock-based equality flakes.
6. **UUIDs used in assertions are constructed inside the test**, not pulled from `uuid.uuid4()` at module scope (except `_CALLER` which is conventional and irrelevant to assertion shape).
7. **No environment-dependent values.** Tests must not read `os.environ` or check `os.getenv("CI")` to alter behavior. The isolation skill handles the local/CI fork once, in `postgres_container`.
8. **`@pytest.mark.integration` / `@pytest.mark.asyncio` are never used.** Path-based collection separates unit from integration; `pytest-asyncio` runs in auto mode (declared once in `pyproject.toml`).


## Docker-absence is a clean skip, never a raising fixture

An integration test's environment guard MUST be a clean `pytest.skip(...)` / `@pytest.mark.skipif(...)` on daemon absence — **never** a fixture that *raises* when Docker is missing. The two report different things: a skip says "this tier did not run on this machine", an error says "this tier is broken". And because the guard sits in a session-scoped fixture, a raise does not fail one test — it errors every test that depends on the fixture, so the whole integration tier fails on any machine with no Docker daemon, including the machine where `ruff`, `mypy` and the unit tier all pass. Guard on the daemon itself and skip; never express a missing environment as a failing test.
