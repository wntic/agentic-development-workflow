---
description: "Manifest validation gate — run the stdlib graph validator (form + graph + loud degradation + §16 skill-coverage) between manifest build and scaffold (spec §6, §16)"
argument-hint: "[manifest] | <NN-slug> | --app <epics-dir> | (empty)"
---

You are the **runner** at the validation gate (spec §6) — the deterministic checkpoint **between
Phase 2 (manifest build) and Phase 3 (scaffold)**. There is **no LLM judgement and no agent** here:
you run the stdlib validator, then **interpret and route** its report. The validator checks the
*graph*, not the code (types/signatures are the toolchain's job, §0-principle 3), so it is fast,
zero-dependency, and runs before any expensive agent is spawned.

`$ARGUMENTS` is one of: empty (validate the discovered epic) · a manifest path · an `<NN-slug>`
epic name · explicit flags (`--app <epics-dir>`, `--uc-dir <dir>`).

## 1. Resolve the target

- **Manifest.** If `$ARGUMENTS` names a path, use it. If it is an `<NN-slug>`, the manifest is
  `specs/epics/<NN-slug>/manifest.yaml` (the corpus root is configurable — honour an explicit path or
  `--epics-dir` in `$ARGUMENTS`, only fall back to `specs/epics/`). While the pipeline is pre-build,
  the fixtures under `.claude/tools/fixtures/` (`helpdesk_manifest.yaml`, `vector_rag`, `label`) are
  valid targets. If discovery is ambiguous (several epics, no obvious one), **stop and ask** — do not
  guess.
- **Multi-context app (block F).** When the epic has sibling context manifests under the same epics
  dir (a `<epics-dir>/<NN>-slug/manifest.yaml` with neighbours), cross-epic refs (`<subdomain>:<Name>`)
  only resolve against the siblings. Pass `--app <epics-dir>` so the validator resolves them; without
  it, a legitimate cross-epic edge surfaces as a (non-blocking) warning, not an error.
- **Sources.** When the manifest carries `sources:` you want checked against the UC corpus, add
  `--uc-dir <use-cases-dir>`.

## 2. Run the validator

```
uv run .claude/tools/validate_manifest.py <manifest> [--app <epics-dir>] [--uc-dir <dir>]
```

It prints one line per finding (`[error|question|warning] <code>: <message>`) then a summary
(`<manifest>: OK|FAILED — N error(s), Q question(s), W warning(s)`). Exit `0` only when there are
**no errors and no open questions**; warnings never block. The script is self-contained (PEP 723) —
nothing to install.

## 3. Interpret + route the report

The validator does four things (spec §6 + §16); each finding routes to a different owner — that
routing is the gate's whole job:

- **`error` (form / graph integrity).** A required field missing, a broken edge (a `dependencies`
  pointing at a non-existent protocol, `endpoint.handler` at no command/query, `repository.store` at
  no datastore), an invalid `@dataclass` field order. This is the **architect's** manifest bug →
  stop, report it, hand back to `/build-manifest` or `/apply-delta`. **Do not scaffold.**
- **`error` + code `skill_gap` (§16 presence-gap).** A manifest declares an artifact `kind` with no
  entry in the `kind→skill` registry. This is **not** an architect bug — it is a *catalog* gap: the
  knowledge layer has no producer skill for this kind. Route it to `meta-skill-author` to draft the
  skill, then a **human accepts** it (the ~5-line review, §16 / PRINCIPLES C5 — never self-mint),
  then re-validate. A **coverage-gap** (the skill exists but does not fit this case) is a judgement
  call the agent escalates, not something this gate detects.
- **`question`.** An unresolved `sources:` ref (with `--uc-dir`) or another open item the validator
  cannot settle. Exit is `1`; report it and route to the architect to resolve before scaffolding.
- **`warning` (loud degradation — never blocks).** `unspecified_body` (a body-bearing node with
  neither `behaviour` nor `notes` — the implementer would have nothing to fill from),
  `unspecified_transition` (a `persists` command whose change is unexplained — a hidden transition),
  or an unresolved cross-epic ref when `--app` was omitted. Surface every warning so it is not
  silently lost; an `unspecified_*` warning is the architect's signal to add a contract channel, and
  a cross-epic warning is usually a missing `--app` (re-run with it). The scaffolder may proceed on
  warnings, but a reviewed manifest should generally clear the `unspecified_*` ones.

## 4. Report

State plainly: the manifest, the flags used (`--app` / `--uc-dir`), `OK` or `FAILED` with the
error/question/warning counts, and — for anything non-clean — **who owns the fix** (architect for
form/graph/questions; `meta-skill-author` + human for a `skill_gap`; the architect's judgement on
whether to clear `unspecified_*` warnings). On a clean `OK`, say the manifest is cleared for
`/scaffold`.

## Notes

- This wrapper adds **no logic** — the validator's `SCHEMAS` + graph checks are canonical (spec §6).
  Its value is being the named gate with the routing above, at parity with the rest of the chain
  (`/build-manifest` → **`/validate-manifest`** → `/scaffold` → `/verify`).
- The architect already runs the validator inline while building a manifest; this command is the
  standalone gate the runner invokes before scaffolding (and a quick manual check on any fixture).
- The validator's own test suite (it lives outside the default `tests/` path) is
  `uv run pytest .claude/tools/test_validate_manifest.py` — run it if you change the validator, not
  to validate a manifest.
