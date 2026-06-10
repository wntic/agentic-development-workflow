# Epic 03 — Labels

**Module(s)**: Support / Reference data
**Member use cases**: UC-03
**Status**: refined

## Scope

Labels are the small, admin-curated vocabulary stuck on tickets to slice the queue. This epic is the
CRUD around that reference list — almost pure CRUD, which makes it a clean first end-to-end exercise of
the pipeline. The Label aggregate is read by everyone but mutated only by admins; the interesting
invariants are the delete-vs-archive lifecycle (a label still in use must not silently vanish) and the
system-maintained `usage_count`.

## Backend filter

### UC-03 — Manage labels
- **Backend**: create — Name required (free text), Pinned optional boolean defaulting off, label created
  with `usage_count = 0` and not archived; update — PATCH semantics, Name and Pinned both optional, only
  supplied fields change, lookup by id; list — any authenticated user reads; archived hidden by default,
  `include_archived` flag returns them too; returns the matching labels plus a total count; A1 — update or
  delete of a non-existent id → not-found error; A2 — delete a label with `usage_count > 0` → conflict
  error (must archive instead); A3 — delete an archived label → conflict error; A4 — delete a live, unused
  label (`usage_count = 0`, not archived) → removed; only Admins create / update / archive / delete,
  Members and Agents may only read; archiving hides a label from the picker without affecting tickets that
  already carry it, unarchiving brings it back; `usage_count` is system-maintained (never edited through
  this UC); `is_pinned` is a stored sort hint.
- **Dropped (UI only)**: "opens the labels admin screen"; "refreshes the list" (UI repaint, the backend
  contract is the list endpoint already captured above).
- **Raised as question**: `name` has no uniqueness constraint in v1 — "the team accepted that two labels
  could share a name. Flag for a future UC if duplicate names become a support problem" → **BA/product**
  (confirm no-uniqueness stays); how/where `usage_count` is incremented as tickets gain and lose labels,
  and whether Label is its own aggregate vs a value on Ticket (denormalized counter) → **architect**.

## Aggregates touched (grouping rationale, not a design)

- **Label** — name, `is_pinned` (sort hint), `is_archived` (lifecycle), `usage_count` (system-maintained).
  All four operations (create / update / list / delete) mutate or read this single noun, with no other
  aggregate involved in v1 → its own epic, distinct from Tickets despite the shared `Support` module.

## Cross-epic edges (candidates)

- **↔ Tickets (Epic 02)**: "the same label list feeds the ticket picker (UC-02's neighbour) and the queue
  filters", and `usage_count` is meant to track how many tickets carry the label — but the apply-label-to-
  ticket operation that moves the counter is a future UC. Noted as a candidate edge.

## Open product questions (seeds for refinement)

- Confirm `name` stays non-unique in v1 (the UC accepts duplicate names but flags it for a future UC).
- Confirm `usage_count` is only ever moved by the (future) apply/remove-label-on-ticket flow and never
  set directly through this CRUD — the UC says so; flagged because the counter has no writer in v1's scope.
