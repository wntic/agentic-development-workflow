# UC-16: Complete an action item

**Actor**: Member, Admin (any signed-in user)
**Module**: Meetings / Action items

## Description

Action items are pulled out of a meeting automatically (UC-13) and start life OPEN. This UC lets a user
tick one off: mark a single action item DONE. It's the first time an action item *changes* after the
pipeline created it — until now they were read-only output (shown in the detail view, UC-14).

This is a small follow-up to the meetings build, but it's a real change to an existing aggregate: the
action item now has a lifecycle (OPEN → DONE) and the store has to be able to fetch one by id and
update it, which the create-only pipeline never needed.

We discussed whether you can **un-complete** (DONE → OPEN) — product wants it eventually but it's not
in this UC; one direction (complete) for now. And **who** can complete one — for v1 any member of the
workspace can complete any action item in the workspace (no per-assignee ownership; action items don't
have assignees yet). **TBD if assignee-ownership is ever added.**

## Main flow

1. User opens a meeting's detail (UC-14) and marks one of its action items done (by action-item id).
2. System loads the action item, confirms it belongs to a meeting in the caller's workspace, and flips
   its status to **DONE**.
3. System persists the change and returns the updated action item (id, title, status DONE).

## Alternative flows

- **A1**: The action item id doesn't exist (or belongs to another workspace). System returns 404.
- **A2**: The action item is already DONE. **TBD** — idempotent no-op success, or refuse? Lean
  idempotent (return it as DONE) for v1.
- **A3**: (Future) un-completing — out of scope, see Description.

## Business Rules

- An action item's status is OPEN or DONE; this UC only does OPEN → DONE.
- Tenant-scoped: you can only complete an action item whose meeting is in your workspace.
- No assignee concept yet — any workspace member may complete any of the workspace's action items.

## Notes

- This adds a fetch-by-id and an update to the action-item store, which UC-13's create-only flow didn't
  need — a contract growth on the existing action-item repository.
- It adds a second member to the action-item status set (DONE), the first transition on that aggregate.
- Out of scope: un-complete, assignees, due dates, bulk-complete. Later UCs.
