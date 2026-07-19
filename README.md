# Spec-driven agentic development workflow

Tooling for a **spec-driven agentic development workflow**: living Markdown specs per bounded
context, a change cycle (red tests → code → run → criteria check → iterate), and deterministic
gates that hold the trust. AI agents build and maintain a strict hexagonal Python backend
**in this repository** through reviewed, branch-isolated changes.

## The core idea

Three layers are kept strictly separate (see [`workflow_v3_spec.md`](workflow_v3_spec.md),
the design doc — read it first; Russian):

- **Knowledge** — *how* to write an artifact — lives in the **skills** (`.claude/skills/`).
- **Specification** — *what* to do and how to verify it — lives in `specs/`: a living spec per
  bounded context (small per-capability files), changed only through delta specs whose
  **acceptance criteria are a checklist agents can only tick with machine-checkable proof**.
- **Enforcement + orchestration** — who does what, what is forbidden, when it is "done" —
  lives in the agents/commands and, first of all, two scripts: `gate.py` ("is it green")
  and `accept.py` ("may it merge").

Two principles carry the design (both earned the hard way — see
[`notes/15_v3_design_review.md`](notes/15_v3_design_review.md)):

- **Hooks are ergonomics; trust is a post-hoc check against the git baseline.** Prevention is
  porous by construction — the gate verifies the *result* (protected-tree diff, test inventory,
  junit-backed criteria, self-hash), so bypassing a hook only gets the result invalidated.
- **One change = one branch; `main` is always green.** Red tests, code, and the verdict live on
  the change branch; `main` only ever receives green merges through `accept.py`.

The cycle separates authorship from judgment: a **test-author** writes red tests from the spec,
an **implementer** (who cannot touch tests) makes the gate green, a **fresh-context evaluator**
proves the criteria against the running app. Accepted deltas merge into the living spec, so
documentation compounds instead of rotting.

## Repository map

```
workflow_v3_spec.md               # THE design doc (Russian) — read first
notes/15_v3_design_review.md      # the adversarial design-review register behind the hardening
tasks/                            # build-out decomposition (T01–T11) — status in tasks/INDEX.md
.claude/                          # skills (knowledge), agents/commands (orchestration),
                                  #   gate.py / accept.py / hooks (enforcement; being built)
specs/use-cases/                  # BA use cases, verbatim — input material
specs/<context>/                  # living spec of a bounded context (created by the cycle)
src/ tests/                       # the target app, maintained through the change cycle
```

## Status

**v3 is being built** — the decomposition and per-task status live in
[`tasks/INDEX.md`](tasks/INDEX.md); each task is executed by a builder agent via `/build-task`
and verified by the runnable checks in its task file.

The predecessor (v2: a YAML-manifest pipeline with a stdlib graph validator and
scaffolder/implementer agents over the manifest DAG) was proven end-to-end and is archived at
tag **`v2-archive`** in `main`'s history; its design rationale is kept in
[`codegen_workflow_spec.md`](codegen_workflow_spec.md).
