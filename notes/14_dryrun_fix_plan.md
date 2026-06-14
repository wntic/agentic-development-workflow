# Dry-run fix plan (prioritized)

Remediation plan for the rough edges found in the full pipeline dry-run (AI Meeting Assistant,
2 contexts + polyglot + brownfield delta). Source report: `notes/pipeline_dryrun_feedback.md`
(findings F-001..F-025). This note is the ACTION list — what to change, where, how to verify.

**Meta-finding (frame everything against this).** The dry-run's "green app / 0 escalations" was
**laundered by 3 manual overrides + silent fixes** — a blind `/scaffold`→`/verify` on that app would
NOT reproduce green. The agentic authoring path (architect → scaffolder → implementer) held at high
complexity; the defects cluster in **(1) the runner/planner** (`plan_implementation.py` — least
multi-context/polyglot exercise before this run) and **(2) the A4 gate-integrity class** ("passes
mypy+ruff but is wrong"). Fixing P0 should remove the honesty caveat (blind run of the same app goes
green); P1 closes the "trust the green" holes. Verified against code: F-009 (planner keys on `backs`,
lines 164 + 348), F-023 (no `# type: ignore` gate; `noqa` is gated), F-024 (no field-order check) — all real.

Verify-everything baseline: from a generated tree, `uv run mypy src tests` · `uv run ruff check src tests`
· `uv run ruff format --check src tests` · `uv run pytest` · `uv run python -c "from <pkg>.restapi.main import create_app; create_app()"`.
For the tooling itself: `uv run pytest .claude/tools/test_validate_manifest.py`.

---

## P0 — blind pipeline writes WRONG / BROKEN code (fix before ANY unsupervised run)

**STATUS — DONE + verified (2026-06-14).** All four landed as one "runner hardening" change:
`plan_implementation.py` (`repo_file_stem` helper used in `build_registry` + `drifted_files`;
repo→table edge in `_wire_deps`; `--app` union mode), conventions block A (polyglot repo-stem rule)
+ block C (connection/engine factory = complete glue, with templates), `scaffolder.md` (connection
factory removed from body-bearing), `verify.md` (`--app` threaded + UNMAPPED-is-a-defect note), and a
new `test_plan_implementation.py` (7 tests). Verified: planner unit tests 7 green + validator 42 green;
a BLIND app-mode re-scaffold of the 2-context Meeting app produced complete connection factories (0
NIE) + correctly-named polyglot repos, and `plan_implementation.py … --app` reports **0 UNMAPPED**,
correct skills, table-below-repo DAG. The runner honesty-caveat is removed. NOTE: the blind scaffolder
run itself stalled on the watchdog before its self-verify/baseline-freeze (F-021, P3) — the runner
logic is proven, but a truly unattended full scaffold→verify→green still waits on the F-021 robustness
fix.

All four live in `.claude/tools/plan_implementation.py` and the runner↔scaffolder seam. Treat as one
"runner hardening" work-package.

### P0-1 · F-009 / F-014 — planner mis-maps polyglot two-repos-one-aggregate
- **Problem.** `build_registry` keys each repo worklist entry as `f"{snake(backs)}_repository"` (line ~164)
  and `drifted_files` checks `f"{snake(backs)}_repository"` (line ~348). When one aggregate has TWO repos
  (Meeting → `IMeetingRepository`/postgres + `IMeetingSearchIndex`/qdrant) both `backs: Meeting` → same
  key → the relational repo gets the QDRANT skill, the vector repo is UNMAPPED, AND the drift check runs
  forever against the wrong file (permanent false "pending" → `/verify` never drains). Polyglot — a
  redesign goal — is unrunnable blind.
- **Root cause.** The repo file/key is derived from `backs` (the aggregate), which is NOT unique under
  polyglot persistence. The scaffolder already dodged the filename collision by naming the *client* repo
  after its PROTOCOL (`meeting_search_index.py`), but conventions never wrote that rule down and the
  planner didn't adopt it — the two layers disagree on the name.
- **Fix (two parts, keep them in lockstep).**
  1. **conventions block A** — define the polyglot repo-file derivation deterministically: a
     bootstrap/relational store repo → `<snake(backs)>_repository.py`; a client-store repo → the
     protocol-derived stem (`IMeetingSearchIndex` → `meeting_search_index.py`). One rule both scaffolder
     and planner read. (The scaffolder already does this; just make it canonical.)
  2. **`plan_implementation.py`** — add a single `repo_file_stem(repo, store_kind)` helper that applies
     that rule, and use it in BOTH `build_registry` (the repo `put(...)`) and `drifted_files` (the
     `check(...)`). Key the registry entry per-repository (by `implements` + store), never by `backs`.
     The protocol lookup in `drifted_files` is already by `implements` (line ~346, correct) — only the
     FILE derivation is wrong.
- **Verify.** On the meeting app: planner lists `meeting_repository.py`→`infra-sqlalchemy-repository`
  and `meeting_search_index.py`→`infra-store-repository` (both mapped, correct skills); after bodies
  filled, worklist drains to 0 (no phantom drift). Add a polyglot fixture (two repos, one aggregate) to
  the runner's test coverage if one is added.

### P0-2 · F-011 — connection-factory bootstraps are UNMAPPED bodies
- **Problem.** `postgres/engine.py` (`create_engine`/`create_session_factory`) and
  `qdrant/connection.py` (`create_<store>_client`) ship as `raise NotImplementedError` scaffolds but
  correspond to no manifest node (store-profile substrate, conventions block C) → planner maps them
  `UNMAPPED` → `/verify` never dispatches → `NotImplementedError` left in the DI path → app dies at
  construct despite green type/lint (the A4 hazard).
- **Fix (preferred).** Make the **scaffolder render them COMPLETE** (declarative/glue category, not a
  body scaffold) — they carry zero judgment (DSN build, `async_sessionmaker(engine, expire_on_commit=False)`,
  qdrant client ctor), and conventions block C already specifies them fully. This removes them from the
  worklist AND the A4 surface. Update `scaffolder.md` (these are glue, regenerated, not NIE) + conventions
  block C (mark the connection factory as scaffolder-complete).
- **Fix (alternative, if judgment ever creeps in).** Teach the planner to recognize
  `infrastructure/<kind>/connection.py` + `postgres/engine.py` as store-profile bodies dispatchable with
  the conventions store profile as the implementer's reference.
- **Verify.** Fresh scaffold: `engine.py`/`connection.py` have no `NotImplementedError`; `create_app()`
  constructs without a connection-factory dispatch.

### P0-3 · F-010 — planner/runner has no `--app` mode (multi-context greenfield)
- **Problem.** `plan_implementation.py` takes ONE manifest + the tree; it scans the whole tree for
  `NotImplementedError` but can only map nodes from the single manifest → every OTHER context's pending
  body is `UNMAPPED`. The validator and scaffolder grew `--app`; the runner didn't. No single command
  maps every body in a multi-context greenfield "scaffold-all-then-verify" run.
- **Fix.** Add `--app <epics-dir>` to `plan_implementation.py` (mirror the validator's glob
  `<dir>/*/manifest.yaml`): load all sibling manifests, build a UNION registry over every context's
  nodes, so no body is UNMAPPED. Thread `--app` through `/verify` (`verify.md`) so the documented
  multi-context flow is single-command.
- **Verify.** `plan_implementation.py <any-manifest> <tree> --app specs/dryrun/epics` lists 0 UNMAPPED
  on the meeting app.

### P0-4 · F-025 — table→repository file dependency missing from the DAG
- **Problem.** The relational table and the repo that `backs` the same aggregate sit at the SAME
  `dag_level` (no manifest edge between `infrastructure.tables` and `infrastructure.repositories`), but
  the repo BODY references the table's columns (`select(meetings_table.c.…)`), so a parallel `/verify`
  could start the repo implementer before the table exists → red / repo-against-column-less-table.
- **Fix.** In `_wire_deps` (`plan_implementation.py` ~222), add a synthetic edge: each relational
  repository depends on its aggregate's table (same store + aggregate) → the table lands one DAG level
  below its repo. (`_wire_deps` currently only wires handler→service and router→handler.)
- **Verify.** Planner DAG places `<agg>` table at a strictly lower level than `<agg>_repository`.

---

## P1 — gate lets "green-but-wrong" through (A4 integrity; more dangerous than blockers — silent)

### P1-1 · F-012 — a table passes mypy+ruff but fails at IMPORT (functional index)
- **Problem.** `Index("ix", "lower(email)", ...)` (bare string) → SQLAlchemy reads it as a column name →
  `ConstraintColumnNotFoundError` at table-construct time. mypy+ruff green; only the final app-construct
  smoke (far from the node) catches it. A table is a "review-tail" node (no executable test) so the
  per-file acceptance misses it entirely.
- **Fix.** (a) `/verify` (`verify.md`) acceptance for an `infrastructure.tables` node: add a metadata
  import smoke `uv run python -c "from <pkg>.infrastructure.postgres import metadata"` — the cheapest
  exercise that actually constructs the Table. (b) `infra-sqlalchemy-table` skill: show the functional
  index idiom `Index("ix", text("lower(email)"))` explicitly + a Hard stop ("a bare string is a column
  NAME; wrap an expression in `text(...)`").
- **Verify.** Re-introduce the bare-string index → the table node's per-file acceptance reds (not just
  the final smoke).

### P1-2 · F-023 — inline `# type: ignore` on content modules passes; there is NO gate
- **Problem.** conventions block E forbids inline `# type: ignore` on content modules (only the pyproject
  `[[tool.mypy.overrides]]` is sanctioned), but `/verify` greps `# noqa: F401` and NOT `# type: ignore`
  (verified: 6 noqa refs, 0 type-ignore refs). Two generated modules carry one:
  `infrastructure/s3/s3_blob_store.py` (`[no-any-return]` on `response["Body"].read()`) and
  `restapi/dependencies.py` (`[attr-defined]`, the scaffolder's `require_role` wrapper stashing
  `__wrapped_role__`) — the latter is SCAFFOLDER-generated, so it recurs on every auth app. mypy "clean"
  is partly because these suppress real errors.
- **Fix.** (a) Add `grep -rn "# type: ignore" src` to `/verify`'s final gate AND the scaffolder
  self-verify (mirror the noqa gate); any hit on a content module fails (allow in `tests/` only, or
  require the pyproject-override form). (b) Fix the scaffolder `dependencies.py` `require_role` pattern
  (`restapi-app-bootstrap`) to not need `[attr-defined]` — carry the role on a typed wrapper (a small
  dataclass/`Protocol`-typed attribute) instead of stashing `__wrapped_role__` on a function. (c) The s3
  boundary (`infra-capability-adapter`) → a typed cast at the boundary (`cast(bytes, …)`), not an ignore.
- **Verify.** The grep gate is green on a fresh auth scaffold (no inline ignores), and red if one is
  reintroduced.

### P1-3 · F-024 — validator accepts an un-generatable dataclass field order
- **Problem.** The Meeting entity declared `created_by` (no default) AFTER defaulted fields — an invalid
  `@dataclass`. `validate_manifest.py` checks field SHAPE but not default-ordering, so it passed; the
  scaffolder silently reordered. Validator shipped a structurally un-generatable manifest, and the
  generated order silently differs from the manifest (invisible-in-review class).
- **Fix.** Add a cheap form check in `validate_manifest.py` (a `_check_field_order` over entities / VOs /
  command-inputs): no field without a `default` may follow one with a `default`. Error at validate time.
  Add a test to `test_validate_manifest.py`.
- **Verify.** A manifest with a non-default field after a defaulted one fails validation with a clear
  message; the meeting manifest (reordered to be valid) still passes.

### P1-4 · F-018 — `test-fake-repository` fakes alias mutable entities → persistence unpinnable
- **Problem.** `FakeMeetingRepository` (and the auth stub) store the entity by reference; `get_by_id`
  returns the SAME object the handler mutates in place → `stored.status == READY` observes the handler's
  in-memory mutation, NOT a recorded `update()` call. A body that mutates but never persists passes
  green. Multiple §9 verifiers found this independently; one root-cause fix strengthens ~5 tests.
- **Fix.** `test-fake-repository` skill template: the fake (a) records an `updated` log (list of
  updated ids/entities) and (b) returns a COPY from `get_by_id`/`get` (`dataclasses.replace(...)` or
  deepcopy) so a "mutate-but-never-persist" body reds. Update the §9 residual recipes that depend on it.
- **Verify.** A handler stubbed to mutate-without-`update()` reds the persistence assert.

---

## P2 — skill / doc gaps (architect & implementer currently guess; friction + latent correctness)

- **F-015 · persist-FAILED-then-re-raise is an unsanctioned 3rd try/except.** ProcessMeeting must set
  status FAILED, persist, then re-raise. `application-command` Rule 5 sanctions only the compensating-tx
  rollback. *Fix:* add this "failure-state transition then re-raise" pattern (write the state the caller
  needs, then re-raise) to `application-command` (or a new `pattern-failure-state`) — name it so a
  body-blind implementer has a sanctioned path.
- **F-016 · compensating-tx assumes a `*_best_effort` method.** `pattern-compensating-tx` says the undo
  call is `<verb>_best_effort`; the protocol modelled only `delete`. *Fix:* make `*_best_effort` optional —
  allow the plain protocol method, swallow errors at the call site; or tell the architect to model a
  `delete_best_effort` when the skill needs it.
- **F-004 · multi-tenant `workspace_id` stamping undocumented.** The `caller_id`-from-auth convention is
  single-valued. *Fix:* one line in `application-command` / `application-query` / `restapi-endpoint` /
  `restapi-auth-dependency`: "auth-derived fields beyond `caller_id` (e.g. `workspace_id`) stamp from
  `CurrentUser` the same way; a tenant-scoped QUERY also stamps `workspace_id` and binds `user: CurrentUser`."
- **F-005 · read-model with DB-managed audit columns has no home.** A read that DISPLAYS `created_at`
  needs a projected read-model, but a domain repo can't return an application DTO, and a per-read domain
  read-model VO is heavy. *Fix:* a `pattern-read-model` skill or a conventions note deciding where the
  projection lives and how a domain repo returns it without importing application.
- **F-006 · "mutate-then-return-a-view" fits neither command(→UUID) nor query(read-only).** *Fix:*
  document the idiom (model as a COMMAND returning the id + a follow-up read) in `application-command` /
  conventions, so a synchronous "do work and return the result" op has a canonical shape.
- **F-019 · a handler depending on a concrete domain SERVICE can't be structurally faked.** mypy rejects
  a structural fake where the ctor annotates the concrete `QuotaPolicy` (not a Protocol). Same family as
  notes/13's type:ignore-on-concrete-stub. *Fix:* `test-application-handler` / `test-fake-repository` —
  either the fake subclasses the service, or the handler injects via a Protocol; document the choice.
- **F-008 · tunable-VO stem convention ambiguous.** conventions block A implies `<Stem>Tunable ←
  <Stem>Settings`, but the fixture sources `LockoutTunable` from `AuthSettings` (mismatch) and works.
  *Fix:* state plainly whether stems MUST match (they don't — make it advisory + explain the DI wiring).
- **F-013 · root `tests/conftest.py` imports `create_app` at module level** → every `tests/unit/**`
  collection pays the whole infra import, so a domain-VO red→green is blocked by an unfilled sibling
  table. *Fix:* `test-integration-isolation` / the conftest template — make app construction a FIXTURE
  used only by tests that need it, not a module-level import.

---

## P3 — robustness / process / lint

- **F-021 · scaffolder died mid-run on a long single-pass brownfield re-scaffold** (socket error after
  ~50 min; report + self-verify lost; left `main.py` imports unsorted — caught only by whole-tree ruff).
  *Fix:* a resumable/checkpointed scaffold for long re-scaffolds, or split the pass; AND `/scaffold`
  should run a whole-tree `ruff --fix` + report-presence check after the scaffolder returns (the
  implementer per-file gate doesn't cover scaffolder-owned glue).
- **F-001 / F-002 · corpus path hard-coded.** Commands resolve `specs/use-cases/` + `specs/epics/`;
  `meta-uc-author` hard-stops outside `specs/use-cases/`. *Fix:* a `--corpus` / `--epics-dir` arg (or
  config knob) on the pipeline commands + relax the meta-uc-author hard-stop to a configured root, so a
  sandbox/second project can coexist with the canonical corpus.
- **Delta skipped `/refine-usecases`** (no `questions_for_ba.md` / `*.refined.md`; product decisions
  folded inline). *Fix:* document when refinement is elidable for a delta, or always run it.
- **ConflictError gap → duplicate-PK is HTTP 500, not 409.** Repos map `IntegrityError` to the base
  `DomainError` (500) — no `ConflictError` in the catalog. *Fix (earn-its-place):* the architect adds
  `ConflictError` the first time a UC inserts on a unique constraint.
- **ruff select lacks `B006`** (mutable default arg) — a `status=[]` default passed. *Fix:* add `B` (or
  `B006`) to the ruff select in conventions block E.

---

## Suggested sequencing
1. **P0 as one "runner hardening" PR** (`plan_implementation.py` + conventions block A repo-naming +
   scaffolder connection-factory + `verify.md --app`). Re-run the meeting app BLIND end-to-end; the
   honesty caveat should disappear (no manual overrides needed).
2. **P1 as one "gate-integrity" PR** (table import smoke, `# type: ignore` gate + the two bootstrap
   pattern fixes, validator field-order check, fake-by-reference fix). Closes the A4 class.
3. **P2** skill/doc gaps as touched (each is small + independent).
4. **P3** robustness/lint when convenient.

Cross-ref: every F-NNN above is detailed in `notes/pipeline_dryrun_feedback.md`. The §9 residual
WEAK-assert queue (test-strength, not body defects) is in that report's "residual review surface"
section and is a separate, optional strengthening track (depends on the F-018 fake fix landing first).
