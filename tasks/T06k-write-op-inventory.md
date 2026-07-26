# T06k — `cp`, `install`, `dd of=`, `truncate` are not in the guard's write-op inventory

## Goal
`bash_guard` recognises redirects and the mutators `rm` / `mv` / `tee` / `sed -i` /
`git checkout -- ` / `git restore`. It does **not** recognise `cp`, `install`, `dd of=…` or
`truncate`. So this is a **miss** today, for any role:

```
cp /tmp/evil.py .claude/tools/gate.py     → ALLOWED
```

Found while building T06i (its finding 6), which correctly left it alone: the write-op inventory is
*policy* — which operations count as writing — while T06i's scope was the *parser*. With the
tokeniser now correct, adding an operation is a small, safe change; before it, it would have been
another guess.

**Severity is ergonomics, not trust** — say this plainly so nobody over-reacts. Under S8 the gate is
the backstop, and a `cp` over `gate.py` is caught post-hoc by `integrity.self-hash` (E-02) and, inside
a repo, by `integrity.protected-trees`. What the miss costs is the early, legible denial; what it does
**not** cost is the trust anchor. Prioritise accordingly.

## The trap that makes this a task rather than a one-liner
`mv`'s rule is "every non-flag argument is a target", because `mv a b` writes both ends in effect.
**Applying that rule to `cp` would recreate variant 6** — the exact defect T06i was built to remove:

```
cp .claude/tools/gate.py /tmp/backup.py    # reads a protected file, writes nothing protected
```

Under the `mv` rule that becomes a fresh false positive blaming a path the command only *reads*.
`cp`'s target is **the last non-flag argument only** (and with `-t <dir>`, the `-t` operand). The same
asymmetry applies to `install`. `dd` is different again — its target is the `of=` operand, not a
positional. `truncate` takes `-s` plus files.

## Depends on
T06i (the tokeniser — `_command_and_args` / `_mutator_targets` are where this lands, and they only
became trustworthy with it), T06, T06b, T06d.

## Read first
- `.claude/hooks/bash_guard.py` — `_mutator_targets` and `_command_and_args`; note how `rm`/`mv`/`tee`
  differ from `sed -i` and from the two `git` forms, and that command position is already resolved.
- `.claude/tools/test_enforcement.py` — the T06i section, especially `RECORDED_FALSE_POSITIVES`: any
  operation added here must not add a new entry to that list.
- `tasks/T06i-tokeniser-family-decision.md` — the seven-variant table. Read it before adding a rule;
  five of the seven were "a token that looked like a target".
- `PRINCIPLES.md` S8 — why a false positive costs more than a miss, which is exactly why the
  last-argument rule matters more than the coverage.

## Deliverables
- `.claude/hooks/bash_guard.py` — add to the write-op inventory, each with its *own* argument rule:
  - `cp` / `install` → **the last non-flag argument only**; with `-t <dir>` / `--target-directory`,
    that operand instead;
  - `dd` → the `of=<path>` operand only (never a positional; `if=` is a read);
  - `truncate` → the file operands (`-s` takes a size, not a path).
  Keep every T06i property: masking, command position, the first-component-expansion rule.
- `.claude/tools/test_enforcement.py` — for **each** added operation, a pair: the write direction
  denies for a non-owner, and the **read** direction (`cp <protected> /tmp/x`, `dd if=<protected>`)
  **allows**. The read-direction cases are the point of this task; without them it is variant 6 again.
- Decide and state whether anything else belongs (`ln -sf`? `git mv`? a shell builtin like
  `printf ... >` — already covered as a redirect). Prefer a short justified list over a long guessed
  one; an operation nobody has actually used against a protected tree is a guess.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green — every pre-existing case **unmodified**
  (T06i's standard: `git diff … | grep -c "^-[^-]"` → 0 for the test file).
- All twelve recorded false positives (seven filed + the five T06i measured) still allow — run the
  `RECORDED_FALSE_POSITIVES` pins, they exist for this.
- `cp /tmp/x .claude/tools/gate.py` (non-owner) → **denies**; `cp .claude/tools/gate.py /tmp/x` →
  **allows**. Both, or the task is not done.
- `uv run pytest .claude/tools` green.

## Out of scope / Escalate if
- Do NOT change the tokeniser. T06i just landed; this adds entries to an inventory it already parses.
- Do NOT add operations speculatively. Each one costs a potential false positive, and the family's
  whole history is false positives.
- **Escalate if** an operation cannot be given a target rule that is right in both directions — that
  means the guard would have to understand the command's semantics, and a miss (S8: the gate
  backstops) is then strictly better than a guess.
