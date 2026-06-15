---
description: "§9 — author the deferred manual-stub asserts in a separate anti-collusion context and adversarially verify them, closing the canonical-test review tail (spec §9, PRINCIPLES D3)"
argument-hint: "<output-dir>  |  <manifest> <output-dir>"
---

The canonical behavioural test is the **unit of trust** (spec §9). The scaffolder authors the **flat**
tests complete-and-red; the harder **manual** stubs (`test_*_manual.py` — relational / time / negative /
multi-dependency / `calls` / `logs` scenarios) are left as `@pytest.mark.skip` functions carrying a
`# CONTRACT —` comment, their asserts **deferred** (implementer.md Out-of-scope). This command closes
that tail: it authors each manual assert **from the contract**, in a context **separate from the body
author** (anti-collusion), runs it against the filled body, and **adversarially verifies** it.

**You orchestrate; you do NOT author the asserts yourself.** If you have seen any body in this session,
authoring its test would be the exact co-adaptation §9 forbids. Every assert is written by a **fresh
subagent** whose only inputs are the contract, the test skill, and the in-memory fakes — never the
implementation under test. Anti-collusion is the whole point (PRINCIPLES D3).

`$ARGUMENTS`: the generated package root (e.g. `examples/generated/helpdesk4`), optionally preceded by
the manifest. The manifest (if given) maps each node's kind → its test skill via `conventions` block B.

## 1. Discover the manual stubs

Glob `<output>/tests/**/test_*_manual.py`. Each holds one or more `@pytest.mark.skip` functions with a
`# CONTRACT —` comment (the `behaviour` `given`/`then` + `notes` the scaffolder distilled). List the
files and, per file, the node + the test skill it maps to (`conventions` block B —
`test-application-handler` for handlers, `test-domain-service` for services, …).

## 2. Author pass — one fresh context per stub FILE (anti-collusion)

For each manual-stub file, dispatch a **fresh** author subagent (the test-author is the scaffolder
role — it authors tests from the contract and, by its own rule, never reads a body or an existing
assert). Its prompt carries **only**:

- the stub file path and the **test skill** for its node (read that skill's *Template(s)* + *Rules* —
  AAA blocks, `pytest.raises(<DomainError>) as exc` + `exc.value.context[...]`, read state back via the
  fake's domain methods, inline `_Raise*` repos for failure injection, the `then.with` post-state) **and
  its Assert-strength recipes** (`test-application-handler`'s "Assert strength" section): pin PERSISTED
  state via the fake's `updated` log + read-back (not the mutated entity), test a drop/skip with a
  SURVIVOR present (never an empty set), exercise a non-boundary tier, distinguish `total` from
  `len(items)` with page<matches, use ≥2 rows to prove scoping, and assert NO side effect on a reject
  path. Write the assert STRONG the first time so the adversarial pass has nothing to flag;
- the in-memory **fakes** under `<output>/tests/unit/fakes/` it may use;
- instruction: replace each skipped function's `pass` with the real assert **derived from that
  function's `# CONTRACT —` comment**, drop the `@pytest.mark.skip`, keep the signature, delete the
  stale "implementer fills the assertion" framing.
- **HARD anti-collusion:** do **not** open the implementation under test (the handler / service /
  repository / adapter body), and do not infer the assert from anything but the contract + skill + fakes.
  Construct the handler under test from the **ctor signature carried in the stub's `# CONTRACT —`
  comment** (the scaffolder records it there precisely so you stay body-blind) — never read the body to
  discover its `__init__` parameter names (the F-020 leak). If the ctor signature is absent from the
  contract, **stop and flag it** (a scaffolder gap), do not peek.
- **Missing fake →** stop and flag it (a `test-fake-repository` gap — a fake the scenario needs that
  isn't in `tests/unit/fakes/`); do not improvise the production body or a half-fake. Author the missing
  fake first (a fresh `test-fake-repository` dispatch — also body-blind), then resume.

Then **run** the authored file from the package root: `uv run pytest <file>` (+ `mypy`/`ruff` on it).
- **green** → the body conforms to the contract as an independent reader understood it → record it.
- **red** → a genuine **divergence** between the body and the contract-as-independently-read. Do **NOT**
  auto-fix either side. Escalate to the human with the failing assert + the contract — this is precisely
  the §9 signal anti-collusion exists to surface (one of body / test is wrong about intent; a colluding
  author would have hidden it).

## 3. Adversarial verify pass — one fresh context per authored file

For each authored, green file, dispatch a **fresh** adversarial verifier (it produces no artifact — a
review context). Its inputs: the authored test + the `# CONTRACT —` comment; **not** the body. Task: try
to **refute** each assert — would a plausibly-wrong body still pass it? Run the `test-application-handler`
"Assert strength" recipes as the named refutation checklist: does it assert on the in-memory entity
instead of the persisted write (a mutate-but-never-persist passes)? does it test a drop/skip on an EMPTY
set (a drop-everything body passes)? boundary-only (the wrong limit/tier passes)? `total` provable from
`len(items)`? a single row where scoping needs two? a constant-satisfiable echoed field? a reject path
that asserts the exception but not the absence of side effects? Plus the generic refutations: a no-op
"re-save unchanged", a swapped/again field, a missing state transition, a dummy returning the happy
value, an exception caught-and-swallowed. Report each assert as **strong** (a wrong body would fail it)
or **weak** (passes but does not pin the contract). A weak assert is **re-authored** (back to step 2's
author context to strengthen it, applying the matching recipe) or, if it cannot be tightened at unit
level, **flagged** into the residual review surface.

## 4. Report + the residual surface

Per file: asserts authored · `pytest` green / **diverged (escalated)** · adversarial verdict (strong /
weak + why) · any fake authored. Then state the **residual human-review surface** — whatever stays
flagged (a real divergence, or an irreducibly-weak assert). §9's point is not zero review; it is that
this surface is **small and explicit** (a named queue), not a blanket `skip`. A node that went green +
strong is now genuinely gated, not just "looks right."

## Notes

- This is the post-hoc closure for an already-filled tree; the eventual home is the scaffolder authoring
  manual asserts complete-and-red at scaffold time (like flat), but the **separate-context** discipline
  is identical either way — the author is never the body author.
- The four roles hold (PRINCIPLES D1): the author is the scaffolder role (test authoring, §3); the
  adversarial verifier is a §9-named review pass, producing no app artifact. Neither is a per-component
  persona.
- A re-run is safe: a file whose asserts are already authored (no `@pytest.mark.skip`) is skipped by
  step 1's discovery.
