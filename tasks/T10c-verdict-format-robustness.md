# T10c — accept.py must not silently deny a verdict on pure formatting

## Goal
Stop `accept.py` from rejecting a substantively-correct verdict over cosmetic template drift.
On `/implement platform/001` the evaluator wrote a correct verdict but `accept.py` DENIED it
twice on formatting, costing a whole orchestrator resume to fix:
- **`verdict.freshness` FAIL** — the SHA line was `` - Gate SHA: `246f84…` `` and the backtick
  between `SHA:` and the hex broke the regex `SHA:\s*([0-9a-fA-F]{7,40})` (accept.py:526), so it
  reported "carries no 'SHA: <sha>' line".
- **`adversarial.presence` FAIL** — the section was titled `## Adversarial pass`; accept.py wants
  exactly `## Adversarial review` (accept.py:419). The `/implement` §4 prose says "adversarial
  **pass**", which is what misled the evaluator into the wrong heading.

Two coordinated fixes: make the parser tolerant, and remove the wording that misleads the author.

## Depends on
T10 (accept.py), T09 (the evaluator + `/implement` prose that must agree with the template).

## Read first
- `.claude/tools/accept.py` — the `SHA:` regex (~line 526) and the `## Adversarial review`
  presence check (~line 419).
- `.claude/templates/verdict.md` — the authoritative format the evaluator should reproduce.
- `.claude/commands/implement.md` §4 — the "adversarial pass" wording.
- `.claude/agents/evaluator.md` — whether it is handed / told to read the verdict template.
- `notes/greenfield-first-change-blockers.md` finding #2.

## Deliverables
- `.claude/tools/accept.py` — tolerant parsing on both checks:
  - SHA: match the first bare 7–40 hex run after a `SHA:` token even if wrapped in backticks or
    other markdown (e.g. `SHA:\s*` + optional `` ` `` + hex). Still require the hex to be a real
    commit; keep the freshness semantics unchanged.
  - Adversarial heading: accept `## Adversarial review` **or** `## Adversarial pass` (case-
    insensitive), so an author-side wording slip is not a silent deny.
- `.claude/commands/implement.md` §4 — rename the step to "**Adversarial review**" (matching the
  template + accept.py) so the author is pointed at the canonical heading.
- `.claude/agents/evaluator.md` — instruct the evaluator to reproduce `.claude/templates/verdict.md`
  (read it, or receive it), so the SHA line and headings come out canonical the first time.
- `.claude/tools/test_accept.py` — cases: SHA line with backticks around the hex → freshness
  reads the sha; heading `## Adversarial pass` → `adversarial.presence` passes; a verdict with no
  hex anywhere → still FAILs (no false accept).

## Verification
- `uv run pytest .claude/tools/test_accept.py` green with the tolerant cases + the still-fails case.
- Feed the exact platform/001 pre-fix verdict.md (backticked SHA + `## Adversarial pass`) to
  `accept.py` → both checks PASS.
- A verdict genuinely missing a SHA or an adversarial section still DENIES.

## Out of scope / Escalate if
- Do NOT loosen freshness itself (the sha must still resolve to a real, gate-GREEN commit) — this
  task only makes the parser tolerant to markdown around the hex, not to a wrong/absent sha.
- If tolerating both headings weakens a real signal (e.g. the template later distinguishes a
  "pass" from a "review"), escalate rather than guessing which one is canonical.
