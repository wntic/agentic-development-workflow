# T02 — Harvest agent prompts, purge v2 machinery (WP1b)

## Goal
Extract every paid-for rule living in v2 agent prompts/commands into a harvest register
with a designated new home (spec §7.4), THEN delete the v2 machinery (spec §8). Harvest
strictly precedes deletion — knowledge dies silently otherwise (finding V-08).

## Depends on
T01.

## Read first
- Spec §7.4, §8.
- `.claude/agents/{analyst,architect,scaffolder,implementer,uc-extractor}.md`.
- `.claude/commands/{ingest-usecases,refine-usecases,build-manifest,apply-delta,validate-manifest,scaffold,verify,author-manual-tests,extract-ucs}.md`.
- `notes/14_dryrun_fix_plan.md` (N-04, ConflictError context).

## Deliverables
- `notes/16_agent_prompt_harvest.md` — register: rule → source file/line → designated home
  (`T08` skill name / `T09` protocol / "dies because …").
- Deletions committed: files listed in spec §8 "уходит" (validator + planner + snapshot +
  gen_template + their tests + fixtures, templates MANIFEST_SCHEMA.md + manifest.template.yaml,
  the five v2 agents, the nine v2 commands, `src/codegen/` + `tests/`, `specs/epics/*/manifest.yaml`).
- `examples/` — remove generator entrypoint + example manifests (they exercise deleted code);
  keep the git-ignored `examples/generated/` convention mentioned in CLAUDE.md.

## Steps
1. Sweep each v2 agent/command for rules that are NOT already in a skill or in the spec.
   Known minimum (must appear in the register): env_prefix = product not context (N-04,
   architect r10 → home: `infra-integration`); ConflictError on first unique-insert
   (architect r9 → `infra-persistence`); flat-vs-review-tail acceptance discipline
   (implementer → §6 protocol / `testing-unit`); scaffolder's multipart→python-multipart
   and HS256→no-cryptography dep gating (→ `conventions` or `infra-integration`); the
   two-channel product/architecture question split (analyst → "dies for core scope, revives
   with upstream stages" note).
2. Delete per spec §8. Use `git rm` so the commit is reviewable.
3. Update `.claude/skills/CONVENTIONS.md` ONLY if it references deleted commands by name
   (defer content changes to T08).

## Verification
- `notes/16_agent_prompt_harvest.md` exists; every "Known minimum" item above present.
- `ls .claude/agents/` → none of the five v2 agents; `ls .claude/commands/` → none of the
  nine v2 commands; `test -d src/codegen` → absent; `test -f .claude/tools/validate_manifest.py` → absent.
- `git status` clean after commit; `grep -rn "validate_manifest\|plan_implementation" .claude/commands .claude/agents CLAUDE.md` → empty.

## Out of scope / Escalate if
- Do NOT touch `.claude/skills/` content (T07/T08). Do NOT write the new agents (T09).
- `specs/use-cases/` stays untouched (verbatim BA corpus). `notes/` never deleted.
- If a v2 rule has NO obvious home, do not invent one — register it with home "ESCALATE"
  and list it in the report.
