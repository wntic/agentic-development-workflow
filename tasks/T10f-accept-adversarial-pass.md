# T10f — Adversarial pass over accept.py's own gates

## Goal
`accept.py` has now shipped three defects found by *using* it, not by its tests:

1. **A silent false-accept in the freshness gate, shipped since T05** — an unresolvable pin produced
   an empty diff, which read as PASS. Exposed and closed incidentally by T10d.
2. **T10c** — a red deny on pure verdict formatting (backticked SHA, `## Adversarial pass` vs
   `review`).
3. **T10e** — `_orphan_sweep` classifying a `Class: behavioral` change as a removal and harvesting
   19 generic identifiers out of the Interface sketch.

Defect 1 is the alarming one: it fails **open**. The other two fail closed (annoying, visible, and a
human notices). A gate that silently passes is worse than no gate, because the whole trust model
(S8: the gate is the backstop for every bypassable hook) rests on it. Two independent defects
surfacing from a single change (`users/002`) is a signal about this script's test coverage.

The T10d builder flagged this pass as worth doing. This is that task.

## Depends on
T05, T10, T10b, T10c, T10d, T10e (do this *after* T10e so the classifier fix is in scope).

## Read first
- `.claude/tools/accept.py` — the whole gate inventory, and every early-return / empty-input path.
- `.claude/tools/test_accept.py` — what is currently covered, and more importantly what shape of
  case is *absent* (the pattern in all three defects is degenerate/empty input, not wrong logic).
- `workflow_v3_spec.md §5.3`, `§5.4` — the acceptance preconditions and the freshness rule these
  gates are supposed to implement.
- `PRINCIPLES.md` S4, S5, S8, S9.
- `tasks/INDEX.md` — the T10d sign-off note recording defect 1.

---

## ESCALATION RESOLVED — author's decision, 2026-07-26

The audit ran, fired this task's own `>~3 fail-open paths` stop condition (**7 found**, plus 3
non-direction defects), and stopped before fixing. **Deliverable 1 is DONE** — the register is
`notes/19_accept_gate_audit.md` (commit `d24d51b`). Do not redo it; read it as the specification of
what to fix. This section is the answer it escalated for.

**Approach: (b) — a validated-input layer plus one enforced rule.** Not (a), seven local patches.
The register's own finding 11 is the argument: `gate.py` guards every integrity `_git` call with
`if rc != 0: FAIL`; `accept.py` guards neither diff call that produces a gate's evidence, and the
three sites that *do* have the reflex got it from whoever wrote them — one of them added by T10d
only after it fell over in production. Seven patches leave gate #15 exposed to the same mistake.

Make "input could not be determined" a **representable value** rather than an empty container —
`check=True` on the base diff, `resolve_targets` distinguishing "no target" from "unknown",
`junit_ac_test_ids` reporting uncorrelated ac-ids — and pin the rule:

> A gate whose input could not be determined returns **FAIL** if it guards trust, **FLAG** if it is
> a review aid. Never PASS, never absent from the report.

enforced by a parametrised `test_no_gate_passes_on_undetermined_input` that walks the gate list, so
a future gate is covered by construction. That test is the durable deliverable; the seven fixes are
its first customers.

**Direction per finding** (the builder's proposal, with F-02 and F-05 decided by the author):

| Finding | Direction | Note |
|---|---|---|
| F-01 unresolvable `--base` → empty diff | **FAIL** | the T10d defect, one line away |
| F-02 birth change escapes adversarial pass | **FAIL** | unknown target ⇒ assume a capability birth ⇒ require the pass. Asymmetry decided: a spurious adversarial pass costs one agent run; a skipped one on a capability birth means an unreviewed first change |
| F-03 `spec.lint` clean on unseen input | FLAG | review aid; also **delete or fix the dead duplicate-capability check** (`seen` is filled from a glob, so it can never fire) |
| F-04 merge-fidelity vacuous | **FAIL** | zero ACs and token-less ACs both |
| F-05 `## Removed` with no symbols | FLAG | consistency with T06f Part B, which made a *missing* heading FLAG on this same reasoning. **Does not need the T03 vocabulary decision.** Requires rewriting `test_orphan_sweep_does_not_flag_when_the_heading_is_present`, which currently pins the PASS deliberately — that rewrite is sanctioned |
| F-06 provenance `?` + wrong-file correlation | **FAIL** | the severest: `--execute` can merge spec content that makes the base branch's own gate RED, i.e. the acceptance script breaking S9. Also correlate on junit `classname`, not function name alone |
| F-07 absent evidence read as fine | FLAG | both sites: unresolvable in-flight `Affects`, and a missing `docker.alembic` check falling through to `PASS "Docker tier ran"` (inverts T04b) |
| F-09 unresolvable target erases two gates | — | fail-closed already; fix the *reporting* half so `spec.lint`/`orphan.sweep` still print as SKIP |
| F-11 capability-birth path untested | — | add the integration test; its absence is *why* F-02 hid. Fix the bare `FileNotFoundError` on the missing `capability.md` template |

## Deliverables
- ~~A written finding register~~ **DONE** — `notes/19_accept_gate_audit.md`, commit `d24d51b`.
- `.claude/tools/accept.py` — the validated-input layer + the seven direction fixes above.
- `.claude/tools/test_accept.py` — the parametrised
  `test_no_gate_passes_on_undetermined_input` walking the gate list, plus a case per finding.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green.
- For each fail-open defect found: demonstrate the old behaviour (test fails against the pre-fix
  function) before fixing it. A finding with no failing test is a claim, not a finding.
- **The `users/002` before-baseline must still reproduce.** The register records it verbatim; the
  branch `change/users-002` (`a931ee6`) and tag `baseline/users-002` (`dd3a64b`) are still present
  for exactly this. Reproduce from the repo root with a detached worktree of that branch and
  `--base markdown-specs` (**not** `main` — `main` is the v2 archive; INDEX rule 4). Expect the same
  `verdict: ACCEPTABLE`. This task must change the answer only for degenerate input, never for a
  legitimate change. Note F-02 makes this a real risk: `users/002` births a capability, so a careless
  fix could newly demand something it already satisfies.

## Out of scope / Escalate if
- Do NOT redesign the acceptance preconditions. This audits the implementation of `§5.3`/`§5.4`
  against its own spec; a *disagreement* with the spec is an escalation, not a fix.
- Do NOT fold in `gate.py`. Same defect class probably lives there too, but that is its own task —
  scoping both into one dispatch is how audits get shallow.
- ~~If the register finds more than ~3 fail-open paths, stop and escalate~~ — **this clause already
  fired and is resolved.** 7 were found; the structural answer is approach (b) above. Do not escalate
  again on the count; escalate only if a *specific* fix cannot be made without a canon change.
- Two register findings are deliberately NOT in this task — do not fix them here:
  **finding 10** (`ESCALATE` is deletable — the change dir is not in `gate.py`'s `PROTECTED_PATHS`,
  so §5.3's "only the human removes it" is unenforced) belongs in `gate.py`'s integrity inventory,
  filed as **T04e**; and the `/accept-change` command never passing `--base` (so it defaults to
  `main`, the wrong base for this repo) is filed as **T10g**.
