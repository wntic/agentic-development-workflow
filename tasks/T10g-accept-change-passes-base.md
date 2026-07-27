# T10g — `/accept-change` never passes `--base`, so it judges against the wrong branch

## Goal
`.claude/commands/accept-change.md` invokes the script as:

```
uv run .claude/tools/accept.py <context>/NNN
```

`accept.py`'s `--base` defaults to `main`. In this repo the S9 base is **`markdown-specs`**; `main`
is the v2 archive. So the command as written judges the change against the wrong branch — and a
consumer project on `master`, or any project whose integration branch is not `main`, hits the same
thing. The `users/002` acceptance only worked because the operator passed `--base markdown-specs`
by hand.

Surfaced by the T10f audit (`notes/19_accept_gate_audit.md`, F-01's reachability note). It is
separate from F-01 itself: F-01 is `accept.py` failing **open** when the base does not resolve;
this is the *command* handing it the wrong base in the first place. T10f fixes the script's
direction; without this, `/accept-change` still asks the wrong question — and the two compound,
because a wrong base that happens not to resolve is exactly F-01's silent-ACCEPTABLE path.

## Depends on
T10 (the command), T10f (the `--base` direction fix — land that first so a wrong base fails loudly).

## Read first
- `.claude/commands/accept-change.md` — every `accept.py` invocation (steps 1 and 6, including the
  `--placement` variant).
- `.claude/tools/accept.py` — the `--base` argument and its default.
- `tasks/INDEX.md` rule 4 — the standing note that this build-out's base is `markdown-specs`.
- `PRINCIPLES.md` C7 (derivation has one home) before hardcoding a branch name anywhere.

## Deliverables
- Resolve the base **once**, in one place, and cite it everywhere else (C7). Decide between:
  **(a)** the command determines the base and passes `--base` explicitly on every invocation; or
  **(b)** `accept.py` derives the default itself (the current branch's upstream, or the repo's
  configured default branch) instead of hardcoding `main`, and the command keeps passing nothing.
  (b) is the stronger shape — it fixes every caller including a human running the script directly —
  but it changes a script default, so state the reasoning either way.
- `.claude/commands/accept-change.md` — all invocations updated consistently, including the
  `--placement` example in step 6.
- Tests for whichever shape is chosen: under (b), `.claude/tools/test_accept.py` cases for the
  derivation and its fallback; under (a), a check that the command's documented invocations name
  `--base`.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green.
- Re-run the recorded `users/002` before-baseline (branch `change/users-002` `a931ee6`, tag
  `baseline/users-002` `dd3a64b`, detached worktree) through the **command's** documented
  invocation — with no hand-added `--base` — and get `verdict: ACCEPTABLE`. That is the whole point:
  the command must reach the right answer unaided.
- `grep -n "accept.py" .claude/commands/accept-change.md` — every invocation consistent; no example
  left showing the bare form if (a) is chosen.

## Out of scope / Escalate if
- Do NOT hardcode `markdown-specs`. That is this build-out's branch, not a property of the workflow;
  baking it in is exactly the C6 scope-overclaim the skills were purged of.
- Do NOT fix F-01 here — that is T10f's. This task assumes a wrong base now fails loudly.
- **Escalate if** the base cannot be derived without a config file. "Where does the workflow record
  the integration branch" is a canon question (§9 substrate), and inventing a config surface is not
  a builder's call.
