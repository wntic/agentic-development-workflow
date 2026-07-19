# v3 design review — 5-probe adversarial audit (2026-07-19)

Five parallel probes attacked `workflow_v3_spec.md` (the pre-review revision, commit 7323d4c)
before any implementation: **E** enforcement red-team · **L** lifecycle/scale stress ·
**V** v2-lessons regression check · **F** Claude Code feasibility verification ·
**O** fresh-eyes outsider critique. ~55 findings; this note is the condensed register with
dispositions. The spec was amended in the same commit series — section refs point at the
POST-review spec.

## The four cross-cutting themes

1. **Prevention hooks are porous by construction; trust must be post-hoc.** Bash file
   mutation, whole-file Write, conftest test-suppression, marker-file forgery, and editing
   gate.py itself all bypass PreToolUse path guards (E-01/02/03/04/05, O-01). Verdict:
   invert the architecture — hooks stay as ergonomics, the trust anchor is `gate.py`
   verifying integrity against a git baseline (protected-tree diff, test-inventory
   cross-check, junit-backed criteria flips, self-hash). → spec §5 rewritten; new S8.
2. **The design governed one change but not the flow of changes.** Committed red tests
   deadlock every other in-flight change (L-01/O-03); stale criteria vs moved spec (L-03);
   verdict freshness undefined (L-04); abandoned changes leave red mines (O-14). Verdict:
   branch-per-change, main always green, accept = gated merge. → §2, §6; new S9.
3. **Seams v2's scaffolder/manifest used to own were left unowned.** Interface names/ctor
   deps invented by test-author with no appeal path (V-01); nobody may delete obsolete
   tests on behavior removal (V-02); refactors/bugfixes/dep-upgrades have no legal lane
   (O-05); migrations unaddressed (O-06); greenfield bootstrap unowned (O-07). → §3.1
   Interface sketch + contract-change protocol; removal duty to test-author; three change
   classes; migrations owned by implementer; vertical-slice rule.
4. **Four of v3's own must-hold rules were prose — violating its own S4** (V-03/05/06/11,
   O-10/11/12): skill coverage, criteria quality, test strength, evaluator's flip monopoly.
   → each got a deterministic gate or an explicit demotion to advice.

## Register (finding → disposition)

### E — enforcement red-team
- E-01 Bash bypasses all path hooks · blocker → ADOPTED: gate.py integrity check vs git baseline (§5.1); Bash-inspection hook demoted to ergonomics.
- E-02 Enforcement infra itself unprotected (gate.py, hooks, pyproject editable) · blocker → ADOPTED: protected-tree list includes `.claude/tools|hooks`, settings, pyproject; gate self-hash vs HEAD (§5.1/5.2).
- E-03 criteria-guard undefined for Write; reword-under-same-checkboxes · blocker → ADOPTED: disk-diff line check; inventory changes only pre-red-commit (§5.2).
- E-04 Role marker file forgeable by the constrained agent · major → SUPERSEDED by F-2: role scoping via agent-frontmatter `disallowedTools`, not hooks/markers (§5.2).
- E-05 conftest/config test-suppression outside tests/** · blocker → ADOPTED: pinned pytest config + collected-inventory cross-check vs red-commit; missing/skipped/xfail baseline test = RED (§5.1).
- E-06 Flip not role-bound; ratchet irreversible · major → ADOPTED: evaluator may flip both ways; role-bound via disallowedTools (§3.3, §5.2). (Also L-05.)
- E-07 Evidence is unverifiable prose; verdict freshness = mtime · major → ADOPTED: junit-xml + git SHA; gate --criteria cross-checks every [x] (§5.1, §6). (Also V-10, O-11.)
- E-08 Escalation ceiling silent & forgeable · major → ADOPTED: ESCALATE file written by the hook itself; accept.py denies while present; human removes (§5.3).
- E-09 /accept-change gates are command prose · major → ADOPTED: accept.py script (§5.4).
- E-10 Path canonicalization (case-insensitive APFS, symlinks) · minor → ADOPTED: realpath+casefold in guard scripts; negative tests must include these (§5.2, WP3).
- E-11 test-author/spec-author restrictions have zero hooks · minor → ADOPTED: symmetric src-guard etc. via disallowedTools (§4, §5.2). (Also O-10.)
- E-12 change.md not frozen after start · minor → ADOPTED: hash frozen at red-commit, part of gate integrity (§5.2).
- E-13 Overfit-to-weak-tests; adversarial pass never required · minor → ADOPTED: adversarial pass mandatory for M/L and first change per capability (§6). (Also V-06.)

### L — lifecycle & scale
- L-01 Red tests of change A deadlock change B's gate · blocker → ADOPTED: branch-per-change (S9).
- L-02 Hotfix drift undetectable; agents rebuild from a lying spec · blocker → ADOPTED: retro-delta lane + drift check in accept.py//orient (§5.5).
- L-03 In-flight criteria vs already-moved spec · major → ADOPTED: Affects-intersection flag at accept (§5.4).
- L-04 Verdict freshness = O(N) recomputes or stale accepts · major → ADOPTED: verdict pins git SHA; recompute only if diff intersects the change's files (§5.4).
- L-05 Regression unrecordable in-cycle ([ ]→[x] only) · major → ADOPTED (with E-06).
- L-06 AC→test link rots after archive; MANUAL unprotected · major → ADOPTED: criteria merge into capability files as invariants with `(verified by: test-id)`/`(MANUAL)`; gate greps referenced tests exist (§5.4).
- L-07 Additive spec rot: merge never cleans contradictions · major → ADOPTED: spec-lint + contradiction pass in accept review diff (§5.4).
- L-08 Legacy-codebase adoption impossible (house-style gates forever red) · major → DEFERRED, honestly scoped: v3 targets apps born under it; adoption (`--adopt`, ratchet baseline) noted as future work (§12).
- L-09 Cross-context change has no home · major → PARTIAL: `Companion:` link + accept gate "companion accepted together"; full cross-context change deferred (earn-its-place) (§6).
- L-10 overview.md is the next monolith · major → ADOPTED: S7 thresholds extended to overview (§2.1).
- L-11 Human = serializing bottleneck; degrades into rubber-stamping · major → PARTIAL: S fast-lane + merge-fidelity precheck; batch-accept deferred to WP7 measurement (§6, §12).
- L-12 NNN collisions; changes∪archive namespace · minor → ADOPTED: allocation rule + `<context>/NNN` ids (§6); archive dir removed entirely (see L-14).
- L-13 Re-cut vs in-flight Affects; spec-guard contradiction · minor → ADOPTED: re-cut is a /spec right and rewrites in-flight Affects (§2.1).
- L-14 archive/ grows unboundedly, poisons grep, duplicates git · minor → ADOPTED: change dirs deleted at accept; git history + tag is the archive (§2).

### V — v2 lessons
- V-01 Interface-ownership vacuum (test-author invents, implementer can't appeal) · blocker → ADOPTED: Interface sketch section (M/L) + contract-change protocol (§3.1, §6).
- V-02 REMOVED flavor: nobody may delete obsolete tests/code · blocker → ADOPTED: test-author owns obsolete-test removal; orphan sweep in accept.py (§4, §5.4).
- V-03 §16 skill-coverage gate died silently · major → ADOPTED: coverage surrogate — diff-path→skill presence check; new tech dir without skill = STOP meta-skill-author (§7).
- V-04 gate.py inventory incomplete (NIE grep, table metadata smoke); config source circular · major → ADOPTED: exhaustive inventory in §5.1; toolchain config lives IN gate.py, conventions cites it.
- V-05 Vague criteria pass silently (loud degradation lost) · major → ADOPTED: deterministic criteria lint (§3.3, /spec gate).
- V-06 Adversarial pass optional → WEAK asserts return · major → ADOPTED (with E-13).
- V-07 44→13 merge guarded only by self-reported diff; meta-test rewritten same WP · major → ADOPTED: machine inventory of paid-for fixes BEFORE merge; test-principles rewritten first (§7, WP4).
- V-08 Knowledge in deleted agent prompts (env_prefix N-04, ConflictError r9) unharvested · major → ADOPTED: harvest-agent-prompts step in WP1 (§10).
- V-09 New D4 doesn't cover cross-change src overwrites; overreach invisible · major → PARTIAL: out-of-scope diff report in verdict; one /implement per context at a time (§6); full attribution not rebuilt.
- V-10 Verdict evidence unchecked machine-wise · minor → ADOPTED (with E-07).
- V-11 "Only evaluator flips" is prose · minor → ADOPTED (with E-06, disallowedTools).

### F — feasibility (corrections adopted into §5/§7/§10)
- F-1 old/new_string inspection undocumented → criteria-guard reads disk + diffs; PARTIAL.
- F-2 PreToolUse can't identify subagent → role scoping = agent frontmatter `disallowedTools`; CONFIRMED SubagentStop payload has agent_type.
- F-3 Bash command inspection hook CONFIRMED (best-effort tier).
- F-4/5 SubagentStop/Stop block+ceiling CONFIRMED (stop_hook_active, cap env var).
- F-6 Skills auto-invoke fields are `description`/`when_to_use` (no `when`); 1536-char cap; works in subagents.
- F-7 Sequential subagent dispatch CONFIRMED; per-dispatch tool tuning NOT supported (use distinct agent defs).
- F-8 Hooks schema CONFIRMED.

### O — fresh eyes
- O-01 Bash hole · blocker → with E-01.
- O-02 Evaluator is the hardest agent, hidden in one table row (seeds, tokens, external services) · blocker → ADOPTED: Verification section must provision env/seed for live checks; otherwise evidence = AC-marked tests, stated explicitly; evaluator env is a named WP5 concern (§6, §12).
- O-03 Red-test deadlock · blocker → with L-01.
- O-04 MANUAL criteria deadlock accept · major → ADOPTED: third state `[m]` (human-only) (§3.3).
- O-05 No lane for refactor/dep-upgrade/perf/prod-bug · major → ADOPTED: three change classes (behavioral / bugfix / invisible) (§3.1).
- O-06 DB migrations absent as a class · major → ADOPTED: implementer owns Alembic revision; Docker-tier runs `alembic upgrade head` (§5.1, §6).
- O-07 §9 cherry-picked; L-change decomposition contradiction; bootstrap unowned · major → ADOPTED: vertical-slice rule for a context's first change; bootstrap = implementer via skills (§9).
- O-08 Cost → bypass → canon rot, no drift detector · major → with L-02/L-11 (fast-lane + drift check).
- O-09 Role-hooks load-bearing TODO; marker race under parallelism · major → SUPERSEDED by F-2 (disallowedTools).
- O-10 test-author/evaluator restrictions prose-only · major → with E-11.
- O-11 AC↔test link unspecified · major → ADOPTED: `@pytest.mark.ac("AC-n")` convention + gate --criteria (§3.3).
- O-12 kind→skill registry died with C5 gate · major → with V-03; plus WP4 hard-stop disposition list (gate or demoted-to-advice).
- O-13 Spec-corpus integrity unchecked · minor → with L-07 (spec-lint).
- O-14 Abandoned change = permanent red mine · minor → ADOPTED: /abandon + branch model (§6).
- O-15 NNN ambiguity, freshness mechanism, red-check prose · minor → ADOPTED (§6, red-check is a script step).
- O-16 Design notes = sanctioned S1 crack · minor → ADOPTED: explicitly non-binding except Interface sketch (binding-for-cycle, amendable) (§3.1).

## Rejected / consciously not adopted
- Parsing/sandboxing every Bash command as the *primary* defense (E-01 fix direction):
  unreliable by construction; post-hoc integrity chosen instead.
- Full cross-context change objects (L-09), batch-accept mechanics (L-11), legacy adoption
  mode (L-08), rebuilt overreach attribution (V-09): deferred until WP7 measurement or real
  pain — earn-its-place.
