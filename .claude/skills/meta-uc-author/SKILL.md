---
name: meta-uc-author
description: Apply when hand-authoring a new use-case file under `specs/use-cases/`. Produces one `UC-NN-<slug>.md` in the narrative, BA-dictated style — title line, Actor / Module header, Description, one or more Main flow blocks, Alternative flows, business rules, Notes. Preserves the "thinking-out-loud" tone (TBDs, "discuss with X", cross-references to other UCs) because a `/spec` change (and any future upstream stage) reads those signals to surface design questions. Does not produce specs, groupings, or any code.
when_to_use: Hand-authoring a brand-new use case in the BA corpus under `specs/use-cases/`. Not for editing an existing UC (edit it directly) or for bulk extraction from a PDF (a future upstream stage, not part of the v3 core today).
---

# Meta — Use-Case Author

A use case in `specs/use-cases/` is a **business-analyst narrative**: one feature described the way a BA would dictate it after a product conversation, including the parts that aren't decided yet. It is the raw input a `/spec` change reads (and, in future, upstream extraction / ingestion / refinement stages would read); those readers depend on the file shape (heading order, A-numbered alternatives, an explicit rules section) and on the narrative signals (TBDs, "discuss with X", cross-UC references) to do their job.

This skill produces one new use-case file. It does not interpret or normalize the content the way the downstream agents do — its job is to write a UC that *looks like* the ones already in `specs/use-cases/`.

## When to use vs. neighbours

- Adding a brand-new use case to `specs/use-cases/` → this skill.
- Extracting UCs in bulk from an existing PDF / export → a future upstream extraction stage, not part of the v3 core today (and not this skill).
- Editing an existing UC to fix a rule or add a flow → not this skill; just edit the file directly.
- Synthesizing design or grouping UCs into a change → the `/spec` session and downstream stages, not this skill.

## File location

```
specs/use-cases/UC-<NN>-<slug>.md
```

The filename is the canonical identifier — downstream agents grep by `UC-<NN>` and key their artifacts off the slug. Use exactly one hyphen between number and slug, and lowercase kebab-case for the slug.

## Template

````markdown
# UC-<NN>: <Title>

**Actor**: <Primary actor (qualifier), secondary actor (qualifier)>
**Module**: <Area> / <Sub-area>

## Description

<2–4 paragraphs. First paragraph: why this exists and the two-sentence overview
of what the user does. Second paragraph: any product / engineering debate worth
preserving — "we considered X but decided Y", "security wants Z", "the team had
a long discussion about W". Third paragraph (optional): how this UC relates to
neighbouring UCs (e.g. "the same modal as UC-02 is reused" or "this UC adds a
new action type to the activity-history aggregate that UC-04 already uses").>

## Main flow<optional " (<variant name>)" — repeat the whole section per variant>

1. <Imperative step naming the actor action.> System <does the response>.
2. <Next step.> The form has fields:
   - **Field name** (required|optional, type / validation hint).
   - **Field name** (...).
3. <User action.> System validates:
   - <One bullet per validation rule.>
4. <Continue. Inline implementation hints are fine and encouraged — "we use
   argon2", "JWT signed with the server-side secret", "stored in `otp_codes`
   table" — but keep them BA-loose, not prescriptive.>
N. <Final step.> System closes the modal / refreshes the page / shows a toast.

## Alternative flows

- **A1**: <One edge case in 1–4 sentences. If the team hasn't decided how to
  handle it, end with "**TBD with <stakeholder>**" or "(<question>? TBD.)" —
  downstream refinement reads these as open questions.>
- **A2**: <...>
- **A3**: <...>

## Business Rules

- <One invariant per bullet. Mix hard rules ("only admins can rename tags")
  with soft ones ("we don't enforce a state machine on status — the team
  wants the flexibility").>
- <Cross-cutting rules that recur across UCs — like a visibility rule — should
  be stated here AND noted as "(applies everywhere, see also UC-XX)" so the
  a downstream stage can lift it into the project design.>
- <Known simplifications go here too: "we don't have teams yet as a separate
  object — for now a manager's team is `users where manager_id = manager.id`.">

## Notes

- <Informal bullets. Technical hints ("autocomplete is debounced 200ms"),
  performance considerations, out-of-scope mentions ("bulk reassignment is
  out of scope for this UC"), "discuss with X" markers, references to UCs
  that don't exist yet ("see UC-12 if/when it's written").>
- <Anything that doesn't belong in a numbered flow step but informs the
  downstream design decision. Downstream stages read this section
  carefully.>
````

If the UC has a single main flow (no web/extension/admin variants), drop the parenthesized variant name and just write `## Main flow`. If it has multiple variants, repeat the whole `## Main flow (<name>)` section once per variant — do not nest variants under a single heading.

## Rules

1. **Title is a noun phrase, not a sentence.** `Archive a lead`, `Reassign a lead to another sales rep`, `Sign in to LeadDesk` — not `User archives a lead` or `As a rep I want to archive`.
2. **Actor line names roles, not individuals.** Qualify roles in parentheses when the role's scope matters (`Sales rep (own leads), manager (team leads)`). Roles must match the role vocabulary already used in the existing UCs.
3. **Module line is a `Area / Sub-area` slash-path.** It groups UCs in the index; mirror an existing module path when this UC extends one (e.g. `Leads / Lead editing` alongside `Leads / Lead capture`).
4. **Description is narrative, not bullets.** Two to four paragraphs of prose. Include the product debate ("we considered X but decided Y") — downstream stages use it to surface design questions. Do not summarize the flow as a list here; that's what `## Main flow` is for.
5. **Main-flow steps are numbered and imperative.** Each step names a user action and the system's response in one or two sentences. Nested bullets are fine for field lists and validation lists.
6. **Field lists use bold field names and a parenthetical type / required hint.** `**Company name** (required, free text)` — mirror the shape used by UC-02 so a later stage can lift entity attributes directly.
7. **Alternative flows are labelled `A1`, `A2`, …** in the order they appear. Each describes one edge case in 1–4 sentences. TBDs are encouraged where the product hasn't decided — write them verbatim as `**TBD**` or `(<question>? TBD.)`.
8. **Business rules are bullets, one invariant each.** Include hard rules, soft rules, known simplifications, and cross-cutting rules that recur in other UCs. A rule that applies in more than one UC should say so: `(applies everywhere, see also UC-XX)`.
9. **Notes is the catch-all for informal context.** Performance hints, out-of-scope markers, "discuss with X", forward references to UCs that don't exist yet. Anything that informs the design but doesn't fit a flow step or a rule.
10. **Cross-reference other UCs by number.** `see UC-02`, `same picker as UC-03`, `referenced in UC-04 A4`. Use `UC-XX` literal form so grep finds them.
11. **Do not invent acceptance criteria, Gherkin scenarios, or formal preconditions / postconditions.** This catalog deliberately avoids that ceremony — the BA's narrative is the spec, and downstream stages do the normalization.
12. **The business-rules heading is `## Business Rules` for new UCs.** The existing catalogue mixes English and Russian (`## Бизнес-правила`); existing files keep whatever they contain, but new files this skill writes should use English unless the user explicitly asks otherwise.

## Hard stops

- Spec asks for formal Gherkin / `Given-When-Then` scenarios → stop, this catalog uses narrative flows.
- Spec asks for explicit acceptance criteria, preconditions, postconditions, or non-functional requirements as named sections → stop, those signals live inline in `## Business Rules` and `## Notes`.
- Spec asks for a use case that exclusively documents UI styling, copywriting, or visual design → stop, those don't drive downstream design and shouldn't be UCs.
- Spec asks to overwrite an existing `UC-NN-*.md` file → stop, that's an edit, not a new UC; either edit the file directly or pick the next free number.
- Spec asks to write multiple UCs in one invocation → stop, one UC per invocation. Loop the skill instead.
- Spec asks for a **filename** other than `UC-NN-<slug>.md` → stop, the filename convention is load-bearing for every downstream agent. The **directory**, however, is the corpus's `use-cases/` dir: `specs/use-cases/` by default, but a sandbox or a second project may set a different **corpus root** (e.g. `specs/dryrun/use-cases/`) — write `UC-NN-<slug>.md` under the corpus root the invocation names, defaulting to `specs/use-cases/`. Only the filename shape is fixed; the corpus root is configurable.
