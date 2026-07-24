# T09e — The cycle agents commit their own work (take the orchestrator off the critical path)

## Goal
Make `/implement` self-sufficient through to an acceptance-ready branch. Today the cycle
subagents produce files but commit nothing: the **implementer** left `src/**` uncommitted and
the **evaluator** left `criteria.md`/`verdict.md` uncommitted, so the human/orchestrator had to
drive every commit and re-pin by hand via `SendMessage` resumes. On `/implement platform/001`
this turned the evaluator into a **5-segment, 116-minute** span over **8m21s** of actual
work — ~108 minutes of idle waiting on orchestrator messages — and the last resume ended in a
user-rejected tool call. The commits are mechanical and their correct order is known; the agents
should just do them.

## Depends on
T09 (the cycle agents + `/implement`), T09e's write path is easier once **T06d** lands (a
first-class owned-tree write path), but the commits go through `git` via Bash and do not strictly
block on it.

## Read first
- `.claude/agents/implementer.md`, `.claude/agents/evaluator.md` — the two defs to amend.
- `.claude/commands/implement.md` — the step 2 / step 3 dispatch prose that must instruct the commit.
- `.claude/tools/accept.py` — the **L-04 freshness** logic and how `changed_since` treats the
  `verdict.md` commit (it excludes the verdict.md-only commit itself, so verdict behind HEAD by
  only verdict.md is still fresh). The commit ORDER below exists to satisfy exactly this.
- `notes/greenfield-first-change-blockers.md` finding #1 (the canonical commit order).

## Deliverables
- `.claude/agents/implementer.md` — on a GREEN gate, the implementer commits `src/**` (and its
  Alembic revision) as the code commit, then reports the SHA. It does not touch specs/tests.
- `.claude/agents/evaluator.md` + `.claude/commands/implement.md` step 3 — the evaluator, after
  flipping criteria and writing verdict, commits in the freshness-correct order:
  **(1) code already committed by the implementer → (2) commit the `criteria.md` flip alone →
  (3) run the gate at that HEAD, pin THAT sha into `verdict.md` → (4) commit `verdict.md` LAST as
  pure metadata.** Report the three SHAs. This is exactly the sequence the orchestrator had to
  dictate by hand across resumes 1–3 of the platform/001 run.
- The `/implement` orchestration prose no longer instructs the human to commit anything mid-cycle;
  a completed `/implement` leaves the branch acceptance-ready (`accept.py` passes freshness with
  no manual re-pin).

## Verification
- Re-run `/implement` on a fresh throwaway change (or replay the platform/001 shape): at the end,
  `git status` is clean, `git log` shows code → criteria → verdict commits in order, and
  `uv run .claude/tools/accept.py <ctx>/NNN` passes its freshness gate (L-04) with **zero**
  orchestrator `SendMessage` resumes for commits.
- `uv run .claude/tools/gate.py --change <ctx>/NNN --criteria` GREEN at the pinned verdict SHA.

## Out of scope / Escalate if
- Do NOT let the implementer or evaluator commit outside its owned tree (D4 ownership stands).
- Do NOT change the freshness semantics of `accept.py` here — this task conforms the agents TO
  the existing L-04 rule. Any freshness change is T10d.
- If the SubagentStop implementer-hold (T06c) interferes with the implementer committing after
  green, record it and escalate — the hold should release on green, not block the code commit.
