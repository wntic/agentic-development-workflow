# `accept.py` — adversarial pass over its own gates (T10f register)

An audit of **every** gate in `.claude/tools/accept.py` against three questions (T10f):

1. **Does it fail open on degenerate input?** — empty diff, missing file, unresolvable SHA,
   empty criteria list, absent verdict section, zero AC, absent `src/`, absent companion branch.
2. **Is its parse anchored structurally**, or does it grep prose? (the T10e defect class)
3. **Can an agent make it pass without doing the work?** (S8, applied to acceptance)

Method: read every early-return and empty-input path, then *reproduce* each suspected defect
against the live script through the real CLI (`test_accept.py`'s fixture repo) or the pure
function. Every finding below carries the verbatim output that produced it — a finding with no
reproduction is a claim, not a finding.

> **STATUS: no fix applied.** The register found **7 fail-open paths** (plus 3 non-direction
> defects). T10f's own Escalate-if says: *"If the register finds more than ~3 fail-open paths,
> stop and escalate before fixing: that many would mean the acceptance script needs a structural
> answer (a single validated-input layer), not a patch per gate."* That threshold is exceeded and
> the paths share one root cause (§ "The single root cause"), so the fix is escalated, not
> improvised. This file is the input to that decision.

Severity legend: **[fail-open]** a gate PASSes (or silently does not run) where the invariant it
guards is violated or unverifiable · **[silent]** the gate's outcome never reaches the human ·
**[papercut]** noise/robustness · **[good]** the gate handles its degenerate input correctly
(kept for balance — three of them are the pattern the fix should generalise).

---

## Gate inventory — the degenerate-input matrix

| # | Result id | Degenerate input | Outcome today | Intended? |
|---|---|---|---|---|
| 1 | `escalate` | no change dir | `AcceptError`, rc 2 | yes |
| 2 | `criteria.complete` | criteria.md empty / all comments | FAIL (`no acceptance criteria`) | yes **[good]** |
| 3 | `verdict.freshness` | verdict.md absent | FAIL | yes |
| 3 | `verdict.freshness` | no `SHA:` hex | FAIL | yes |
| 3 | `verdict.freshness` | pin unresolvable (pruned) | FAIL | yes (T10d) |
| 3 | `verdict.freshness` | **base branch unresolvable → empty `base...HEAD` diff** | **FLAG → ACCEPTABLE** | **NO — F-01** |
| 4 | `companion` | no `Companion:` line | PASS | yes |
| 4 | `companion` | companion context dir absent | PASS (reads as "already accepted") | yes (dir gone == accepted) |
| 5 | `adversarial.presence` | **`resolve_targets` returns `[]` (capability-birthing change)** | **PASS "not required — S depth on an existing capability"** | **NO — F-02** |
| 5 | `adversarial.presence` | `### Interface sketch` (h3, not h2) | not required | no — F-08 (papercut) |
| 6 | `gate.green` | verdict.json missing / gate crash | uncaught traceback, rc ≠ 0 | acceptable (loud, closed) |
| 7 | `docker.tier` | **no `docker.alembic` check in the verdict at all** | **PASS "Docker tier ran"** | **NO — F-06 (latent)** |
| 8 | `criteria.junit-backing` | check absent from the gate verdict | FAIL | yes **[good]** — the pattern to generalise |
| 9 | `criteria.manual-verdict` | check absent from the gate verdict | FAIL | yes **[good]** |
| 10 | `affects.intersection` | **another in-flight change's targets unresolvable** | **PASS "no intersection"** | **NO — F-07 (latent)** |
| 11 | `merge.fidelity` | targets unresolvable | FAIL (`cannot determine target…`) | yes — but **[silent]** F-09 |
| 11 | `merge.fidelity` | **zero AC (both sources empty)** | **PASS "all 0 acceptance criteria are present"** | **NO — F-04 (latent)** |
| 11 | `merge.fidelity` | **AC text with no ≥3-char token** | **PASS (vacuous)** | **NO — F-04** |
| 12 | `merge.placement` | multi-target, no map | FLAG (check) / refuse (`--execute`) | yes (spec §5.4) |
| 13 | `spec.lint` | **overview.md absent entirely** | **PASS "spec-lint clean"** | **NO — F-03** |
| 13 | `spec.lint` | **`overview.md` lists the same capability twice** | **PASS** (the duplicate check is structurally dead) | **NO — F-03** |
| 13 | `spec.lint` | the capability *born by this merge* is unlisted | PASS (lint reads the pre-merge tree) | no — F-03 |
| 13 | `spec.lint` | the same dangling ref twice | FLAG, finding printed twice | papercut — F-10 |
| 14 | `orphan.sweep` | not a removal | SKIP | yes |
| 14 | `orphan.sweep` | `Class:` declares removal, no `## Removed` | FLAG | yes (T06f part B) **[good]** |
| 14 | `orphan.sweep` | **`## Removed` present, no backticked symbol in it** | **PASS "lists no concrete removed symbols to sweep"** | **NO — F-05** |
| 14 | `orphan.sweep` | `src/` absent | sweeps spec text only | yes (nothing to orphan) |
| — | provenance (`junit_ac_test_ids`) | **junit/inventory missing or uncorrelatable** | **invariant written as `(verified by: ?)`, no gate** | **NO — F-06** |
| — | `instantiate_capability` | `.claude/templates/` absent | uncaught `FileNotFoundError` | closed but unhandled — F-11 |

---

## The single root cause

Every **[fail-open]** below is the same sentence in different clothes:

> a helper that **cannot determine** its input returns an **empty / neutral** value, and the gate
> reads "empty" as **"nothing wrong"** instead of **"nothing known"**.

- `_git(..., check=False)` on an unresolvable base → empty stdout → empty `change_files` (F-01)
- `resolve_targets()` → `[]` → `creates_new = False` (F-02)
- missing `overview.md` → `""` → the coverage lint is disabled by its own `if overview_text` (F-03)
- a glob-derived name list can never collide → the duplicate-capability check is dead code (F-03)
- `_significant_tokens()` → `∅` → "no missing tokens" → merge-fidelity PASS (F-04)
- `classify_removal().terms` → `()` → "nothing to sweep" → PASS (F-05)
- `junit_ac_test_ids()` → `{}` → provenance `?` (F-06)
- an absent check in the gate verdict → `next(..., "")` → "Docker tier ran" (F-07/F-06)

The three **[good]** rows are exactly the sites that wrote the opposite reflex explicitly
(`if c is None: FAIL`, `if not criteria: FAIL`, `if not resolvable: FAIL` — the last one added by
T10d *after* it fell over in production). None of them is enforced as a rule; each is one author
remembering. That is why the count is 7 and not 1.

`gate.py` already has the reflex as a habit — every `_git` call in its integrity checks is followed
by `if rc != 0: return Check(..., "FAIL", "git diff against baseline failed")`. `accept.py` has that
guard on neither of the two `git diff` calls that produce a gate's *evidence* — both discard `rc`
(`check=True` is used for `rev-parse HEAD` and inside `execute()`, never for evidence; the
`merge-base` / `rev-parse --verify` probes do read `rc`, correctly). The two scripts disagree about
what an unusable git result means.

> **CORRECTION (2026-07-26, T04f).** The first sentence above — "**every** `_git` call in its
> integrity checks is followed by `if rc != 0`" — **was false when written**, and this register
> stated it as fact while using `gate.py` as the counter-example the fix should imitate.
> `_baseline_paths()` did `return [...] if rc == 0 else []`: an unanswerable `git ls-tree` was
> indistinguishable from "the baseline commit carries no such path" — this file's own root-cause
> sentence, one function away from `escalate_state()`, which spells the opposite reflex out in a
> docstring. Its three callers (`integrity.criteria-flips`, `integrity.change-frozen`,
> `integrity.test-inventory`) failed **closed** only by luck: the per-file `_baseline_blob()` fails
> for the same reason, and the resulting FAIL blamed the work tree — "created after the baseline
> commit" — for a git failure. Fail-closed-with-the-wrong-cause is how the fuse stayed unlit: no run
> ever went green, so nobody looked, and the misleading sentence sent the next reader after the
> spec files instead of after git.
>
> **Fixed in T04f:** the helper raises `GateError`, each caller turns that into a FAIL naming the git
> call, and `_baseline_blob_problem()` refuses to attribute an unreadable blob to a path the baseline
> tree lists.
>
> **What survives of the claim, after a sweep of every `_run`/`_git` in `gate.py`:** the reflex is
> real everywhere else it matters — `check_protected_trees` (both calls), `escalate_state` (both),
> `collect_baseline_inventory` (`git archive` + the collection run), `check_self_hash` (all three)
> and the ref-resolution probes in `resolve_context()`. The sweep found **no second fail-open site**,
> and two rc's that are discarded but degrade *loudly* by design, recorded here so the next reader
> need not re-derive them: `rev-parse HEAD` → `sha: UNKNOWN` in the printed header and in
> `verdict.json` (reachable only on an unborn HEAD, where there is no baseline either, so integrity
> is already SKIPPED loudly), and `status --porcelain` → the `dirty` flag, which is human-facing
> metadata no gate and no hook reads, and which a failing `git status` sets to `True` anyway because
> the helper merges stderr into its output. The habit was real; the blanket "every" was not — i.e. the
> paragraph directly above this correction, applied to the script it holds up as the good example:
> "each one is an author remembering", and one author did not.

---

## Findings

### F-01 **[fail-open]** an unresolvable `--base` turns an L-04 deny into ACCEPTABLE

`prechecks()` computes the change's file set with

```python
_, out = _git(actx.tree, "diff", "--name-only", f"{actx.base}...{actx.head}")
change_files = {line for line in out.splitlines() if line.strip() and line != verdict_rel}
```

`check=False`, so a base that does not resolve yields rc≠0, **empty stdout, no message** →
`change_files = ∅` → *every* post-verdict edit looks non-intersecting. This is the T05-era defect
class T10d closed for the SHA pin, still open one line away for the base.

Reproduced on the standard fixture repo, with one post-verdict commit touching `src/app/core.py`
(the exact scenario `test_stale_verdict_with_intersecting_diff_denies` pins):

```
=== base main ===
[FAIL] verdict.freshness — verdict SHA 9f9091d4befd is behind HEAD ad25aeeee42d and the diff
       intersects the change's files — recompute the evaluator (L-04): src/app/core.py
verdict: DENIED                                                                  (rc 1)
=== base ghost-branch ===
[FLAG] verdict.freshness — verdict SHA 9f9091d4befd is behind HEAD ad25aeeee42d but the diff
       does not intersect the change's files — verdict still fresh (L-04)
verdict: ACCEPTABLE                                                              (rc 0)
```

Same repository, same commits, one CLI typo apart. The rebase path (`rebase_freshness_state`) takes
`change_files` too, so it degrades identically: with an empty set it reports the attested tree
"byte-identical" without having compared anything.

Reachability is not hypothetical: `--base` defaults to `main`, `/accept-change` never passes
`--base` at all (`commands/accept-change.md` lines 28/104/111), and this build-out's S9 base is
`markdown-specs` (INDEX rule 4). A consumer project on `master`/`trunk` gets the fail-open by
default, silently.

*Direction fix:* resolve the base once, loudly — `git rev-parse --verify <base>` at `resolve()`
time, `AcceptError` if it fails; and `check=True` on the diff.

### F-02 **[fail-open]** a capability-**birthing** change escapes the mandatory adversarial pass

Spec §6 step 4 makes the adversarial pass mandatory for M/L depth **and for the first change of a
capability**. `prechecks()` asks:

```python
targets = resolve_targets(actx.tree, actx.ctx, actx.change_md)     # NOTE: no birth_slug
creates_new = any(not (...).exists() for name in targets) if targets else False
```

`resolve_targets` has a fourth parameter, `birth_slug`, that exists precisely so a
capability-birthing first change (no `Affects:`, no capability file yet, no name in overview.md)
can derive its target from the change-dir slug — and `compute_merge()` **does** pass it
(`actx.change_dir.name`). `prechecks()` does not. So on the greenfield first change the two call
sites disagree: acceptance derives a target and births `specs/<ctx>/<slug>.md`, while the
adversarial gate sees `targets == []`, falls into `creates_new = False`, and reports the change as
"S depth on **an existing capability**" — a statement contradicted by the prepared merge diff
printed 20 lines below it.

Reproduced on a greenfield fixture (no capability file, empty `## Capabilities`, no `Affects:`,
S-depth change.md, verdict.md whose adversarial section is the bare `N/A (S)`):

```
[PASS] adversarial.presence — adversarial pass not required — S depth on an existing capability
       — the adversarial pass is opt-in
...
== PREPARED MERGE DIFF (criteria -> capability invariants; not yet applied) ==
--- (new) specs/demo/thing.md
+++ specs/demo/thing.md
...
verdict: ACCEPTABLE                                                              (rc 0)
```

This is the F1 primary path (the first change of a new context), i.e. exactly the case the rule was
written for. It is invisible today only because `platform/001` and `users/002` both carried a filled
Interface sketch (M/L), which satisfies the requirement by the other branch of the `or`.

*Direction fix:* pass `actx.change_dir.name` as `birth_slug` in `prechecks()` (one derivation, one
home — C7), and treat unresolvable targets as `creates_new = True` (unknown ≠ safe).

### F-03 **[fail-open]** `spec.lint` claims "clean" on the two inputs it cannot see

Three sub-defects in one gate (§5.4 item 5 asks for dangling refs, **duplicate capabilities**,
>300-line files, **a capability missing from overview.md**):

a) **overview.md absent → the coverage check is disabled by its own guard.** `if overview_text and
   cap_files ...` — with no overview at all, *every* capability is unlisted, and the lint reports
   the opposite:

```
no overview.md -> PASS | spec-lint clean (no dangling refs, duplicates, oversize or unlisted capabilities)
```

b) **the duplicate-capability check is dead code.** `seen` is filled from
   `sorted(ctx_dir.glob("*.md"))` — filesystem names are unique by construction, so
   `if cap.name in seen` can never be true. The duplicate a human can actually create is a repeated
   entry in overview.md's `## Capabilities` list, which the lint never reads:

```
duplicate listing -> PASS | spec-lint clean (no dangling refs, duplicates, oversize or unlisted capabilities)
```
   (input: `- \`core.md\`` listed twice in overview.md)

c) **the lint reads the pre-merge tree.** A capability born *by this acceptance* is never checked
   against the overview map — see the F-02 reproduction: `thing.md` is about to be created and
   `## Capabilities` is empty, and the lint says clean. The drift lands on the base branch and is
   only reported at the *next* acceptance.

*Direction fix:* parse `overview.md`'s Capabilities list (the `_overview_capabilities` helper
already exists — C7), FLAG a missing overview.md, FLAG duplicate entries in the list, and run the
coverage check over `cap_files ∪ plan.targets`.

### F-04 **[fail-open]** merge-fidelity passes vacuously on an empty criterion set or a token-less AC

```
empty AC list  -> []          # "all 0 acceptance criteria are present in the merge diff (L-11)"
token-less AC  -> []          # ("AC-9", "`id` is up") vs an unrelated merge text
```

`_significant_tokens()` keeps only ≥3-char words (digits excepted), so an AC whose whole text is
short tokens has an empty token set and therefore *no missing tokens*, whatever the merge contains.
The zero-AC case is currently unreachable through the CLI (`criteria.complete` FAILs first and
short-circuits) — it is latent, not shipped, but it is the same reflex and it will be reachable the
moment the short-circuit order changes.

*Direction fix:* a criterion that contributes no comparable token is not "found", it is
**unverifiable** — report it as a violation naming the reason; and refuse to report PASS over an
empty AC list.

### F-05 **[fail-open]** `## Removed` with no backticked symbol → the sweep does nothing, and says PASS

Known and named in the INDEX (T06f finding 6); reconfirmed verbatim:

```
heading, no backticked symbol -> PASS | removal-flavour change lists no concrete removed symbols to sweep
```

Input: `Class: behavioral, removal flavour` + `## Removed` + the prose "The legacy export endpoint,
entirely." — while `LegacyExportHandler` is still in both the spec text and `src/`. T06f part B
turned the *missing heading* case into a FLAG on exactly this reasoning ("a gate that can quietly
not-run does not exist", S4); the *empty heading* case kept the PASS. The `PASS` string is also
untrue in the direction that matters: it reads as "the sweep ran and found nothing".

*Direction fix (needs no vocabulary decision):* FLAG, with the same wording family as the
missing-heading case. The **real** fix — narrowing the vocabulary so `/spec` emits a machine-readable
`## Removed` list — is the open T03 decision recorded in `tasks/INDEX.md` and is not this task's.
Note that changing PASS→FLAG requires rewriting `test_orphan_sweep_does_not_flag_when_the_heading_is_present`,
which currently pins the PASS deliberately.

### F-06 **[fail-open]** invariant provenance degrades to `?` — and can point at the wrong test

`junit_ac_test_ids()` returns `{}` when `.gate/last-run.xml` is absent, and `build_invariant_lines`
turns a missing entry into a literal `?`:

```
empty gate dir -> {}
invariant line -> [('AC-1', '- add returns the sum (verified by: ?)')]
```

Nothing gates that. The invariant would be written into the canonical capability file with an
unresolvable provenance mark, and `gate.py`'s L-06 check resolves `(verified by: ?)` by searching the
test corpus for `def ?(` — which cannot match, so `spec.invariant-tests` goes **FAIL**. Read at the
S9 altitude: `accept.py --execute` would merge, into the base branch, spec content that makes the
base branch's own gate RED. "main is always green" broken by the acceptance script itself.

Worse, the correlation is by **function name only** (`node_id.rsplit("::")[-1] == name`), ignoring
junit's `classname`. Two same-named tests in different files → the invariant is attributed to
whichever node-id sorts first:

```
junit:      classname="tests.test_b" name="test_create"  (ac=AC-1)
inventory:  tests/test_a.py::test_create, tests/test_b.py::test_create  (both passed)
result   -> {'AC-1': 'tests/test_a.py::test_create'}          # the wrong file
```

`test_create` / `test_delete` / `test_get` in `tests/unit/` and `tests/integration/` is not an exotic
shape — `users/002` alone ships 19 tests across several files.

*Direction fix:* correlate on `classname` + `name` (module path is right there in the junit), and
FAIL when a proven criterion has no resolvable node-id instead of writing `?`.

### F-07 **[fail-open, latent]** `affects.intersection` and `docker.tier` read "absent" as "fine"

- `affects.intersection`: an in-flight change whose own `Affects` cannot be resolved contributes an
  empty set, so it can never intersect — L-03 silently does not consider it.
- `docker.tier`: `docker_detail = next((c["detail"] for c in checks if c["id"] == "docker.alembic"), "")`
  → if the gate verdict carries **no** `docker.alembic` check, the branch falls through to
  `PASS "Docker tier ran"` — asserting a tier ran on the evidence of its absence. Today `gate.py`
  always emits the check, so this is latent; it is listed because T04b's whole point was that a
  skipped Docker tier must never be a silent default.

### F-08 **[papercut]** `_section()` only sees `## ` headings

`_section` matches `line.strip().lower().startswith("## ")`, so a `### Interface sketch` or
`###Context` is invisible. Consequences split by direction: in `verdict.md` it fails closed (the
adversarial section reads as absent → FAIL), in `change.md` it fails open (an M/L change reads as S
depth → the adversarial pass is not required). Low priority, but it is the T10c defect class
(cosmetics deciding a verdict) still alive on the change.md side.

### F-09 **[silent]** an unresolvable target erases two gates from the report

When `compute_merge` returns `plan.error`, `gate_dependent_checks` appends the `merge.fidelity` FAIL
and **returns early** — `spec.lint` and `orphan.sweep` are never computed *and never printed*, not
even as SKIP (the SKIP filler in `run()` only covers the prechecks-blocked path). Reproduced:

```
[FAIL] merge.fidelity — cannot determine target capability file — add an 'Affects: <capability>.md' line to change.md

== ACCEPT ==
verdict: DENIED
```

Fail-closed overall, so no false accept — but two gates vanish from the human's output with no
trace, which is the reporting half of the same disease.

### F-10 **[papercut]** `spec.lint` emits duplicate findings

Named in the INDEX as the cheap one; confirmed — the same dangling ref referenced twice in one file
prints twice:

```
specs/demo/core.md references missing spec file `ghost.md`
specs/demo/core.md references missing spec file `ghost.md`
```

`re.findall` over the file yields one finding per occurrence, not per (file, ref).

Live on `users/002` (`accept.py users/002 --base markdown-specs`), where it compounds with F-03c —
the ref is not dangling at all, it is the capability this very acceptance births:

```
[FLAG] spec.lint — spec-lint findings for the review diff (L-07/O-13):
       specs/users/overview.md references missing spec file `user-management.md`
       specs/users/overview.md references missing spec file `user-management.md`
```

So the greenfield birth case produces a **false** finding, twice. Harmless (FLAG), but it is noise
in the one output the human is asked to read carefully, on the workflow's primary path.

### Baseline for the follow-up: `users/002` today

Run in a detached worktree at `change/users-002` (`GATE_DOCKER=0`, base `markdown-specs`), with the
register's `accept.py` unmodified:

```
GATE: GREEN
[PASS] escalate · criteria.complete (14) · verdict.freshness (tree-identity after rebase) ·
       companion · adversarial.presence (first change of a capability) · gate.green ·
       criteria.junit-backing (14) · criteria.manual-verdict (0) · affects.intersection ·
       merge.fidelity (14/14)
[FLAG] docker.tier (DOCKER SKIPPED, forced) · spec.lint (the F-10/F-03c false ref, twice)
[SKIP] orphan.sweep (not a removal)
verdict: ACCEPTABLE
```

Whatever fix lands for F-01…F-07 must reproduce this verdict line for line, except that `spec.lint`
should stop reporting `user-management.md` twice (F-10) and should stop reporting it at all (F-03c).
Note that `users/002` is a capability-birthing change that **does** carry `Affects:` — which is why
F-02 does not bite it, and why F-02 stayed invisible through two full cycle runs.

### F-11 **[papercut]** the capability-birth path has no integration coverage, and crashes bare

`instantiate_capability()` reads `.claude/templates/capability.md` with no guard. Every fixture repo
in `test_accept.py` copies `TOOL_FILES` only, and every fixture change has an existing target, so
**no integration test has ever exercised a capability birth through the CLI**. Building one for F-02
produced:

```
FileNotFoundError: [Errno 2] No such file or directory:
  '<repo>/.claude/templates/capability.md'
```

as an uncaught traceback out of `main()`. Harmless in this repo (the template exists) and
fail-closed, but the missing coverage is what let F-02 sit unnoticed: the greenfield first change is
the workflow's F1 primary path and no test drives it to acceptance.

---

## Question 2 — is each parse anchored structurally? (the T10e class)

| Parse | Anchor | Verdict |
|---|---|---|
| `classify_removal` | `^Class:` line + `^#+\s*Removed` heading, terms harvested from the matched section only | anchored (T10e) |
| `parse_verdict_sha` | `SHA:` token + hex run, markdown-tolerant | anchored; tolerance widens the parse, not the semantics |
| `_adversarial_body` | `## ` heading, two accepted spellings | anchored, but h2-only (F-08) |
| `resolve_targets` | `^Affects:` line, `.md` tokens, HTML comments stripped | anchored |
| `_overview_capabilities` | `## Capabilities` section, `*.md` tokens | anchored (and under-used — F-03) |
| `Companion:` | `(?m)^Companion:\s*([A-Za-z0-9_-]+/\d+)` | anchored to a line start, but matches **anywhere** in the file, including inside a fenced code block or a quoted example. Protected by `gate.py`'s `integrity.change-frozen` (change.md is hash-frozen against the baseline), so an agent cannot add or remove the line post-baseline. |
| `_change_ac_texts` | `## Acceptance criteria` section + `^-\s*AC-\d+:` | anchored; a checkbox-style `- [ ] AC-1:` does not match and falls back to criteria.md — acceptable |
| `merge_fidelity_violations` | token-set, deliberately fuzzy (§5.4 "grep-class") | fuzzy by design; the vacuous-token hole is F-04 |
| `spec.lint` refs | `` `<name>.md` `` in any file | fuzzy: a `.md` name mentioned in prose counts as a reference. Noise-only (FLAG gate) |

No new prose-grepping classifier of the T10e kind survives. The remaining fuzziness is in gates that
only FLAG, except F-04.

---

## Question 3 — can an agent make a gate pass without doing the work? (S8)

| Gate | Bypass | Backstop |
|---|---|---|
| `escalate` | **delete the `ESCALATE` file and commit** | **none.** §5.3 says "снять файл может только человек" — that is prose. The change dir is not in `gate.py`'s `PROTECTED_PATHS` (`.claude/tools`, `.claude/hooks`, `.claude/settings.json`, `pyproject.toml`), only `criteria.md` (legal flips) and `change.md` (hash) are watched. Deleting `ESCALATE` is invisible to both scripts. |
| `criteria.complete` | flip every box | `gate.py` `integrity.criteria-flips` (legal flips only) + `criteria.junit-backing` (a `[x]` needs a **passed** ac-test in this run's junit) |
| `verdict.freshness` | re-pin the SHA by hand | weak by construction (the pin is self-reported), but the tree comparison is computed from git, not from the verdict — except under F-01 |
| `companion` | delete the `Companion:` line | `integrity.change-frozen` |
| `adversarial.presence` | write any non-`N/A` prose under the heading | **presence only, by design** (documented in the docstring: "criteria_guard cannot tell a human evaluator from a self-certifying one"). F-02 makes even the presence requirement skippable for the birth case. |
| `gate.green` | tamper with `.gate/verdict.json` | none needed: accept **re-runs** `gate.py` in-process (§5.4's "не доверяет git-ignored `.gate/verdict.json`") and `gate.py` self-hashes |
| `criteria.junit-backing` | — | delegated to `gate.py` (one implementation, C7) |
| `merge.fidelity` | — | it compares change.md's AC text against the invariant built from criteria.md's text, so it catches a **dropped** or reworded criterion (its L-11 purpose). It is not a strength check and cannot be one: both texts are authored in the same `/spec` session. Called out so no one mistakes the PASS for "the criterion is good". |
| `spec.lint` / `affects.intersection` / `orphan.sweep` | — | FLAG-class, advisory to the human by design |

The one real S8 hole is the `ESCALATE` file. It is not a degenerate-input defect and it is out of
T10f's scope (the fix belongs in `gate.py`'s integrity inventory, §5.1 — e.g. an ESCALATE deletion
between baseline and HEAD is RED unless the human's commit removed it), but it is recorded here
because the audit asked the question and this is where the answer will be looked for.

> **CORRECTION (2026-07-26, after T04e).** The fix sketched in the paragraph above — "an ESCALATE
> deletion between baseline and HEAD is RED" — **was built (T04e, `086fee5`, check
> `integrity.escalate-intact`) and does not close this hole.** Two reasons, both re-derived from
> source:
>
> 1. **The file is never tracked.** `.claude/hooks/subagent_stop.py:169` writes it with a bare
>    `escalate.write_text(...)` — no `git add`, no commit — and `.gitignore` does not mention it. Git
>    retains nothing about a never-committed file, so no `gate.py`-only check can see its removal.
> 2. **Even if it were committed, a baseline-vs-HEAD comparison would still miss it.** The hook fires
>    at the *implementer's* ceiling, i.e. after the test-author's RED baseline is committed and
>    tagged — and `red_check` refuses any baseline commit touching non-`tests/` paths, so an ESCALATE
>    can never be in the baseline tree. Baseline says "absent", HEAD says "absent" → PASS.
>
> **What T04e's shipped check actually covers:** only an ESCALATE that somehow reached the *baseline
> commit*. In the shipped flow that is unreachable. The check is correct, tested, and harmless, and
> it becomes load-bearing under the real fix — but it must not be read as closing this row.
>
> **Second victim of the same root cause:** `accept.py`'s `escalate` gate is `escalate.exists()` on
> the work tree. A fresh `git worktree` never carries untracked files, so a worktree-based acceptance
> — which is how this very register's `users/002` baseline was produced — cannot see a genuine
> ESCALATE at all. No agent misbehaviour required.
>
> The real fix (hook commits the file + a branch-history check + a sanctioned clearing step, since
> `red_check --rebaseline` refuses a non-`tests/` commit) is filed as **T06h**. This row stays
> **OPEN**.

> **CLOSED (2026-07-26, T06h).** All three parts landed. `subagent_stop` now writes **and commits**
> the ESCALATE (`git add -- <p>` then `git commit -- <p>`, never `-A`; a failing commit never unwrites
> the file and its reason reaches the `systemMessage`). `gate.py`'s `escalate_state()` asks the
> **branch-history** question — ls-tree at the anchor ∪ `git log anchor..HEAD`, both rc-guarded — and
> `accept.py`'s precheck asks the same question through that helper (C7), so the worktree blindness
> above is gone: a tracked file is carried by a fresh checkout. The sanctioned clearing step is
> `red_check.py --change <ctx>/NNN --clear-escalate`, which makes true the promise `gate.py`'s own
> comment had been making since T04e. Measured both directions: pre-fix the delete-and-commit bypass
> gave `GATE: GREEN` / `verdict: ACCEPTABLE`; post-fix `GATE: RED` / `verdict: DENIED` naming the
> flag.
>
> Two things this row's own history is worth remembering for:
>
> - **T04e's ls-tree half is not dead code**, contrary to its own builder's conclusion. A
>   baseline-carried ESCALATE *is* reachable: after a lock is committed, a TESTS-HANDBACK plus
>   `--rebaseline` moves the tag onto a tests commit that **descends** from the ESCALATE commit, so
>   the new baseline tree carries it. Both halves are load-bearing and are now one union.
> - **A third instance of this register's own defect class, found while implementing the fix:**
>   `git diff-tree -r <merge>` prints **no** path names, so a merge commit inside
>   `old-baseline..HEAD` would have read as "touches nothing" and let an arbitrary tree into the new
>   baseline. `--clear-escalate` now refuses any merge commit in the range. Degenerate input again —
>   this time a *shape* of commit rather than an unresolvable ref.
>
> Accepted knowingly (S8): the clearing path cannot distinguish a human from an agent, so an agent at
> its ceiling can run it. The deliverable is that the act is **recorded** — a commit plus a tag move —
> not that it is prevented. Not yet exercised in a live session; that needs a real `/implement`
> reaching its ceiling in the T16 venue.

---

## Proposed structural answer (the escalation)

The 7 fail-opens are one missing rule. Two ways to land it:

**(a) Patch per site.** Seven local fixes (F-01…F-07), each with a test that fails against the
current function. Smallest diff, no new abstraction, gate semantics stay visible at each call site.
Leaves the class open: gate #15 gets it wrong again unless its author remembers.

**(b) A validated-input layer + one rule, enforced by a parametrised test.** Make "input could not
be determined" a *representable value* instead of an empty container: `_git` fails loudly for the
base (`check=True` at resolve time), `resolve_targets` distinguishes "no target" from "unknown",
`junit_ac_test_ids` reports uncorrelated ac-ids, and every gate obeys one rule —

> a gate whose input could not be determined returns **FAIL** if it guards trust
> (freshness, criteria, provenance, adversarial presence), **FLAG** if it is a review aid
> (spec-lint, affects-intersection, orphan sweep); never **PASS**, never absent from the report.

with a parametrised `test_no_gate_passes_on_undetermined_input` that walks the gate list, so a
*future* gate is covered by construction (T10f's own deliverable wording).

(b) is more work and touches the signatures of four helpers, but it is the answer the T10f Escalate-if
predicts. The direction assignment above (which gates FAIL vs FLAG) is the design decision that must
come from the human, not from the builder: F-01/F-02/F-04/F-06 look like FAIL, F-03/F-05/F-07 like
FLAG — but F-05's direction is entangled with the open T03 removal-vocabulary decision, and F-02's
"unknown target ⇒ treat as a birth ⇒ require the adversarial pass" is a policy call, not a bug fix.

Reproductions for every finding are in the probe harness used to write this register (throwaway,
not committed); each is a small mutation of `test_accept.py`'s `make_repo` fixture and is described
inline above so it can be rebuilt from this file alone.
