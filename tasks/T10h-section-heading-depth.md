# T10h — `_section` only sees `## `, so a `### ` heading silently skips the adversarial pass

## Goal
`accept.py`'s `_section()` (line ~166) recognises a section only when a line
`.strip().lower().startswith("## ")`. A `### Interface sketch` heading therefore matches **nothing**,
the section comes back empty, `_has_real_content()` is false, and the change is classified **S
depth** — so `adversarial.presence` PASSes with *"adversarial pass not required — S depth on an
existing capability"* for a change that is actually M or L.

That is a fail-open in the same family as T10f's F-02, and it is the half F-02 did **not** cover:
F-02 fixed the *capability-birth* path, this is the *existing-capability* path. Found by the T10f
builder (its finding 8) and deliberately left, because it also touches `verdict.md`'s parse.

`_section` has **six call sites** (`accept.py:318, 670, 672, 685, 1171` + the definition), so the
blast radius is wider than depth detection alone: overview's `Capabilities` list, the verdict's
sections, and `Acceptance criteria` all read through it. The AC path is currently backstopped by
T10f's F-04 fix (zero ACs now FAIL instead of passing vacuously) — but that is a backstop, not a
reason to leave the parse wrong.

## Depends on
T10f (the undetermined-input rule and the `GATES` registry — the fix must obey both).

## Read first
- `.claude/tools/accept.py` — `_section()` and **all six** call sites; `_has_real_content()`; the
  depth classification at `:670-672`; the verdict-section parse at `:685`.
- `notes/19_accept_gate_audit.md` — the parse-anchoring table (Question 2). This is the same defect
  class it inventories: a parse that is *nearly* structural.
- `.claude/templates/change.md` and `.claude/templates/verdict.md` — what heading depth the templates
  actually emit, which decides whether this is a latent bug or a live one.
- `tasks/T10e-orphan-sweep-classifier.md` — the sibling lesson: a heading regex that was too loose.
  This one is too strict. Both come from grepping prose shapes by hand.

## Deliverables
- `.claude/tools/accept.py` — `_section()` matches a heading at **any depth** (`#+`), and terminates
  at the next heading of **the same or shallower** depth, so a `### Sub` inside a `## Section` stays
  part of that section instead of ending it. Naïvely matching any `#+` as a terminator would break
  nested content — that is the trap in this task.
- Decide and state: does a `### Interface sketch` under a `## Something` count as the Interface
  sketch? Recommended **yes** — the question the gate is asking is "did the author write one", not
  "at what depth". Whatever you choose, pin it in a test with a comment saying why.
- `.claude/tools/test_accept.py` — cases: `### Interface sketch` → the change reads as M depth and
  `adversarial.presence` is **required**; a `### ` subheading inside a `## ` section does not
  truncate it; the existing `## ` behaviour is unchanged for every current fixture.

## Verification
- `uv run pytest .claude/tools/test_accept.py` green, and each new case demonstrably fails against
  pre-fix `accept.py`.
- **The `users/002` baseline is unchanged** — detached worktree at `change/users-002` (`a931ee6`),
  `--base markdown-specs` (or bare, post-T10g), `GATE_DOCKER=0` → `verdict: ACCEPTABLE`, the same
  gate lines. That change uses `## ` headings throughout, so a correct fix cannot move it.
- `uv run pytest .claude/tools` — whole meta suite green.

## Out of scope / Escalate if
- Do NOT rewrite the templates to force `## `. That would make the *documents* obey the parser
  instead of the parser reading the documents, and it leaves every hand-written or
  differently-nested change.md still misclassified.
- Do NOT widen this into a Markdown parser. Heading depth is the whole scope.
- **Escalate if** changing the terminator rule moves any existing fixture's result. That would mean
  a current test encodes the buggy behaviour, and which side is right is then a canon question
  about the templates, not a parser detail.
