# T05 — accept.py + its test suite (WP3b)

## Goal
Acceptance preconditions as a script, not command prose (E-09 / S4): the only path by which
a change reaches main and the canonical spec.

## Depends on
T04.

## Read first
- Spec §5.4 (the six gates + post-approval actions), §5.5 (drift-check), §2 (merge/tag/
  delete semantics), §3.3 (`[m]`).
- `notes/15_v3_design_review.md` — E-08/09, L-03/04/06/07, O-04.

## Deliverables
- `.claude/tools/accept.py` — stdlib-only.
- `.claude/tools/test_accept.py`.

## Steps
1. CLI: `accept.py <context>/NNN [--execute]`. Default = check mode (prints gate results +
   the prepared merge diff for human review); `--execute` performs the actions only after
   all gates pass.
2. Gates in §5.4 order: criteria all `[x]|[m]` with junit backing (reuse gate.py's checker,
   import it — one implementation); verdict SHA == branch HEAD else demand recompute (the
   L-04 intersection rule); gate.py GREEN on the branch — and if the run carries
   `DOCKER SKIPPED` / exempted integration tests (T04b), that is surfaced as an EXPLICIT
   flag in the review material: accepting with a skipped Docker tier is a conscious human
   decision, never a silent default; no ESCALATE file; Companion gate;
   Affects-intersection vs in-flight changes → flag list; merge-fidelity pre-check (each AC
   text findable in the spec-merge diff); spec-lint (dangling refs, duplicate capabilities,
   >300-line files, capability missing from overview); orphan sweep for removal-class.
3. Post-approval actions (`--execute`): criteria → capability-file invariants with
   provenance (a NEW capability file is instantiated from `.claude/templates/capability.md`
   — T03 finding 6: `/spec` never creates capability files, this script is the template's
   consumer); merge branch to the S9 base (see INDEX rule 4); tag `change/<context>-NNN`;
   delete the change dir; run the §5.5 drift-check and print its report.
4. The LLM contradiction-hunt pass (§5.4.5b) is NOT in this script — it's a step of the
   /accept-change command (T10). The script covers everything deterministic.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green; deny cases covered: ESCALATE present,
  unbacked `[x]`, stale verdict SHA with intersecting diff, missing companion, criteria.md
  containing `[ ]`, AC text absent from merge diff.
- Check mode on a fixture change prints the merge diff without touching main.

## Out of scope / Escalate if
- No command file (T10). If merge-fidelity grep is too brittle for a legit AC phrasing,
  weaken it to token-set matching and record that as a finding — do not remove the gate.
