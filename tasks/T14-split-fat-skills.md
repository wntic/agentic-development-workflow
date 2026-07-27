# T14 — Split the over-threshold skills into router + topic files

## Goal
Apply the T13 contract: split each over-threshold theme-skill into a thin `SKILL.md` router plus one
`<topic>.md` per artifact — **without losing a single paid-for line**. This is the mechanical twin of
T13, and it repeats T08's discipline exactly: `test_skill_catalog.py` is the acceptance oracle and is
**never edited** (`rglob("*.md")` already covers bundled files, so a moved line stays found; a red
run pinpoints a lost line). Auto-invocation frontmatter is moved **verbatim** — discovery must not
regress.

## Depends on
T13 (hard — the target format must exist first, or the split drifts back to `## ` sections).

## Read first
- `.claude/skills/CONVENTIONS.md` — the T13 "Skill format" (the shape to produce + the threshold).
- `.claude/tools/test_skill_catalog.py` — the oracle (do not edit; note it `rglob`s all `*.md`).
- Each skill being split (see the candidate list) — its `## `-heading outline IS the split plan.
- `tasks/T08-skill-merge.md` — the "one commit per skill, run the guard after each" discipline.

## Candidates (measured 2026-07-24; final list obeys T13's threshold)
Definite (well over threshold): `testing-integration` (1792, 7 artifacts + constitution),
`restapi` (1256, 7), `testing-unit` (1045, 7 + constitution), `infra-persistence` (733, 3).
Borderline — split only if T13's threshold says so: `application` (585), `infra-integration` (537).
Under threshold, leave alone: `domain-model` (449) and everything smaller.

## Deliverables (per split skill)
- `SKILL.md` reduced to the thin router: **unchanged frontmatter** + the router "When to use vs.
  neighbours" naming every topic with an imperative pointer to its file + any genuinely cross-topic
  material kept inline (the testing "constitution" sections are cross-topic — they stay in `SKILL.md`
  or a clearly-pointed `constitution.md`, the builder's call per T13).
- One `<topic>.md` per artifact, each keeping the full four-section body moved **verbatim** (When to
  use / Template(s) / Rules / Hard stops + the two optional helper sections when present). No
  frontmatter in a topic file.
- Every internal cross-reference that used to point at a `## ` section now points at the topic file.

**Two sweeps T13 identified that nobody else owns — do them here (its findings 3 and 4):**

- **`CLAUDE.md` goes stale the moment the first split lands.** Line ~230 says *"Every skill follows the
  four-section body"* — true today only because no skill is split yet. Reword for both shapes (a
  single-topic skill, or a router beside one topic file each keeping the four-section body). While there,
  the "44 skills now → ~13 after T08" line is also stale; T08 landed.
- **The agent prompts point at a theme as "the one home", and after this task that home is a file
  auto-invocation does not inject.** `.claude/agents/evaluator.md:99` says the assert-strength recipes
  come "from the **`testing-unit`** skill — that skill is the one home"; `test-author.md:71` says "For
  unit tests read **`testing-unit`**". The theme name still resolves, so neither is *wrong* — but the
  Human-verification question below ("does the subagent actually follow the pointer?") partly depends on
  the **agent prompt** telling it to. Make both prompts name the topic file for the specific thing they
  send the agent to read, keeping the theme name as the entry point.

## Steps
1. One skill per commit (reviewable). Move content verbatim; do not reword paid-for lines.
2. After **every** commit: `uv run pytest .claude/tools/test_skill_catalog.py` — a red run means a
   signature was dropped or mangled; fix before the next skill.
3. Verify each router points at every topic it split out, and no pointer dangles.

## Verification
- `uv run pytest .claude/tools/test_skill_catalog.py` GREEN with `git diff
  .claude/tools/test_skill_catalog.py` **empty** — the guard passes because the knowledge survived,
  not because the oracle was relaxed (V-07 discipline from T08).
- Every split `SKILL.md` is now ≤ the T13 threshold: `wc -l .claude/skills/*/SKILL.md`.
- Frontmatter is byte-identical to before per split skill (extract the frontmatter block and diff
  against the pre-split version — discovery must not regress).
- No `<topic>.md` file contains a `name:`/`description:` frontmatter block (only `SKILL.md` does):
  `grep -rl "^description:" .claude/skills/*/` lists only `SKILL.md` paths.
- Each router SKILL.md references each of its topic files (grep the filenames); no orphan topic.
- `ls .claude/skills/` still shows exactly the §7 theme names — no theme added or removed.

## Human verification
- **Reliability of on-demand topic reads by the cycle subagents is confirmed only in an e2e probe**
  (T11-style / the next `/implement`): auto-invocation injects `SKILL.md`, and the test-author /
  implementer / evaluator must actually follow the router's pointer and Read the right `<topic>.md`.
  If a subagent skips the pointer and writes from the router alone, the router's imperative wording
  needs strengthening (or a topic is too far from the trigger) — record it as a finding, do not
  paper over it.

## Out of scope / Escalate if
- **No knowledge authored or reworded** — pure move + router-wiring, exactly like T08's merge.
- A paid-for line that has no natural topic home (belongs to the cross-topic constitution) stays in
  the router — do not force it into a topic file just to shrink `SKILL.md`.
- If the T13 threshold leaves a skill ambiguous (borderline `application`/`infra-integration`),
  follow the threshold verbatim; if it genuinely cannot decide, ESCALATE rather than guessing.
