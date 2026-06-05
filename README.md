# Agentic codegen pipeline

Tooling for an **agentic, manifest-driven code-generation pipeline**: a system of AI agents
and a deterministic generator that turn business-analyst use cases into a Python backend and
then maintain it through change.

This repository is **not** an application — it is the pipeline that *produces* one. The pilot
target is a strict hexagonal / four-layer Python backend (domain → application → infrastructure
→ REST), and the generator is exercised end-to-end on the example manifests under `examples/`.

## The core idea

Three layers are kept strictly separate (see [`codegen_workflow_spec.md`](codegen_workflow_spec.md),
the design doc):

- **Knowledge** — *how* to write a component — lives in the **skills** (`.claude/skills/`).
- **Specification** — *what* the specific component is — lives in the **manifest** (one YAML per epic).
- **Orchestration** — *who* runs what, when — lives in the **runner / agents**.

And one dividing line governs determinism — **scaffold-first**:

- Declarative artifacts (entities, value objects, enums, exceptions, DTOs, REST schemas, settings)
  and all graph-glue (DI container, `__init__`, imports, `pyproject.toml`, route registration) are
  **generated** from Jinja2 templates — no LLM.
- *Every method body* (handlers, infra adapters, endpoint functions, the relational table schema) is
  emitted as a **scaffold** — a signature + contract comment + `NotImplementedError` — that the
  implementer LLM fills behind the contract.

Which path a node takes is **derived from its category**, never declared in the manifest.

## Quick start

The project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.12.

```bash
uv sync                                  # install the generator + its test deps
uv run pytest                            # run the generator's test suite
uv run ruff check src examples           # lint

# generate a full hexagon from a manifest (output under examples/generated/, git-ignored):
uv run python examples/generate.py examples/helpdesk_manifest.yaml --package hdk
uv run python examples/generate.py examples/vector_rag_manifest.yaml --package vrag
```

See [`examples/README.md`](examples/README.md) for what the generator emits.

## Repository map

```
codegen_workflow_spec.md          # THE design doc — read first
codegen_pipeline_v2_with_ingestion.svg  # the pipeline diagram
src/codegen/                      # the generator (Python package)
  manifest/                       #   Pydantic schema + graph validator
  generator/                      #   the scaffold-first forward generator
  templates/                      #   Jinja2 templates (declarative + glue)
  scaffold/                       #   package-agnostic reference files copied verbatim
tests/                            # the generator's own test suite + fixtures
.claude/
  skills/                         # the knowledge layer — one artifact-kind per skill
  agents/ commands/ templates/    # pipeline agents, slash-commands, the manifest schema doc
specs/use-cases/                  # example BA use cases — the pipeline input
examples/                         # example manifests + a script that runs the generator
```

## Status

What exists today: the skill catalog, the manifest Pydantic schema + graph validator, and the
scaffold-first generator (green end-to-end on the example manifests). Still to build: the
analyst / architect / implementer agents and the pipeline slash-commands — see the work order in
`codegen_workflow_spec.md`.
