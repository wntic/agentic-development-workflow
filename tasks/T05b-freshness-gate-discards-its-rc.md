# T05b — the freshness gate's second `git diff` still discards its return code

## Goal
`accept.py`'s `verdict.freshness` gate makes two `git diff` calls. T10f fixed the first
(`base...HEAD`) with `check=True` after F-01. The second still reads:

```python
_, out = _git(actx.tree, "diff", "--name-only", verdict_sha, actx.head)
changed_since = {...}
```

An unusable diff therefore yields an **empty** `changed_since`, which the freshness logic reads as
*"nothing changed since the pin"* — the register's root-cause sentence exactly, on a **TRUST**-class
gate. Found by T04g's sweep (its finding 3) and correctly left alone: it is a one-word change to what
a trust gate *means*, which belongs in a task that argues it rather than in a lint pass.

**Why it has not bitten, and why that is not a reason to leave it.** `resolvable` is verified by a
`rev-parse --verify` immediately above, so the diff's inputs are known-good today — the guard is
upstream, not local. The sibling call twelve lines up already carries `check=True` **with exactly this
reasoning**, so the file currently disagrees with itself about whether upstream verification is
enough. And T04g's finding 1 is the cautionary case: the same "rc discarded, empty reads as fine"
shape on `execute()`'s work-tree precondition would have `rmtree`'d a change directory on an
unanswerable `git status`, and *that* one also looked guarded until it was measured.

Note the multiplier that makes this family so easy to miss here: `accept.py`'s `_git` returns
**stdout only** (`return proc.returncode, proc.stdout`), so a failed call yields `""` rather than an
error string — there is nothing in the value to notice.

## Depends on
T10f (which fixed the sibling call and wrote the undetermined-input rule), T10d (which owns the
freshness semantics — tree-identity, signed off 2026-07-25), T04g (which found this).

## Read first
- `.claude/tools/accept.py` — the `verdict.freshness` gate: both `_git` diff calls, `freshness_state`,
  `rebase_freshness_state`, and the `resolvable` / `reachable` probes above them. Note which call
  already has `check=True` and why.
- `notes/19_accept_gate_audit.md` — F-01 and the root-cause section; this is the same finding one call
  along, and the register should gain a line when this lands.
- `tasks/T10d-freshness-survives-rebase.md` — the tree-identity semantics, so the fix does not
  accidentally re-open the commit-identity question.
- `PRINCIPLES.md` S8, A3's second clause.

## Deliverables
- `.claude/tools/accept.py` — the second diff cannot be read as evidence unless git answered. Prefer
  `check=True` for consistency with its sibling; if raising is wrong here (the gate is inside a
  results list, so an exception changes the report shape), return a **FAIL** naming the failed git
  call instead — but do **not** leave the empty-means-fine path. State which you chose and why.
- `.claude/tools/test_accept.py` — a case where that diff cannot be answered: the gate FAILs (or the
  run aborts) naming git, and **never** reports the verdict as fresh. The T10f pattern
  (`test_no_gate_passes_on_undetermined_input`) is the model; if the new case fits that parametrised
  walk, add it there rather than as a one-off.
- `notes/19_accept_gate_audit.md` — one dated line under F-01: same defect, second call, closed.

## Verification
- `uv run pytest .claude/tools` green.
- The new case demonstrably differs against pre-fix `accept.py` — today an unanswerable second diff
  reports **fresh**. Assert on the verdict, not only on the message.
- **`users/002` reproduces unchanged**, and this is the case that matters: its verdict was rebased
  away and is judged *by tree identity* through this very call (`verdict SHA … was rebased away but
  the change's attested tree is byte-identical`). If that line changes, the fix broke T10d.
  Recipe in the INDEX; commit tool edits first (T18).
- `uv run pytest .claude/tools/test_accept.py -k freshness` green.

## Out of scope / Escalate if
- Do NOT change what freshness *means*. T10d settled tree-identity over commit-identity and it was
  signed off; this task only stops an unanswerable git call from being read as evidence.
- Do NOT sweep the rest of `accept.py` for `_, x = _git(...)`. T04g's sweep already did: this is the
  only remaining site where an empty value is read as a positive fact. Adding `check=True` to calls
  whose emptiness is *legitimately* meaningful would be a fresh fail-closed noise source.
- **Escalate if** making it FAIL turns `users/002` red. That would mean the call is unanswerable in a
  legitimate rebase case, and then the fix has to distinguish "git refused" from "the pin is gone",
  which is a T10d question, not this one.
