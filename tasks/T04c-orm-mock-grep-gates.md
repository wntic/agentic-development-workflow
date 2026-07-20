# T04c — Add the no-ORM + no-mocks grep-gates to gate.py

## Goal
T08 finding 5 honestly logged no-ORM and no-mocks as ungated ADVICE in notes/17. Both are
must-hold house rules with CLEAN deterministic signatures, so by S4 they belong in a gate,
not in prose — leaving them as advice is exactly the "rules-get-violated" failure (провал 2)
v3 exists to end. This must land BEFORE T09 runs the cycle, so the implementer is held to
both from its first change. (logging-content and env_prefix altitude stay ADVICE — they are
semantic, with no clean grep; do NOT gate those.)

## Depends on
T04, T08 (notes/17 exists with the ADVICE rows to flip).

## Read first
- `.claude/tools/gate.py` — `check_greps` (the existing src/** grep-gates + their finding-id
  comment style) and how checks are registered/reported.
- `notes/17_hardstop_dispositions.md` lines ~104 (no-ORM) and ~167 (no-mocks).
- Spec §5.1 (the grep-gate inventory), S4.

## Deliverables
- `.claude/tools/gate.py` — two new grep-gates:
  - **no-ORM** over `src/**`: RED on `declarative_base`, `DeclarativeBase`, `Mapped[`,
    `mapped_column`, `relationship(` (SQLAlchemy ORM signatures — Core, the house style, uses
    none of them). Word-boundary where a bare token could collide.
  - **no-mocks** over `tests/**`: RED on `unittest.mock`, `MagicMock`, `AsyncMock`, `@patch`,
    `mocker.`/`monkeypatch` used to stub (the no-mocks contract — fakes for unit, real
    backends for integration).
- `.claude/tools/test_gate.py` — red + green case for each.
- `notes/17_hardstop_dispositions.md` — flip the no-ORM and no-mocks rows from ADVICE to
  GATE, naming the new check ids.

## Steps
1. Follow the existing `check_greps` shape and finding-id comment convention exactly (one
   home, one style). no-ORM scans `src/**`; no-mocks scans `tests/**` (mirror the src-only
   scoping decision from T04 finding 8, inverted for the test-tier rule).
2. Keep precision bias where a signature could false-positive on a legitimate line; a real
   collision just prompts review, but avoid gratuitous noise.

## Verification
- `uv run pytest .claude/tools/test_gate.py` green, with the new cases (ORM import in a src
  fixture → RED; Core-only src → GREEN; `MagicMock` in a test fixture → RED; fakes-only
  tests → GREEN).
- Running gate.py on THIS repo stays GREEN (no ORM in .claude tooling; the tooling's own
  tests use no mocks — confirm, or scope no-mocks to the target app's `tests/**` only, not
  `.claude/tools/`).
- notes/17 no-ORM and no-mocks rows now read GATE with the check ids.

## Out of scope / Escalate if
- Do NOT gate logging-content or env_prefix (semantic, no clean grep — stay ADVICE).
- If the no-mocks scan would red the meta-layer tooling's own tests, scope it to the target
  app's tests/ and record that boundary — don't weaken the rule for the target app.
