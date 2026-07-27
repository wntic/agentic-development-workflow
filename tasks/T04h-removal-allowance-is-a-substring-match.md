# T04h — the legal-removal allowance is a raw substring match over the whole `change.md`

## Goal
`gate.py`'s test-inventory check lets a removal-flavour change delete a baseline test, and it decides
what is allowed like this (`gate.py:1322`):

```python
if node_id in allowed_removals_text:
```

`allowed_removals_text` is the baseline `change.md` blobs **concatenated raw** — HTML comments and all.
So any node-id appearing *anywhere* in that document grants the allowance, including one that appears
only inside an instruction comment.

This is the **third** instance of "a comment is not content", and the worst-directed one:

- T10j — `gate.py`'s L-06 read `(verified by: <test-id>)` out of a template comment. Fixed there,
  **one function away from this one**, using `criteria_lint._strip_html_comments`.
- T10i / T10k — `accept.py`'s `_spec_lint` (fixed) and `_overview_capability_tokens` (T10k, open).
- **Here** — and unlike those, this one *widens a permission*: a comment could silently authorise
  deleting a baseline test for **every** change that keeps the template's comment, which is every
  change. That is the fail-open direction the whole `notes/19` register is about.

**Nothing is open today, and the reason matters.** T03c's builder found this while shipping the
`## Removed` skeleton and deliberately wrote the template's placeholders as
`tests/<file>.py::<test_name>` — non-node-ids — so no real node-id lives in a comment. The mechanism
is intact and the next template edit re-opens it. Fix the reader, not the document (T10j's ruling).

**Second half of the same finding, and it wants a ruling.** Because the match is substring-anywhere,
**`## Removed` is a convention, not an enforced location** — a node-id listed under any heading, or in
prose, grants the allowance just as well. T03c's template comment states this truthfully rather than
claiming more. Decide whether the allowance should be *scoped to the `## Removed` section* now that
the section exists and is parsed (`classify_removal` already returns its body). Scoping it would make
the section load-bearing for both readers instead of only for the sweep — but it is a **behaviour
narrowing**, so a change that legally listed removals elsewhere would start failing.

## Depends on
T10j (the fix pattern and the ruling that the *reader* is what changes), T03c (which found it, pinned
the vocabulary, and made `classify_removal` return a same-or-shallower-terminated section body),
T04 (the inventory check), T10k (the sibling still-open reader — share one helper, C7).

## Read first
- `.claude/tools/gate.py` — `inventory_violations()` (`~:1300-1325`) and `check_test_inventory`, which
  concatenates the baseline `change.md` blobs. Note `_strip_html_comments` is **already imported** in
  this file for two other checks; this is a third call site, not new machinery.
- `.claude/tools/accept.py` — `classify_removal()` / `RemovalFlavour.sections` after T03c: the
  already-parsed `## Removed` body, if the scoping half is chosen.
- `.claude/templates/change.md` — T03c's `## Removed` skeleton and its deliberately non-node-id
  placeholders, i.e. why this is latent rather than live.
- `notes/19_accept_gate_audit.md` — the root-cause section, so this is read as the family it belongs to.
- `PRINCIPLES.md` S4, C7, D4 (the allowance exists because a removal change's test-author owns
  deleting obsolete tests — do not break that).

## Deliverables
- **The strip, unconditionally.** `inventory_violations` (or its caller) matches against
  comment-stripped text, through the same helper the other two checks use. If T10k has promoted it to
  a public name by then, use that name; if not, this task may promote it — but only one of the two
  should, so say which you did.
- **The scoping half: decide, implement or decline with a reason.** Either keep substring-anywhere and
  state in the code why (the allowance is about *intent recorded in the frozen change.md*, and E-12
  freezes the whole document, so location adds little), or scope it to the `## Removed` body and accept
  the narrowing. Recommended: **strip first, and scope only if you can show a real hole** — the
  document is frozen at baseline, so an author cannot widen the allowance after the fact, which is
  most of what location would buy.
- Tests in `.claude/tools/test_gate.py`: a node-id present **only** in an HTML comment does **not**
  grant the allowance (the load-bearing case); a node-id in real content still does; and, if scoped,
  a node-id outside the `## Removed` section no longer does.

## Verification
- `uv run pytest .claude/tools` green.
- The comment case demonstrably differs against pre-fix `gate.py` — plant a real node-id in a
  `change.md` comment, delete that baseline test, and show the pre-fix run PASSing
  `integrity.test-inventory` and the post-fix run FAILing it. Without that pair the fix is unproven.
- **A legitimate removal still works:** a `Class: behavioral, REMOVED` change whose `## Removed`
  section lists a node-id may still delete that baseline test. This is the regression that would hurt —
  breaking it means a removal change can never pass the inventory check again.
- `users/002` reproduces unchanged (INDEX's recipe; it removes nothing, so the allowance is empty).

## Out of scope / Escalate if
- Do NOT edit `.claude/templates/change.md` to dodge this. T10j ruled that fixing the document hides
  the class; T03c's placeholders are already safe, and the point is that the reader must be correct.
- Do NOT weaken the inventory check itself. A missing baseline test with **no** allowance must stay a
  FAIL — that is E-05, and it is what makes a silently dropped test impossible.
- **Escalate if** the scoping half turns out to break a real recorded removal (check `git log` for any
  accepted `REMOVED` change before assuming there is none). Then the narrowing needs a migration story
  and is its own task.
