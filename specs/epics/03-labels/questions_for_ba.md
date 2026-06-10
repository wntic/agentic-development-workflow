# Questions for the BA — Epic 03 Labels

Product questions only — decisions for the product owner / BA. Architecture questions are not here.
Answer inline under each question; leave everything else as-is. When every answer is filled, re-run
`/refine-usecases 03-labels` to fold them into the refined use cases.

> **Note (test data):** these answers are stand-in values filled by the dev to exercise Stage B, not
> real BA decisions. Replace with the product owner's actual answers before treating the refined UC as
> canonical.

## Q1 · Duplicate label names in v1 — UC-03
- **From**: "`name` is free text with no uniqueness constraint in v1 — the team accepted that two labels could share a name. Flag for a future UC if duplicate names become a support problem."
- **Question**: Do we confirm for v1 that two labels are allowed to share the same name (no uniqueness check at all), or should the system reject creating/renaming a label to a name that already exists?
- **Answer**: Confirmed for v1 — two labels may share a name; there is no uniqueness check on create or rename. (Flagged for a future UC if duplicates become a support problem.)

## Q2 · How `usage_count` changes in this UC — UC-03
- **From**: "`usage_count` is maintained by the system as tickets gain and lose the label; it is never edited directly through this UC."
- **Question**: Do we confirm that within label CRUD (this UC) `usage_count` is read-only — never set or edited directly by an admin — and only ever moves through the (future) apply/remove-label-on-a-ticket flow?
- **Answer**: Confirmed — within label CRUD `usage_count` is read-only; an admin never sets or edits it directly. It moves only through the future apply/remove-label-on-a-ticket flow, and a new label starts at 0.

## Q3 · Is unarchive an admin operation in v1 — UC-03
- **From**: "Archiving hides a label from the picker without affecting tickets that already carry it; unarchiving brings it back."
- **Question**: Should this v1 UC expose both archive and unarchive as admin actions, or only archive (with unarchive deferred)? The explicit flows describe create/update/list/delete but not an archive/unarchive action, so we need to confirm which of these are in scope for v1.
- **Answer**: Both archive and unarchive are admin actions in v1. Archive is the soft alternative to deletion (and the only path for an in-use label); unarchive brings a label back into the picker. Both are in scope; the mechanism (a dedicated action vs a flag on update) is the architect's call.

## Q4 · Name field constraints — UC-03
- **From**: "**Name** (required, free text)."
- **Question**: Beyond "required", are there product constraints on the label name — e.g. a minimum length (non-empty / no whitespace-only), a maximum length, or any character restrictions — or is any non-empty free-text value acceptable in v1?
- **Answer**: Required and non-empty after trimming whitespace, with a maximum of 50 characters; no character restrictions. Labels are meant to be short and human-readable.
