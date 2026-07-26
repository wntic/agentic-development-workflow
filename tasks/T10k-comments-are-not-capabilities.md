# T10k — the last reader that treats HTML comments as content, and the helper three tools now share

## Goal
Two small, related pieces of the "a comment is not content" thread that T10j opened and T10i
continued. Both are in `accept.py`'s overview parsing, which is the one reader still on raw text.

**1. `_overview_capability_tokens` reads comments as capability names.** `accept.py:332-339` takes
`_section(overview, "Capabilities")` and runs
`` re.findall(r"`?([A-Za-z0-9_.\-]+\.md)`?", body) `` over the **raw** body. Measured:

```
comment line  <!-- see `foo.md` for the shape -->   →  ['foo.md']
```

So a comment inside `## Capabilities` that happens to name a backticked `*.md` becomes a capability
token. That matters more than a lint nit because the same function feeds `_overview_capabilities` →
`resolve_targets` → the **capability-birth** path: a comment could name the file an acceptance
*creates*, or produce a false "names X more than once" finding.

**Scope correction, verified — do not chase the wrong half.** T10i's finding 5 also claimed the
template placeholder `` `<capability>.md` `` matches as the token `capability.md`. It does **not**:
`<` and `>` are outside the character class, so the whole token fails to match and the template's
`## Capabilities` section yields `[]`. Confirmed by running the real regex against
`.claude/templates/overview.md`. The defect is the comment case only, and it is **latent** — nothing
in the shipped template triggers it. Fix it because the birth path is downstream, not because it is
firing today.

**2. `criteria_lint._strip_html_comments` is underscore-private with three external call sites.**
`gate.py` (two: the criteria check, and T10j's capability-provenance check) and `accept.py`'s
`_spec_lint` (T10i) all reach into it. T10j's finding 5 predicted this coupling would grow, and it
has. Nothing enforces that the underscore stays put, and it is now load-bearing for two tools and
three checks.

## Depends on
T10j (the gate-side fix and the rule), T10i (the spec-lint side and the third call site), T10f
(`_overview_capability_tokens`'s repeats-preserving contract — do not break it).

## Read first
- `.claude/tools/accept.py` — `_overview_capability_tokens` (**note its docstring contract: in order,
  WITH repeats**, because T10f's F-03 duplicate-capability check depends on repeats surviving),
  `_overview_capabilities`, and `resolve_targets`'s birth path.
- `.claude/tools/criteria_lint.py` — `_strip_html_comments`, and whether anything inside
  `criteria_lint` itself depends on the private name.
- `.claude/tools/gate.py` — its two call sites; `.claude/templates/overview.md` — what the shipped
  template actually contains in that section (it is clean; keep it that way).
- `PRINCIPLES.md` C7 (one home for a derivation) — the reason this is a rename and not a copy.

## Deliverables
- `.claude/tools/accept.py` — `_overview_capability_tokens` strips HTML comments before the regex,
  through the shared helper. **Preserve order and repeats** — the duplicate-capability check reads
  them.
- **Promote the helper to a public name** in `criteria_lint` (e.g. `strip_html_comments`), update all
  four call sites (two in `gate.py`, one in `accept.py`'s `_spec_lint`, the new one), and keep a
  private alias only if something inside `criteria_lint` needs it. One home, one name (C7).
- Tests: a `## Capabilities` section whose **comment** names a backticked `*.md` yields no token, while
  a real listed capability still does; a capability listed twice in real content is still reported
  twice (the T10f contract); and the birth path is unaffected for a clean overview.

## Verification
- `uv run pytest .claude/tools` green.
- The comment case demonstrably differs against pre-fix `accept.py` — today it returns the phantom
  token; assert on the token list, not just on a status.
- **The birth path still works:** a capability-birthing change still resolves its target from
  `overview.md`'s real Capabilities list. This is the regression that would hurt — `users/002`'s
  acceptance depends on it (`accept.py` derives the birth capability from that list).
- `users/002` reproduces unchanged: detached worktree at `a931ee6`, `GATE_DOCKER=0` → `ACCEPTABLE`,
  `[PASS] spec.lint`, `[PASS] merge.placement — single-target Affects (user-management.md)`.

## Out of scope / Escalate if
- Do NOT change what `_overview_capability_tokens` returns for real content — the repeats contract is
  T10f's and the duplicate check depends on it.
- Do NOT touch `.claude/templates/overview.md`. It is clean; the fix belongs in the reader, exactly as
  T10j ruled for the capability template (fixing the document hides the class of defect).
- Do NOT widen this into a general Markdown parser. Comment stripping is the whole scope.
- **Escalate if** promoting the helper turns out to need a signature change that ripples into
  `criteria_lint`'s own callers — then the rename is a separate, larger piece of work and this task
  should ship the `accept.py` fix alone, saying so.
