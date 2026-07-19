# Epic 01 — Accounts (Identity & Workspace)

**Module(s)**: Accounts / Authentication, Accounts / Workspace
**Member use cases**: UC-10, UC-11
**Status**: refined

## Scope

The front door and the "who am I" panel of MeetingMind, a multi-tenant SaaS. A user signs in with
email + password and receives a signed bearer token carrying `user_id`, `role`, and the single
`workspace_id` that every other use case is tenant-scoped by (UC-10). A signed-in user can read their
own workspace identity (name, plan tier, their role) — a read-only convenience panel (UC-11). The two
UCs group because they share the `User`/`Account` and `Workspace` aggregates and the `Role` enum: the
token sign-in produces is exactly what the workspace panel reads back. No self-service registration in
v1 — accounts are provisioned during onboarding.

## Backend filter

### UC-10 — Sign in to the workspace
- **Backend**: email matched case-insensitively against a lower-cased stored email; password verified
  against an argon2id hash; account must be active (`is_active`); on success issue a signed JWT bearer
  carrying `user_id` + `role` + `workspace_id`; generic "invalid email or password" for both wrong
  password and unknown email, with a dummy-hash timing-equalization on unknown email (no existence
  leak); deactivated account refused with a distinct "account inactive" error; min-8-char password to
  even attempt; one workspace per user in v1; token signed with the server-side key.
- **Dropped (UI only)**: "opens the sign-in screen", "client stores the token and lands the user on
  their meeting library".
- **Raised as question**: lockout thresholds + cool-off after repeated failures (A3, must be config);
  token TTL (Notes).

### UC-11 — View my workspace and plan
- **Backend**: return workspace name + plan tier (Free/Pro/Enterprise) + the caller's role; tenant-
  scoped — workspace derived from the token's `workspace_id`, never a request parameter; 401 on
  missing/invalid/expired token (shared with every authenticated endpoint); plan tier is a stored
  workspace attribute (billing out of scope).
- **Dropped (UI only)**: "the small panel in the corner of the app", "client requests it on load".
- **Raised as question**: whether the monthly usage meter ("7 of 20") belongs on this screen (A2 /
  Description) — flagged for the architect, not the BA (ownership of the number).

## Aggregates touched (grouping rationale, not a design)

- UC-10: `User`/`Account` (credentials, `is_active`, `role`), `Workspace` (the `workspace_id` the token
  carries); `Role` enum.
- UC-11: `Workspace` (name, `plan` tier), the caller's `role`; `Plan` and `Role` enums.

Both UCs read/identity the same `User` + `Workspace` pair and share the `Role` enum — the connectedness
that clusters them. The architect decides whether `User` and `Workspace` are one or two aggregates and
the real bounded-context split.

## Cross-epic edges (candidates)

- **Meetings → Accounts** (incoming, formalized in Epic 02): every Meetings UC is tenant-scoped by the
  token's `workspace_id` and stamps `created_by` from the token's `user_id`; UC-12's quota check reads
  `Workspace.plan`. Notation hypothesis: `accounts:IWorkspaceRepository`, `accounts:Role`,
  `accounts:IUserRepository`.

## Open product questions (seeds for refinement)

- **UC-10 A3** — lockout policy: how many failures in what window, and how long the lock? (proposal:
  5 in 10 min, lock 15 min; must be config, not hard-coded). Is lockout in v1 scope at all?
- **UC-10 Notes** — token TTL value (previous product used 1h; longer-lived batch tokens are out of
  scope).
- **UC-10 Notes** — confirm password reset is out of v1 (admin re-sets it); confirm SSO/Google login
  deferred past v1.

### Raised for the architect (not the BA)
- **UC-11** — should the live usage meter ("7 of 20 meetings this month") appear on the workspace
  panel? The count lives on the Meetings side; if it must show here, who owns the number? (cross-context
  read vs Meetings-owned surface).
