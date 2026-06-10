# Epic 01 — Identity & Authentication

**Module(s)**: Identity / Authentication
**Member use cases**: UC-01
**Status**: refined

## Scope

The front door of the closed Helpdesk: there is no public sign-up, so authentication is the only
Identity operation in v1. This epic owns the credential exchange — looking up an account by email,
verifying the password, confirming the account is active, and issuing the signed bearer token that
every other epic assumes. The User account (with its role) is the aggregate; the session token is the
output contract the rest of the system reads.

## Backend filter

### UC-01 — Sign in with email and password
- **Backend**: email matched case-insensitively (lower-cased lookup); password required, min 8 chars
  to attempt; verify against stored argon2id hash; account-active check (`is_active`); on success issue
  a signed bearer JWT carrying user id, role, and expiry; generic "invalid email or password" that
  never reveals whether the email exists; dummy-hash on unknown email so response timing doesn't leak
  account existence; A2 — correct credentials but `is_active=false` → "account inactive" error; A3 —
  account lockout after 5 failed passwords in a 10-minute window, locked 15 minutes (thresholds are
  config, not hard-coded); token signed with the server-side key, sent as `Authorization: Bearer …`.
- **Dropped (UI only)**: "opens the sign-in screen"; "lands the user on their home view — the open-tickets
  list for Agents and Admins" (pure navigation, the open-tickets list is UC-02's read side, not this epic).
- **Raised as question**: lockout thresholds (5 / 10 min / 15 min) — UC says "discuss final numbers with
  security" → **BA/product** (and: is lockout itself in v1, or deferred?); token shape + expiry and the
  "keep the login response shaped so a challenge step could slot in later" line → **architect** (token
  contract, not a product decision); OTP second factor and self-service password reset are explicitly
  out of v1 — noted, not questioned.

## Aggregates touched (grouping rationale, not a design)

- **User / account** — looked up by email, carries the password hash, an `is_active` flag, and a role
  (Member / Agent / Admin). This is the only aggregate this UC mutates state around (failed-attempt
  counters for lockout, if lockout lands in v1). UC-01 stands alone in its module → its own epic.

## Cross-epic edges (candidates)

- **Consumed by Tickets (Epic 02)**: `ticket.assignee` must reference an existing User with the Agent
  role — the inbound edge other epics draw into this one (working notation `auth:IUserRepository`).
- The role enum (Member / Agent / Admin) issued in the token is read by every authenticated route across
  all epics. The architect formalizes where the role enum and token-verifier capability live.

## Open product questions (seeds for refinement)

- Is account lockout (A3) in v1 scope at all, and if so what are the final thresholds? UC defers the
  numbers to security ("discuss final numbers with security").
- Self-service password reset is out of v1 ("Flag for a future UC if self-service reset is ever
  prioritized") — confirm it stays deferred.
- OTP / second factor is out of v1 but flagged as a likely fast follow — confirm deferral.
