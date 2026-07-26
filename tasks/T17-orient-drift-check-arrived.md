# T17 — `/orient` still skips a drift-check that shipped two tasks ago

## Goal
`.claude/commands/orient.md:28-30` says:

> This command's drift-check — comparing capability files against the observable surface (OpenAPI
> routes) and listing `main` src-commits not tied to change tags (spec §5.5) — is *planned
> (T05/T10)*: it arrives with `accept.py` and `/accept-change`; **until then, skip that step**.

T05 and T10 are both `[x]`. `accept.py` already performs and prints the §5.5 drift report — observed
verbatim on a real `--execute`:

```
drift-check on markdown-specs (spec §5.5):
  every src commit is attached to a change/* tag
  OpenAPI route⊆operation drift is surfaced by /orient (needs a constructed app); not re-run here
```

So each side points at the other: `accept.py` defers the OpenAPI half to `/orient`, and `/orient`
defers the whole thing to `accept.py`'s arrival. **Nobody runs the OpenAPI half.** Found by the human
running `/orient` in T16's venue (2026-07-26), who did the check by hand and found it clean — which
is the only reason it is not a live gap today.

This is §5.5's whole point: an unlegalised hotfix shows up as a `main` src-commit with no `change/*`
tag, and capability drift shows up as a route the spec does not describe. One half is now automated
and the other is documented as "skip".

## Depends on
T05, T10 (both shipped — that is the premise), T04 (`gate.py`'s construct-smoke already builds the
app, so a constructed `app.openapi()` is available machinery to reuse, C7).

## Read first
- `.claude/commands/orient.md` — the whole file, and lines 28-30 in particular.
- `workflow_v3_spec.md §5.5` — what the drift check is *for*: the hotfix-legalisation tail
  (`/spec --retro`), not a general lint.
- `.claude/tools/accept.py` — the drift report it already emits at the end of `--execute`, including
  the sentence that hands the OpenAPI half to `/orient`. **Reuse it; do not restate it** (C7).
- `.claude/tools/gate.py` — `smoke.construct` (`create_app()` + `app.openapi()`): the app-construction
  machinery already exists and is the cheap way to get the route list.
- `PRINCIPLES.md` S4 (a rule with no enforcement does not exist), C7.

## Deliverables
- `.claude/commands/orient.md` — delete the *planned (T05/T10)* deferral and describe the step as
  live. Say **how** it runs, in the same spirit as the rest of the command: point at the script that
  owns each half rather than restating the logic.
- **Decide where the OpenAPI half lives.** Two shapes, pick one and say why:
  **(a)** `/orient` constructs the app and diffs `app.openapi()` routes against the capability files
  — prose in the command, the LLM does the comparison; or
  **(b)** it becomes a script (or a flag on an existing one) so the answer is deterministic and the
  command just relays. (b) is more in keeping with S4 and with how every other must-hold check in
  this workflow ended up; (a) is cheaper and the comparison is genuinely semantic (a route may be
  described in prose that no grep matches). The semantic half may be why the spec left it to a
  reader — check §5.5 before assuming (b).
- Whichever shape wins, the **hotfix half** (src-commits on the base with no `change/*` tag) is
  already deterministic in `accept.py` — `/orient` should invoke or cite it, never reimplement it.

## Verification
- Run `/orient` in this repo: the drift step executes and reports, rather than announcing itself as
  planned.
- Run it in T16's venue (`~/Projects/adw-consumer-probe`): its one route `GET /health` is described
  in `specs/health/service-health.md`, and every `main` src-commit is tied to `health/001` — so the
  expected result is **clean**, and the human's manual check on 2026-07-26 is the oracle.
- Manufacture drift and see it caught: add a route to the venue's app without touching the spec →
  the OpenAPI half reports it. This is the check that matters; a step that runs but cannot fail is
  the defect class `notes/19` is about.
- If (b): its tests green, and the new script obeys T10f's undetermined-input rule (an app that
  cannot be constructed must not read as "no drift").

## Out of scope / Escalate if
- Do NOT turn the drift check into a blocking gate. §5.5 is a *surfacing* mechanism — a hotfix is
  legal, just not silent (`/spec --retro` legalises it). Making it deny would change canon.
- Do NOT reimplement the hotfix half that `accept.py` already does (C7).
- **Escalate if** §5.5 turns out to require the OpenAPI comparison to be semantic in a way no script
  can settle. That is a real answer, not a failure — but then say so in the command, instead of
  leaving a deferral that reads as "not built yet".
