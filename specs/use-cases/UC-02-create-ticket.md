# UC-02: Create a support ticket

**Actor**: Member, Agent (any authenticated user)
**Module**: Support / Tickets

## Description

A ticket is the unit of work in the Helpdesk: someone reports a problem, an agent picks it up, and it
moves through a small lifecycle until it is resolved. This UC covers the very first step — opening a
ticket. Any authenticated user may open one; assignment and triage are separate concerns.

We argued about whether a ticket needs an explicit status on creation. The team decided every new
ticket starts in a single well-known state (`OPEN`) and the state machine is intentionally loose —
we want the flexibility to add states later without a migration dance. Assignment is optional at
creation time; an unassigned ticket simply sits in the queue.

## Main flow

1. User opens the "new ticket" form and submits it. The form has fields:
   - **Title** (required, free text, 3–200 chars).
   - **Description** (required, free text).
   - **Assignee** (optional; an Agent's user id — defaults to unassigned).
2. System validates the input:
   - Title length is within bounds.
   - If an assignee is supplied, it must reference an existing user with the Agent role.
3. System creates the ticket in the `OPEN` state, stamps it with the creating user, and persists it.
4. System returns the new ticket id and shows the ticket detail view.

## Alternative flows

- **A1**: Title is blank or too short. System rejects with a validation error naming the field; no
  ticket is created.
- **A2**: The supplied assignee is not an Agent (or does not exist). System rejects with a "cannot
  assign to this user" error.

## Business Rules

- Any authenticated user may open a ticket; you do not need the Agent role to be a reporter.
- A new ticket always starts in `OPEN`. We do not enforce a strict state machine — the team wants
  the flexibility (applies to the whole ticket lifecycle).
- Only Agents can be assignees; a Member can report but not be assigned.

## Notes

- Re-assignment, status transitions, and resolution are out of scope for this UC — they ride on the
  ticket aggregate this UC creates.
- We considered attachments on tickets but deferred file upload to a later UC.
