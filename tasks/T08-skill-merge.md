# T08 — Skill catalog merge 44 → ~13 (WP4b)

## Goal
Merge the catalog per the spec §7 map, purge manifest-era coupling, wire auto-invocation
frontmatter — WITHOUT losing a single paid-for line (T07's suite is the proof).

## Depends on
T07 (hard); T02 (v2 command references gone).

## Read first
- Spec §7 (map + all five numbered rules), `.claude/skills/CONVENTIONS.md`, every skill
  being merged, `notes/16_agent_prompt_harvest.md` (T02 output — homes assigned here).

## Deliverables
- Merged catalog: the 13 skills from the §7 table (each `<name>/SKILL.md`, four-section
  body kept).
- Frontmatter per skill: `description` + `when_to_use` (≤1536 chars combined — F-6; no
  `when` field, it does not exist).
- Harvested rules from notes/16 inserted into their designated homes.
- `notes/17_hardstop_dispositions.md` — per Hard stop of every merged skill: "gate in
  gate.py (which check)" or "demoted to advice (why)" (O-12; S4 litmus applied).
- `.claude/skills/CONVENTIONS.md` — updated index (13 entries, shared vocabulary kept);
  `conventions/SKILL.md` — kind→skill registry removed, toolchain section now CITES gate.py;
  also cites gate.py's Docker-tier DSN handoff (T04 finding 3): the app's `alembic/env.py`
  must honor the `DATABASE_URL`/`GATE_DATABASE_URL` env vars — the convention's home is
  gate.py, conventions cites it (C7).
- `testing-integration` skill carries the **Docker-absence rule** (T04b finding 2): an
  integration test's environment guard MUST be a clean `pytest.skip`/`skipif` on daemon
  absence, NEVER a fixture that raises — gate.py's inventory carve-out exempts only a
  *skipped* baseline integration test, so a raising/erroring one turns a Docker-less machine
  permanently RED. This is a Hard stop, gated indirectly by gate.py (T04b) — note it as such
  in notes/17.
- Old skill directories removed.
- Stale-pointer sweep from the purge (notes/16): `meta-uc-author` "When to use" no longer
  references the deleted `extract-ucs`/`uc-extractor` (U1 — point it at "hand-authoring a UC",
  upstream extraction marked as a future stage); `.claude/skills/CONVENTIONS.md` no longer
  names the deleted v2 agents.

## Steps
1. Merge group by group (one commit per target skill — reviewable); move content verbatim
   where possible; deduplicate cross-references that become internal.
2. Purge manifest-era lexicon (C1/C3): "manifest", "scaffolder", "runner", "kind",
  "validator", "report to the coordinator"-class phrasing.
3. Insert harvest items; add the `ac`-marker convention to `testing-unit` (§3.3).
4. Write the disposition list as you encounter each Hard stop — not as an afterthought.
5. Run T07 suite after EVERY group commit — a red run pinpoints the lost line immediately.

## Verification
- `uv run pytest .claude/tools/test_skill_catalog.py` green against the merged catalog.
- `ls .claude/skills/` → exactly the §7 table names + CONVENTIONS.md.
- `grep -rn "manifest\|scaffolder\|kind→skill\|validate_manifest" .claude/skills/` → empty.
- Frontmatter check: every SKILL.md has `description`; combined description+when_to_use
  ≤ 1536 chars (script the check inline).
- `notes/17_hardstop_dispositions.md` covers every merged skill (count them).
- Every ⚠ TRANSFER / "Open transfers" row of `notes/16_agent_prompt_harvest.md` addressed to
  T08 (R1, I2, I3, C4, U1) is closed: inserted (cite skill + section in the report) or
  escalated — none silently dropped.

## Out of scope / Escalate if
- No new knowledge authored here — merge + harvest-insert only. A Hard stop that fits
  neither "gate" nor "advice" cleanly → ESCALATE entry in notes/17, human decides.
