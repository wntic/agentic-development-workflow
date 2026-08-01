---
name: meta-skill-author
description: Apply when adding a new skill to the catalog. Produces one `<name>/SKILL.md` in the canonical format — the frontmatter that drives auto-invocation, the four-section body, and the shared placeholder vocabulary — so a reader who has applied one skill can apply the new one the same way.
when_to_use: Adding a brand-new skill, or checking that a hand-written one conforms to the canonical frontmatter and the four-section body. Not for editing an existing skill (edit it directly) or for sweeping cross-references after a rename.
---

# Meta — Skill Author

A skill is **narrow**: it covers one artifact, or one set of artifacts that always arrive together.
Skills are read as reference knowledge; the job is to show how the right file gets written. Uniformity
matters more than expressiveness — a reader who has applied one skill should be able to apply any other.

This skill produces one new `SKILL.md`. It does **not** edit other skills (that is an audit task) or
design the change format.

**Read the sibling `CONVENTIONS.md` in this skill's own directory before writing anything.** It carries
the catalog's shared placeholder vocabulary (`Foo`, `Bar`, `myapp` and the names derived from them), the
index of what each existing skill covers, and the two standing catalog decisions — what is deliberately
out of scope, and why repositories are not split read/write. Only this file is loaded automatically; the
sibling is not, so open it rather than working from this summary of it.

## When to use vs. neighbours

- Adding a brand-new skill → this skill.
- Editing an existing skill to fix a rule or a template → not this skill; edit the file directly.
- Sweeping cross-references after a rename → not this skill; that is an audit task.
- Documenting a process rather than an artifact → still this skill; the format adapts (no `Template(s)`
  section, every other section still applies).

## File location

```
skills/<skill-name>/SKILL.md
```

The directory name **is** the skill name. One `SKILL.md` per directory, plus sibling files when the skill
needs them — this skill's own `CONVENTIONS.md` is one. A theme large enough that its body would exceed
~500 lines takes sibling topic files alongside `SKILL.md`, which then becomes navigation — but reach for that only when the body genuinely does not fit, because only `SKILL.md` is
loaded when a skill is preloaded, so a sibling file is reached by an explicit instruction to read it.

## Frontmatter

Every field is optional. `description` is what makes the skill findable, so in practice it is required.

```yaml
---
name: <skill-name>
description: <what it covers and when — see rules below>
when_to_use: <trigger phrases and example requests; appended to description>
paths: <optional glob(s) limiting automatic activation>
---
```

The fields this catalog uses, and why:

- **`name`** — the skill's name. Keep it identical to the directory name.
- **`description`** — what the skill covers and when to apply it. This is what gets matched to decide
  whether to load the skill.
- **`when_to_use`** — trigger phrases and example requests. Appended to `description` for matching
  purposes, which is why the two are budgeted together.
- **`paths`** — glob patterns that limit automatic activation to work touching matching files. Use it
  when a skill is unmistakably scoped to one part of the tree; leave it off for cross-cutting skills
  that always apply.

Two more exist and are deliberately **not** used here: `user-invocable: false` hides a skill from the
`/` menu, and `disable-model-invocation: true` blocks automatic loading. The second has a trap — it
*also* prevents the skill from being preloaded, so a skill carrying it can only ever be invoked by hand.

Description rules:

- **Budget: `description` + `when_to_use` together are capped at 1536 characters**, and past that the
  text is cut. Aim well under it — around 300 characters for the two combined is the working target,
  because every skill's entry competes for one shared listing budget, and when that budget overflows
  descriptions are dropped outright, starting with the least-used skills. A skill whose description got
  dropped is a skill that will not be found.
- **Put the key case first.** The first clause decides whether the skill is loaded, so it carries the
  trigger: what artifact, what situation.
- **Negative routing goes in the body, not here.** "Does not produce X — use `<other-skill>`" belongs
  in `When to use vs. neighbours`. It is the most expensive text to keep in a description and the first
  to be cut.
- One paragraph, no bullets, no line breaks. It should read as a sentence.
- No application-specific names (no `Material`, no `Order`). Use the placeholder vocabulary from the
  sibling `CONVENTIONS.md`.

## Body — the canonical sections

Every skill has these sections, in this order, with these exact headings — templates have one
allowance, stated in rule 1. Four sections are required; two (`Inlined typing / import rules`,
`Package wiring`) are optional helpers, included only when load-bearing.

```markdown
# <Title> — usually `<Prefix> — <Concept>` or `<Concept>` alone

<One short opening paragraph: what the skill covers and its hardest boundary.>

## When to use vs. neighbours

<3–5 bullets contrasting this skill with each adjacent one. Each bullet is one line: "X → `skill-name`."
Goal: a reader who misclassified the work sees its real home immediately. This is also where the
negative routing lives that the description deliberately leaves out.>

## Template(s)

<One or more literal file templates with placeholder names, from the sibling CONVENTIONS.md. Show
the entire file content, not a fragment. When the skill covers several kinds (standalone vs UoW-managed
repository, list vs cursor pagination), give one template per kind under `### <kind>` subheadings.>

## Rules

<Numbered list of the rules specific to writing this artifact. Don't restate cross-cutting rules
(typing, imports, packaging) — reference the cross-cutting skill instead. Each rule is one short
paragraph or one bold-led bullet.>

## Inlined typing / import rules

<Optional but common. A 3–6 bullet slice of the cross-cutting rules most load-bearing for THIS
artifact, so the reader need not pull the full cross-cutting skill when only a few rules apply.>

## Package wiring

<Optional. When the artifact requires updating an `__init__.py` re-export, point to
`architecture` in one line. Do not restate the rules.>

## Hard stops

<Bullet list of "asked for X → stop, use `<other-skill>` (or fix the request)". One line each. These
are how a reader self-detects "I'm in the wrong skill".>
```

## Rules

1. **Match the section order exactly — with one allowance for templates.** Section headings are how a
   reader decides what to read, so renaming or reordering breaks navigation. The allowance: a skill
   covering **several artifacts** may group its templates by topic instead of collecting them under one
   `## Template(s)` — topical `##` sections with the templates as `###` subheadings inside. What makes
   that form legal is a single condition: **the heading names the artifact** (`## The Table`,
   `## The container`, `## Upload templates`), never the subject of a discussion (`## Notes`,
   `## Background`). An artifact name answers "is this the section I need?" as well as `Template(s)`
   does; a topic name does not. Every other section keeps its exact heading and its place in the order.
   A skill covering **one** artifact keeps the single `## Template(s)`, and a Reference skill still
   omits it — neither changes.
   The allowance rests on one observation: a skill already written in the topical form was loaded and
   applied, and no template went unfound. That is evidence of success, not a test of failure. If a
   template is ever missed because it sat under a topical heading, the allowance is withdrawn and the
   single `## Template(s)` becomes the only form.
2. **Keep the body concise.** Once a skill is loaded its body stays in context for the rest of the
   session, so every line is a recurring cost. State what to do rather than narrating how or why. A
   body past ~500 lines is the signal to split into sibling topic files.
3. **Templates are literal, not prose.** Show the entire file to be written. Use the placeholders the
   sibling `CONVENTIONS.md` defines — `Foo`, `<root>`, `<subdomain>` — and read that file for the full
   set rather than guessing at it.
4. **One artifact kind per skill, or one set that always arrives together.** Two unrelated artifact
   types means two skills. Producing 2–3 tightly-coupled files (command + handler; protocol + adapter)
   is fine, and so is one skill covering several artifacts a single change always adds at once.
5. **Cross-cutting rules are referenced, not restated.** Point to the cross-cutting skill rather than
   copying its rules. An inlined slice of 3–6 bullets is acceptable when load-bearing.
6. **Hard stops are explicit.** Every plausible wrong-skill case becomes a hard stop with a redirect.
   This is how a reader recovers from misclassification without overreaching.
7. **Use placeholder vocabulary.** `Foo` for the primary aggregate, `Bar` for the secondary, `myapp`
   for the project root. Never name a real aggregate from the application at hand.
8. **No author-side notes in the body.** Lines like "do not duplicate these rules here" address the
   author, not the reader, and they cost context on every load. Put them in the commit message.
9. **A skill must not know what invokes it.** No mention of who calls it, what it reports back, or what
   inputs some caller must supply — those belong to layers outside the skill. The purity test: would a
   new developer read this as onboarding documentation? If they would trip over a line, that line is a
   leaked layer — cut it.

## Skill shapes (a navigational aid, not a requirement)

Every skill falls into one of four shapes. The section format is universal — shapes add and remove
nothing; they signal which sections will be load-bearing rather than ceremonial. Identify the shape
before writing, so the content matches skills already in the same shape.

### Producer — the default

Creates one or more new files. Emphasis: `Template(s)` carries full literal file content with
placeholders; `Package wiring` appears when a new module needs registering in an `__init__.py`.

Examples: `domain-model`, `application`, `infra-persistence`, `restapi-endpoint`,
`testing-unit-domain`.

### Modifier

Extends an existing file rather than creating one. Emphasis: `Template(s)` shows what gets inserted — a
class body, a function, a decorator argument — not a whole file; `Package wiring` is usually absent
because the file already lives in a package.

Examples: `infra-wiring` (modifies `containers.py`), `restapi-route-contracts` (adds a decorator
argument), `patterns` (shapes a handler body), `test-architecture-rule` (appends a test
function).

### Bootstrap

Produces a fixed set of files, once per project. Emphasis: `Template(s)` carries several full file
templates under `###` subheadings, one per file; `When to use vs. neighbours` says plainly that it is
one-shot and names what other skills depend on it having run.

Examples: `restapi-app`, `testing-integration-setup`, `test-discovery-invariants`.

### Reference

Produces no file — documents conventions other skills consult. Keeps `When to use vs. neighbours`,
`Rules` and `Hard stops`; omits `Template(s)` and `Package wiring`.

Examples: `conventions`, `architecture`, `python-style`, `test-principles`.

### Picking a shape

| Question | If yes |
|---|---|
| Does it create a brand-new file each time? | **Producer** |
| Does it only extend a file that already exists? | **Modifier** |
| Does it produce a fixed set of files, once per project? | **Bootstrap** |
| Does it produce no file at all — just rules others follow? | **Reference** |

A skill that fits no shape cleanly probably mixes concerns; split it.

## Universal rules, whatever the shape

- No `## Revision` footer and no author history block — that is author metadata paid for on every load.
  Use git history.
- No section describing what the skill returns or who invokes it (rule 9).
- Hard stops use the canonical phrasing: "X → stop, use `<other-skill>`" or "X → stop, <action>".
- A reference skill omits `Template(s)` and `Package wiring`; everything else keeps all four sections,
  under the template allowance of rule 1.

## Common pitfalls

- **Two skills wearing one name.** A description that reads "apply when X *or* Y" is two skills. Split.
- **A description that does not disambiguate.** "Apply when working with foos" is too vague. Compare
  "Apply when adding or modifying a repository adapter for an aggregate on a relational store", which
  excludes the other foo-touching work by construction.
- **A description carrying the whole neighbour map.** Every "does not produce" clause is budget spent
  where it is cut first. Move them to `When to use vs. neighbours`.
- **Templates that document the rule instead of showing the file.** More comments than code means the
  rule is being explained. Move the explanation to `Rules` and tighten the template.
- **Hard stops that are not stops.** "Think carefully before X" is not a hard stop. The form is
  "X → stop, use Y".
- **A leaked layer.** Writing what the skill hands back to something else, or a table of inputs some
  caller must supply, is rule 9 being broken.

## After writing the file

Add a one-line entry to the index in the sibling `CONVENTIONS.md`, under the matching layer heading and
in the order the skills are conceptually used, in the form:
`` - `<skill-name>` — <one sentence that complements, not duplicates, the description>. ``

## Hard stops

- Asked for a skill whose whole content is a handful of rules already stated by an existing skill →
  stop; that is an edit to the existing skill, not a new one.
- Asked for a skill whose description overlaps an existing one's by more than half → stop, same reason.
- Asked for a skill built around a frontmatter field this catalog does not use → stop, put the
  information in the body and keep the frontmatter to the four fields above.
- Templates use application-specific names (`Order`, `Material`, `Invoice`) → stop, replace with
  `Foo`/`Bar`.
