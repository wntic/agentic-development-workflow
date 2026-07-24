# T13 — Progressive-disclosure contract for theme-skills

## Goal
Legalise **progressive disclosure inside a theme-skill** so a large theme stops living as one
monolithic body. Today `CONVENTIONS.md` (the "Skill format" section) mandates *"a merged
theme-skill carries one `## …` section per artifact"* — that rule is what produces the fat skills
(`restapi` 1256 lines, `testing-integration` 1792, `testing-unit` 1045, `infra-persistence` 733).
Replace it with: a theme-skill's `SKILL.md` is a **thin router** (frontmatter + cross-topic
constitution + an imperative pointer per artifact), and each artifact's four-section body moves into
a sibling `<topic>.md` the agent reads **on demand**. This task changes only the **contract** (the
format doc + the authoring skill + one C-series clarification); the actual split is T14.

**This is design-sensitive** — it edits the local format contract that governs every skill. It does
**not** contradict spec §7: §7 mandates ~13 *themes* (auto-invocation entries), and bundling keeps
~13 themes — it splits their bodies, not the catalog. No canon edit; if §7 seems to forbid it,
ESCALATE instead of improvising.

## Depends on
T08 (the merged catalog exists). Blocks T14.

## Read first
- `.claude/skills/CONVENTIONS.md` — the "Skill format" section (lines ~71–80) is the rule being
  rewritten; the shared-vocabulary + index sections stay.
- `PRINCIPLES.md` C-series (C1, C2, C7) — C2 ("one theme per skill") must be clarified, not broken.
- `.claude/skills/meta-skill-author/SKILL.md` — the skill that PRODUCES skills in this format; it
  must teach both shapes after this task.
- `workflow_v3_spec.md §7` (design canon, read-only) — confirm bundling is compatible with the
  ~13-theme map before writing.
- `.claude/skills/restapi/SKILL.md` — the motivating example (7 artifacts under one theme).

## The loading mechanism (state it, do not re-decide it silently)
Auto-invocation injects **only `SKILL.md`** when the theme triggers (frontmatter unchanged →
discovery is byte-identical to today). Bundled `<topic>.md` files are **not** auto-injected — the
agent reaches them with Read, following the router's pointer. Therefore the make-or-break is that
the router's pointer is **imperative and unmissable** ("To write an endpoint, read `endpoint.md`
now"), not a soft cross-reference. The `test_skill_catalog.py` guard already `rglob("*.md")`s the
whole skill tree, so paid-for lines living in a `<topic>.md` stay covered — no guard change (T14
relies on this).

## Deliverables
- **`.claude/skills/CONVENTIONS.md`** — the "Skill format" section rewritten to define two shapes:
  - **Single-topic skill** (unchanged): one `SKILL.md`, four-section body. Used when the theme
    covers one artifact (`conventions`, `python-style`, `application` if it stays under threshold).
  - **Multi-topic theme** (new): a thin `SKILL.md` = frontmatter + a "When to use vs. neighbours"
    router that names each topic and points at its file + any genuinely cross-topic material (e.g.
    the testing "constitution") + a one-line imperative pointer per topic; plus one `<topic>.md` per
    artifact, each keeping the full four-section body. Bundled topic files carry **no** frontmatter
    (only `SKILL.md` is a skill; a stray topic frontmatter must not mint a phantom skill).
  - A **threshold trigger** telling an author when to bundle rather than add a `## ` section:
    e.g. *"`SKILL.md` would exceed ~500 lines, or the theme carries > 3 distinct artifacts → split
    to bundled topics."* (Pick the number; justify it in one line.)
- **`.claude/skills/meta-skill-author/SKILL.md`** — teaches both shapes and the threshold; its
  template/examples show the thin-router + one-topic-file form. No orchestration leak (C1/C3).
- **`PRINCIPLES.md` C2** — one added sentence: "one theme" permits bundled per-topic reference files
  loaded on demand; the theme is **one auto-invocation entry**, not necessarily one file. C7 stays
  intact (derivation still has one home).

## Steps
1. Rewrite the CONVENTIONS "Skill format" section; keep shared-vocabulary + index + out-of-scope.
2. Amend C2 (one sentence). Do not touch the S-series or spec.
3. Update `meta-skill-author` to author both shapes; verify its own body still obeys the four
   sections and stays a single-topic skill.
4. Re-read the three edited docs together for internal consistency (no doc now contradicts another
   on "one `##` per artifact").

## Verification
- `grep -n "one .* section per artifact\|## … section" .claude/skills/CONVENTIONS.md` → the old
  mandate is gone (or explicitly reframed as the single-topic case).
- `grep -ni "bundled\|topic file\|on demand\|router" .claude/skills/CONVENTIONS.md` → the new
  contract is present.
- `meta-skill-author` mentions both shapes and the threshold (grep for the threshold number).
- `PRINCIPLES.md` C2 still opens with "one theme per skill" AND now allows bundled topics.
- No edit to `workflow_v3_spec.md`, `notes/15_*`, or `test_skill_catalog.py`.

## Human verification
- The format change reads as a coherent contract a future author can follow blind (skill-format
  review is a human call, like T03's templates).

## Out of scope / Escalate if
- **No skill is split here** — that is T14. This task ships only the contract.
- If bundling appears to conflict with spec §7's ~13-theme map or with C2's rationale in a way one
  sentence cannot reconcile → ESCALATE, do not edit canon.
