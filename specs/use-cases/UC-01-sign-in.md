# UC-01: Sign in with email and password

**Actor**: Member, Agent, Admin (any registered user)
**Module**: Identity / Authentication

## Description

The Helpdesk is a closed system — there is no public sign-up, every account is created by an
administrator. Signing in is therefore the front door for everyone. A user enters their email and
password, and if those are correct the system issues a session token that every other use case
assumes.

We kept v1 deliberately simple: a single email+password exchange that returns a signed bearer
token. We discussed adding a second factor (email OTP or an authenticator app) but decided to defer
it — the audience is internal support staff behind a VPN, and the product owner wanted the smallest
thing that works first. The token shape and expiry live with the auth slice; this UC ends the moment
a valid session is issued.

## Main flow

1. User opens the sign-in screen and submits credentials. The form has fields:
   - **Email** (required, email; matched case-insensitively against the stored account).
   - **Password** (required, free text, min 8 chars to even attempt).
2. System validates the credentials:
   - Looks up the account by a lower-cased email.
   - Verifies the password against the stored hash (we use argon2id).
   - Confirms the account is active.
3. On success, System issues a signed bearer token (a JWT carrying the user id, role, and an expiry)
   and returns it to the client.
4. System lands the user on their home view — the open-tickets list for Agents and Admins.

## Alternative flows

- **A1**: Wrong password. System returns a generic "invalid email or password" — we deliberately do
  not reveal whether the email exists. An unknown email still runs a dummy hash so response timing
  doesn't leak account existence.
- **A2**: Account is deactivated (`is_active=false`). Credentials may be correct but System refuses
  with an "account inactive" error. The user must contact an admin.
- **A3**: Too many failed passwords. After 5 failures inside a 10-minute window the account is locked
  for 15 minutes. (Thresholds are config, not hard-coded — discuss final numbers with security.)

## Business Rules

- No self-service registration — accounts exist only because an admin created them.
- Credentials are validated case-insensitively on email but exactly on password.
- We never reveal whether an email is registered — same generic error and same response timing for
  unknown-email and wrong-password (applies to all auth responses).
- The bearer token is signed with the server-side key; clients send it as `Authorization: Bearer …`.

## Notes

- Password reset / "forgot password" is intentionally **not** in v1 — a forgetful user is handled by
  an admin editing the account. Flag for a future UC if self-service reset is ever prioritized.
- A second factor (OTP) is out of scope for v1 but likely a fast follow — keep the login response
  shaped so a challenge step could slot in later without breaking clients.
