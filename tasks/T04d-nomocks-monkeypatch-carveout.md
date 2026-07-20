# T04d — Narrow the no-mocks gate off monkeypatch (false positive)

## Goal
T04c's no-mocks grep bans bare `monkeypatch`, but the house style **sanctions** it:
`testing-unit` allows `monkeypatch.setenv` inside settings-parsing tests
(`tests/unit/infrastructure/test_*_settings.py`, exercising the env-reading code itself) and
lists `monkeypatch.setattr` as available (just never to patch handler dependencies). In the
**trust anchor** a false positive is a hard RED, not a soft nudge — and every app has a
settings test, so this would block T09's first real app on a house-sanctioned pattern. Fix
before T09.

## Depends on
T04c.

## Read first
- `.claude/tools/gate.py` — the `grep.no-mocks` alternation added by T04c.
- `.claude/skills/testing-unit/SKILL.md` lines ~239, ~1017–1024 (the sanctioned monkeypatch
  uses); `testing-integration` line ~1054 (no monkeypatch on infrastructure).
- `notes/17_hardstop_dispositions.md` no-mocks row; T04c finding 5.

## Deliverables
- `.claude/tools/gate.py` — `grep.no-mocks` narrowed to the **mock family only**:
  `unittest.mock`, `MagicMock`, `AsyncMock`, `@patch`, `mock.patch`, `mocker.` (all with
  zero sanctioned uses). **Remove `monkeypatch`** from the alternation. Keep finding-3's
  precision (no bare `patch(` — REST `.patch()` is legitimate).
- `.claude/tools/test_gate.py` — drop/replace the assertion that bare `monkeypatch` fires;
  ADD green cases: `monkeypatch.setenv` in a settings test → GREEN; `monkeypatch.setattr`
  → GREEN. Keep the mock-family RED cases.
- `notes/17_hardstop_dispositions.md` — no-mocks row: mock-family = GATE (`grep.no-mocks`);
  monkeypatch-misuse (patching dependencies) = **ADVICE** (semantic, has sanctioned uses —
  setenv in settings tests, setattr for non-deps).

## Verification
- `uv run pytest .claude/tools/test_gate.py` green, with: `MagicMock` in tests → RED;
  `monkeypatch.setenv` in a settings test → GREEN; `monkeypatch.setattr` → GREEN;
  `client.patch('/x')` → GREEN (finding-3 precision preserved).
- gate.py on this repo still GREEN.

## Out of scope / Escalate if
- Do not try to grep-gate monkeypatch-misuse (which attr is a "dependency" is semantic — it
  stays advice, enforced by review + the fake-repository pattern). If a clean signature for
  "monkeypatch on a handler dependency" turns out to exist, note it — don't force one.
