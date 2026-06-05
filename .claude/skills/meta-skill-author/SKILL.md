---
name: meta-skill-author
description: Apply when adding a new skill to `.claude/skills/`. Produces one `<prefix>-<name>/SKILL.md` file conforming to the catalog's canonical format — frontmatter, the four-section body, and placeholder vocabulary — so agents reading the new skill can apply it the same way they apply every existing one. Does not produce the agents that invoke skills (those live under `.claude/agents/`) or the spec format itself.
---

# Meta — Skill Author

A skill in this catalog is **component-narrow**: it produces exactly one kind of artifact (one entity file, one repository module, one endpoint, one test file, …). Skills are read by agents (or humans) as reference knowledge; the skill's job is to show how the right file(s) are written. Uniformity matters more than expressiveness — an agent that has read one skill should be able to apply any other.

This skill produces one new `SKILL.md`. It does **not** modify other skills (that's an audit task), produce agents (`.claude/agents/`), or design the spec format.

## When to use vs. neighbours

- Adding a brand-new skill → this skill.
- Editing an existing skill to fix a rule or template → not this skill; just edit the file directly.
- Sweeping cross-references after a rename → not this skill; that's an audit task.
- Documenting a process (brainstorm, retrospective) → still this skill, but use the `process-` or `meta-` prefix; the format adapts (no "Templates" section, but every other section still applies).

## File location

```
.claude/skills/<full-skill-name>/SKILL.md
```

The directory name **is** the skill name (e.g. `domain-entity/SKILL.md`). One SKILL.md per directory, no other files unless the skill needs sibling assets (rare; explain in the body why).

## Frontmatter (exact shape — no custom fields)

```yaml
---
name: <full-skill-name>
description: <one paragraph — see rules below>
---
```

Only `name` and `description`. **No** custom frontmatter fields like `component:`, `produces:`, `layer:`. Tooling does not parse them; they make the format look variable.

Description rules:

- One paragraph (can be 2–4 sentences). No bullets, no line breaks.
- **First clause:** "Apply when …" — the trigger condition. The agent should be able to decide whether to invoke this skill from this clause alone.
- **Middle:** what the skill produces — name the file(s) and key shape.
- **End:** explicit "Does not produce X — use `<other-skill>`" pointers to adjacent skills. This is what makes the catalog navigable.
- No application-specific names (no `Material`, no `Order`). Use `Foo` / `Bar` per CONVENTIONS.md.
- Read like a sentence; not a heading or list.

## Body — the canonical sections

Every skill has these sections, in this order, with these exact headings. Four are required; two (`Inlined typing / import rules`, `Package wiring`) are optional helpers included only when load-bearing.

```markdown
# <Title> — usually `<Prefix> — <Concept>` or `<Concept>` alone

<One short opening paragraph: what the skill produces and its hardest boundary.>

## When to use vs. neighbours

<3–5 bullet points contrasting this skill with each adjacent one. Each bullet is one line: "X → `skill-name`." Goal: an agent that misclassified the work sees its real home immediately.>

## Template(s)

<One or more literal file templates with placeholder names. Use `Foo`/`Bar` from CONVENTIONS.md. Show the entire file content, not a fragment. When the skill has multiple kinds (e.g. standalone vs UoW-managed repository, list vs cursor pagination), give one template per kind under `### <kind>` subheadings.>

## Rules

<Numbered list of the rules specific to writing this artifact. Don't restate cross-cutting rules (typing, imports, packaging) — reference the cross-cutting skill instead. Each rule is one short paragraph or one bold-led bullet.>

## Inlined typing / import rules

<Optional but common. A 3–6 bullet slice of the cross-cutting rules that are most load-bearing for THIS artifact. The point is to save the agent from loading the full `general-typing-conventions` / `general-imports-conventions` when only a few rules apply. Bullet form, short.>

## Package wiring

<Optional. When the artifact requires updating an `__init__.py` re-export, point to `general-python-package` in one line. Do not restate the rules.>

## Hard stops

<Bullet list of "spec asks for X → stop, use `<other-skill>` (or fix the spec)". Each bullet is a single line. These are how the agent self-detects "I'm in the wrong skill".>
```

## Rules

1. **Match the section order exactly.** Agents scan section headings to decide what to read. Renaming or reordering breaks navigation.
2. **No custom frontmatter fields.** Only `name` and `description`. Information that doesn't fit in the description goes in the body.
3. **Templates are literal, not prose.** Show the entire file the agent should write. Use placeholders like `Foo`, `<root>`, `<subdomain>` consistently with CONVENTIONS.md.
4. **One artifact kind per skill.** If the skill would produce two unrelated artifact types, split into two skills. Producing 2–3 tightly-coupled files (command + handler; protocol + impl + integration) is fine.
5. **Cross-cutting rules are referenced, not restated.** Point to `general-typing-conventions`, `general-imports-conventions`, `general-python-package`, `general-logging`, `general-layered-architecture` rather than copying their rules. Inlined slices (3–6 bullets) are acceptable when load-bearing.
6. **Hard stops are explicit.** Every plausible "wrong-skill" case becomes a hard stop with a redirect. This is how agents recover from misclassification without overreaching.
7. **Use placeholder vocabulary.** `Foo` for the primary aggregate, `Bar` for the secondary, `myapp` for the project root. Never name a specific aggregate from the current application.
8. **No meta-notes for skill authors inside the body.** Lines like "Do not duplicate these rules here" are instructions for the author, not the agent — they pollute runtime context. Put author-side notes in the commit message or in CONVENTIONS.md.
9. **One paragraph descriptions read as sentences.** Not lists, not headings. The description is what an agent grep-scans to find the right skill.
10. **No orchestration, no spec-shape leakage.** A skill is knowledge injected into context, not an executor. It must not describe what invokes it, what it returns to a runner, or which inputs a manifest must carry — those are layers that belong to the runner and the manifest schema, not to the skill. The purity test: would a new live developer read this as onboarding docs? If they'd trip over a line, that line is a leaked layer — cut it.

## Skill modes (a navigational aid, not a new requirement)

Every skill in this catalog falls into one of four implicit **modes**. The section format is universal — modes don't add or remove sections; they just signal which sections will be load-bearing vs. ceremonial for this particular skill. Identify your mode before writing so the section content matches the pattern of skills already in the same mode.

### Producer (the default, ~25 skills)

Creates one or more new files. Section emphasis:

- `Template(s)` — full literal file content with placeholders. The agent copy-paste-modifies.
- `Package wiring` — present when a new module needs registering in an `__init__.py`.

Examples: `domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, `test-domain-entity`.

### Modifier (~5 skills)

Extends an existing file rather than creating a new one. Section emphasis:

- `Template(s)` — shows what gets inserted (a class body, a function, a decorator argument, a registry entry), not a whole file.
- `Package wiring` — usually absent; the file already lives in a package.

Examples: `infra-di-provider` (modifies `containers.py`), `restapi-error-responses` (adds decorator kwarg + optional `MIDDLEWARE_ERRORS` entry), `application-compensating-tx` (modifies a handler body), `domain-exception` in extend mode, `test-architecture-rule` (appends a test function).

### Bootstrap (~5 skills)

Produces a fixed set of files, runs **once per project**. Section emphasis:

- `Template(s)` — multiple full file templates under `###` subheadings, one per produced file.
- `When to use vs. neighbours` — explicitly notes "one-shot per project" and the catalog-ordering that other skills depend on.

Examples: `restapi-app-bootstrap`, `test-integration-isolation`, `test-integration-authed-client`, `test-discovery-invariants`, `domain-exception` in bootstrap mode.

### Reference (~6 skills)

Produces nothing — documents conventions other skills consult. Keeps `When to use vs. neighbours`, `Rules`, `Hard stops`; omits `Template(s)` and `Package wiring`.

Examples: `general-typing-conventions`, `general-imports-conventions`, `general-python-package`, `general-layered-architecture`, `general-logging`, `test-principles`.

### Picking a mode

| Question | If yes |
|----------|--------|
| Does the skill create a brand-new file from scratch each time it runs? | **Producer**. |
| Does it only extend or insert into a file that already exists? | **Modifier**. |
| Does it produce a fixed set of files that runs exactly once per project? | **Bootstrap**. |
| Does it produce no file at all — just rules other skills follow? | **Reference**. |

`meta-skill-author` is itself a **producer** (it produces a new `SKILL.md`). A skill that doesn't cleanly fit one mode probably mixes concerns — split it.

## Adapted format for non-producer skills

The body assumes the skill **produces an artifact**. Skills that describe cross-cutting conventions or meta-tasks adapt the format:

### `general-*` — cross-cutting convention skills

These document rules that apply continuously across the catalog (typing, imports, packaging, layering, logging). They are consulted, not invoked per artifact — so the producer-shaped sections don't apply.

**Required sections:**

- Frontmatter (`name`, `description`).
- One opening paragraph.
- `## When to use vs. neighbours` — list adjacent convention skills and the consuming layers ("Apply alongside every layer skill that touches X").
- `## Rules` — the actual rules. May be subdivided (e.g. per layer for `general-logging`).
- `## Hard stops` — the patterns the rule treats as non-negotiable. Existing skills used `Forbidden patterns` or `Hard rules` for this; normalize to `Hard stops` for consistency.

**Omitted:** `## Template(s)` and `## Package wiring` — neither applies when no file is produced.

### `process-*` and `meta-*` skills

A process skill (brainstorm, retrospective) and a meta skill (this one) may produce a file or not:

- If a file is produced (this skill writes a new SKILL.md), keep the full format.
- If no file is produced (a pure process), use the same shape as `general-*`.

### Universal rules (every skill, regardless of prefix)

- No custom frontmatter fields.
- No `## Revision` footer or author-side history block — that's author metadata that pollutes runtime context. Use git history.
- No meta-notes addressed to skill authors inside the body ("Do not duplicate these rules here").
- No orchestration sections (what the skill returns, who invokes it) and no manifest-input tables — those layers live in the runner and the manifest schema, not in the skill.
- Hard stops use the canonical phrasing: "X → stop, use `<other-skill>`" or "X → stop, <action>".

## Common pitfalls (read before writing)

- **Two skills, one prefix.** If your candidate skill description starts with "Apply when X *or* Y," you're combining two skills. Split.
- **Description that doesn't disambiguate.** "Apply when working with foos" is too vague. Compare to "Apply when adding or modifying a SQLAlchemy repository for an aggregate" — the latter excludes other foo-touching work explicitly.
- **Templates that document the rule instead of showing the file.** If the template has more comments than code, you're explaining the rule, not showing the output. Move the explanation to "Rules" and tighten the template.
- **Hard stops that aren't actually stops.** "Hard stop: think carefully before X" isn't a hard stop. The format is "X → stop, use Y."
- **A leaked orchestration or input-table section.** If you find yourself writing what the skill returns to a runner, or a table of fields a manifest must supply, stop — that's a different layer (see rule 10).

## After writing the file

Update `CONVENTIONS.md`:

1. Insert a one-line entry under the matching layer section (e.g. `### Domain`, `### Tests`).
2. Keep entries in the order they're conceptually used (`domain-entity` before `domain-value-object` before `domain-enum`, etc.).
3. The entry follows the format: `- \`<skill-name>\` — <one-sentence summary that complements, not duplicates, the description>.`

## Hard stops

- Spec asks for a skill that produces no file at all (pure documentation) → stop, that belongs in CONVENTIONS.md or a layer skill's body, not as its own skill.
- Spec asks for a skill that requires custom frontmatter fields → stop, use the body for the information.
- Spec proposes a skill whose description overlaps an existing one's by more than half its content → stop, this is an edit to the existing skill, not a new one.
- Spec uses application-specific names (`Order`, `Material`, `Invoice`) in templates → stop, replace with `Foo`/`Bar`.
