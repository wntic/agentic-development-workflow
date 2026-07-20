# 17 — Hard-stop dispositions (T08, spec §7 item 3 / O-12)

Every merged skill carries a **Hard stops** section (often several, one per absorbed artifact). Spec §7
requires each hard stop to get an explicit ruling under the S4 litmus — *what physically happens when an
agent ignores it?* — landing in exactly one of:

- **GATE** — a deterministic check in `gate.py` (or `accept.py`) invalidates the result. The specific
  check is named. `gate.py`'s inventory (spec §5.1): the toolchain (`mypy src tests`, `ruff check` with
  `B006`/`B904`, `ruff format --check`, `pytest`), the grep-gates (`# type: ignore` on content modules,
  `from __future__ import annotations`, `# noqa: F401`, `raise NotImplementedError` in `src/**`), the
  construct-smoke (`create_app()` + `app.openapi()`, table metadata-import), the Docker tier
  (`alembic upgrade head`), `--criteria` junit cross-check, and the baseline integrity inventory.
  The per-app **architecture-rule tests** (`tests/unit/test_architecture.py` grep firewalls) run inside
  `gate.py`'s `pytest`, so a rule pinned by such a test is GATE.
- **ADVICE** — the S4 answer is "nothing deterministic": no gate sees the violation, it is caught only by
  human review (or by a *downstream* toolchain failure when the wrong artifact happens not to type-check /
  construct / test). Recorded honestly as advice, not laundered as a gate.

**Recurring category: wrong-artifact navigation.** The bulk of hard stops read "spec asks for X → stop, use
`<other-skill>`". These are **navigational advice**: they steer skill selection. The *consequence* of picking
wrong is frequently caught by the toolchain (a misplaced adapter fails mypy at the layer boundary, an
under-filled body fails construct-smoke, a missing test fails the criteria/inventory checks), and a subset is
directly gated by the architecture firewall — but the redirect itself is not a dedicated gate. Where a hard
stop maps to a *specific* gate beyond generic type/construct/test coverage, it is called out.

Two hard stops that the task named explicitly are settled first:

- **offset-vs-cursor mutual exclusivity** (`domain-model`, filter section: "needs both `limit/offset` and
  `cursor` → pick one with the user"). Disposition: **ADVICE**. This is *not* a cursor ban (cursor is a
  sanctioned alternative — T07 finding 1); it is a design choice made *with the human*, and no gate enforces
  "exactly one pagination shape". The paid-fixes guard keeps the *phrase* alive (`test_pagination_pick_one_never_both`),
  but the rule itself is advice by construction.
- **Docker-absence must be a clean skip, never a raising fixture** (`testing-integration`). Disposition:
  **GATE (indirect)**. `gate.py`'s baseline test-inventory carve-out (T04b ruling, spec §5.1) exempts a
  baseline integration test *only* when the gate's own Docker probe found the daemon absent and the test
  therefore **skipped**. A fixture that *raises*/*errors* instead of skipping is not covered by the carve-out,
  so on a Docker-less machine it turns the whole gate permanently RED — the gate is what makes the rule bite.

---

## architecture (← general-layered-architecture, general-python-package, general-imports-conventions)

- Layer-direction stops (`infrastructure/`→`application/`, `application/`→`infrastructure/`, `domain/` imports
  non-stdlib, entrypoint instantiates a concrete adapter): **GATE** — the architecture-rule grep firewalls in
  `tests/unit/test_architecture.py`, run under `gate.py`'s `pytest`; a cross-layer import also reds `mypy`.
- Circular import between modules/subpackages/layers: **GATE** — `mypy` / import resolution fails at
  `gate.py`; construct-smoke also reds if the cycle breaks `create_app()`.
- Same-package / grandparent import form, `import X as`, 3+-dot relative, in-function/`TYPE_CHECKING`
  imports-to-dodge-a-cycle: **ADVICE** for the style form; the *broken* re-export (`name-defined`) case is
  **GATE** via `mypy` (the N-01 lesson: a grandparent import is `attr-defined`, a mypy error).
- Package mechanics (two top-level classes per file, filename≠class, `__all__` before imports, `__init__`
  with logic, `__init__` referencing `module.__all__` without the submodule import): **ADVICE** for layout
  style; the last one (`__all__` without `from . import module`) is **GATE** — `mypy` `name-defined`.

## python-style (← general-typing-conventions, general-logging)

- `from __future__ import annotations` anywhere: **GATE** — `gate.py` grep-gate (N-03).
- `# type: ignore` without a `[rule]`/reason, on a content module: **GATE** — `gate.py` grep-gate (F-023);
  the only sanctioned silence is the `[[tool.mypy.overrides]]` block.
- `Optional`/`Union` instead of `X | None`, bare `Any`, untyped `**kwargs`, `cast(...)` to silence: **ADVICE**
  for the form; a genuine type error left behind is **GATE** via `mypy strict`.
- All logging stops (log-and-re-raise, log in `domain/`, `log.error` in `application/`, `import logging`,
  `print()`, logging a full body / secrets / a `UUID` object, non-past-tense event name): **ADVICE** — there is
  no log-content gate in the §5.1 inventory; these are house-style caught by review. Honest S4 answer: an agent
  that logs in the domain layer is not stopped by any deterministic check today.

## domain-model (← domain-entity, -value-object, -enum, -filter, -exception)

- Wrong-artifact redirects (needs another aggregate's state → service; frozen-by-content → VO; persistence →
  repository/infra; runtime-extensible values → VO+lookup; `id`+mutation → entity; closed string set → enum;
  cross-aggregate validation → service): **ADVICE** (navigational; the misplaced artifact's failure is the
  downstream catch).
- offset-vs-cursor "pick one with the user": **ADVICE** (see preamble; not a cursor ban).
- Exception stops (raise a new type from outside `domain/exceptions.py`; subclass overrides `__init__`/adds
  fields; log at raise site): the "outside the catalog" and "override `__init__`" cases are **GATE-adjacent** —
  a raise of an undefined name reds `mypy`/construct-smoke; the "log at raise site" case is **ADVICE**
  (no log gate). Duplicate-semantics reuse is **ADVICE** (review).

## domain-ports (← domain-repository-protocol, domain-capability-protocol, domain-service)

- Method-count / cohesion stops (>~3 single-action methods → capability; >2 on a capability; >~4–5 rules on a
  service → split): **ADVICE** (cohesion judgment; no gate counts methods).
- SQL/framework types on a protocol signature, `ABC`/concrete base instead of `typing.Protocol`, default
  implementation in the protocol, class-level state, direct SQLAlchemy session, reading settings: **ADVICE**
  for the design smell; where it produces a real type/layer violation (framework type imported into `domain/`)
  it becomes **GATE** via the architecture firewall + `mypy`.

## application (← application-command, -query, pattern-compensating-tx, pattern-unit-of-work)

- Command-vs-query redirects (mutation returns data → query; query mutates → command), Pydantic in a handler,
  result-shape creep, cross-aggregate validation inline → service, atomic writes → UoW, external-IO-before-write
  → compensating-tx: **ADVICE** (navigational). The compensating-tx *shape* itself (record-status-then-reraise,
  best-effort undo) is kept alive as paid phrases (F-015/F-016) and its absence would fail the handler's own
  `ac`-test — **GATE** via `--criteria` when a criterion pins the undo.
- Compensating-tx protocol stops (missing `*_best_effort`; compensation can raise; two-backend saga): **ADVICE**
  (design-shape; no gate). "log a read event" stop: **ADVICE** (no log gate).
- UoW stops (only one repo; two backends; per-aggregate UoW): **ADVICE** (design-shape).
- Handler-body harvest rules (I2 "don't duplicate a guarantee the called method gives"; I3 "a blocked contract
  is a contract defect, not a `try/except`"): **ADVICE** — judgment rules caught by adversarial review /
  assert-strength, not a deterministic gate.

## infra-persistence (← infra-sqlalchemy-repository, -table, infra-store-repository)

- ORM / declarative-base / relationships instead of Core: **ADVICE** — there is **no** "no-ORM" grep-gate in
  §5.1; the Core-only rule is house-style kept alive as a paid phrase (`test_ban_orm_use_sqlalchemy_core_only`)
  and enforced by review. Honest S4: an agent that reaches for the ORM is not stopped by the gate today.
  *(Candidate for a future grep-gate — logged for the human.)*
- Repository logs / generates IDs / commits inside a UoW-managed form: **ADVICE** (design; "logs" has no gate).
- Constraint-name misalignment between table and repository `_map_integrity_error`: **GATE (indirect)** — the
  repository-contract integration test asserts `context["constraint"]`, so a mismatch reds `pytest` under the
  Docker tier.
- Postgres `ENUM`/`String(n)` instead of `Text`+`CheckConstraint`: **ADVICE** (style).
- Bare string to `Index`/`CheckConstraint` (raises at table-construct): **GATE** — `gate.py`'s table
  metadata-import construct-smoke (F-012) reds it (green under mypy/ruff).
- Data migration in a table file, cross-store atomicity, client-store creating/migrating its collection,
  wrong store profile (`uses_bootstrap` → relational path; capability port → adapter): **ADVICE** (navigational).
- **ConflictError-on-first-unique-insert (R1, harvested)**: **GATE (indirect)** — omitting it surfaces the
  duplicate as HTTP 500; the change's 409 `ac`-test fails, so `--criteria` reds. The declare-in-catalog step
  itself is **ADVICE** (author judgment) but its omission is caught by the pinned behaviour test.

## infra-integration (← infra-capability-adapter, infra-settings, infra-di-provider)

- Adapter talks to Postgres/SQLAlchemy, inherits `ICanX` explicitly, logs, retries/caches internally,
  constructs its own SDK client: **ADVICE** for the design smells; "adapter logs" has no gate.
- **Untranslated SDK exception at the boundary** (Rule 10 broad-catch fallback): **GATE (indirect)** — the
  capability-adapter integration test asserts the boundary raises the promised `DomainError` (and its `context`
  keys), so an untranslated SDK exception reds `pytest`.
- env reads outside a settings class, two integrations under one prefix, adapter takes individual fields:
  **ADVICE** (design). env_prefix-stems-on-product (R2/N-04) is kept alive as a paid phrase; its violation is
  **ADVICE** (no prefix gate) but bites operationally when a second context joins.
- DI stops (dependency not yet declared, repository wired `Singleton` instead of `Factory`, conditional
  per-env wiring, importing `restapi/` into `containers.py`): the missing-dependency and wrong-direction cases
  are **GATE** — construct-smoke (container fails to build) / architecture firewall; the `Singleton`-vs-`Factory`
  choice is **ADVICE**.

## restapi (← restapi-app-bootstrap, -endpoint, -schema, -auth-dependency, -error-responses, -file-transfer, -middleware)

- `domain/error_catalog.py` (obsolete), branching the translator beyond `UnauthorizedError`, business logic on
  lifespan, missing `domain/exceptions.py` / `containers.py` bootstrap: the missing-module bootstraps are
  **GATE** — construct-smoke reds `create_app()`; the "translator stays minimal" and "no lifespan business
  logic" are **ADVICE**.
- Route logs / has a `try/except` (non-file-transfer) / constructs a domain entity: **ADVICE** for style;
  a route `try/except` swallowing a `DomainError` would drop an advertised status and fail the endpoint's
  `ac`-test — **GATE (indirect)** via `--criteria`.
- Static path declared after `/{id}`: **GATE (indirect)** — the discovery/endpoint tests exercise routing, so
  the shadowed route reds `pytest`.
- Response schema needs fields the result lacks; `*Response` validates input; all-`None` create request;
  shared base class; importing a domain entity into a schema: **ADVICE** (wire-contract style); a genuinely
  missing field reds the endpoint test — **GATE (indirect)**.
- Auth stops (inline role check → `require_role`; per-route verifier; reading `Authorization` directly;
  omitting auth on a non-public route of an authed app; a third auth dependency; a role-gated route advertising
  401 but not 403): the 401/403 advertisement mismatch is **GATE (indirect)** — the discovery-invariant test
  `test_unauth_returns_401` + the openapi-advertises-error-codes test red it; the rest are **ADVICE**.
- Error-responses stops (branching `error_handler.py`; a route translating a domain exception; an HTTP status
  no subclass produces and not in `MIDDLEWARE_ERRORS`; `WWW-Authenticate` on 403): the "status with no
  producer" case is **GATE (indirect)** — the openapi-advertises-error-codes discovery test; the rest **ADVICE**.
- File-transfer stops (extra `try/except`; route computes size limits / parses content; a download header
  beyond `Content-Disposition` without CORS `expose_headers`): **ADVICE** (design); the CORS-header case bites
  only at runtime, no gate.
- Middleware stops (one-route concern → endpoint; needs a handler/entity; authenticates → auth-dependency;
  reaches for `BaseHTTPMiddleware`; introduces a status with no domain exception): the `BaseHTTPMiddleware`
  one is **GATE (indirect)** — it buffers the body, breaking the size-cap discovery test (`test_request_size_limit`);
  the rest are **ADVICE**/navigational.

## testing-unit (← test-application-handler, test-fake-repository, test-domain-*, test-architecture-rule)

- `MagicMock`/`AsyncMock`/`monkeypatch` to stub, `@pytest.mark.asyncio`/`.integration`: **ADVICE** — the
  no-mocks contract and the marker bans are house-style; there is **no** anti-mock grep-gate in §5.1. Honest
  S4: an agent that reaches for `MagicMock` is not stopped by the gate (the paid phrases keep the rule visible,
  not enforced). *(Candidate grep-gate for `unittest.mock` in `tests/unit/` — logged for the human.)*
- Test hits a real DB/HTTP/S3, or imports `myapp.restapi.*`/`infrastructure.*` from a unit test: **GATE** —
  the architecture firewall pins "no infra/restapi import from `tests/unit/`" and reds under `pytest`.
- **Concrete-domain-service faked structurally** (F-019): **GATE (indirect)** — a structural fake of a concrete
  service fails `mypy` (`strict`); the rule says subclass or inject via Protocol.
- **Missing fake → stop and author first (C4, harvested)**: **ADVICE** — an improvised half-fake is caught by
  the assert-strength adversarial pass, not a deterministic gate; but the *absence* of a needed fake reds the
  handler test (`pytest`).
- Fake-shape stops (failure-injection flags on the fake, modelling `InUseError` in the default fake, `__all__`
  in fakes dir, copied-not-invented contract): **ADVICE** (design); the fakes-dir `__init__`/`__all__` case is
  benign.
- Domain-test stops (builder as fixture, testing dataclass-given equality, re-implementing the invariant,
  `caplog`, `created_at` in the builder, `==` vs `is` on boolean returns, unlisted enum members, looping over
  members): **ADVICE** (test-authoring craft); the `ac`-marker requirement itself is **GATE** via `--criteria`.

## testing-integration (← test-repository-contract, -store-repository-contract, test-restapi-endpoint, test-discovery-invariants, test-integration-isolation, -authed-client, test-infra-capability-adapter)

- **Docker-absence = clean skip, never a raising fixture**: **GATE (indirect)** — see preamble (T04b carve-out).
- Wrong-tier redirects (relational store → sqlalchemy path; single-store client → store-repository; capability
  port → capability adapter), provisioning inside the repository, cross-store atomicity: **ADVICE** (navigational).
- Session-loop-scope / rollback-isolation / exact-count / no-`uuid4`-suffix / no-`os.environ`-fork /
  no-convenience-autouse rules (from the moved reliability constitution): **ADVICE** for craft; a broken loop
  scope surfaces as a real teardown error under the Docker tier — **GATE (indirect)** via `pytest`.
- SDK-error-translation and `context`-key assertions (store-repository / capability-adapter): **GATE
  (indirect)** — asserted by the integration tests under the Docker tier.
- `test-infra-capability-adapter` placement note: this test skill is **not named in the §7 map**; its content
  (dominant flavour: containerized + `respx` integration, one pure-CPU unit flavour) was folded into
  `testing-integration` at merge. Recorded as a T08 finding.

## conventions (self-merge, reference skill)

- No `## Hard stops` section (reference skill). Its "fail-loud-not-crash" invariants (unknown store kind →
  loud comment, not a silent crash; complete-glue connection factory, not a `NotImplementedError`) are
  **GATE** — a `NotImplementedError` left in glue reds `gate.py`'s grep-gate; a broken connection factory reds
  construct-smoke.

## meta-skill-author (self-merge, meta skill)

- Hard stops (skill produces no file → belongs in CONVENTIONS.md; custom frontmatter fields; description
  overlaps an existing skill >½; app-specific names in templates): **ADVICE** — these govern *authoring a new
  skill* (a meta-catalog act), outside the target-app gate. The catalog's own guard (`test-principles`) is the
  standing machine check that a reorganisation loses no paid phrase.

## test-principles (self-merge, reduced to the guard)

- Hard stops (rewording would change a paid phrase; using it to write a test; satisfying the guard by quoting
  a signature in the summary): **GATE** — the paid-fixes guard `.claude/tools/test_skill_catalog.py` is exactly
  the deterministic check; a lost phrase reds a named test. This is the one skill whose hard stops are a gate
  by construction.

## meta-uc-author (survives the merge unchanged in role; not a §7 merge target)

- Hard stops (Gherkin / named AC sections / UI-only UC / overwrite an existing UC / multiple UCs per run /
  non-canonical filename): **ADVICE** — UC authoring is upstream input material, outside the target-app gate.
  Included here for coverage completeness though it is not one of the §7 merge targets.
