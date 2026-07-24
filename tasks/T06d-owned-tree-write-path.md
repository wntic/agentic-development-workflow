# T06d — Give cycle subagents a sanctioned write path to their OWNED tree

## Goal
Close the deadlock that cost the two "protected-tree" agents a bypass on every `/implement`
run: they have **no Write/Edit tool at all**, and `bash_guard.py` denies the shell fallback for
exactly the trees they own. The implementer (writes `src/**`, which the guard does not protect)
sailed through with 0 blockers; the test-author (`tests/**`) and the evaluator
(`criteria.md`/`verdict.md`) each had to bypass the hook via a scratchpad python-helper. The
owner cannot write what it owns — pure ergonomics friction that also drills the S8-forbidden
bypass reflex.

**Observed on `/implement platform/001`:** test-author `Write` → *"Write exists but is not
enabled in this context"*; `ToolSearch select:Write,Edit` → *"No matching deferred tools"*;
`cat > tests/...` → DENIED `shell write to a protected path (tests/)`. Same sequence for the
evaluator against `criteria.md` (`specs/`).

**Root-cause hypothesis to confirm first:** the agent defs use **path-scoped**
`disallowedTools` (test-author disallows `Write(src/**)`, `Write(**/criteria.md)`,
`Write(**/verdict.md)` but NOT `Write(tests/**)`), so Write *should* remain available for the
owned tree. It did not — Write was absent entirely. Determine whether a path-scoped `Write(...)`
disallow entry drops the Write tool wholesale in a subagent context; the fix depends on the
answer.

## Depends on
T06 (bash_guard), T09 (the cycle agent defs).

## Read first
- `.claude/agents/test-author.md`, `.claude/agents/evaluator.md`, `.claude/agents/implementer.md`
  — the path-scoped `disallowedTools` lists.
- `.claude/hooks/bash_guard.py` — `PROTECTED_FRAGMENTS` (protects everything but `src/`) and the
  docstring's S8 "ergonomics, the gate backstops" framing.
- `notes/greenfield-first-change-blockers.md` — the recurring meta-finding (sharpened
  2026-07-24: "the guard blocks exactly the owners").
- The agent-report bundle transcript excerpts if still present under
  `~/.claude/projects/.../agent-reports/BUNDLE-implement-platform-001/` (the two deadlock traces).

## Deliverables
Pick whichever of the two the root-cause confirms — one must land, both are acceptable together:
- **(A) Tool provisioning** — restore Write/Edit to the cycle agents scoped to their owned tree
  (test-author→`tests/**` + `pyproject.toml`/`uv.lock`; evaluator→`**/criteria.md` +
  `**/verdict.md`), so the first-class path works and the Bash fallback is never needed. If
  path-scoped `disallowedTools` cannot keep Write for the non-matching paths, record the harness
  constraint and fall to (B).
- **(B) Role-aware `bash_guard.py`** — the guard reads the stopping/acting role (payload
  `agent_type` where available, or the branch/cycle context) and does NOT deny a shell write when
  the target is the acting role's OWNED tree (test-author→`tests/`, evaluator→`criteria.md`/
  `verdict.md`/`specs/<ctx>` prose it is allowed to flip). Everyone else stays denied. Keep the
  precision bias (T06b): a write to a NON-owned protected tree still fires.
- `.claude/tools/test_enforcement.py` (or the guard's own tests) — cases: test-author writes
  `tests/foo.py` → allowed; test-author writes `src/foo.py` → denied; evaluator writes
  `criteria.md`/`verdict.md` → allowed; evaluator writes `tests/foo.py` → denied; implementer
  writes `src/` → allowed (unchanged), writes `tests/` → denied (unchanged).

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green with the new role/owned-tree cases.
- Re-dispatch the test-author (or a simulated payload) against an empty `tests/` tree: it creates
  its file through a sanctioned path with **no denial and no scratchpad workaround** in the trace.
- `uv run .claude/tools/gate.py` still catches a bypass: writing a foreign tree via Bash is still
  denied, and the post-hoc baseline diff (S8) is unchanged.

## Out of scope / Escalate if
- Do NOT weaken the gate's integrity checks (S8) — this is ergonomics only; the gate still diffs
  every protected tree against the baseline. The owner-write allowance must not let an agent
  mutate a tree it does not own.
- If restoring Write per path is impossible AND a role-aware guard cannot reliably identify the
  acting role from the Bash PreToolUse payload, escalate — do not fall back to "let the agent
  bypass via scratchpad" as the documented sanctioned path.
