# T10j — A successful `accept.py --execute` leaves the base branch RED (S9 violated)

## Goal
Accepting a capability-birthing change **breaks the base branch**. After a clean
`accept.py --execute` — merged, tagged, change dir deleted, `verdict: ACCEPTABLE` — `gate.py` on the
base is RED:

```
[FAIL] spec.invariant-tests — invariant references rotted (L-06):
       specs/health/service-health.md: (verified by: <test-id>) — test not found
```

The acceptance script is the one thing standing behind **S9 (`main` is always green)**, and it is
what turns the base red. Mechanism, verified end to end:

1. `accept.py`'s capability-birth path copies `.claude/templates/capability.md` **verbatim**,
   including its HTML comment, which contains the literal line
   `- <invariant> (verified by: <test-id>)` (`capability.md:16`).
2. `gate.py:808` runs `CAPABILITY_REF` (`:195`, `\(verified by:\s*([^)]+)\)`) over the file's **raw
   text**, so it reads `<test-id>` out of the comment as a real provenance reference and looks for a
   test by that name.
3. `lint._strip_html_comments` is already imported and used in `gate.py` — one function away, at
   `:755`, for the criteria check. The capability check simply does not call it.

Measured on the born file: `CAPABILITY_REF.findall(...)` → `['<test-id>', 'tests/integration/api/
health/test_health.py::test_get_health_returns_200_and_status_ok']`. One real invariant, one ghost.

**Why it survived to now:** no acceptance had ever been `--execute`d and *then gate-checked*. The
`users/002` acceptance in this repo was executed and reset before anyone ran `gate.py` on the merged
state, and the trial venue that finally exposed it (T16) did not exist. This is exactly the class of
defect T16 was stood up to catch, caught on its first use.

**Blast radius beyond the red base:** `subagent_stop` then holds the *next* change's implementer on a
RED that no `src/**` edit can clear — the T09f deadlock shape, arriving from a completely different
direction.

## Depends on
T10 (the acceptance script), T04 (`gate.py`), T16 (which found it, and whose venue reproduces it).

## Read first
- `notes/20_consumer_trial_venue.md` — T16's runbook and F-01, the finding this task closes.
- `.claude/tools/accept.py` — `instantiate_capability` (the birth path) and how it writes the file.
- `.claude/tools/gate.py` — `CAPABILITY_REF` (`:195`), `check_invariant_tests` (`:800-810`), and the
  **existing** use of `lint._strip_html_comments` at `:755`. The asymmetry between those two checks
  is the whole bug.
- `.claude/templates/capability.md` — the comment block, and what it is for (it instructs the human
  reading a freshly born file).
- `PRINCIPLES.md` S9, S4, A4.

## Deliverables
Two independent halves. **Do both** — either alone leaves a sharp edge:

- **`gate.py` must not read provenance out of HTML comments.** `check_invariant_tests` strips
  comments before matching, exactly as the criteria check already does. This is the real fix: a
  comment is not content, and *any* capability file may legitimately carry one.
- **`accept.py`'s birth path must not emit a placeholder that looks like data.** Decide and state
  which: strip the instructional comment when instantiating, or reword the template so its example
  cannot be mistaken for a reference (e.g. no parenthesised `verified by:` form inside the comment).
  Prefer stripping — the comment's audience is the author of the *template*, not the reader of a born
  file, and a born file that carries `<invariant>` placeholders reads as unfinished.
- Tests both sides: `test_gate.py` — a capability file whose comment contains a `(verified by: …)`
  line passes `spec.invariant-tests` while a genuinely rotted reference still FAILs;
  `test_accept.py` — a birth produces a file that `gate.py` accepts.

## Verification
- `uv run pytest .claude/tools/test_gate.py .claude/tools/test_accept.py` green; both new cases
  demonstrably fail against the pre-fix scripts.
- **The end-to-end proof, and this is the one that matters:** in a scratch repo (or the T16 venue on
  a throwaway branch), drive a capability-birthing change through `accept.py --execute` and then run
  `gate.py` on the base — **GREEN**. Today it is RED. A unit test alone does not discharge this task;
  the defect existed *because* nobody ran that sequence.
- `uv run pytest .claude/tools` — whole meta suite green.
- The T16 venue's `main` is repaired (see below) and `gate.py` there is GREEN.

## Out of scope / Escalate if
- Do NOT fix this by deleting the comment from `.claude/templates/capability.md` alone. That hides
  today's instance and leaves `gate.py` still parsing comments as data — the next template edit, or
  any human comment in a capability file, reproduces it.
- Do NOT weaken L-06. A genuinely rotted `(verified by: …)` must still FAIL; that check is what keeps
  provenance honest.
- **Repair the T16 venue** (`~/Projects/adw-consumer-probe`, `main` is RED on this and nothing else)
  as part of the task, so the venue is usable for the next trial. Do not simply hand-edit the file
  there and call the task done — repair it *with* the fix, as the end-to-end proof above.
- **Escalate if** stripping comments changes the result for any existing capability file in this
  repo or the venue beyond removing the ghost reference.
