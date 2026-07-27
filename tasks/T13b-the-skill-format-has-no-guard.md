# T13b — the skill-format contract is prose, and the paid-fixes oracle guards its own format doc

## Goal
T13 wrote the progressive-disclosure contract and then applied S4's litmus to it honestly: **nothing
enforces it.** Three rules it states have no check behind them —

- a topic file carries **no frontmatter** (frontmatter belongs to `SKILL.md` alone);
- **every** topic file is pointed at by its router (an unreferenced topic is invisible to a reader who
  only ever sees `SKILL.md`);
- a pointer is an **instruction to read**, not a summary — the one thing standing between shape 2 and
  an agent writing an artifact from the router's paraphrase.

T14's Verification greps for these **once, by hand**, and then they are never run again.
`test_skill_catalog.py` cannot be the home: it is the deliberately-untouched paid-fixes oracle and
asserts content *signatures*, not format.

And a second, independent weakness T13 found in that oracle (its finding 6): `_load_catalog()`
concatenates `SKILLS_DIR.rglob("*.md")`, which is *why* bundled topic files are covered for free — the
premise T13/T14 rest on — but it also pulls **`CONVENTIONS.md` itself** into the guarded corpus. So a
paid-for needle could in principle be satisfied by text in the *format document* rather than in any
skill body, and the guard would still pass. T13 checked that its own edits introduce no needle text;
the weakness is structural and undocumented.

**Do this after T14, not before.** The rules are cheap to check once real routers exist; writing the
guard against zero split skills would pin an empty set (and `test_self_lint.py`'s non-vacuity guard is
the precedent for why that matters).

## Depends on
T13 (the contract), T14 (which produces the first routers — the guard needs them to be non-vacuous),
T07 (the paid-fixes inventory whose oracle is involved).

## Read first
- `.claude/skills/CONVENTIONS.md` "Skill format" — the three rules, in the wording that must be checked.
- `.claude/skills/meta-skill-author/SKILL.md` `## Where the body lives` — the router template and its
  five rules; the guard should agree with that template rather than reinterpret it.
- `.claude/tools/test_skill_catalog.py` — `_load_catalog()` (the `rglob` that creates both the coverage
  and the corpus weakness) and how signatures are asserted. **Do not edit it** — it is T07's oracle.
- `.claude/tools/test_self_lint.py` — the shape to imitate: discover by rglob, assert, and carry a
  **non-vacuity guard** so an empty discovery set cannot read as success.
- `PRINCIPLES.md` S4, C2, C7.

## Deliverables
- `.claude/tools/test_skill_format.py` — **new**, the standing guard. At minimum:
  - a topic file (any `*.md` under a skill dir that is not `SKILL.md`) has **no** `---` frontmatter
    block;
  - every topic file is referenced by its own skill's `SKILL.md`, and every pointer in a `SKILL.md`
    resolves to a file that exists;
  - each pointer reads as an instruction (an imperative "read …", not a bare filename in prose) —
    if that cannot be checked without false positives, check the resolvable half and **say in the test
    why the imperative half is not checked**, rather than pretending it is covered;
  - a non-vacuity guard: the discovered set of skills is non-empty, and once T14 lands, at least one
    router exists.
- **The corpus weakness: fix or document, one of the two.** Either exclude non-skill documents
  (`CONVENTIONS.md`, and any future format doc) from `_load_catalog`'s corpus — but that edits T07's
  oracle, so it needs its own argument — or record the weakness in `test_skill_catalog.py`'s docstring
  so the next auditor knows a needle can be satisfied by the format doc. **Prefer documenting**: the
  oracle's value is that nobody edits it.
- A line in `.claude/skills/CONVENTIONS.md` naming the guard, so the contract cites its enforcement
  (S4: a rule with a gate says where the gate is).

## Verification
- `uv run pytest .claude/tools` green.
- **Each rule demonstrably fails when broken** — plant, in a scratch copy: frontmatter in a topic file;
  an unreferenced topic file; a pointer to a nonexistent file. All three must red the guard, then pass
  when removed. A guard nobody proved red is decoration (A5's corollary).
- The non-vacuity guard reds when the discovery set is empty.
- `uv run pytest .claude/tools/test_skill_catalog.py` green and **unmodified** (`git diff` on that file
  is empty unless you took the documenting option, which touches only its docstring).

## Out of scope / Escalate if
- Do NOT edit `test_skill_catalog.py`'s assertions or its signature list. It is T07's oracle and T14's
  correctness argument depends on it being untouched.
- Do NOT enforce the ~500-line threshold as a hard failure. It is a *when to split* heuristic, not an
  invariant; a 520-line single-topic skill is a judgment call, and failing the suite over it would make
  the number a rule nobody agreed to.
- Do NOT add format rules the contract does not state. This guards T13's contract; extending the
  contract is a separate act with a separate argument.
- **Escalate if** the imperative-pointer rule cannot be checked without unacceptable false positives
  **and** you judge that leaving it unguarded defeats the point. That is the rule with the most
  behavioural weight and the least checkability, and trading it away is the author's call.
