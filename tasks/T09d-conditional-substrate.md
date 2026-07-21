# T09d — Evolving/conditional substrate ownership

## Goal
Close the T09c finding-5 frontier: `bootstrap.py` establishes only the always-present §D
substrate (fastapi, pydantic, di, structlog…). A change that needs CONDITIONAL substrate —
`sqlalchemy`/`asyncpg`/`alembic` (relational store), `pyjwt`/`argon2` (auth),
`python-multipart` (upload), a client-store SDK — has no role to add it to `pyproject.toml`:
the implementer is tool-blocked from it, and `pyproject.toml` is a frozen gate-protected tree,
so the dep must be present at baseline. Greenfield `/health` doesn't hit this; the accounts
sign-in slice (auth + persistence) hits it immediately. This is the substrate-evolution
sibling of the F2/F3 greenfield gap.

## Depends on
T09c (bootstrap.py exists; the substrate-establishment pattern is set).

## Read first
- `.claude/tools/bootstrap.py` (the §D-substrate merge + the pre-baseline-commit pattern to reuse).
- `.claude/skills/conventions` §D (the conditional-substrate rows: which feature pulls which
  packages — the graph-derived dep rules, incl. the multipart→python-multipart and
  HS256→no-cryptography gating harvested in notes/16 S1/S2/S3).
- Spec §5.1 (pyproject frozen tree), PRINCIPLES B8 (deps derived from the graph, names-only,
  no version floors except a known breaking boundary).
- The T09c report finding 5.

## Open design question (rule before building)
Who declares conditional substrate, and from what signal? In v2 the manifest declared it; v3
has no manifest. Candidate: the bootstrap/substrate step re-runs at baseline time and derives
the conditional deps from a signal in the change — most likely the Interface sketch / the
change's declared feature (a relational repo in the sketch → sqlalchemy substrate), since the
implementer's code doesn't exist yet at baseline. This needs a human ruling (sibling to the
T09c ruling); DO NOT invent a manifest, and do NOT hand pyproject to the implementer.

## Deliverables (after the ruling)
- The conditional-substrate mechanism (likely an extension of `bootstrap.py` / a pre-baseline
  substrate step) that adds graph-derived conditional deps names-only, before the baseline,
  keeping the frozen-pyproject integrity check intact.
- Tests: a change declaring persistence → sqlalchemy/asyncpg/alembic present at baseline;
  an auth change → the auth substrate; a plain change → no conditional deps added.

## Verification
- An accounts-style slice needing a DB reaches a green gate through the full cycle without a
  human override (the conditional substrate lands pre-baseline).
- `red_check` still refuses src in the baseline (T09b); frozen-pyproject integrity still passes.

## Out of scope / Escalate if
- Do NOT revive the manifest or hand pyproject write access to the implementer. If the signal
  for "which conditional deps" can't be derived cleanly without the implementer's code,
  escalate with the specific case — that's the crux the ruling must settle.
