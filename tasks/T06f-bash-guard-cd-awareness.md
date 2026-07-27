# T06f — bash_guard must resolve relative write targets against the command's effective cwd

> **Scope note (author, 2026-07-25):** this task carries **two concerns**, deliberately. Part A is
> the `bash_guard` fix it was filed for. Part B is a one-line `accept.py` change closing a fail-open
> that T10e opened. They are unrelated in code and would normally be separate tasks — they are
> batched because both are protected-tree canon fixes that must land **before** the single
> `change/users-002` rebase, and a third dispatch would cost a third rebase. Do Part A first and
> commit it separately; do not let B's triviality tempt you into folding the commits.

---

# Part A — bash_guard

## Goal
`bash_guard` denies legitimate writes into scratch directories outside the repo whenever the
command reaches them by `cd`-ing first. It twice blocked the `users/002` adversarial evaluator on
`cd /private/tmp/.../scratchpad/mut && cat > tests/integration/.../test_probe.py` — a write into a
throwaway mutation copy of the tree, nowhere near the repo.

This is **not** the bug T06e closed. T06e anchored the match to the repo root for *absolute*
targets. The remaining hole is relative targets: `offending()` does resolve them against `cwd`
(`bash_guard.py:199-201`), but the `cwd` in the PreToolUse payload is the **session** cwd, and
`_write_targets()` has no `cd` awareness at all (zero occurrences of `cd` in the file). It
flat-tokenises the compound command, so the `cd` prefix is invisible and `tests/…` resolves under
the repo root.

Fixing this also closes what looked like a second, separate defect: the same agent's *other* denial
had its real mutations in `src/`, and died only because a leading `rm -f tests/.../test_probe.py`
sat in the same compound command. There is no per-target deny to add — a PreToolUse hook can only
allow or deny the whole call — but once that `rm` target correctly resolves into the `/tmp` copy, it
falls outside the repo and never fires. One fix, both symptoms.

Cost of leaving it: the agent rerouted and completed all 8 mutations anyway. That is the bypass
reflex the guard exists to prevent, trained by the guard itself. Under S8 the gate is the backstop,
so a false positive is strictly more expensive than a miss — keep T06b's precision bias.

## Depends on
T06, T06b (precision-first tokeniser), T06d (role-aware owned-tree allowance), T06e (repo-root
anchor — do not regress it).

## Read first
- `.claude/hooks/bash_guard.py` — `_write_targets()` (the flat tokeniser), `_repo_relative()`
  (`:190-201`, already cwd-aware), `offending()` (`:218-249`, first-match return), `deny()`.
- `tasks/T06e-bash-guard-repo-root-anchor.md` — what was already fixed, and its fallback rule.
- `PRINCIPLES.md` S8 — why precision beats prevention here.

## Deliverables
- `.claude/hooks/bash_guard.py` — track the command's **effective** cwd when resolving relative
  write targets:
  - honour a leading `cd <dir>` (and `cd <dir> &&` / `pushd`) before resolving subsequent relative
    targets in that command;
  - when the effective cwd cannot be determined with confidence, or the command `cd`s to a path
    outside the repo root, **do not fire** on relative targets (T06b precision bias — the gate
    backstops).
  - Keep T06e's absolute-path anchoring and T06d's owned-tree allowance intact.
- `.claude/hooks/bash_guard.py` — **filename fragments must not match as bare substrings.** Found
  building T10e: `git show … > .claude/tools/fixtures/users-002-change.md` was denied because the
  protected fragment `change.md` is a substring of `users-002-change.md`. The builder worked around
  it by *renaming the fixture*, which means the guard is dictating filenames — a T06b precision
  defect of the same family as Part A's. Match a filename fragment against the target's **basename
  or a full path component**, not `frag in path`. Directory fragments (`tests/`, `specs/`) keep
  their prefix/component semantics.
- `.claude/tools/test_enforcement.py` — cases:
  - `cd /tmp/mut && cat > tests/integration/x_test.py` (non-owner role) → **allowed** (regression);
  - `cd /tmp/mut && rm -f tests/x.py && cat > src/y.py` (non-owner) → **allowed** (the compound-veto
    regression);
  - `cat > tests/x.py` with no `cd`, session cwd = repo (non-owner) → still **denied**;
  - `cd /tmp/mut && cat > /repo/tests/x.py` (absolute, non-owner) → still **denied**;
  - `> .claude/tools/fixtures/users-002-change.md` → **allowed** (the basename regression); a write
    to a real `specs/**/change.md` by a non-owner → still **denied**;
  - owned-tree write under a T06d role → still allowed.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green with the new cases.
- Simulated PreToolUse payload replaying both `users/002` denials verbatim → exit 0 (allowed).
- The in-repo denial cases from T06/T06b/T06d/T06e all still deny — run the full module, not just
  the new cases.

## Out of scope / Escalate if
- Do NOT implement a general shell interpreter. Handle the `cd`-prefix idiom agents actually emit;
  anything ambiguous degrades to not-firing, and the gate catches the miss.
- Do NOT relax in-repo protection for a non-owning role. This narrows resolution, not ownership.
- If honouring `cd` cannot be done without materially widening the bypass surface *inside* the repo
  (e.g. `cd .. && cat > repo/tests/x.py` slipping through), record the trade-off and escalate before
  choosing — that is a canon call about how much prevention the guard is meant to carry.

---

# Part B — close the V-02 fail-open T10e opened

## Goal
T10e made `_orphan_sweep` classify structurally, which was right and closed a false FAIL. But two of
its own findings (#2, #3) combine into a **fail-open**:

- the classifier now keys on a `#+ Removed` heading, and **nothing instructs `/spec` to emit one** —
  `.claude/agents/test-author.md:79-82` references a "Removed tests block" that exists in no
  template, and `commands/spec.md:38` asks only that removed behaviour be "listed explicitly";
- a change whose `Class:` line *does* declare the removal flavour but carries no heading now returns
  **SKIP** (per T10e's task instruction).

Net: a genuine removal change can reach acceptance with **V-02 never running, and nothing said about
it**. That is strictly better than T10e's false FAIL, but it trades a loud wrong answer for a quiet
absent one — and under S4 a must-hold rule whose gate can silently not-run does not exist. Same
failure direction as the T05 freshness hole T10f is being filed to hunt.

## Deliverables
- `.claude/tools/accept.py` — when `RemovalFlavour.by_class` is true but `sections` is empty, return
  **FLAG**, not SKIP, with a reason naming the missing `## Removed` heading. FLAG is
  surfaced-but-non-blocking, so a legitimate removal is not deadlocked while the T03 template gap is
  open — but the absent sweep is visible in the human's review output instead of silent.
  Leave the not-removal-at-all path as SKIP (that one is correct and is `users/002`'s case).
- `.claude/tools/test_accept.py` — a case asserting FLAG (not SKIP, not PASS) for
  class-declared-without-heading, and that the not-a-removal path still SKIPs.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green (39 tests, up from T10e's 38).
- `uv run .claude/tools/accept.py users/002 --base markdown-specs` still reports
  `[SKIP] orphan.sweep — not a removal-flavour change` and verdict ACCEPTABLE. **Part B must not
  change `users/002`'s answer** — if it does, the SKIP/FLAG split is wrong.

## Out of scope / Escalate if
- Do NOT make it FAIL. Blocking every removal change on a heading no command emits would trade the
  fail-open for a deadlock — the T10e defect inverted.
- Do NOT edit the `change.md` template or `/spec` here. Pinning the removal vocabulary + shipping a
  `## Removed` skeleton is the **T03 decision the author still owes** (T10e finding #1); this part
  only makes the gap visible. Note the FLAG's reason text will need updating once that lands.
