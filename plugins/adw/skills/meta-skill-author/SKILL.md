---
name: meta-skill-author
description: "Apply when adding a new skill to `skills/`. Produces one `<name>/SKILL.md` — plus sibling `<topic>.md` files when the theme is large enough to need a router — conforming to the catalog's canonical format: the `name` + `description` + `when_to_use` frontmatter (the last two drive auto-invocation, ≤1536 chars combined), the four-section body, and placeholder vocabulary, so agents reading the new skill apply it the same way they apply every existing one. Does not produce the agents that invoke skills (those live under `agents/`) or the spec format itself."
when_to_use: "Adding a brand-new skill to the knowledge catalog, or checking that a hand-written skill conforms to the canonical frontmatter, the four-section body, and the single-topic-vs-router shape rule. Not for editing an existing skill (edit it directly) or sweeping cross-references after a rename."
---

# Meta — Skill Author

A skill in this catalog is **theme-narrow**: it covers one coherent theme an agent can pick by its `description` / `when_to_use` (e.g. `domain-model`, `restapi`, `testing-unit`). A theme may span several closely-related artifacts: a small theme carries them in one body, a large one keeps a thin `SKILL.md` router plus one `<topic>.md` per artifact (both shapes below). Skills are read by agents (or humans) as reference knowledge; the skill's job is to show how the right file(s) are written. Uniformity matters more than expressiveness — an agent that has read one skill should be able to apply any other.

This skill produces one new `SKILL.md` (plus its topic files, if the theme needs them). It does **not** modify other skills (that's an audit task), produce agents (`agents/`), or design the spec format.

## When to use vs. neighbours

- Adding a brand-new skill → this skill.
- Editing an existing skill to fix a rule or template → not this skill; just edit the file directly.
- Sweeping cross-references after a rename → not this skill; that's an audit task.
- Documenting a process (brainstorm, retrospective) → still this skill, but use the `process-` or `meta-` prefix; the format adapts (no "Templates" section, but every other section still applies).

## File location

```
skills/<full-skill-name>/
    SKILL.md          # always: frontmatter + either the whole body (single-topic)
                      #         or the router (multi-topic theme)
    <topic>.md        # multi-topic theme only: one file per artifact, no frontmatter
```

The directory name **is** the skill name (e.g. `domain-model/SKILL.md`). One `SKILL.md` per directory, and it is the only file with frontmatter — the sibling files a large theme bundles are topic files, not skills. Any other sibling asset is rare; explain in the body why it exists.

## Frontmatter (exact shape — no custom fields)

```yaml
---
name: <full-skill-name>
description: <one paragraph — see rules below>
when_to_use: <one or two sentences naming the trigger situations — drives auto-invocation>
---
```

Only `name`, `description`, and `when_to_use`. `description` + `when_to_use` are the two fields the runtime lists for auto-invocation, so keep them ≤1536 characters combined. **No** other custom fields like `component:`, `produces:`, `layer:`. Tooling does not parse those; they make the format look variable.

Frontmatter belongs to `SKILL.md` alone. A bundled `<topic>.md` starts at its `# ` title with no frontmatter block — a stray `name:` / `description:` there would advertise a phantom skill in the catalog listing and split one theme into two auto-invocation entries.

Description rules:

- One paragraph (can be 2–4 sentences). No bullets, no line breaks.
- **First clause:** "Apply when …" — the trigger condition. The agent should be able to decide whether to invoke this skill from this clause alone.
- **Middle:** what the skill produces — name the file(s) and key shape.
- **End:** explicit "Does not produce X — use `<other-skill>`" pointers to adjacent skills. This is what makes the catalog navigable.
- No application-specific names (no `Material`, no `Order`): use the placeholder vocabulary → **read `CONVENTIONS.md` now**.
- Read like a sentence; not a heading or list.

## Body — the canonical sections

Every skill has these sections, in this order, with these exact headings. Four are required; two (`Inlined typing / import rules`, `Package wiring`) are optional helpers included only when load-bearing.

```markdown
# <Title> — usually `<Prefix> — <Concept>` or `<Concept>` alone

<One short opening paragraph: what the skill produces and its hardest boundary.>

## When to use vs. neighbours

<3–5 bullet points contrasting this skill with each adjacent one. Each bullet is one line: "X → `skill-name`." Goal: an agent that misclassified the work sees its real home immediately.>

## Template(s)

<One or more literal file templates with placeholder names — the placeholder vocabulary → **read `CONVENTIONS.md` now**. Show the entire file content, not a fragment. When the skill has multiple kinds (e.g. standalone vs UoW-managed repository, list vs cursor pagination), give one template per kind under `### <kind>` subheadings.>

## Rules

<Numbered list of the rules specific to writing this artifact. Don't restate cross-cutting rules (typing, imports, packaging) — reference the cross-cutting skill instead. Each rule is one short paragraph or one bold-led bullet.>

## Inlined typing / import rules

<Optional but common. A 3–6 bullet slice of the cross-cutting rules that are most load-bearing for THIS artifact. The point is to save the agent from loading the full `general-typing-conventions` / `general-imports-conventions` when only a few rules apply. Bullet form, short.>

## Package wiring

<Optional. When the artifact requires updating an `__init__.py` re-export, point to `general-python-package` in one line. Do not restate the rules.>

## Hard stops

<Bullet list of "spec asks for X → stop, use `<other-skill>` (or fix the spec)". Each bullet is a single line. These are how the agent self-detects "I'm in the wrong skill".>
```

## Where the body lives — single-topic skill vs. router + topics

The four-section body above is invariant. What you decide is which of two shapes carries it.

**Single-topic skill.** One `SKILL.md`: frontmatter + one four-section body. A theme covering a few artifacts an author reaches for together keeps each under its own `## ` heading inside that single body, still four-sectioned. This is the default.

**Multi-topic theme (router + bundled topics).** `SKILL.md` shrinks to a router and each artifact's four-section body moves into a sibling `<topic>.md` the agent reads on demand. The theme is still **one** skill and one auto-invocation entry.

**The threshold: a `SKILL.md` that would exceed ~500 lines becomes a router.** Below that, stay single-topic however many artifacts the theme covers — the number of artifacts is not a trigger, size is. Past ~500 lines a single artifact's body is a minority of what gets injected, so an agent writing one artifact pays several times over for knowledge it will not use; below it the whole theme is cheaper to inject than a routing round-trip is to risk.

The router's shape:

```markdown
---
name: <full-skill-name>
description: <unchanged — the theme's trigger, as for any skill>
when_to_use: <unchanged>
---

# <Title>

<One short opening paragraph: what this theme covers and its hardest boundary.>

## When to use vs. neighbours

<2–4 bullets contrasting this THEME with adjacent themes, as in any skill.>

<Then one imperative line per topic — the router's load-bearing content:>

- <Writing artifact A (naming the sub-decisions it covers)> → **read `a.md` now**.
- <Writing artifact B> → **read `b.md` now**.

## <Cross-topic material — only what no single topic owns>

<E.g. a tier's constitution: pyramid, naming, fixture discipline. A long one may become
its own `constitution.md` with an imperative pointer like any other topic.>

## Hard stops

<Theme-level redirects only: "spec asks for X → stop, use `<other-skill>`". Artifact-level
hard stops stay in their topic file.>
```

Rules for this shape:

- **Pointers are instructions, not cross-references** → §Pointer form below.
- **Every topic is pointed at exactly once, and every pointer resolves.** An unpointed topic file is dead knowledge; a dangling pointer sends the agent to nothing.
- **A topic file carries the full four-section body** (plus the optional helpers when load-bearing) and **no frontmatter**.
- **Name the file after the artifact, not the theme:** `restapi/endpoint.md`, never `restapi/restapi-endpoint.md`.
- **Nothing else changes:** the theme keeps its name and its frontmatter.

## Pointer form

Every cross-reference a skill writes — to a section of itself, to another theme, to a bundled topic — takes one of four forms. One rule generates all four: **a pointer is qualified by its theme, except when it points inside the same file.**

| Case | Form |
|---|---|
| a section of this same file | → §`<Heading>` below (or above) |
| a single-topic theme (`architecture`, `python-style`, `conventions`, `domain-model`, `domain-ports`) | → `architecture` §`<Heading>` |
| a topic file of another theme | → `restapi` `endpoint.md` |
| a router pointing at its own topic | → **read `endpoint.md` now** |

Why the third case names the theme as well as the file: a topic file is injected to nobody, not even when its theme is preloaded. A reader who has the theme opens the file directly; a reader who does not invokes the theme, gets its router, and the router's imperative sends them to the same file. Both branches land in one place.

Why the fourth case is an imperative and not a name: only `SKILL.md` is injected, so a bundled topic reaches the agent only if the agent opens it. A soft cross-reference — "see also `endpoint.md`", "more detail in `endpoint.md`" — leaves the agent writing the artifact from the router's summary and never loading the rules.

## Rules

1. **Match the section order exactly.** Agents scan section headings to decide what to read. Renaming or reordering breaks navigation.
2. **No custom frontmatter fields.** Only `name`, `description`, and `when_to_use`. Information that doesn't fit in the description goes in the body.
3. **Templates are literal, not prose.** Show the entire file the agent should write. Placeholders (`Foo`, `<root>`, `<subdomain>`) are used consistently → **read `CONVENTIONS.md` now**.
4. **One theme per skill.** A skill covers one coherent theme, which may span several closely-related artifacts — held in one body, or in bundled topic files behind a router once the theme outgrows the threshold. "One theme" is one auto-invocation entry, not necessarily one file. If a candidate would cover two unrelated themes, split it into two skills. If its hard stops fire, the task asked for the wrong artifact — switch skills, don't stretch this one.
5. **Cross-cutting rules are referenced, not restated.** Point to `architecture` (layers, packages, imports), `python-style` (typing, logging), and `conventions` (derivation) rather than copying their rules. Inlined slices (3–6 bullets) are acceptable when load-bearing. Toolchain commands are never restated — cite the project's toolchain config.
6. **Hard stops are explicit.** Every plausible "wrong-skill" case becomes a hard stop with a redirect. This is how agents recover from misclassification without overreaching.
7. **Use placeholder vocabulary.** `Foo` for the primary aggregate, `Bar` for the secondary, `myapp` for the project root. Never name a specific aggregate from the current application.
8. **No meta-notes for skill authors inside the body.** Lines like "Do not duplicate these rules here" are instructions for the author, not the agent — they pollute runtime context. Put author-side notes in the commit message.
9. **One paragraph descriptions read as sentences.** Not lists, not headings. The description is what an agent grep-scans to find the right skill.
10. **No orchestration, no process leakage.** A skill is knowledge injected into context, not an executor. It must not describe what invokes it, what it returns to a caller, the change cycle, criteria files, or "report to the coordinator" — those are the orchestration layer (agents and commands), not the skill. The purity test: would a new developer read this as onboarding docs? If they'd trip over a line, that line is a leaked layer — cut it.

## Skill modes (a navigational aid, not a new requirement)

Every skill in this catalog falls into one of four implicit **modes**. The section format is universal — modes don't add or remove sections; they just signal which sections will be load-bearing vs. ceremonial for this particular skill. Identify your mode before writing so the section content matches the pattern of skills already in the same mode.

### Producer (the common case)

Creates one or more new files. Section emphasis:

- `Template(s)` — full literal file content with placeholders. The agent copy-paste-modifies.
- `Package wiring` — present when a new module needs registering in an `__init__.py`.

Examples: the producing topics of `domain-model`, `application`, `infra-persistence`, `restapi`, `testing-unit`.

### Modifier

Extends an existing file rather than creating a new one. Section emphasis:

- `Template(s)` — shows what gets inserted (a class body, a function, a decorator argument, a registry entry), not a whole file.
- `Package wiring` — usually absent; the file already lives in a package.

Examples: the DI-provider topic of `infra-integration` (modifies `containers.py`), the error-responses topic of `restapi` (adds a decorator kwarg), the compensating-tx topic of `application` (shapes a handler body), the architecture-rule topic of `testing-unit` (appends a test function).

### Bootstrap

Produces a fixed set of files, runs **once per project**. Section emphasis:

- `Template(s)` — multiple full file templates under `###` subheadings, one per produced file.
- `When to use vs. neighbours` — explicitly notes "one-shot per project" and the catalog-ordering that other skills depend on.

Examples: the app-bootstrap topic of `restapi`; the isolation, authed-client, and discovery-invariant topics of `testing-integration`.

(Note: the exception catalog `domain/exceptions.py` is a single append-only file — a new exception appends one class, it is not created once as a bootstrap file.)

### Reference

Produces nothing — documents conventions other skills consult. Keeps `When to use vs. neighbours`, `Rules`, `Hard stops`; omits `Template(s)` and `Package wiring`.

Examples: `conventions`, `architecture`, `python-style`.

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

### Reference / cross-cutting convention skills (`conventions`, `architecture`, `python-style`)

These document rules that apply continuously across the catalog (derivation, layering, packaging, imports, typing, logging). They are consulted, not invoked per artifact — so the producer-shaped sections don't apply.

**Required sections:**

- Frontmatter (`name`, `description`, `when_to_use`).
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

- No custom frontmatter fields, and frontmatter in `SKILL.md` only — a bundled topic file has none.
- No `## Revision` footer or author-side history block — that's author metadata that pollutes runtime context. Use git history.
- No meta-notes addressed to skill authors inside the body ("Do not duplicate these rules here").
- No orchestration sections (what the skill returns, who invokes it) and no spec-input tables — those layers live in the agents/commands and the spec format, not in the skill.
- Hard stops use the canonical phrasing: "X → stop, use `<other-skill>`" or "X → stop, <action>".

## Common pitfalls (read before writing)

- **Two skills, one prefix.** If your candidate skill description starts with "Apply when X *or* Y," you're combining two skills. Split.
- **Description that doesn't disambiguate.** "Apply when working with foos" is too vague. Compare to "Apply when adding or modifying a SQLAlchemy repository for an aggregate" — the latter excludes other foo-touching work explicitly.
- **Templates that document the rule instead of showing the file.** If the template has more comments than code, you're explaining the rule, not showing the output. Move the explanation to "Rules" and tighten the template.
- **Hard stops that aren't actually stops.** "Hard stop: think carefully before X" isn't a hard stop. The format is "X → stop, use Y."
- **A leaked orchestration or input-table section.** If you find yourself writing what the skill returns to a caller, or a table of fields a spec must supply, stop — that's a different layer (see rule 10).
- **A soft pointer in a router.** "See also `endpoint.md`" or "more detail in `endpoint.md`" leaves the agent writing the artifact from the router's summary, because only `SKILL.md` is injected. Every pointer is imperative and names the file: "→ **read `endpoint.md` now**".
- **A router that keeps summarising its topics.** If the router explains how the artifact is written, the rules now live in two places and will drift. The router routes; the topic file teaches.

## Hard stops

- Spec asks for a skill that produces no file at all (pure documentation) → stop, that belongs in a layer skill's body, not as its own skill.
- Spec asks for a skill that requires custom frontmatter fields → stop, use the body for the information.
- Spec proposes a skill whose description overlaps an existing one's by more than half its content → stop, this is an edit to the existing skill, not a new one.
- Spec uses application-specific names (`Order`, `Material`, `Invoice`) in templates → stop, replace with `Foo`/`Bar`.
- A bundled topic file is asked to carry its own `name:` / `description:` frontmatter → stop, that would mint a phantom skill; frontmatter lives in `SKILL.md` alone.
- The theme's `SKILL.md` is heading past ~500 lines and another `## ` artifact section is being appended → stop, convert it to a router with one `<topic>.md` per artifact.
- A second theme is being minted just to shrink a large one (`restapi-endpoint` beside `restapi`) → stop, that is a bundling job inside the existing theme, not a new auto-invocation entry.
