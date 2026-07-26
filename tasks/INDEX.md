# v3 build-out — task index

Decomposition of `workflow_v3_spec.md` §10 (WP1–WP7) into single-session tasks.
Each task is one file in this directory, executed by the `v3-builder` agent via
`/build-task tasks/TNN-<slug>.md`. The spec is the source of truth — task files POINT at
spec sections, they do not restate them; on any conflict the spec wins and the builder
escalates instead of improvising.

## The `users/002` reproduction fixture — read this before concluding it is gone

Many task files ask you to confirm that `users/002` still reproduces. **The worktree is not
persistent — you create it.** A builder once looked for an existing `git worktree`, found none, and
concluded the change had been accepted; it had not. The facts, as of 2026-07-26:

- branch `change/users-002` → `a931ee6` (7 commits), tag `baseline/users-002` → `dd3a64b`, plus
  `backup/users-002-prerebase` → `201cff8`;
- there is **no** `change/users-002` *tag*, so the acceptance has **not** happened — it was executed
  once and deliberately reset, because this repo is a trial harness and T15 evicted trials from it;
- `markdown-specs` itself carries no `specs/`, `src/` or `tests/`, so an empty `specs/` in the work
  tree is **expected** and is not evidence about the branch.

Reproduce with:

```
git worktree add --detach <scratch>/u002 a931ee6
GATE_DOCKER=0 uv run .claude/tools/accept.py users/002 --tree <scratch>/u002   # → ACCEPTABLE
git worktree remove --force <scratch>/u002
```

`--base` is no longer needed (T10g derives it). Never commit to, rebase, or delete that branch inside
a task; it is the shared regression fixture. **T09h is blocked on it being accepted or abandoned** —
that decision is the author's.

**Commit your tool edits BEFORE running this regression.** Since T18 the gate anchors the whole
enforcement layer against git HEAD — every `tools/*.py`, `hooks/*.py`, `hooks/*.json`, `bin/*.py`,
`.claude-plugin/*.json` and `settings.json`, **by glob, so a new tool is anchored the moment you add
it**. An uncommitted edit to any of them makes the run return `DENIED` on
`[FAIL] integrity.self-hash` — a **spurious** red that has nothing to do with your change. It bit
T10h's builder on its first attempt, and T17's when it added `drift.py`. T18's stated cost, not a
defect. (Do not write the anchor *count* anywhere: it is glob-derived and drifts. Two documents
already said "12" one task after it became 13.)

**T15's distribution rule is confirmed against a real install — measured 2026-07-26, after T19's
builder reported the opposite.** T19 finding 5 claimed *every* installed plugin is a content copy with
no `.git`, which would have made `check_self_hash` FAIL permanently in every consumer and evaporated
T18's whole protection. It does not hold. All four plugins installed on this machine are registered
under one marketplace, but they split by **what the marketplace entry points at**:

| plugin | `.git` | `gitCommitSha` |
|---|---|---|
| `superpowers` | **yes** (shallow clone, `origin = github.com/obra/superpowers.git`) | its own |
| `frontend-design`, `code-review` | no | `6cf7e633` — **the marketplace repo's own commit** |

The three without `.git` share the *marketplace's* sha because they **are** its subdirectories, exported
as content. `superpowers` points at a **separate whole repo** and is therefore **cloned**, so `.git`
survives. That is exactly the split T15 measured and mandated: release adw by `git subtree split` into
its own repo and register a **whole-repo** source, never `git-subdir`. `notes/21` §5 is correct.

Still owed, and only the operator can do it: a real `claude plugin marketplace add <adw repo>` +
`claude plugin install adw`, then `gate.py` in that consumer. The evidence above is a genuine installed
whole-repo-source plugin keeping `.git`, which is strong — but it is not adw. Note the clone is
**shallow** and carries **no tags**, which is independently why T19 rejected its release-tag option.

**`/adw:orient` in *this* repo ends on `verdict: DRIFT`, and that is a true positive.** T17's drift
check reports 8 `src`-touching commits reachable from no `change/*` tag — all v2-era or the T02 purge,
and this repo has no `change/*` tag at all. It is real §5.5 output about real unlegalised history, not
a bug to chase; the venue reports `CLEAN`. Since T15 evicted trials from this repo, that `src/` history
is archaeology, so expect the line permanently unless someone legalises it with `--retro`.

## Task file format (all tasks follow it)

- **Goal** — one paragraph.
- **Depends on** — tasks that must be `[x]` first.
- **Read first** — spec §§, notes, existing files the builder must read before writing.
- **Deliverables** — exact paths.
- **Steps** — ordered work items.
- **Verification** — commands the builder RUNS and their expected outcomes; a task is done
  only when these pass. Checks the builder cannot run (interactive commands, human review)
  are listed under "Human verification" and left to the operator.
- **Out of scope / Escalate if** — hard boundaries.

## Status

- [x] T01 — Rewrite CLAUDE.md + PRINCIPLES.md (WP1a)
- [x] T02 — Harvest agent prompts, purge v2 machinery (WP1b)
- [x] T03 — Spec format: templates + criteria lint + /spec (WP2)
- [x] T04 — gate.py + its test suite (WP3a)
- [x] T04b — Docker-skip carve-out in gate's inventory check (design ruling on T04 finding 2)
- [x] T05 — accept.py + its test suite (WP3b)
- [x] T06 — Enforcement wiring: hooks, ESCALATE, bypass tests (WP3c)
- [x] T06b — Tighten bash_guard toward precision (T06 finding 3 false positives)
- [x] T07 — Paid-fixes inventory + test-principles rewrite (WP4a)
- [x] T08 — Skill catalog merge 44 → ~13 (WP4b)
- [x] T04c — no-ORM + no-mocks grep-gates in gate.py (T08 finding 5; do BEFORE T09)
- [x] T04d — narrow no-mocks off monkeypatch (T04c finding 5 false positive; do BEFORE T09)
- [x] T09 — Cycle agents + /implement + /abandon (WP5)
- [x] T09b — red-baseline commit must be tests-only (T09 finding 2 anti-collusion)
- [x] T10 — /accept-change command (WP6)
- [x] T10b — accept.py honours a multi-target placement map (T10 finding 2; before T11 IFF the probe goes multi-target)
- [x] T06c — SubagentStop must hold only the implementer (greenfield-probe F1 bug; blocks a clean re-run)
- [x] T09c — greenfield bootstrap (bootstrap.py) — **REVERTED 2026-07-22.** bootstrap.py was a
  v1/v2 codegen regression (a script emitting the app shell; D1/A3). Replaced by **approach A**:
  the substrate is an external-template precondition and the workflow is brownfield-only. Spec §9
  rewritten, `bootstrap.py` + `test_bootstrap.py` removed, `/implement` §0.5 dropped.
- [x] T09d — evolving/conditional substrate ownership — **RESOLVED by T12.** Conditional deps
  (relational / auth / multipart) are the **test-author's** pre-baseline concern, per change, declared
  from the Interface sketch — never predicted into a template or a script.
- [x] SKILL-GATE — architecture/restapi skill templates must be gate-clean under RUFF_SELECT (still
  live, and now a T12 dependency: the implementer writes the app shell from these skills, so the
  emitted code must pass the gate's ruff select). Core tension: the architecture re-export contract
  mandates `from .module import *` → F403/F405. See `tasks/SKILL-GATE-templates-gate-clean.md`.
  RESOLVED at the skill level (option a): each wildcard re-export line carries `# noqa: F403`
  (F405 never fires — `__all__ = module.__all__` names the explicitly-imported submodule), the
  `errors.py` `__all__` is RUF022-sorted; no `gate.py` change needed. Guard:
  `.claude/tools/test_skill_shell_ruff.py`.
- [x] TEMPLATE — external project scaffold — **DROPPED (superseded by T12).** A scaffold template that
  ships fastapi/a shell re-encodes the prediction the workflow must not do; agents own deps + shell,
  and new-project setup is plain `uv init` + the installed plugin.
- [x] T12 — agents own dependencies and the app shell (dissolve bootstrap AND the template):
  test-author lands the change's deps in a pre-baseline commit (from the Interface sketch);
  implementer writes the behaviorless shell from the skills; `red_check` gains a greenfield
  collection-error fallback (static AST marker scan). `gate.py` untouched. See `tasks/T12-*.md`.
- [ ] T11 — E2E probe runbook (WP7, human-driven). Greenfield e2e runs after T12:
  **`uv init --package`** project → `/spec` → `/implement` reaches green with no bootstrap and no
  template; thereafter brownfield. (**Corrected 2026-07-26:** said plain `uv init`, which on uv
  0.11.6 emits `main.py` at the root and creates neither `src/<pkg>/` nor `[build-system]` — the
  probe would have reproduced the broken layout and "verified" the wrong thing. Same drift as
  `workflow_v3_spec.md` §9; see the note at the end of this section.) The probe is also the only
  thing that exercises the shipped artifact in a real consumer project — so it is the acceptance
  test for **T15**.

### Skill-catalog progressive disclosure (2026-07-24 — the T08 merge produced monolithic bodies)

The §7 merge (44 → 13) was right on *theme count* but concatenated each theme into one body:
`testing-integration` 1792 lines, `restapi` 1256, `testing-unit` 1045, `infra-persistence` 733. An
agent writing one endpoint loads all 7 restapi artifacts. Fix = progressive disclosure *inside* a
theme (thin `SKILL.md` router + one `<topic>.md` per artifact, read on demand). Frontmatter and the
~13-theme map are untouched — this splits bodies, not the catalog. Contract first (T13), then apply
(T14) — the T07→T08 shape.

- [ ] T13 — Progressive-disclosure contract: rewrite CONVENTIONS.md "Skill format" (thin router +
  bundled `<topic>.md`, with a split threshold), teach both shapes in `meta-skill-author`, clarify
  C2 ("one theme" = one auto-invocation entry, not one file). Design-sensitive; no canon edit.
  Depends: T08.
- [ ] T14 — Split the over-threshold skills into router + topic files per T13, losing no paid-for
  line. `test_skill_catalog.py` is the unedited oracle (`rglob("*.md")` already covers bundled
  files). Frontmatter moved verbatim. On-demand-read reliability confirmed only in an e2e probe.
  Depends: T13.

### Post-`/implement platform/001` friction fixes (2026-07-24 agent-report analysis)

The first full `/implement platform/001` run was GREEN end-to-end but ~85% of wall-clock was
friction, not agent reasoning (evaluator: 8m21s work across a 116m span). Five fixes, ordered by
impact. See `notes/greenfield-first-change-blockers.md` (cost profile + findings #1–#4).

- [x] T06d — Give cycle subagents a sanctioned write path to their OWNED tree. Write/Edit is
  absent entirely and `bash_guard` protects everything but `src/`, so the two protected-tree
  agents (test-author, evaluator) must bypass the hook while the implementer sails through.
  Restore path-scoped Write OR make `bash_guard` role-aware. Depends: T06, T09.
- [x] T09e — The cycle agents commit their own work. implementer commits `src/**` at green;
  evaluator commits criteria→verdict in freshness order — takes the orchestrator off the critical
  path (kills the 116m evaluator span + the SendMessage resumes). Depends: T09; easier after T06d.
  Confirmed by the 2026-07-24 `health/001` replay: all three subagents self-committed in freshness
  order, zero orchestrator commits, `accept.py` → ACCEPTABLE with no SendMessage re-pins.
- [x] T09f — `red_check.py` must screen the baseline for lint before tagging. A `ruff I001` in the
  test-author's `conftest.py` passed red_check (it checks only markers + redness), got tagged, then
  DEADLOCKED the implementer: ruff is per-file and the implementer is tool-blocked from `tests/**`,
  so it burned all 3 ESCALATE blocks over a defect outside its lane. Run the gate's ruff-check +
  ruff-format over baseline `tests/**` before tagging; refuse a lint-dirty baseline. NOT mypy
  (greenfield tests import a not-yet-written package — that import failure is the intended redness).
  Surfaced by the 2026-07-24 `health/001` run. Depends: T09b (red_check anti-collusion), T04 (gate's
  ruff config, reused not restated — C7).
- [x] T10c — accept.py must not silently deny on pure formatting. Tolerant SHA parse (backticked
  hex) + accept `## Adversarial pass|review`; rename `/implement` §4 to "Adversarial review" and
  hand the evaluator the verdict template. Depends: T10, T09.
- [x] T10d — accept.py freshness should survive a rebase (kill the re-pin cascade). Anchor L-04 to
  tracked-tree identity, not commit identity, so a rebase that preserves the tree preserves the
  verdict. **Design-sensitive (freshness canon) — confirm semantics before coding.** Depends: T10, T09e.
- [x] T03b — Interface sketch must not claim "no layers" when the mandated `restapi` shell ships a
  domain-exception base + error schema. Wording/altitude fix so a first change lands no false V-09.
  Depends: T03.
- [x] T06e — Anchor `bash_guard`'s protected-path match to the repo root (found building T09f: it
  denies non-owner writes to `/tmp/.../tests/...` by substring-matching the fragment anywhere).
  Cheap false-positive fix; keep T06b precision + T06d role-awareness. Depends: T06, T06b, T06d.

**T10d — SIGNED OFF (2026-07-25, author).** Freshness is anchored to **tracked-tree identity**, not
commit identity: the question §5.4 asks is *does the diff intersect the change's FILES* (content),
not *is the verdict's commit still an ancestor*. A rebase that preserves the tree therefore preserves
the verdict, and no evaluator re-run is owed. T10d is closed. The fail-open hole it incidentally
exposed (unresolvable pin → empty diff → PASS, shipped since T05) is carried forward as **T10f**.

### Post-`/implement users/002` findings (2026-07-25 report analysis)

`users/002` (user CRUD, 14 AC) ran the cycle in **one clean pass** — zero orchestrator commits, all
four agents self-committing in freshness order, 38 min total active compute with no SendMessage
resumes. The T09e/T10c friction fixes worked: the round-trip cascade that dominated `platform/001`
is gone. The adversarial pass earned its keep by mutation-testing (8 injected mutations, 6 died).
What it surfaced is below. Every claim re-derived from source before filing.

- [x] T10e — `_orphan_sweep` classifies removal-flavour by grepping prose: `#*` is zero-or-more, so
  a wrapped sketch line ("removed id, or `None`…") reads as a heading, and the term capture then
  anchors on the *first* "removed" anywhere and harvests 19 generic identifiers (`id`, `save`,
  `None`). Blocks `/accept-change users/002` on a change that removes nothing. Classify off `Class:`
  + `#+\s*Removed`; anchor the capture to the heading. **Blocks users/002 acceptance.**
  Depends: T10, T05, T03.
- [x] T06f — `bash_guard` denies relative writes into a scratch tree reached by `cd`: it resolves
  relative targets against the *session* cwd because `_write_targets()` has no `cd` awareness. Not
  the bug T06e closed (that was the absolute-path variant of the same finding — T06e closed on one
  variant and never checked the other). Twice denied the `users/002` adversarial evaluator, which
  rerouted and finished anyway — i.e. the guard trained the bypass reflex it exists to prevent.
  Also dissolves the "one stray `tests/` token vetoes a legal `src/` command" symptom, same fix.
  **Rescoped 2026-07-25 into Part A + Part B** (two concerns, batched so both land before the single
  users/002 rebase): Part A adds the filename-fragment precision fix found building T10e (protected
  `change.md` matched `fixtures/users-002-change.md` by substring — so fragments now match whole path
  components; `pyproject.toml` no longer matches `pyproject.toml.bak`). **Correction (T06f finding 1):
  the filing claimed T10e's builder dodged that denial by renaming the fixture — false. Both the
  original and renamed paths are denied identically, by `.claude/tools`, and the builder actually used
  the `Write` tool. The rename was cargo-cult, prompted by the misleading `(change.md)` reason string;
  the fix makes the reason truthful, it does not open the path.** Part B closes the **V-02 fail-open T10e opened** —
  its findings #2+#3 combine so a genuine removal change can reach acceptance with the sweep silently
  not running; class-declared-without-heading becomes FLAG instead of SKIP. Depends: T06, T06b, T06d,
  T06e, T10e.
- [x] T06g — `bash_guard` tokenises heredoc **bodies**, so prose inside a multi-line commit message
  is read as a redirect: `git commit -F - <<'EOF' … "the prose mentions > tests/x.py" … EOF` is
  DENIED, while the same heredoc without a `>` token passes. Found building T06f (its finding 3, on
  its own commit message) and reconfirmed against the live hook. Worse than a normal false positive
  on two counts — it fires on message *content* rather than command shape (so it looks
  unreproducible), and it hits the repo's own multi-line commit convention, i.e. every agent. T06b
  fixed the quoted `-m "…"` case; the heredoc case survived it. Last known member of the
  tokeniser-precision family (T06b → T06e → T06f → this); one function. The correctness boundary:
  a redirect on the heredoc's own command line (`cat > tests/x.py <<'EOF'`) must **still** fire.
  Depends: T06, T06b, T06f.
- [x] T10f — Adversarial pass over `accept.py`'s own gates. Three defects now found by *using* the
  script (T10c, T10e, and the T05-era freshness hole), and the freshness one fails **open** — the
  worst possible direction for the backstop the whole S8 trust model rests on. All three share a
  defect class: degenerate/empty input, not wrong logic. **Concrete input from T06f finding 6:** Part
  B moved the V-02 fail-open one step in but did not close the family — a `## Removed` heading whose
  body carries no backticked symbol still returns **PASS** ("lists no concrete removed symbols to
  sweep"), so the sweep quietly does nothing. Pinned in a test as deliberate-for-now; the real fix
  pairs with the T03 vocabulary decision below. Also cheap: `spec.lint` emits duplicate findings (no
  dedupe on a repeated ref). **Sequencing:** off the acceptance path — T10f edits the very script that
  must judge `users/002`, and batching it early saves no rebase (after acceptance nothing is in
  flight), so run it AFTER `users/002` merges. Depends: T10e.
  **ESCALATED then RESOLVED (2026-07-26).** The audit ran and fired this task's own `>~3` stop
  condition: **7 fail-open paths**, one root cause. Register (deliverable 1) is DONE —
  `notes/19_accept_gate_audit.md`, commit `d24d51b`. Author's decision: **approach (b)** — a
  validated-input layer making "input could not be determined" representable, plus the enforced rule
  *"a gate whose input could not be determined returns FAIL if it guards trust, FLAG if it is a review
  aid — never PASS, never absent from the report"*, pinned by a parametrised
  `test_no_gate_passes_on_undetermined_input` that walks the gate list so a future gate is covered by
  construction. Not (a)/seven patches — the register's finding 11 is the argument: `gate.py` guards
  every integrity `_git` call, `accept.py` guards neither diff that produces a gate's evidence, and
  the three sites that do have the reflex got it from whoever wrote them (one added by T10d only
  after it fell over in production). Directions decided in the task file; the severest is **F-06** —
  provenance degrading to `(verified by: ?)` makes `--execute` merge spec content that turns the base
  branch's own gate RED, i.e. the acceptance script breaking S9.
- [x] T04e — `ESCALATE` is deletable by an agent, so §5.3's "only the human removes it" is prose, not
  a rule (S4 litmus: `gate.py` sees nothing). The change dir is not in `gate.py`'s `PROTECTED_PATHS`,
  so the agent that hit its iteration ceiling can unlock itself. Make the *disappearance* of the file
  gate-failing against the baseline — NOT by protecting the whole change dir, which would deadlock
  the cycle (`criteria.md` flips and `verdict.md` writes are legal traffic). From T10f's register,
  finding 10. Depends: T04, T06, T10f.
  **BUILT, BUT THE SPECIFICATION WAS WRONG — the hole is still open (→ T06h).** The task file (mine)
  specified a baseline-vs-HEAD check without checking whether the file ever reaches git. It does not:
  `subagent_stop.py:169` writes it untracked with a bare `write_text`, and the hook fires *after*
  baselining anyway, so even a committed ESCALATE would sit outside the baseline tree. The shipped
  `integrity.escalate-intact` is correct, tested and harmless, and becomes load-bearing under T06h —
  but it covers only an ESCALATE that somehow reached the baseline commit, which the shipped flow
  cannot produce. Kept rather than reverted for that reason; its narrow reach is now stated in
  `CLAUDE.md` and in a dated CORRECTION block in `notes/19`.
- [x] T06h — Make the `ESCALATE` lock real: (1) the hook **commits** the file (scoped to that path),
  (2) `gate.py`+`accept.py` ask a **branch-history** question ("committed since baseline, now gone?")
  instead of a baseline diff / a filesystem `exists()`, (3) a sanctioned way for the human to clear
  it — without which clearing a lock leaves the gate permanently RED, since `red_check --rebaseline`
  refuses a non-`tests/` commit. All three or none: any one alone leaves the lock broken. Also fixes
  the second victim — `accept.py`'s `exists()` gate is invisible to a **detached worktree**, which is
  how `notes/19`'s own baseline and every acceptance run of 2026-07-25/26 were produced, so that gate
  has never been exercised against a real lock. Depends: T04e, T06, T09b, T09f, T10f.

- [x] T16 — Stand up a **packaging-faithful consumer project** as the trial venue: a sibling repo
  created with `uv init --package`, `.claude/` symlinked (verified: `check_self_hash` resolves
  through the symlink back to the workflow repo, so E-02 survives unchanged), one small change driven
  end to end, and a runbook in `notes/`. **Blocks T12b** — T12b would otherwise ship two checks whose
  live branches cannot be exercised here (the toolchain preflight: this repo always has the toolchain;
  the import check: this repo is permanently non-installable, so only its SKIP runs). Shipping gates
  whose failure paths were never exercised is the exact defect class `notes/19` is about. Deliberately
  **not** the plugin — no manifest, no `${CLAUDE_PLUGIN_ROOT}`, no marketplace (that is T15, and it
  answers "does it work when *installed*"). Keeping them apart means a failure is attributable.
  Also answers T15's open "where does a trialled change live" with evidence. Depends: none.
  **BUILT 2026-07-26 (`e396012`), and it paid for itself on first use.** Venue at
  `~/Projects/adw-consumer-probe`, runbook `notes/20_consumer_trial_venue.md`. It immediately caught
  an **S9 violation nobody could have seen here** (→ **T10j**), and confirmed both halves of T12b
  live: the toolchain preflight is genuinely missing (three FAILs reading `No module named mypy`
  with no guidance), and — the useful half — because `uv init --package` ships `[build-system]`, the
  operator's own `uvicorn` command works with **no gate-provided `PYTHONPATH``. So the A4 hole is a
  property of *this repo's* non-installable layout, not of the workflow. Caveat recorded by the
  builder: a builder subagent cannot spawn subagents, so all four cycle roles were played by one
  agent in one context — every *script* ran for real, but the cycle's anti-collusion properties
  (fresh-context evaluator, `disallowedTools`, the SubagentStop ceiling) were **not** exercised.
  **Last owed item DISCHARGED 2026-07-26 (human, `/orient` run in the venue): Claude Code does load
  a symlinked `.claude/`** — the session registry carried the v3 agents (test-author / implementer /
  evaluator / v3-builder) and commands (`/spec`, `/implement`, `/accept-change`, `/abandon`) through
  the symlink. Harness discovery, not hand-fed payloads. The same run reproduced F-01 unchanged and
  surfaced two further findings → **T17** (`/orient`'s drift-check) and the empty `## Behaviour`
  question, now folded into T10j.
- [x] T06j — **The toolchain preflight T12b built never reaches the one who must act on it.** Two
  entry points throw the sentence away: `subagent_stop.run_gate` discards the gate's stdout and reads
  only `.gate/verdict.json`, so an exit-2 abort surfaces to the implementer as `gate produced no
  verdict.json` **three times** and then writes ESCALATE — the T09f deadlock shape a third time, an
  implementer burning its whole ceiling on something no `src/**` edit can fix; and `red_check.py` has
  no preflight at all, so a consumer missing `ruff` hits a raw error at *baseline* time, which on a
  first change is the very first script the workflow runs. Underlying rule worth stating once: **a
  precondition failure must be legible to whoever can act on it** — a swallowed diagnostic is the
  same defect as none, and worse here because the agent retries. From T12b findings 1–2.
  Depends: T12b, T06, T09f, T06c.
- [x] T17 — `/orient` still defers its §5.5 drift-check as *planned (T05/T10)* and says "skip that
  step" — but both shipped. Worse, the two sides point at each other: `accept.py`'s `--execute`
  report ends with *"OpenAPI route⊆operation drift is surfaced by /orient"*, while `/orient` waits
  for `accept.py` to arrive. **Nobody runs the OpenAPI half.** The hotfix half (base src-commits with
  no `change/*` tag) *is* automated in `accept.py` and must be cited, not reimplemented (C7). Open
  choice: prose-in-the-command (the comparison is genuinely semantic — a route may be described in
  prose no grep matches) or a script (S4's shape, and how every other must-hold check here ended up);
  read §5.5 before assuming the latter. Not a blocking gate — §5.5 surfaces, it does not deny.
  Found by the human's `/orient` in the venue, who did the check by hand and found it clean — which
  is the only reason this is not a live gap today. Depends: T05, T10, T04.
- [x] T10j — **A successful `accept.py --execute` leaves the base branch RED — S9 broken by the
  acceptance script itself.** The birth path copies `.claude/templates/capability.md` verbatim
  including its HTML comment, whose `- <invariant> (verified by: <test-id>)` line is then read by
  `gate.py:808` as a real provenance reference (`CAPABILITY_REF`, `:195`, runs over raw text) → L-06
  FAILs looking for a test named `<test-id>`. `lint._strip_html_comments` is already used one
  function away at `:755`, for the criteria check — the capability check just does not call it.
  Verified on the born file: `findall` returns the ghost **and** the real reference. Survived because
  no acceptance had ever been `--execute`d *and then gate-checked* — `users/002`'s was executed and
  reset before anyone ran the gate on the merged state. Blast radius: `subagent_stop` then holds the
  next change's implementer on a RED no `src/**` edit can clear (T09f's deadlock, from a new
  direction). Fix both halves (gate stops parsing comments; birth stops emitting a data-shaped
  placeholder) and repair the venue's `main` **with** the fix as the end-to-end proof — a unit test
  alone does not discharge this, since the defect existed precisely because nobody ran the sequence.
  **Blocks the next trial.** Depends: T10, T04, T16.
- [x] T10k — the last reader that treats HTML comments as content, plus the helper three tools share.
  `_overview_capability_tokens` matched over the raw `## Capabilities` body, so a comment naming a
  backticked `*.md` became a capability token — and that list feeds `resolve_targets`' capability-BIRTH
  path, so a comment could name the file an acceptance CREATES. Latent (the overview template's
  `<capability>.md` placeholder does not match the regex — T10i finding 5's second half does not
  reproduce), fixed because the birth path is downstream. Also promotes
  `criteria_lint._strip_html_comments` to `strip_html_comments` — **seven** external call sites, not
  the three filed — and fixes T17 finding 2's one-token latent crash in `run()`'s `--execute` tail.
  Depends: T10j, T10i, T10f.
- [x] T10h — `accept.py`'s `_section()` matches only `"## "`, so a `### Interface sketch` is found as
  **nothing** → empty section → reads as S depth → `adversarial.presence` PASSes for an M/L change.
  The existing-capability half of T10f's F-02 (which fixed only the birth path); left unfixed there
  because it also touches verdict.md's parse. Six call sites (`:318, 670, 672, 685, 1171`). The trap:
  a naïve `#+` terminator would let a `### ` subheading truncate its parent `## ` section — match any
  depth, terminate at same-or-shallower. Depends: T10f.
- [x] T04f — `gate.py`'s `_baseline_paths()` swallows the git rc (`return [...] if rc == 0 else []`);
  `notes/19` credits `gate.py` with guarding *every* integrity `_git` call, which is false for this
  helper. Both callers fail closed **by luck** (`_baseline_blob` also fails, giving a misleading
  "created after the baseline commit"), so the fuse is unlit, not absent — F-01's family. Includes a
  sweep for the same pattern and a correction to the register's claim. Depends: T04, T04e, T10f.
  **BUILT 2026-07-26.** Helper raises `GateError`; each caller returns a FAIL naming the git call
  (not an abort — a broken baseline is a verdict about the tree). **Three** callers, not two: the
  filing missed `check_test_inventory`, where the swallowed rc silently shrinks the legal-removal
  allowance read out of the baseline `change.md`, i.e. would blame the tests for a git failure. The
  sweep found **no second fail-open site** (so no escalation), and two rc's that are discarded but
  degrade loudly by design — `rev-parse HEAD` → `sha: UNKNOWN`, `status --porcelain` → the `dirty`
  flag nothing reads; both recorded in the `notes/19` correction. Also fixed the misattribution that
  hid the defect: an unreadable blob for a path the baseline tree *lists* can no longer be reported
  as "created after the baseline commit". Lint debris cleared in `gate.py` only — the pinned
  `RUFF_SELECT` still flags **21** findings across the rest of `.claude/tools|hooks` (accept.py 11,
  red_check 2, hooks 2, test files 6), a separate cleanup with a separate argument.
- [x] T06i — **Six point fixes into the `bash_guard` tokeniser** (T06b quoted `-m` · T06e absolute
  paths · T06f relative/`cd` · T06f substring filenames · T06g heredoc bodies · open: `;` glued to a
  quoted word makes `rm`'s target slice swallow a later `cp`'s **source**). Each fix correct, each
  left another variant; every miss trains the bypass reflex the guard exists to prevent and blames
  the wrong path. Decide: a seventh point fix, a real tokeniser (stdlib `shlex(punctuation_chars=True)`
  may be near drop-in), or shrink what the guard claims to prevent (S8 permits it). The 113 existing
  cases are the specification — they must all survive. Escalate the comparison before rewriting.
  Depends: T06, T06b, T06e, T06f, T06g.
- [x] T03c — **Pin the removal-flavour vocabulary.** Four documents say four different things (spec
  §3.1 `REMOVED` · the template comment "removal flavour" · `/spec` "listed explicitly" ·
  `test-author.md`'s "Removed tests block", a section that exists in **no template**), and the V-02
  sweep now keys on a `#+ Removed` heading nobody is instructed to emit. T10e's tolerant classifier
  and T06f Part B's FLAG are holding patterns, not the fix. Ship a `## Removed` skeleton, narrow the
  classifier, close T10f's F-05 (an empty heading still PASSes). Depends: T03, T10e, T06f, T10f.
  **BUILT 2026-07-26.** One spelling everywhere: `Class: behavioral, REMOVED` (case-sensitive — the
  marker is a tag) plus the `## Removed` skeleton the `change.md` template now ships, which states
  the grammar the sweep actually harvests (backticked identifiers, `::node_id` tails) and the second
  reader nobody had documented — the gate's legal-removal allowance (E-05) is read out of change.md,
  so an obsolete test deleted without its node-id listed there is RED for the whole cycle. The
  classifier reads only the marker, but **never ignores** another wording: an unpinned `Class:` line
  is FLAGged, because narrowing without reporting trades T10e's false positive for a silent false
  negative. **F-05 stays FLAG, not FAIL** (argument recorded in code): the template made the message
  actionable, but a removal whose behaviour has no symbol to name — a route string, a feature flag —
  is legitimate, and denying it trains routing-around. Also fixed T10h finding 3's terminator (all
  three section parses now end at same-or-shallower) and ruled on the three-grammar C7 smell:
  **stay three**, deliberately, with the reason next to the regex.
- [x] T09g — **A test-strengthening change has no red phase, so it has no home.**
  `red_check.rebaseline` refuses unless the tests are still a valid RED baseline; strengthened tests
  over already-correct code are green on arrival. So `users/002`'s F1/F2 cannot be acted on, which
  makes the adversarial pass — the one step whose job is measuring test strength — advisory theatre
  (S5/D3). Design-sensitive: extend `invisible` (same no-red-phase shape, check whether it has the
  hole too), a new class proved by **mutation** rather than redness (strictly stronger, and the
  adversarial pass already produces it), or let the adversarial step commit within the change
  (collides with D4). Escalate the shape first; expect a §3 canon edit. Depends: T09, T09b, T09f, T03, T10.
- [x] T10i — Two T10f leftovers plus one cosmetic: `merge.placement`'s REVIEW-vs-TRUST class (its
  check-mode FLAG means a multi-target change reads ACCEPTABLE while being un-executable);
  `/accept-change`'s prose gate list omits `invariant.provenance` (prefer replacing the enumeration
  with a pointer to the registry — enumerations in prose are how this drifted); `_spec_lint` emits
  duplicate findings. Depends: T10f, T10g.
  **BUILT 2026-07-26.** `merge.placement` **stays REVIEW**, with the argument recorded next to the
  registry entry: check mode is what `/accept-change` step 1 runs, and step 4 (propose the map) is
  only reached on a non-denied run — so a TRUST deny would block the very acceptance whose map it
  demands, while §5.4 says accept.py only *flags* the distribution. What was missing was legibility,
  not severity: check mode now prints `verdict: ACCEPTABLE — pending the placement map --execute
  requires`. Item 2 replaced the prose enumeration with a pointer to `GATES`. Item 3 turned out to
  be **already fixed by T10f** at the (file, ref) level — not reproducible on the `users/002`
  baseline any more — so it became a list-level dedupe plus the pin nobody had written; the honest
  defect of the four was item 4, whose S7 half (every born capability file's ~20 template comment
  lines counted toward the 300-line cut) had no filed symptom at all.
- [x] T10g — `/accept-change` never passes `--base`, and `accept.py` defaults to `main` — but this
  repo's S9 base is `markdown-specs` (`main` is the v2 archive), and a consumer project may be on
  `master`. The `users/002` acceptance only worked because the operator passed `--base` by hand.
  Distinct from T10f's F-01 (the script failing *open* on an unresolvable base) and compounding with
  it: a wrong base that fails to resolve is exactly F-01's silent-ACCEPTABLE path. Prefer deriving
  the default in `accept.py` over patching the command, and never hardcode `markdown-specs` (C6).
  Depends: T10, T10f.
- [x] T12b — The app the cycle ships is not an importable package: `pyproject.toml` has no
  `[build-system]`, and `gate.py` injects `PYTHONPATH=src` itself — so the gate constructs the app
  under an import path only the gate provides, and `uvicorn` by hand fails. An **A4** finding (the
  gate isn't exercising the real failure mode, it's papering over it), not the ergonomics annoyance
  the run reports filed it as. Depends: T12, T04.
  **ESCALATED then REWRITTEN (2026-07-26) — the original framing was wrong.** "Make this repo's
  `pyproject.toml` installable" is now explicitly forbidden, for three verified reasons: (1)
  `[build-system]` with an absent `src/<pkg>/` makes `uv` hard-fail *every* command; (2) this repo's
  `src/` is transient (T02 purged it, `users/002` recreated it), so declaring it would couple the
  meta layer's test env to the presence of a trial app — purge the trial and `pytest .claude/tools/`
  breaks; (3) this `pyproject.toml` is a trial-harness dev artifact wearing three hats, and
  untangling that is **T15**. T12b is now consumer-facing only: `[build-system]` into `conventions`
  block D (backend `uv_build`, matching what `uv init --package` emits); a **toolchain preflight** in
  `gate.py` (there is none today — a consumer missing `ruff`/`mypy` gets a raw `ModuleNotFoundError`
  from a subprocess instead of a sentence); and an import check with the injection stripped (FAIL if
  the project declares itself installable and isn't, loud SKIP if it doesn't — this repo's permanent,
  honest case). The injections **stay** — the editable `.pth` is absolute, and
  `collect_baseline_inventory` needs one to reach the extracted baseline tree.
- [x] T15 — Split the shipped plugin from the trial harness. The root `pyproject.toml` serves three
  masters: the trial app's runtime deps, the toolchain a consumer legitimately needs (correct where
  it is — `gate.py` runs `sys.executable -m mypy|ruff|pytest`, so the tools must see the project's
  code), and the meta layer's own test env for the 297 `.claude/tools/` tests, which ships nowhere.
  The third has no home — the workflow's own dependencies live outside the workflow. No
  `.claude-plugin/plugin.json` exists yet, so nothing has forced the question. Deliverables: the
  manifest + `${CLAUDE_PLUGIN_ROOT}` paths, a home for the meta layer's env (**acceptance test:
  delete `src/` and `pytest .claude/tools/` still passes**), a decision on where a trialled change
  lives (today it is not packaging-faithful to a consumer project — which is how T12b's A4 hole
  survived), and the rule for what is excluded from the shipped plugin. Escalate with a layout
  before writing code. Depends: T12b; coordinate with T11. Supersedes the `plugin-packaging-plan`
  note.
  **ESCALATED then RESOLVED (2026-07-26).** Layout C approved: **`.claude/` *is* the plugin root and
  not one file moves**, so the gate's `PROTECTED_PATHS` and the guard's fragments stay literally true
  and unedited. Five decisions settled in the task file: **D1** the namespaced `agent_type` fix folds
  in (see below — it is the reason this escalation paid for itself); **D2** plugin name `adw`, rename
  sweep scoped to `.claude/**` only, since by ship-by-location a consumer reads nothing outside it;
  **D3** two homes for hook wiring (a plugin cannot ship hooks in `settings.json`), pinned by an
  equivalence test rather than a comment (S4); **D4** a `bin/` shim, required to work uninstalled;
  **D5** deferred to **T18**. Distribution is a *correctness* requirement, measured: release via
  `git subtree split --prefix=.claude` with a **whole-repo** marketplace source — a `git-subdir`
  source is a content copy with no `.git`, and `check_self_hash` then FAILs, turning **every gate run
  in every consumer RED**. The obvious packaging choice was the broken one.
  **D1, the finding that justifies the whole dispatch:** plugin-shipped agents get a **namespaced**
  `agent_type` (`adw:implementer`), while `subagent_stop.py:55/173` compares against bare
  `"implementer"` and `bash_guard.ROLE_OWNED` (`:121-125`) is keyed on bare names. Shipped as-is the
  implementer would **never be held on a RED gate** (T06c dead) and all three cycle roles would
  **lose their owned-tree write path** (T06d dead) — silently, and invisible to every test in this
  repo. Verified in source.
- [x] T18 — **Once installed, almost nothing protects the plugin's own files.** Measured across T16
  F-02 and T15's probes: the plugin lives outside the consumer repo, so `bash_guard` **allows** writes
  to its `tools/`/`hooks/`/`plugin.json` (targets resolve outside the anchored root — by design,
  T06e), and `integrity.protected-trees` diffs paths that do not exist in the consumer tree, passing
  **vacuously**. All that remains is `check_self_hash`, covering `gate.py` + `criteria_lint.py`
  **alone** — `accept.py`, `red_check.py`, the four hooks and `plugin.json` itself are unprotected,
  and `plugin.json` names the components, so tampering with it silently unhooks everything. Not a
  packaging defect (T15's layout is right); an unanswered trust-model question — *which files are
  anchors, and what does the gate do when it cannot vouch for one?* One sub-question is worth more
  than the fix: what backstops each hook in a consumer, where the honest answer may be "nothing".
  Depends: T15, T04, T04e/T06h.
  **BUILT 2026-07-26.** (1) Anchors = plugin-root-relative **globs** (`tools/*.py`, `hooks/*.py`,
  `hooks/*.json`, `bin/*.py`, `.claude-plugin/*.json`, `settings.json` — deliberately **not** recording
  the file count, which is glob-derived and drifted from 12 to 13 within one task when T17 added
  `drift.py`), so a new tool or hook is anchored by construction; `tools/test_*.py` and the knowledge
  layer stay out (no decision reads them). Cost, as predicted: every edit to a tool/hook/manifest must be committed before a gate
  run passes. (2) A non-git plugin keeps **FAIL**ing — message now names the directory and the remedy.
  (3) The walk is in `notes/20` F-02: `criteria_guard` → criteria-flips (real); `bash_guard` → partial
  (protected-trees vacuous in a consumer, but test-inventory + the tests-only baseline keep
  anti-collusion); **`subagent_stop` → nothing, `session_stop` → nothing** — a post-hoc check judges a
  tree, those two judge a *moment*, so a missing ceiling costs iterations, not correctness. Verified in
  T16's venue against a `git subtree split` clone outside it: GREEN → tamper `tools/accept.py` +
  `plugin.json` → RED naming both → delete `hooks/subagent_stop.py` → RED → restored → GREEN.
  Two limits left open, stated in the note: self-hash compares against the plugin's **local** HEAD (an
  agent that can write the plugin dir can commit there), and in the symlink venue the plugin's
  `settings.json` *is* the project's.
- [x] T06k — `cp`, `install`, `dd of=`, `truncate` are **not** in `bash_guard`'s write-op inventory,
  so `cp /tmp/evil.py .claude/tools/gate.py` is ALLOWED for any role. Severity is **ergonomics, not
  trust** — under S8 the gate backstops, and `integrity.self-hash` (E-02) catches a modified
  `gate.py` post-hoc; what the miss costs is the early legible denial. The reason it is a task and
  not a one-liner: **applying `mv`'s "every non-flag arg" rule to `cp` would recreate variant 6** —
  `cp .claude/tools/gate.py /tmp/backup.py` reads a protected file and writes nothing protected, so
  it would become a fresh false positive blaming a path the command only reads. `cp`/`install` take
  the **last non-flag argument only**; `dd` takes `of=`; `truncate` takes the file operands. Each
  addition needs a **read-direction** test as well as a write-direction one, or the task is variant 6
  again. From T06i finding 6, deliberately left there because the inventory is policy and the parser
  was not yet trustworthy. Depends: T06i.

### Filed but previously missing from this list (bookkeeping fix, 2026-07-26)

T10k's builder found that this status list had stopped being a complete index of `tasks/` — seven task
files existed with no line here, which makes `/build-task`'s "every *Depends on* entry is `[x]`"
**uncheckable** for them. That is a protocol break, not a cosmetic gap. The entries:

- [x] T04g — the repo lints its own tooling with a rule set narrower than the gate imposes on the app:
  pre-commit runs ruff with `pyproject.toml`'s config, which sets **no `select`**, so only ruff's
  default `E4,E7,E9,F` applies. That is why `RUF103`/`RUF100` sat in `gate.py` itself until T04f. The
  finding that makes it more than hygiene: among the 21 remaining is `RUF059 "Unpacked variable rc is
  never used"` in `accept.py` — **ruff finds a discarded git return code unaided**, i.e. part of the
  `notes/19` defect class a whole audit dispatch was spent enumerating. Treat `RUF059` and `B905`
  (`zip` without `strict=` in `criteria_guard`, which silently truncates) as bug reports, not nits.
  Depends: T04, T04f.
- [x] T04h — the legal-removal allowance is a **raw substring match over the whole `change.md`**
  (`gate.py:1322`, comments **not** stripped), one function away from the `CAPABILITY_REF` path T10j
  fixed with the stripper already imported in that file. So a node-id in an instruction comment would
  authorise deleting a baseline test for every change that keeps the comment. Third instance of "a
  comment is not content" and the only one that **widens a permission** — the fail-open direction.
  Latent only because T03c's builder wrote the template placeholders as non-node-ids on purpose.
  Depends: T10j, T03c, T04, T10k.
- [x] T06l — `git rm` is not in `bash_guard`'s write-op inventory, so it deletes protected files where
  plain `rm` is denied — and it is a **documented instruction**
  (`tasks/T02-harvest-and-purge.md:40`, "Use `git rm` so the commit is reviewable"), so it has actually
  been used that way. No read-direction to get wrong. `--cached` is ruled a write (tracked state is
  what every integrity check compares). Also consolidates the twelve family pins into
  `RECORDED_FALSE_POSITIVES`, which currently holds 7 of 12 while its name promises the family.
  Depends: T06i, T06k.
- [ ] T09h — **AC ids collide across changes, so the second change in any repo cannot get a baseline**
  and the gate's `--criteria` half **fails open** (a change with zero tests reads
  `criteria.junit-backing PASS`). Blocks brownfield, the primary mode (F1). Decided: the marker carries
  the change (`@pytest.mark.ac("users/002:AC-8")`), bare = a previously accepted change's test.
  **BLOCKED** on `users/002` being accepted or abandoned — see the fixture note at the top of this file.
  Depends: T09b, T09f, T09g, T04.
- [x] T09i — the tests-only baseline screen inspects **HEAD only**, so with T12's pre-baseline `deps:`
  commit any earlier commit goes unscreened: a test-author committing `conftest.py` or `src/` first
  gets that commit unexamined, and the gate's protected trees do not cover `src/**` (it is the
  implementer's lane after the baseline). The screen's stated property holds; the property it exists to
  buy does not. `rebaseline`'s range walk is already the right shape to reuse, merge-commit refusal
  included. Depends: T09b, T12, T09f — **not T09h** (corrected 2026-07-27 in the task file: T09h only
  *found* this, and blocking on it would be an invented dependency).
- [x] T19 — `check_self_hash` anchors against a HEAD **the agent can rewrite**: `bash_guard` allows
  writes to the plugin directory by design (T06e), so an agent can tamper an anchor and
  `git -C <plugin> commit -a` until the tree matches. T18 made this strictly larger by anchoring the
  whole enforcement layer. **May not be fixable** in the sense the other tasks were — a precise written
  statement of the limit is a legitimate outcome; the cheap middle option is comparing against the
  release tag when one resolves. No network call. Depends: T18, T15, T04.
  **RULED 2026-07-26 — option (a): stated, not closed, and (b) rejected on measurement.** The limit is
  reproduced end to end through the shipped path (split plugin + `bin/adw.py` driven from the venue:
  tamper → RED naming the file; `git -C <plug> commit -a` → GREEN), and the release-tag comparison dies
  in both directions: **an installed plugin's marketplace cache is a *shallow* clone whose only refspec
  is `+refs/heads/main`, so it carries zero tags** (measured on a third-party marketplace installed on
  this machine) — the comparison would be inoperative exactly where it is wanted, and making it resolve
  means the network call this task forbids; while `claude plugin tag --dry-run .claude` reports it tags
  **`adw--v0.1.0` in THIS repo**, where every one of the last 30 commits touches an anchor path, so the
  tag is stale one commit after it is cut → the escalate clause's "RED every day" outcome. Plus the S8
  reading that needs no measurement: whoever can `git -C <plugin> commit -a` can
  `git -C <plugin> tag -f`. The statement lives in `notes/20` F-02 — with the one-command check a human
  *can* run (`git diff @{u}` over the anchor dirs after a `fetch`) — and in `check_self_hash`'s
  docstring. No behaviour change; option (c), a checksum pinned outside the plugin, remains the only
  real close and adds a concept nobody owns.
- [ ] T04i — two T04h findings about the legal-removal allowance. **(1)** It is collected from **every**
  change dir in the baseline tree (all `specs/**/changes/**/change.md` blobs concatenated), so change A's
  `## Removed` list authorises deleting a baseline test during change B's cycle — usually one document
  under S9, but a `Companion:` pair puts two there **by design**, which is why the obvious narrowing is
  a real question rather than a one-liner. **(2)** A granted removal is **silent and mislabelled**: the
  check prints `all N baseline tests collected and run (E-05)` where N counts the removed test that was
  neither collected nor run, and nothing about the grant reaches the verdict. Compare T04b's Docker
  carve-out, loud by construction with `docker_exempt` in the verdict — that asymmetry is the point,
  since `/accept-change` shows the gate's output to the human precisely so consequential things are
  seen. Depends: T04h, T04b, T09b, T03c.
- [ ] T05b — the freshness gate's **second** `git diff` still discards its rc (`_, out = _git(...,
  verdict_sha, actx.head)`), so an unusable diff yields an empty `changed_since` that reads as
  *"nothing changed since the pin"* — the register's root-cause sentence on a **TRUST** gate. T10f fixed
  the sibling call twelve lines above **with exactly this reasoning**, so the file disagrees with
  itself. Not bitten yet because `resolvable` is verified upstream — but T04g's finding 1 is the
  cautionary case: the same shape on `execute()`'s work-tree precondition also looked guarded and
  would have `rmtree`'d a change directory. Multiplier worth knowing: `accept.py`'s `_git` returns
  **stdout only**, so a failed call yields `""` with nothing in the value to notice. From T04g finding
  3, deliberately left there because it changes what a trust gate means. Depends: T10f, T10d, T04g.
- [ ] T06m — `bash_guard.ROLE_OWNED` has **no entry for `v3-builder`**, the role whose entire job is
  writing `.claude/**` — so the one role that legitimately owns the protected tree is the only one with
  no sanctioned path, and the denial message lists the three cycle lanes without mentioning it. T06d's
  exact shape, one role later. **The route around it is one line and was taken:** T04g's builder, denied
  `cp … .claude/tools/accept.py`, wrote the same six files with a `python3 - <<'PY' … write_text(…) PY`
  heredoc, which the guard allows — it cannot see interpreter writes. Fourth builder this session to
  route around rather than be stopped. Ergonomics, not trust (T18 anchors every `.claude/**` file), but
  the habit is what T06i measured twelve false positives' worth of damage from. Fix = a **scoped** lane
  from `v3-builder.md` (`.claude/**`, `tasks/`, `notes/`, design docs) that stays **denied** on
  `src/`, `tests/`, `specs/`. Depends: T06d, T06f, T06i, T06k, T18.
- [ ] T09j — `red_check.py` calls the shared `criteria_lint.strip_html_comments` **and** carries its own
  `_strip_html_comments` regex thirty lines below, and the two are **not** equivalent: the regex deletes
  the span including newlines (shifting every later line number) while the shared helper blanks in
  place, which is the contract T10k made public because the layer depends on it. One rule, two grammars,
  one file, no note. Precedent says either outcome is fine but an unexplained duplicate is not (the
  three `_section` parses were ruled on and *kept*, with the reason beside the code). Also: after T10k
  fixed its arguments, `accept.run()`'s no-plan branch still **prints a merge that did not happen** —
  unreachable today, which is why it should be fixed rather than trusted. From T10k findings 2 and 5.
  Depends: T10k, T17, T09f.
- [x] T20 — the `invisible` class **cannot be run and has no implemented proof**: `red_check.py` has no
  `Class:` parse at all (so it can never obtain a baseline tag, and `/implement` step 1 blocks), and its
  declared "empty before/after OpenAPI diff" exists in no script. T09g settled that it is not a lane to
  extend for test-strengthening; it still needs to either work or go. Building the diff also gives T17's
  OpenAPI half its implementation — share one, do not duplicate (C7). Depends: T09g, T17, T03/T03c.

**T06i's decision paid for itself, recorded because it is the strongest available argument against
point-fixing:** the builder re-measured before coding and found the family is **7 filed, 12
measured** — differential-testing old against new over ~120 commands surfaced five more false
positives nobody had filed (leading `~` joined onto the repo root; the `${VAR}` brace form; a
*quoted* `>` read as a redirect and blaming the file being read; a trailing `# comment` read as a
command; an **input** redirect's operand read as a write). Fixing only variants 6 and 7 would have
shipped with 8–12 live. It also closed three **misses** — `>|`, `&>`/`&>>` were never recognised as
redirects, and `echo x > $'tests/x.py'` (ANSI-C quoting) bypassed the guard **entirely**. All twelve
are now pinned in one `RECORDED_FALSE_POSITIVES` list, so the next rewrite is measured against the
family rather than against the fix at hand.

**CANON EDIT LANDED — §9's `uv init` → `uv init --package` (2026-07-26, author-authorised).**
`workflow_v3_spec.md:591` said a new project is «просто `uv init`… откуда выводится корень пакета
`src/<pkg>/`». Probed on uv 0.11.6: plain `uv init` emits `main.py` at the root and creates **neither
`src/<pkg>/` nor `[build-system]`** — the package root the sentence calls "derived" is never created
by the command it names. Fixed, with the reason inline so nobody "simplifies" it back. T11's copy is
corrected; T12b is written to match.

**No canon edit is needed for the removal vocabulary (T03c) — §3.1 is already right.** It pins the
marker (`REMOVED`) *and* the obligation ("change явно перечисляет отменяемое поведение"). The four-way
disagreement is entirely downstream: the `change.md` template comment, `/spec`, and `test-author.md`'s
"Removed tests block". So T03c is a **conform-to-§3.1** task, not a canon question — which is C7
exactly: the derivation has one home, and the home was correct all along.

**RESOLVED 2026-07-26 by T03c — option (a).** The block below is kept for the reasoning; the pinned
spelling is §3.1's `REMOVED` marker plus the template's `## Removed` section, the classifier reads
only that, and an unpinned wording is a FLAG rather than silence.

**OPEN DECISION the author owes T03 (from T10e findings #1/#2):** the removal-flavour vocabulary is
not pinned anywhere. `workflow_v3_spec.md §3.1` says `REMOVED`, the `change.md` template comment says
"removal flavour", `/spec` (`commands/spec.md:38`) says only "listed explicitly", and
`.claude/agents/test-author.md:79-82` instructs a "Removed tests block" that exists in **no
template**. T10e's classifier is deliberately tolerant of all three spellings on the `Class:` line;
T06f Part B makes a missing `## Removed` heading a visible FLAG. Neither is the fix. Choose: **(a)**
pin one spelling in the template + ship a `## Removed` section skeleton, then narrow the classifier
to it; or **(b)** keep the classifier tolerant and accept that `/spec` may emit any spelling. Until
this lands, V-02's coverage on a genuine removal rests on a heading nothing instructs anyone to write.

**Not tooling defects — routed back into the change (F1/F2).** The adversarial pass found two
surviving mutations, both future-regression exposure rather than shipped bugs (verified: the shipped
`save()`/`delete()` both carry `.where(id == …)`):
- **F1** — dropping `.where()` from `save()` rewrites every row and all 19 tests stay green. AC-8 and
  AC-9 each create exactly one user; AC-10 has a bystander but its PATCH 409s, so no test performs a
  *successful* PATCH with another row present. Correctly self-diagnosed as a **criteria** defect
  first: the AC text never mentions other users, so no test satisfying it literally could catch it.
- **F2** — a filtering soft delete passes AC-13, though `change.md` forbids tombstones. "No
  tombstones" is устройство and unenforceable as a criterion (S1) — but the *consequence* the pass
  found is observable and belongs as an AC: re-creating a deleted user's email would 409.

Routed via **TESTS-HANDBACK on `users/002`** (author's call, 2026-07-25) rather than deferred to a
follow-up change — the baseline tag has to move for the T10e/T06f rebase anyway, so
`red_check --rebaseline` runs once for both, and it exercises the handback path end-to-end for the
first time. Criteria text is edited by the human (S3).

## Dependency order

```
T01 ──► T02 ──────────────┐
  └───► T03 ──────────────┤
T02 ──► T04 ──► T05 ──────┼──► T09 ──► T10 ──► T11
          └───► T06 ──────┤
T07 ──► T08 ──────────────┘
```

Parallelizable groups: {T03, T04, T07} after T02 · {T05, T06, T08} after their parents.
Gate before T09: T06's bypass tests MUST be green — spec §10: "без enforcement v3 — это
v2 минус валидатор, то есть хуже v2".

## Rules for whoever drives this

1. One task per `v3-builder` dispatch. Tick the checkbox here only after Verification passed.
2. The builder never edits `workflow_v3_spec.md`, `notes/15_v3_design_review.md`, or task
   files (except this INDEX's checkboxes). Design questions → escalate to the human.
3. Every manual workaround during a task is a finding — recorded in the task report and,
   during T11, in the defect log (the notes/pipeline_dryrun_feedback.md honesty discipline).
4. **Branch base during the build-out:** until `markdown-specs` merges into `main`, it plays
   `main`'s role for S9 — `change/<context>-NNN` branches base on it and `accept.py` merges
   back into it (`main` is still the v2 archive). Revisit after T11.
5. **Cite by symbol/content, not line number** (line numbers drift — a task citing `accept.py:526`
   was really :558). A durable finding a builder must read belongs in repo `notes/`, NOT in
   agent-memory — task files must not point `Read first` at a path that isn't in the repo.
