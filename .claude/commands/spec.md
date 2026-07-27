---
description: "Interview the human into one change spec — change.md + criteria.md on a fresh change/<context>-NNN branch; --retro legalises a hotfix post-factum"
---

# /spec [<context>] [<description>] [--retro]

> Invoked as `/adw:spec` when the workflow is installed as a plugin, `/spec` when it is
> loaded from a project's own `.claude/` — as in the workflow's own repo. The two forms name
> this same file; other commands are referred to below in the `/adw:` form.

Interactive — this is the **spec-author** session (human + you, spec §4). It produces exactly
one change: a delta spec living on its own branch. Your lane: files under `specs/` plus branch
creation — you never write code or tests (advice is enough here; the session runs under the
human's eyes). Spec content is written in the project's dialogue language (whatever the
project's CLAUDE.md sets; English if it sets none) — it is input for the human, not for the
machine; ids, slugs, and branch names stay ASCII.

The format has ONE home — the templates. Do not restate their rules here or improvise
sections: `.claude/templates/change.md` (sections, classes, binding/non-binding notes),
`.claude/templates/criteria.md` (states, immutability), `.claude/templates/overview.md` and
`.claude/templates/capability.md` (canonical spec skeletons).

## Procedure

1. **Orient.** Parse `$ARGUMENTS` into context, free-form description, and the `--retro`
   flag; anything missing or ambiguous → ask. Read `specs/<context>/overview.md` and the
   capability files the description touches (point context, not the whole corpus), plus any
   referenced `specs/use-cases/` sources.

2. **First change of a context** (no `specs/<context>/` yet, or an empty skeleton): propose
   the capability cut per spec §2.1 — cohesion-of-change, usually 1–2 UCs per file at the
   start; the human decides. Write the skeleton `overview.md` from the template with the
   agreed capability list (capability files themselves are born at acceptance, when criteria
   merge in). Shape the change as a **vertical slice** (spec §9): ONE end-to-end observable
   AC, all substrate on the way — never a "bootstrap"/"DI"/"tables" change (no observable
   behaviour, S1/S3 forbid such AC).

3. **Interview.** Ask the human about every ambiguity (AskUserQuestion) — idempotency,
   permissions, failure modes, limits — until the acceptance criteria write themselves. Then
   propose, human decides:
   - **Class** — behavioral (default) / bugfix / invisible / hardening; definitions live in the
     change.md template. A **removal** is behavioral carrying spec §3.1's pinned marker — you
     write `Class: behavioral, REMOVED` *and* fill the template's `## Removed` section, which is
     where the removed behaviour is "listed explicitly": the removed symbols and the obsolete
     tests' node-ids, in the grammar the template's own comment specifies. Both are owed here and
     only here — change.md freezes at the baseline commit and no agent inside the cycle may edit
     it, and the orphan sweep understands no other wording.
     A **hardening** change (the tests get stronger, behaviour stays identical — normally the
     follow-up an adversarial pass earns) additionally needs a `## Mutations` section: **you and
     the human write it here**, lifting the surviving mutations from the `## Adversarial review`
     table of the change that found them. It is the class's baseline proof, so an agent inside the
     cycle must never author it — the template states what `red_check` then enforces.
     An **invisible** change (refactor / dependency upgrade / performance) writes its AC as the
     behaviour that must stay **unchanged**, phrased so a test can pin it *before* the refactor:
     its proof is a green gate plus an empty before/after OpenAPI diff (`gate.py`'s
     `invisible.openapi-diff`), and `red_check` asks that the ac-marked tests already **pass** at
     the baseline. So it is brownfield-only by construction — behaviour that does not exist yet
     cannot be left unchanged.
   - **Depth** — S/M/L (spec §3.2); litmus: if the diff fits one sentence, S is enough. Only
     Acceptance criteria are mandatory; do not inflate ceremony.
   - **Interface sketch** (M/L) — propose module/class names + ctor dependencies; once the
     human approves, it is the binding contract of the cycle.

4. **Allocate the id.** `NNN = max(existing ∪ tags) + 1`, zero-padded to three digits, where
   existing = `specs/<context>/changes/NNN-*/` directories and tags = `change/<context>-NNN`
   and `abandoned/<context>-NNN` (numbers are never reused, even after an abandon). The id
   everywhere is `<context>/NNN`; the directory slug is an English kebab of the short name.

5. **Branch.** Create `change/<context>-NNN` off the green mainline — `main` (S9; while v3
   itself is still being built on a work branch, that branch stands in for `main`). All
   artifacts of this change live on this branch.

6. **Write the artifacts** into `specs/<context>/changes/NNN-<slug>/` from the templates:
   `change.md` and `criteria.md`. Criteria mirror the Acceptance criteria section 1:1 as
   `AC-n` items.

7. **Exit gate** — the session does not end until all of this holds:
   - `uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py" criteria-lint specs/<context>/changes/NNN-<slug>/criteria.md`
     is green — a vague criterion does not enter work; rewrite with the human until it names
     observable artifacts;
   - Verification answers "how do we prove it is done": required for M/L; every criterion
     that needs a live run has its environment provisioning named there (seed data, docker,
     tokens) — an unprovisioned criterion is proven by its ac-marked test alone, and a
     criterion neither can prove is flagged now as an `[m]` candidate. For S depth the answer
     is the fast-lane itself (`gate.py --criteria` over ac-marked tests);
   - a **removal** carries both halves of the vocabulary: the `REMOVED` marker on the `Class:`
     line and a `## Removed` section that actually lists something (a section left holding only
     the template comment counts as unfilled). `accept.py`'s orphan sweep FLAGs a half-written
     pair at acceptance, but by then change.md is frozen — so it is fixed here;
   - `change.md` + `criteria.md` (+ the overview skeleton, if step 2 ran) are committed on
     the change branch.

8. **Hand off.** Tell the human the change id and the next step: `/adw:implement <context>/NNN`.

## `--retro` — hotfix legalisation (spec §5.5)

A hotfix past the workflow is legal (prod was burning) but never silent. Same procedure,
with three differences:

- Class is `bugfix` or `behavioral` only; the Context section lists the `main` commits this
  change legalises, so the drift-check can tie them to a change tag;
- the criteria describe the behaviour the hotfix already established — they lint like any
  other criteria;
- the change then flows through the normal cycle: `/adw:implement` pins the behaviour with
  ac-marked tests, `/adw:accept-change` merges its essence into the capability files.

## Re-cutting capabilities (a /spec right, spec §2.1)

Thresholds: a file past ~300 lines → cut (for overview.md — extract `glossary.md` /
`invariants.md` as equally canonical files); every second delta touching the same pair of
files → merge them. Re-cutting moves canonical text between files AND deterministically
rewrites `Affects:` in every in-flight `changes/*/change.md`. It is a reviewable commit,
NOT a delta spec — system behaviour does not change.
