# Agentic codegen pipeline

Tooling for an **agentic, manifest-driven code-generation pipeline**: a system of AI agents that
turn business-analyst use cases into a backend and then maintain it through change.

This repository is **not** an application — it is the pipeline that *produces* one. The pilot
target is a strict hexagonal / four-layer Python backend (domain → application → infrastructure
→ REST).

## The core idea

Three layers are kept strictly separate (see [`codegen_workflow_spec.md`](codegen_workflow_spec.md),
the design doc — read it first):

- **Knowledge** — *how* to write a component — lives in the **skills** (`.claude/skills/`).
- **Specification** — *what* the specific component is — lives in the **manifest** (one YAML per epic).
- **Orchestration** — *who* runs what, when — lives in the **runner / agents**.

And one principle governs determinism — **it lives in verification, not authoring**:

- All code (declarative shells, graph-glue, and method bodies) is **authored by agents**: a
  **scaffolder** lays down every file with its scaffold + contract comment; an **implementer** fills
  the bodies behind those contracts.
- Consistency is held by **deterministic verifiers** — a graph validator + the target language's
  toolchain (compile / type-check / lint) + canonical behavioural tests. Who wrote a line matters
  little; what checks it does.

The application handlers are the backend's **public API**; an entrypoint (REST/FastAPI first; CLI,
gRPC, … later) is a driving adapter over it. Language-specific knowledge is isolated in the
knowledge layer, so a new language is an additive pack rather than a tooling rewrite.

> **Redesign in progress (2026-06).** An earlier deterministic Jinja2 *generator* (`src/codegen/`) is
> being retired in favour of the agent + verifier path above. It still lives on disk and is removed
> only once the agent path is proven on an epic. The spec is the source of truth for the target
> design; see its "Смена курса" note.

## Repository map

```
codegen_workflow_spec.md          # THE design doc — read first
codegen_pipeline_v2_with_ingestion.svg  # the pipeline diagram (updated for the redesign)
.claude/
  skills/                         # the knowledge layer — one artifact-kind per skill
  agents/ commands/ templates/    # pipeline agents, slash-commands, the manifest schema doc
specs/use-cases/                  # example BA use cases — the pipeline input
examples/                         # example manifests (Helpdesk, Vector-RAG)
src/codegen/                      # the deterministic generator — being retired (see note above)
```

## Status

What exists today: the skill catalog, the manifest schema + graph validator, example manifests, and
the (being-retired) generator. The build order for the redesign is in `codegen_workflow_spec.md` §13:
a stdlib-only validator → the Python knowledge layer (skills + conventions) → the agent-scaffolder →
the implementer + verify loop → a first epic end-to-end without the generator.
