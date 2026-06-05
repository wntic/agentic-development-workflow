# UC-03: Manage labels

**Actor**: Admin (mutations); Member, Agent (read)
**Module**: Support / Reference data

## Description

Labels are the small, shared vocabulary agents stick on tickets to slice the queue — `billing`,
`urgent`, `bug`, and so on. They are reference data: a short, admin-curated list that everyone reads
but only admins change. This UC is the CRUD around that list. It is almost pure CRUD, which makes it
a good first end-to-end exercise of the pipeline.

We debated deleting versus archiving. The team decided a label that is still stuck on tickets must
not silently vanish, so deletion is blocked once a label is in use; archiving is the soft path that
hides a label from the picker without breaking the tickets that already carry it. A small `is_pinned`
flag lets admins float the handful of labels they use constantly to the top of the picker — it is a
plain presentation hint, not a rule.

## Main flow (create)

1. Admin opens the labels admin screen and submits the "new label" form. The form has fields:
   - **Name** (required, free text).
   - **Pinned** (optional boolean; defaults off — a pinned label sorts to the top of the picker).
2. System validates the input and creates the label with `usage_count = 0`, not archived.
3. System returns the new label id and refreshes the list.

## Main flow (update)

1. Admin edits a label's name or pinned flag. Both fields are optional on update (PATCH semantics —
   only the supplied fields change).
2. System looks up the label by id and applies the changes.

## Main flow (list)

1. Any authenticated user requests the labels. By default archived labels are hidden; an
   `include_archived` flag returns them too.
2. System returns the matching labels plus a total count.

## Alternative flows

- **A1**: Update or delete targets an id that does not exist. System rejects with a not-found error.
- **A2**: Delete a label whose `usage_count > 0` (still stuck on tickets). System refuses with a
  conflict error — the admin must archive it instead.
- **A3**: Delete a label that is archived. System refuses with a conflict error; an archived label is
  already hidden and is kept for the tickets that reference it.
- **A4**: Delete a live, unused label (`usage_count = 0`, not archived). System removes it.

## Business Rules

- Only Admins create, update, archive, or delete labels; Members and Agents may only read them.
- A label cannot be deleted while in use (`usage_count > 0`) or while archived — archive is the soft
  alternative to deletion.
- Archiving hides a label from the picker without affecting tickets that already carry it;
  unarchiving brings it back.
- `usage_count` is maintained by the system as tickets gain and lose the label; it is never edited
  directly through this UC.
- `is_pinned` is a presentation hint only (sort order), not an access or lifecycle rule.

## Notes

- `name` is free text with no uniqueness constraint in v1 — the team accepted that two labels could
  share a name. Flag for a future UC if duplicate names become a support problem.
- The same label list feeds the ticket picker (UC-02's neighbour) and the queue filters.
