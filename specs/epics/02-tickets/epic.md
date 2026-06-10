# Epic 02 — Tickets

**Module(s)**: Support / Tickets
**Member use cases**: UC-02
**Status**: ingested

## Scope

The ticket is the unit of work in the Helpdesk. This epic covers the first step of its lifecycle —
opening a ticket — owned by the Ticket aggregate. Any authenticated user may open one; the ticket is
created in a single well-known state and optionally pointed at an Agent assignee. Re-assignment, status
transitions, and resolution are explicitly deferred to later UCs that ride on this same aggregate, so
the epic is scoped to creation and the invariants creation must hold.

## Backend filter

### UC-02 — Create a support ticket
- **Backend**: Title required, free text, 3–200 chars; Description required, free text; Assignee optional
  (an Agent's user id, defaults to unassigned); validate title length within bounds; if an assignee is
  supplied it must reference an existing user with the Agent role; create the ticket in the `OPEN` state,
  stamp it with the creating user, persist it; return the new ticket id; A1 — blank/too-short title →
  validation error naming the field, no ticket created; A2 — supplied assignee is not an Agent (or does
  not exist) → "cannot assign to this user" error; any authenticated user may open a ticket (Agent role
  not required to report); only Agents can be assignees.
- **Dropped (UI only)**: "opens the 'new ticket' form"; "shows the ticket detail view".
- **Raised as question**: the loose state machine — "every new ticket starts `OPEN`" is a clear backend
  invariant and kept, but "we do not enforce a strict state machine … the team wants the flexibility"
  describes how the status field is modeled going forward → **architect** (status as a free enum vs a
  guarded transition table); re-assignment / status / resolution are explicitly out of this UC — noted,
  not questioned.

## Aggregates touched (grouping rationale, not a design)

- **Ticket** — created here with title, description, status (`OPEN` on creation), a creating-user stamp,
  and an optional assignee. The Notes confirm the future lifecycle UCs "ride on the ticket aggregate this
  UC creates", which is why this UC is its own epic distinct from Labels: separate noun, separate aggregate.

## Cross-epic edges (candidates)

- **→ Identity (Epic 01)**: the optional `assignee` references an existing User with the Agent role —
  validating it requires reading the Identity user store (working notation `auth:IUserRepository`); the
  creating-user stamp comes from the authenticated session issued by Epic 01.
- **→ Labels (Epic 03)**: the label list feeds the ticket picker, and a label's `usage_count` is meant to
  rise and fall as tickets gain and lose labels — but applying labels to a ticket is a future UC, not this
  one. Noted as a candidate edge for when that UC arrives.

## Open product questions (seeds for refinement)

- Confirm `OPEN` is the only creation state and there is genuinely no other initial state in v1 (the UC
  says yes; flagged only because the "loose state machine" wording invites a follow-up).
- Attachments / file upload on tickets were considered and deferred — confirm out of v1.
