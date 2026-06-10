# Questions for the BA — Epic 02 Tickets

Product questions only — decisions for the product owner / BA. Architecture questions are not here.
Answer inline under each question; leave everything else as-is. When every answer is filled, re-run
`/refine-usecases 02-tickets` to fold them into the refined use cases.

> **Note (test data):** these answers are stand-in values filled by the dev to exercise Stage B, not
> real BA decisions. Replace with the product owner's actual answers before treating the refined UC as
> canonical.

## Q1 · Only creation state — UC-02
- **From**: "every new ticket starts in a single well-known state (`OPEN`) and the state machine is intentionally loose"
- **Question**: For v1, is `OPEN` genuinely the only state a ticket can be created in — i.e. there is no other initial state (a draft, an unassigned-vs-assigned split, etc.) a user could pick at creation time? (The lifecycle after creation is a separate, later UC; this is only about the state on creation.)
- **Answer**: Yes — `OPEN` is the only creation state in v1. The user cannot pick a state; there is no draft or alternate initial state. The post-creation lifecycle is a separate later UC.

## Q2 · Attachments out of v1 — UC-02
- **From**: "We considered attachments on tickets but deferred file upload to a later UC."
- **Question**: Confirm that file attachments / uploads are out of scope for v1 ticket creation — a ticket is created with only Title, Description, and an optional Assignee, and there is no way to attach a file at creation time?
- **Answer**: Confirmed — attachments/uploads are out of v1. A ticket is created with Title, Description, and an optional Assignee only; no file attachment at creation.

## Q3 · Title length bounds — UC-02
- **From**: "Title (required, free text, 3–200 chars)."
- **Question**: Are 3 and 200 the committed minimum and maximum for the title length in v1, and are both bounds inclusive (3 chars allowed, 200 chars allowed)?
- **Answer**: Yes — 3 and 200 are the committed bounds, both inclusive (3 chars allowed, 200 chars allowed). Length is measured after trimming surrounding whitespace.

## Q4 · Description length / emptiness — UC-02
- **From**: "Description (required, free text)."
- **Question**: The description is required free text but no length bound is stated. For v1, should a description have any minimum (e.g. non-empty / non-whitespace) or maximum length, or is any non-empty text acceptable?
- **Answer**: Required and must be non-empty after trimming whitespace. No maximum length in v1 — any non-empty text is acceptable.

## Q5 · Member self-assignment vs reporter stamp — UC-02
- **From**: "Any authenticated user may open a ticket; you do not need the Agent role to be a reporter." / "Only Agents can be assignees; a Member can report but not be assigned."
- **Question**: When a Member (non-Agent) opens a ticket, the ticket records who created it (the reporter) and may optionally name an Agent assignee. Is the reporter stamp always the authenticated user who submitted the form (i.e. a user can only open a ticket on their own behalf, not report on behalf of someone else)?
- **Answer**: Yes — the reporter stamp is always the authenticated user who submitted the form. In v1 a user can only open a ticket on their own behalf; reporting on behalf of someone else is not supported.
