# Generator examples — run it yourself

Two epic manifests and a script that runs the forward generator on them, so you
can see what a manifest turns into.

```
examples/
  helpdesk_manifest.yaml     # tickets + JWT bearer auth — the primary end-to-end exercise
  vector_rag_manifest.yaml   # polyglot persistence (Postgres + Qdrant) + an OpenAI embedder
  generate.py                # validate a manifest + generate the whole hexagon
```

## Run

From the repo root:

```bash
# the helpdesk epic → examples/generated/hdk/
uv run python examples/generate.py examples/helpdesk_manifest.yaml --package hdk

# the vector-RAG epic → examples/generated/vrag/
uv run python examples/generate.py examples/vector_rag_manifest.yaml --package vrag
```

The script validates the manifest (Pydantic form + graph), then generates the
full hexagonal slice under `examples/generated/<package>/` (+ `tests/`). Output is
disposable and git-ignored — re-run any time. (Migrations are **not** generated —
Alembic owns the chain; see the storage redesign.)

Inspect what came out:

```bash
find examples/generated/hdk -name '*.py' | sort
cat examples/generated/hdk/restapi/routers/tickets.py
cat examples/generated/hdk/domain/support/ticket.py
# lint it (the generated package is first-party for its own imports):
uv run ruff check --config 'lint.isort.known-first-party=["hdk"]' examples/generated
```

## What you get

From one manifest, every layer:

- `domain/` — entity shells (fields + identity), value objects, enums, repository and
  capability protocols, domain services, and the graph-derived exception catalog.
- `application/` — frozen command/query DTOs, scaffolded handler bodies, **canonical
  behaviour tests** (generated from the manifest's `behaviour:` blocks), and in-memory
  fake repositories.
- `infrastructure/` — SQLAlchemy Core table scaffolds, the repository adapters, SDK
  capability adapters (e.g. JWT, an embedder), `pydantic-settings`, and the
  `dependency-injector` container.
- `restapi/` — Pydantic schemas, routers, the FastAPI app (`create_app`), derived auth
  dependencies (`get_current_user` / `require_role`), and the central error handler.

The split between **generated** (declarative + glue, always overwritten) and
**scaffolded** (a body the implementer LLM fills behind a contract) is derived from each
node's category, never declared in the manifest. Every method body — handlers, capability
adapters, the relational table schema — is emitted as a scaffold (`NotImplementedError` +
the contract comment); the declarative domain, DTOs, REST schemas, settings, and all
graph-glue are generated whole.

## What a manifest may contain

See `helpdesk_manifest.yaml` for the broadest worked example (auth slice + a CRUD slice
with a cross-aggregate domain service) and `vector_rag_manifest.yaml` for polyglot
persistence and a non-CRUD capability. The manifest carries **identifiers and contracts
only** — module paths, class-name suffixes, imports, DI wiring, and `__init__` re-exports
are all derived by the generator at dispatch time. A manifest using a node kind the schema
does not yet model is rejected loudly (a clear error, never silent wrong code).
