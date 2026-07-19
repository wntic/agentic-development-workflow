# 16 — Agent-prompt harvest register (T02, spec §7.4)

Before the v2 machinery is deleted (spec §8), every paid-for rule living in the v2 agent
prompts and commands is inventoried here with a **designated new home**. Line numbers cite
the files at the pre-purge tip of this branch (the deletion commit's parent) — after the
purge, `git show <that-commit>:<path>` recovers any source verbatim.

Legend for **Home**:

- **T08 → `<skill>`** — must land in (or already lives in and must survive into) the named
  post-merge skill of the §7 catalog map.
- **T09 → protocol** — belongs to the §6 cycle protocol / the new agent definitions.
- **spec §N / T04 / T05** — already specified in `workflow_v3_spec.md`; the builder of that
  task implements it, nothing to transfer from the prompt.
- **skill (already)** — the rule is already preserved verbatim in a current skill and only
  needs to survive the T08 merge; the agent-prompt copy dies with the file.
- **dies: …** — the rule has no v3 home, with the reason. "Revives with upstream stages"
  = spec §6: "Охват — «ядро»; upstream-стадии v2 переносятся потом."

Rows marked **⚠ TRANSFER** carry knowledge that exists **nowhere else** — T08/T09 must pick
them up or the knowledge dies silently (finding V-08).

---

## analyst.md

| # | Rule (paid-for content) | Source | Home |
|---|---|---|---|
| A1 | **Two question channels, never merged**: PRODUCT questions → the BA, batched, via an async file (`questions_for_ba.md`); ARCHITECTURE questions → the human, in chat. Mixing them dumps 30 questions on the wrong head. | analyst.md:22–28, rules 1–2 | **dies for core scope, revives with upstream stages** — v3's `/spec` interviews the human directly (spec §6), so there is no BA file channel in the core cycle. When the upstream stages (extraction → ingestion → refinement) are ported, this split is the first rule to restore. |
| A2 | **Backend filter is not a silent skip**: a UI-phrased line often hides a backend invariant — raise it as a question, never cut silently; dropped lines are recorded, not deleted from the trail. | analyst.md:30–32, 52–62, rule 1 | dies with the ingestion stage (revives with upstream stages). Its essence — "no scenario drops silently" — is already load-bearing in v3 as `criteria.md` owning the scenario *list* (spec §3.3, S3). |
| A3 | Epic ≠ bounded context; group by the consistency boundary (aggregates that change together); the `Module` label loses to the UC body on conflict. | analyst.md:34–39, 64–81 | superseded by spec §2.1 cutting rules (context = "doesn't change together", capability = cohesion-of-change). Nothing to transfer. |
| A4 | Refinement mechanics: batched-not-drip-fed questions, each quoting its source line verbatim with a blank answer slot; generate-vs-fold detected from file state; never invent answers; answered questions never clobbered on re-run. | analyst.md:140–213 | dies for core scope, revives with upstream stages. |
| A5 | Never edit the verbatim source under `specs/use-cases/`. | analyst.md rule 4 | already v3 canon (CLAUDE.md; T02 hard boundary). |

## uc-extractor.md

| # | Rule | Source | Home |
|---|---|---|---|
| U1 | PDF-extraction discipline: verbatim (no translation, renumbering, normalization, interpretation); idempotent re-runs; changed content → `UC-NNN.proposed.md` + `CHANGES.md`, never overwrite; no deletions (a disappearing UC is a surfaced anomaly, UCs are append-only); duplicate-ID collision is a hard stop; chunked page-range reads. | uc-extractor.md (whole file) | **dies for core scope, revives with upstream stages** — v3 core takes `specs/use-cases/` as given input. Note: `meta-skill-author`'s sibling `meta-uc-author` covers *hand-authoring* a new UC, not PDF extraction, and its "When to use" still references the deleted `extract-ucs`/`uc-extractor` — a stale pointer for the T08 sweep. |

## architect.md

| # | Rule | Source | Home |
|---|---|---|---|
| R1 | **⚠ TRANSFER · ConflictError on first unique-insert** (rule 9): declare `ConflictError` (`code: CONFLICT`, 409) the first time a UC inserts/renames against a unique constraint, so the relational repository can map `IntegrityError` to it — omit it and the duplicate surfaces as base `DomainError` → **HTTP 500 instead of 409**. Same earn-per-UC rule for `NotFoundError`/`ValidationError`/`InUseError`; never a blanket catalog. (notes/14: "ConflictError gap → duplicate-PK is HTTP 500, not 409".) | architect.md:165–171; notes/14:273–275 | **T08 → `infra-persistence`.** The repository-side `_map_integrity_error` translator already lives in `infra-sqlalchemy-repository`, but the *catalog-side* declare-on-first-need rule exists only in the agent prompt (`domain-exception` has no trace of it) — it must be added at merge, phrased for the spec-author/test-author reader ("a unique constraint in the change implies ConflictError in the catalog and a 409 test"). |
| R2 | **env_prefix stems on the APP/product, never the bounded context** (rule 10, N-04): env vars are an app-level deployment concern (`MM_DB_`, never `ACCOUNTS_DB_`); doubly load-bearing for shared-substrate settings, where a context-named prefix breaks the moment a second context joins. | architect.md:172–177; notes/14:346–358 | **T08 → `infra-integration`** — already preserved verbatim in `infra-settings` SKILL.md line 20 (the N-04 fix landed in both places); the agent copy dies, the skill copy must survive the merge. |
| R3 | Three contract channels: `behaviour` VERIFIES, `notes` GUIDE, `sources` is PROVENANCE — never mixed. | architect.md:45–58 | dies with the manifest; the v3 analog is already specified — AC verify, change.md Context/Task guide, UC links trace (spec §3.1). |
| R4 | Earn-its-place / anticipation-litmus / identifiers-only (no derivable fields, logic is a body not a field). | architect.md:39–43 | dies with the manifest schema; the litmus survives as S1/S2 in PRINCIPLES.md. |
| R5 | Blast radius = a deterministic graph query, presented as a ~5-line semantic review. | architect.md:122–131 | superseded: v3 deliberately has **no** machine index — blast radius is grep/agent over specs + code (spec §1), plus the Affects-intersection gate in `accept.py` (§5.4). |
| R6 | Orphan GC / rename-with-body-transfer is a **human-declared, reviewed** statement (`replaces`/removal), never an agent guess. | architect.md:132–136 | already specified: removal-flavour change class (test-author owns obsolete tests, §3.1) + `accept.py` orphan sweep (§5.4). |
| R7 | A product decision that can't be expressed → escalate the gap; never silently downgrade a product commitment into an architecture liberty. | architect.md hard stops | free Markdown removes the schema-gap class; the non-downgrade essence survives as S3 (criteria text is human-owned, agents append-only). |
| R8 | `then.with` on state transitions so a no-op "re-save unchanged" body goes red. | architect.md:48–51 | skill (already): `test-application-handler`'s "Assert strength" recipes (the notes/14 §9-residual closure) → survives into **T08 → `testing-unit`**. |

## implementer.md

| # | Rule | Source | Home |
|---|---|---|---|
| I1 | **⚠ TRANSFER · Flat-vs-review-tail acceptance discipline**: acceptance has two shapes — a node with an executable test is done on green; a node with **no** executable test is accepted on mypy+ruff+contract conformance **only if flagged loudly into a named human-review queue** — never silently presented as proven. | implementer.md:50–53 (step 6), rule 7; verify.md:75–80 | **T09 → §6 protocol**: maps to `criteria.md`'s `[m]` state — the test-author names the physically-untestable AC as an `[m]`-candidate in its report, the evaluator marks per-AC PASS/FAIL/**MANUAL-candidate** in `verdict.md`, and only the human accepts `[m]` with a reason (spec §3.3, §6). The test-strength side already lives in `test-application-handler` → **T08 → `testing-unit`**. |
| I2 | **⚠ TRANSFER · Don't duplicate a guarantee the called method already gives** (rule 8): no defensive pre-check that re-asserts a declared `raises` — `delete(id)` raising `NotFoundError` is called directly, never preceded by a `get_by_id` that triggers the same error; load-then-act is only for mutations that need the entity in hand. | implementer.md:84 | **T08 → `application`** — in no current skill (checked `application-command`); add to the merged skill's handler rules. |
| I3 | Contract-change worked example: a lookup typed to *raise* `NotFoundError` where the contract treats not-found as normal should be a `T \| None` return on the protocol — an upstream contract fix, never a `try/except` buried in the handler. No silent workarounds (default-args to please tests). | implementer.md hard stops (4th) | the protocol itself is spec §6 (contract-change protocol); the worked example is worth carrying into **T08 → `application`** rules as the canonical "signal of a contract defect". |
| I4 | Same-package import collapse + import a re-exported name from its immediate re-exporting parent, never a grandparent (N-01). | implementer.md rule 6 | skill (already): `general-imports-conventions` (the N-01 fix) → survives into **T08 → `architecture`**. |
| I5 | Anti-collusion (run tests, never read them) + the 3-iteration ceiling. | implementer.md rule 1, hard stops | already spec §4/§6 + PRINCIPLES D3. |
| I6 | No `# noqa: F401` ever; an unused import is deleted, not annotated. | implementer.md:30 | already spec §5.1 grep-gates → **T04 `gate.py`**. |

## scaffolder.md

| # | Rule | Source | Home |
|---|---|---|---|
| S1 | **multipart endpoint → `python-multipart` runtime dep**, graph-derived: FastAPI imports it at `create_app()` for any `Form(...)`/`UploadFile` route; mypy/ruff/unit stay green without it (the A4 hazard). An app with no multipart endpoint must not carry it. | scaffolder.md:150 | skill (already): `conventions` block D:215 → survives the **T08 `conventions`** trim; the enforcement side is the construct-smoke in **T04 `gate.py`** (spec §5.1). |
| S2 | **auth + asymmetric tokens (RS256) → `cryptography` dev dep; HS256/opaque → must NOT carry it** (a dep nothing imports is the stray-package bug). | scaffolder.md:150 | skill (already): `conventions` block D:217 → survives **T08 `conventions`**. |
| S3 | Dev deps under `[dependency-groups]` (PEP 735), never the deprecated `[tool.uv.dev-dependencies]`; substrate carries names only, `>=` floors only at a known breaking-version boundary with the reason (B8). | scaffolder.md:150 | skill (already): `conventions` block D:222–224 → survives **T08 `conventions`**. |
| S4 | pytest-asyncio **session** loop scope (`asyncio_default_fixture_loop_scope`/`_test_loop_scope = "session"`) — without it a DB-touching integration test whose statement errors dies at teardown with `RuntimeError: Event loop is closed`. | scaffolder.md:150 | skill (already): `test-integration-isolation`:264 → survives into **T08 → `testing-integration`**. |
| S5 | Alembic bootstrap: config is glue, the `0001` baseline is write-once (emitted only when `versions/` is empty — never clobber a chain); every later migration is a real revision authored in the loop. | scaffolder.md:123 | skill (already): `conventions` "Relational migrations bootstrap" block:142–207; v3 assigns revision ownership to the implementer (spec §5.1 Docker tier runs `upgrade head`; PRINCIPLES E3) → **T08 → `conventions`/`infra-persistence`** decide final placement. |
| S6 | Middleware ordering: Starlette wraps last-added outermost; CORS (added first by the bootstrap) sits innermost; wire in declared order. | scaffolder.md:149 | skill (already): `restapi-middleware` rule 7 → survives into **T08 → `restapi`**. The manifest-side `introduces_http` union dies with the manifest. |
| S7 | Never import the protocol an adapter implements — structural subtyping; the protocol appears in the *consumer's* signature. | scaffolder.md:61 | skill (already): `infra-sqlalchemy-repository`/`infra-capability-adapter`/`infra-store-repository` → survives into **T08 → `infra-persistence`/`infra-integration`**. |
| S8 | Package `__init__` re-export contract + carve-outs (root minimal `__version__`-only; `restapi/__init__` minimal; `routers/__init__` empty; wildcard only class-modules, never bare-object modules). | scaffolder.md:146, rule 10 | skill (already): `general-python-package` → survives into **T08 → `architecture`**. |
| S9 | Discovery-invariant tests are **graph-gated by feature presence** (C6): `test_unauth_returns_401` only when auth exists, `test_info` only when an info endpoint exists, `test_request_size_limit` only when a 413-introducing middleware exists. | scaffolder.md:116 | skill (already): `test-discovery-invariants` rule 11 → survives into **T08 → `testing-integration`**. |
| S10 | The scaffold form itself: CONTRACT comment, `raise NotImplementedError` bodies, column-less table, flat-vs-manual test seam, ctor signature in the stub (F-020), resume-not-restart (F-021), the `.scaffold/` attribution snapshot. | scaffolder.md passim | **dies with the scaffolder role.** Each need it served has a named v3 successor: the published names contract → Interface sketch (spec §3.1); red-tests-before-code baseline → the test-author's red commit (§6); attribution/integrity → the git-baseline diff in `gate.py` (S8); the anti-collusion seam → tests-vs-src file ownership (D4). |
| S11 | Docker-gated integration tier: emitted always, run under a daemon; `DockerException` without one is expected, not a pass. | scaffolder.md:129; verify.md:102–108 | already spec §5.1 — the Docker tier with a **loud `DOCKER SKIPPED`** verdict → **T04 `gate.py`**. |

## Commands

| # | Rule | Source | Home |
|---|---|---|---|
| C1 | Construct-smoke: `create_app()` + `app.openapi()` render, and the table-metadata import (`from <pkg>.infrastructure.postgres import metadata`) — the cheapest exercises that catch construct-time failures the type/lint/unit layers miss (A4). | verify.md:81–88, 109–116 | already spec §5.1 → **T04 `gate.py`**. |
| C2 | The three deterministic grep gates: `# noqa: F401`, `# type: ignore`, `from __future__ import annotations` — each with its "why the toolchain misses it" rationale (F-023, N-03). | verify.md:117–139 | already spec §5.1 grep-gates → **T04 `gate.py`** (each check traces to its finding number per §10 WP3). |
| C3 | Manual-assert authoring: fresh context per file, body-blind, constructs the handler from the recorded ctor signature; assert-strength recipes applied at authoring time and re-run as the adversarial refutation checklist; a red authored test = a genuine divergence → escalate, never auto-fix either side. | author-manual-tests.md | recipes already in `test-application-handler` → **T08 → `testing-unit`**; the fresh-context + adversarial pass is spec §6 step 4 / §4 → **T09**. The divergence-escalation rule maps to the evaluator's FAIL verdict routing (§6 step 5). |
| C4 | **Missing fake → stop and author the fake first (also body-blind); never improvise a half-fake or the production body.** | author-manual-tests.md step 2 | **T08 → `testing-unit`** — the fake-authoring skill (`test-fake-repository`) has the honour-every-param rule but not the "missing fake is a stop, not an improvisation" rule; carry it into the merged skill's rules. |
| C5 | Validator finding-routing (form/graph error → architect; `skill_gap` → `meta-skill-author` + human accept; warnings loud, never blocking). | validate-manifest.md | dies with the validator; the human-gated skill-gap STOP survives as PRINCIPLES C5 / spec §7.5. |
| C6 | Resume-not-restart: the partial tree is the checkpoint; ≤2 resume attempts; never hand-fill as the orchestrator. | scaffold.md 3a | dies with the single-pass scaffolder — v3 has no whole-tree pass (one change = a small diff on a branch). |
| C7 | `UNMAPPED` planner item = a defect to report, never a body to fill. | verify.md:43–45 | dies with the planner. |
| C8 | Approval-gated ~5-semantic-lines review before writing (ingestion); one epic per subagent dispatch. | ingest-usecases.md, refine-usecases.md | dies for core scope, revives with upstream stages. v3's human touchpoints are already fixed: the `/spec` interview and the `/accept-change` merge-diff review (spec §6). |

---

## Known-minimum checklist (task T02 step 1)

- env_prefix = product not context (N-04, architect r10) → **R2** (`infra-integration`).
- ConflictError on first unique-insert (architect r9) → **R1** (`infra-persistence`, ⚠ transfer).
- flat-vs-review-tail acceptance discipline (implementer) → **I1** (§6 protocol / `testing-unit`, ⚠ transfer).
- scaffolder multipart→python-multipart and HS256→no-cryptography dep gating → **S1**, **S2** (`conventions`).
- two-channel product/architecture question split (analyst) → **A1** (dies for core scope, revives with upstream stages).

## Open transfers T08/T09 must close

- **R1** — declare-on-first-unique-insert exception rule → `infra-persistence`.
- **I1** — review-tail = `[m]`-candidate mapping → the `/implement` protocol + evaluator verdict format (T09).
- **I2**, **I3** — handler-body judgment rules → `application`.
- **C4** — missing-fake-is-a-stop → `testing-unit`.
- Stale pointer: `meta-uc-author` "When to use" references the deleted `extract-ucs`/`uc-extractor` (U1) — T08 sweep.
