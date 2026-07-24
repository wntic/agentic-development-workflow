# T10d — accept.py freshness should survive a rebase (kill the re-pin cascade)

## Goal
Stop a branch rebase from invalidating an otherwise-fresh verdict. On `/implement platform/001`
a canon fix to `accept.py` (the capability-birthing Affects gap, main `d25e21e`) was made **while
the change was in flight**; the branch was rebased onto the fixed main **twice** (fix + refine),
each rebase rewrote every SHA, and each time the verdict's pinned `SHA:` pointed at a commit that
no longer existed → the L-04 freshness gate failed → two more orchestrator re-pin resumes. The
5th such resume was user-rejected — the human cut the cascade off by hand. The verdict's
*content* was valid at every step; only the pin identity churned.

**Design-sensitive: this touches the L-04 freshness canon. Confirm the intended semantics against
`workflow_v3_spec.md` §5 / accept.py before changing behaviour — escalate if the spec's freshness
guarantee would be weakened.**

## Depends on
T10 (accept.py freshness), T09e (self-commit — with self-commit the churn is smaller but a
rebase can still orphan the pin).

## Read first
- `.claude/tools/accept.py` — the L-04 freshness gate: how it resolves the pinned SHA, and what
  it compares (tracked-tree identity vs commit-identity).
- `workflow_v3_spec.md` §5 (the freshness rationale — what the pin is meant to guarantee: that
  the verdict attests to THIS code+criteria, not a stale one).
- `notes/greenfield-first-change-blockers.md` finding #3 (the rebase-and-re-tag sequence).

## Deliverables (pending the design confirmation above)
- `.claude/tools/accept.py` — freshness accepts a pinned SHA whose commit is no longer in history
  **iff** a live commit with a **byte-identical tracked tree** (code + criteria at the verdict's
  claimed state) exists at/reachable-from HEAD. I.e. anchor freshness to *tree identity of the
  attested state*, not to *commit identity*, so a rebase that preserves the tree preserves the
  verdict. A tree that actually changed still fails.
- `.claude/tools/test_accept.py` — cases: pin to a commit, rebase the branch (new SHAs, same
  tree) → freshness still PASSES; pin, then amend the code → freshness FAILS; pin, then rebase +
  change criteria → FAILS.
- **Process note (docs, not code):** record in `/implement` / the operator rules that canon fixes
  SHOULD NOT be applied to a change mid-flight where avoidable; if unavoidable, tree-identity
  freshness makes the single re-pin unnecessary.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green with the rebase-preserves / tree-changed cases.
- Replay: pin a verdict, `git rebase` the change branch onto an updated base (tree unchanged),
  run `accept.py <ctx>/NNN` → freshness PASSES with no re-pin.

## Out of scope / Escalate if
- Do NOT let a changed tracked tree pass freshness under any rebase story — the whole point of the
  pin is that the verdict attests to the exact code+criteria. Tree-identity is the safe relaxation;
  commit-identity is the accidental strictness.
- If the spec's freshness guarantee is defined in terms of commit reachability for a reason this
  task misses, escalate to the human — this is a canon question, not a mechanical fix.
