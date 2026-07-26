# T04g — the repo lints its own tooling more loosely than the gate lints the app

## Goal
T04f corrected a claim in my own filing and the correction is the point of this task. "Nothing lints
`.claude/tools` today" is imprecise: `.pre-commit-config.yaml` **does** run `ruff-check --fix` +
`ruff-format` on changed files — but with `pyproject.toml`'s config, which sets only `line-length`
and `target-version` and **no `select`**. So ruff's default `E4,E7,E9,F` applies.

The workflow therefore holds the app it builds to `E,W,F,I,N,UP,B,C4,SIM,RUF` (the gate's pinned
`RUFF_SELECT`) while holding **its own enforcement layer** to a rule set several times narrower. That
is why `RUF103` and `RUF100` sat in `gate.py` — the gate's own file — until T04f removed them.

**The finding that makes this worth doing rather than filing as hygiene:** among the 21 remaining
findings T04f measured is

```
accept.py:~1357  RUF059  Unpacked variable `rc` is never used
```

**Ruff finds a discarded git return code, unaided.** That is precisely the defect class the whole
`notes/19` register is about — seven fail-open paths, one root cause, "a helper that cannot determine
its input returns an empty value and the gate reads empty as nothing-wrong" — and one of its instances
is sitting in a linter's output that nobody runs. The register cost a full audit dispatch to write;
the linter would have pointed at part of it for free.

Measured inventory (T04f, deliberately untouched by it since widening scope was forbidden):
`accept.py` 11 · `red_check.py` 2 · `hooks/bash_guard.py` 1 (`RUF005`) ·
`hooks/criteria_guard.py` 1 (`B905`, `zip` without `strict=`) · test files 6.

## Depends on
T04 (`RUFF_SELECT` lives in `gate.py` and is the single definition of the toolchain — cite it, never
restate it, C7), T04f (which measured the inventory and fixed `gate.py`'s own two).

## Read first
- `.claude/tools/gate.py` — `RUFF_SELECT` and `ruff_common()`; **reuse them**, do not write a second
  select list anywhere.
- `.pre-commit-config.yaml` and `pyproject.toml`'s `[tool.ruff]` — the current, narrower reality.
- `tasks/T04f-*.md` and the T04f report — the measured 21, and which sites are *deliberate* loud
  degradations rather than defects (`rev-parse HEAD` → `sha: "UNKNOWN"`; `status --porcelain` → the
  human-facing `dirty` flag). Do not "fix" those into silence.
- `notes/19_accept_gate_audit.md` — the root-cause section, so the `RUF059` hit is read as evidence
  rather than as a style nit.
- `PRINCIPLES.md` C7, A4.

## Deliverables
- **Decide the scope and say it plainly:** does the enforcement layer hold itself to the gate's own
  `RUFF_SELECT`? The honest default is **yes** — a workflow that imposes a standard on its consumers'
  code and exempts its own tooling is the A4 shape (the check does not exercise its own subject).
  If some rule is genuinely wrong for stdlib-only tools, name it and carve it out **explicitly**,
  with the reason inline.
- Clear the 21, one commit per file or per rule family so the diff stays reviewable. `RUF002`
  (en-dash) and `E501` are cosmetic; `RUF059`, `B905` and the four `RUF100`s are substantive — treat
  the `RUF059` hit as a **bug report** and check whether that discarded `rc` is a real fail-open
  before silencing it. Same for `B905`: `zip` without `strict=` silently truncates, which in
  `criteria_guard` means comparing mismatched line lists.
- **Make it stick, or it will not** (S4): either extend `pyproject.toml`'s `[tool.ruff.lint] select`
  to the gate's set so pre-commit enforces it, or add a `.claude/tools/` test that runs the gate's
  own select over `.claude/**` and FAILs on findings. Prefer the pre-commit route if it can cite
  `gate.py`'s list rather than duplicating it; if it cannot, the test is the better home (a
  duplicated select list is exactly the drift C7 forbids, and this whole task exists because two
  configs disagreed).

## Verification
- `uv run pytest .claude/tools` green.
- `uv run python -m ruff check --isolated --select "E,W,F,I,N,UP,B,C4,SIM,RUF" --line-length 120
  --target-version py312 .claude/tools/ .claude/hooks/ .claude/bin/` → **clean** (or clean modulo the
  carve-outs you named, each with its reason in the file).
- The enforcing mechanism demonstrably fails on a planted finding, then passes when it is removed.
  Without that, the rule is prose.
- `uv run .claude/tools/gate.py` GREEN in this repo, and `users/002` still reproduces (detached
  worktree at `a931ee6`, `GATE_DOCKER=0`, → `ACCEPTABLE`).

## Out of scope / Escalate if
- Do NOT change `RUFF_SELECT` itself. It is the app's contract; this task is about applying it to
  ourselves, not about editing it.
- Do NOT silence a finding you have not understood. `RUF059` and `B905` are the two that may be real
  defects; a `noqa` on either without a stated reason is the opposite of this task's point.
- **Escalate if** honouring the full select requires restructuring a tool (e.g. a `SIM` rule
  demanding a rewrite of a load-bearing function). A carve-out with a reason beats a risky refactor
  inside a lint task — the enforcement scripts are the trust anchors, and churn in them is not free.
