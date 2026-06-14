---
description: "Scaffold a validated manifest into a disposable project tree via the scaffolder agent (spec §3)"
argument-hint: "<manifest> <package> <output-dir>  |  <manifest>  |  (empty)  |  <context-manifest> into an existing multi-context tree"
---

You dispatch the **scaffolder** agent (spec §3) to lay down the entire target tree from a validated
manifest — declarative artifacts + glue rendered in full, every body as a `raise NotImplementedError`
scaffold, the red canonical tests — then it freezes the baseline. You do **not** scaffold by hand and
you do **not** fill any body (that is `/verify` → the implementer).

`$ARGUMENTS` is one of: `<manifest> <package> <output-dir>` (explicit) · `<manifest>` alone (derive the
rest) · empty (discover / ask).

## 1. Resolve inputs

- **Manifest** — the path in `$ARGUMENTS`, else the epic under `specs/epics/<NN>-slug/manifest.yaml`,
  else (pre-pipeline) the fixture `.claude/tools/fixtures/helpdesk_manifest.yaml`. If several plausible
  manifests exist and none is named, **stop and ask**.
- **Package name** — the second token if given; else derive a short package id from `meta.epic` /
  the manifest (e.g. `01-helpdesk` → `hdk`). State the chosen name.
- **Output dir** — the third token if given; else `examples/generated/<package>/`. **If the output dir
  already exists and contains filled bodies** (a previous run), warn and **ask** before proceeding —
  the scaffolder regenerates declarative/glue but must not clobber an implementer-owned body (§4); a
  fresh tree is the clean case. For a clean test run, pick a NEW dir (e.g. `examples/generated/helpdesk6/`).

**Multi-context (app-mode).** A context that draws cross-epic edges (`<subdomain>:<Name>`, e.g. Tickets →
`auth:IUserRepository`) is scaffolded into the SAME package as the context it depends on (`conventions`
block F — contexts as sibling subpackages, shared substrate). When `$ARGUMENTS` names such a context (or
the output tree already holds another context), treat the in-scope set as the **app**: the new context's
manifest + the manifests of the contexts already in the tree. Scaffold into the existing output dir, not
a fresh one.

## 2. Pre-flight (deterministic, no agent)

`uv run .claude/tools/validate_manifest.py <manifest>` — must be `ok`. For a **multi-context** manifest
(cross-epic edges present), validate with `--app specs/epics` so those edges resolve against their
sibling manifests (an unresolved cross-epic ref is then a real error, not a warning). A form/graph error
or a §16 presence-gap (a `kind` with no skill) is the **architect's** to fix; stop and report. The
scaffolder only runs on a fully valid, fully covered manifest.

## 3. Dispatch the scaffolder

Spawn one **`scaffolder`** subagent. Its invocation prompt carries only the resolved inputs (it reads
the `conventions` skill, the per-node producer skills, and the reference skills itself):

- the **validated manifest** path — or, in app-mode, the **set of in-scope context manifests** (the new
  context + the contexts already in the tree), with a note to emit the shared substrate from their UNION
  (`conventions` block F) and to resolve `<subdomain>:<Name>` cross-epic refs as cross-subdomain imports;
- the **package name** + the **output root** (the existing tree, in app-mode);
- a reminder that the output is a disposable, git-ignored src-layout project
  (`<output>/pyproject.toml` + `<output>/src/<package>/` + `<output>/tests/`).

The scaffolder walks the graph in one pass, self-verifies (ruff + reference-integrity + mypy green on
the `NotImplementedError` bodies + unit tests collecting red-on-NotImplementedError), and as its **last
step freezes the scaffold baseline** (`scaffold_snapshot.py snapshot <output>` → `<output>.scaffold/`)
so `/verify` can later attribute every implementer edit. Do not fill any body to clear a red — that is
the implementer's, and it breaks anti-collusion (§9).

## 4. Report + next step

Relay the scaffolder's report (files written, body scaffolds, flat vs manual tests, any
degradations/escalations, toolchain status). Then tell the user the next command:

```
/verify <manifest> <output-dir>
```

— the runner that fills the body scaffolds (dispatching implementers by DAG level) and verifies to
green. `/verify` is also where a single body is exercised in isolation: `/verify <node>`.

## Notes

- One scaffolder, one pass — it is **not** parallelized (glue needs the whole-graph view, §3/§11);
  parallelism is the implementers' inside `/verify`.
- The scaffolder is the **only** role that creates files. If it stops on a presence-gap / coverage-gap
  (an uncovered `kind`, a node that fits no skill), that is a human-gated skill-authoring step
  (`meta-skill-author`, §16), not something to improvise around.
- Re-running `/scaffold` on an existing tree regenerates declarative/glue and leaves filled bodies
  alone (§4) — but for a clean end-to-end test, scaffold into a fresh output dir.
