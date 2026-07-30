---
name: meta-uc-author
description: Apply when hand-authoring a new use case under `specs/use-cases/`. Produces one `UC-NN-<slug>.md` in the narrative, BA-dictated style — title, Actor / Module header, Description, one or more Main flow blocks, Alternative flows, Business Rules, Notes — keeping the thinking-out-loud tone (TBDs, "discuss with X", cross-references) that later refinement reads as open questions.
when_to_use: Writing a brand-new use case in the BA corpus by hand. Not for editing an existing UC (edit it directly) and not for bulk extraction from a PDF or export.
---

# Meta — Use-Case Author

A use case in `specs/use-cases/` is a **business-analyst narrative**: one feature described the way a BA
would dictate it after a product conversation, including the parts that are not decided yet. Its shape is
load-bearing — heading order, A-numbered alternatives, an explicit rules section — and so are its
narrative signals: TBDs, "discuss with X", references to other UCs. Whoever refines this into a concrete
change later reads those signals to find the open questions, so preserving them matters more than tidying
them away.

This skill writes one new use-case file. It does not normalize or resolve the content — its job is to
produce a UC that *looks like* the ones already in the corpus.

## When to use vs. neighbours

- Hand-authoring a brand-new use case → this skill.
- Editing an existing UC to fix a rule or add a flow → not this skill; edit the file directly.
- Bulk-extracting use cases out of a PDF or an export → not this skill.
- Turning a UC into a concrete change, or grouping UCs → not this skill; a UC is the raw narrative, and
  what happens to it afterwards is a different activity entirely.

## File location

```
specs/use-cases/UC-<NN>-<slug>.md
```

The filename is the canonical identifier — the corpus is grepped by `UC-<NN>` and cross-references are
written in that form. Exactly one hyphen between number and slug; lowercase kebab-case for the slug.

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
  these are read later as open questions.>
- **A2**: <...>
- **A3**: <...>

## Business Rules

- <One invariant per bullet. Mix hard rules ("only admins can rename tags")
  with soft ones ("we don't enforce a state machine on status — the team
  wants the flexibility").>
- <A cross-cutting rule that recurs across UCs — like a visibility rule —
  should be stated here AND marked "(applies everywhere, see also UC-XX)" so
  it can be lifted into the project-wide design later.>
- <Known simplifications go here too: "we don't have teams yet as a separate
  object — for now a manager's team is `users where manager_id = manager.id`.">

## Notes

- <Informal bullets. Technical hints ("autocomplete is debounced 200ms"),
  performance considerations, out-of-scope mentions ("bulk reassignment is
  out of scope for this UC"), "discuss with X" markers, references to UCs
  that don't exist yet ("see UC-12 if/when it's written").>
- <Anything that doesn't belong in a numbered flow step but informs a design
  decision. This section gets read carefully.>
````

If the UC has a single main flow (no web / extension / admin variants), drop the parenthesized variant
name and write `## Main flow`. With several variants, repeat the whole `## Main flow (<name>)` section
once per variant — do not nest variants under a single heading.

## Rules

1. **Title is a noun phrase, not a sentence.** `Archive a lead`, `Reassign a lead to another sales rep`,
   `Sign in to LeadDesk` — not `User archives a lead` or `As a rep I want to archive`.
2. **The Actor line names roles, not individuals.** Qualify roles in parentheses when the role's scope
   matters (`Sales rep (own leads), manager (team leads)`). Roles must match the vocabulary already used
   in the corpus.
3. **The Module line is an `Area / Sub-area` slash-path.** It groups UCs; mirror an existing module path
   when this UC extends one (e.g. `Leads / Lead editing` alongside `Leads / Lead capture`).
4. **Description is narrative, not bullets.** Two to four paragraphs of prose, including the product
   debate ("we considered X but decided Y"), because that is where the design questions hide. Do not
   summarize the flow as a list here; `## Main flow` is for that.
5. **Main-flow steps are numbered and imperative.** Each step names a user action and the system's
   response in one or two sentences. Nested bullets are fine for field lists and validation lists.
6. **Field lists use bold field names and a parenthetical type / required hint.**
   `**Company name** (required, free text)` — mirror the shape the corpus already uses, so entity
   attributes can be read straight off the list.
7. **Alternative flows are labelled `A1`, `A2`, …** in the order they appear, one edge case each in 1–4
   sentences. TBDs are encouraged where the product has not decided — write them verbatim as `**TBD**`
   or `(<question>? TBD.)`.
8. **Business rules are bullets, one invariant each.** Hard rules, soft rules, known simplifications,
   and cross-cutting rules that recur elsewhere. A rule that applies in more than one UC should say so:
   `(applies everywhere, see also UC-XX)`.
9. **Notes is the catch-all for informal context.** Performance hints, out-of-scope markers, "discuss
   with X", forward references to UCs that do not exist yet.
10. **Cross-reference other UCs by number.** `see UC-02`, `same picker as UC-03`, `referenced in UC-04
    A4`. Use the literal `UC-XX` form so grep finds them.
11. **Do not invent acceptance criteria, Gherkin scenarios, or formal preconditions / postconditions.**
    This corpus deliberately avoids that ceremony: the BA's narrative is the material, and normalizing
    it is a separate activity.
12. **The business-rules heading is `## Business Rules` for new UCs.** An existing corpus may mix
    languages (`## Бизнес-правила`); existing files keep whatever they contain, but a new file uses
    English unless asked otherwise.

## Hard stops

- Asked for formal Gherkin / `Given-When-Then` scenarios → stop, this corpus uses narrative flows.
- Asked for explicit acceptance criteria, preconditions, postconditions, or non-functional requirements
  as named sections → stop, those signals live inline in `## Business Rules` and `## Notes`.
- Asked for a use case that exclusively documents UI styling, copywriting, or visual design → stop,
  those are not use cases.
- Asked to overwrite an existing `UC-NN-*.md` → stop, that is an edit; either edit the file directly or
  take the next free number.
- Asked to write several UCs at once → stop, one UC at a time.
- Asked for a **filename** other than `UC-NN-<slug>.md` → stop, the filename shape is load-bearing. The
  **directory** is not: the corpus root is `specs/use-cases/` by default, and a sandbox or a second
  project may set a different one (e.g. `specs/dryrun/use-cases/`). Write `UC-NN-<slug>.md` under
  whichever corpus root is named, defaulting to `specs/use-cases/`.
