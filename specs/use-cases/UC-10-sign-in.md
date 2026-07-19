# UC-10: Sign in to the workspace

**Actor**: Member, Admin (any registered user)
**Module**: Accounts / Authentication

## Description

MeetingMind is a multi-tenant SaaS: every customer is a **workspace**, and every person belongs to a
workspace. There is no public sign-up in v1 — a workspace and its first admin are provisioned by us
during onboarding, and the admin invites members (invitations are a later UC, not this one). Signing
in is the front door: a user submits email + password and, if they match, gets a signed bearer token
that every other use case assumes.

We debated whether a person can belong to more than one workspace (consultants who serve several
clients asked for it). We decided **one workspace per user for v1** — multi-workspace membership is a
real future need but it complicates the token and every query's tenant scoping, so it's deferred. The
token therefore carries the user's id, their role, and their single workspace id. We considered SSO /
Google login but pushed it past v1 (discuss with the platform team — likely the first fast-follow).

This is the same credential model the team used on a previous product, so argon2id + a JWT bearer is
the assumed baseline unless security objects.

## Main flow

1. User opens the sign-in screen and submits credentials. The form has fields:
   - **Email** (required, email; matched case-insensitively against the stored account).
   - **Password** (required, free text, min 8 chars to even attempt).
2. System validates the credentials:
   - Looks up the account by a lower-cased email.
   - Verifies the password against the stored hash (argon2id).
   - Confirms the account is active.
3. On success, System issues a signed bearer token (a JWT carrying the user id, role, **and the
   workspace id**) and returns it.
4. Client stores the token and lands the user on their meeting library (see UC-14).

## Alternative flows

- **A1**: Wrong password or unknown email. System returns a generic "invalid email or password" — we
  do not reveal whether the email exists, and an unknown email still runs a dummy hash so timing
  doesn't leak existence.
- **A2**: Account is deactivated (`is_active=false`). Credentials may be correct but System refuses
  with an "account inactive" error; the user must contact their workspace admin.
- **A3**: Too many failed passwords. After several failures in a short window the account is locked
  for a cool-off period. (We want this, but the exact numbers are **TBD with security** — 5 in 10
  min, lock 15 min is a starting proposal, must be config not hard-coded.)

## Business Rules

- No self-service registration in v1 — accounts exist because we (or a workspace admin via invite,
  later UC) created them.
- A user belongs to **exactly one workspace** in v1 (see Description — multi-workspace is deferred).
- We never reveal whether an email is registered — same generic error and same response timing for
  unknown-email and wrong-password (applies to all auth responses, see also UC-12/UC-14 which all sit
  behind this token).
- The bearer token is signed with the server-side key; clients send `Authorization: Bearer …`.

## Notes

- Password reset is **not** in v1 — an admin re-sets it. Flag for a future UC.
- The token must carry `workspace_id` because every meeting query is tenant-scoped by it — if we ever
  do multi-workspace, this is the thing that breaks first, so keep it isolated.
- Discuss with platform: token TTL. The previous product used 1h; ML folks asked for longer-lived
  tokens for batch jobs but that's out of scope here. **TBD.**
