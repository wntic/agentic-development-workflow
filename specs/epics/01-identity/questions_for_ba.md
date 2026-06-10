# Questions for the BA — Epic 01 Identity & Authentication

Product questions only — decisions for the product owner / BA. Architecture questions are not here
(token shape/expiry, the role-enum location, and keeping the login response shaped for a future
challenge step live in `epic.md` for the architect). Answer inline under each question; leave
everything else as-is. When every answer is filled, re-run `/refine-usecases 01-identity` to fold them
into the refined use cases.

> **Note (test data):** these answers are stand-in values filled by the dev to exercise Stage B, not
> real BA decisions. Replace with the product owner's actual answers before treating the refined UC as
> canonical.

## Q1 · Account lockout in v1 scope — UC-01
- **From**: "A3: Too many failed passwords. After 5 failures inside a 10-minute window the account is locked for 15 minutes. (Thresholds are config, not hard-coded — discuss final numbers with security.)"
- **Question**: Is failed-attempt lockout part of v1 at all, or deferred to a future UC? (If deferred, A3 drops from the refined UC and the User account carries no failed-attempt counter.)
- **Answer**: In v1. Brute-force protection is a baseline expectation even behind the VPN, and A3 is already fully described — keep it. The User account carries a failed-attempt counter.

## Q2 · Lockout thresholds — UC-01
- **From**: "Thresholds are config, not hard-coded — discuss final numbers with security."
- **Question**: If lockout is in v1, are the placeholder numbers (5 failures / 10-minute window / 15-minute lock) the agreed values, or does security set different ones? They remain config, not hard-coded — this only fixes the defaults.
- **Answer**: Agreed as the v1 defaults: 5 failures / 10-minute window / 15-minute lock. They stay config-driven so security can retune without a code change.

## Q3 · Lockout reset and scope — UC-01
- **From**: "A3: Too many failed passwords. After 5 failures inside a 10-minute window the account is locked for 15 minutes." (the UC names the trigger but not the reset or the scope)
- **Question**: If lockout is in v1: does a successful sign-in clear the counter? Does the counter reset on window expiry only, or also once the 15-minute lock lapses? And is lockout tracked per account (by email) or per request source (e.g. IP)?
- **Answer**: A successful sign-in clears the counter. The counter also resets when the 10-minute window lapses with no new failure, and the lock auto-releases after 15 minutes (counter starts fresh afterwards). Tracked per account (by the looked-up user), not per IP — internal staff share egress IPs, so per-account is the meaningful unit.

## Q4 · "Account inactive" message vs the non-disclosure rule — UC-01
- **From**: "A2: Account is deactivated (`is_active=false`). Credentials may be correct but System refuses with an 'account inactive' error." — set against the Business Rule "We never reveal whether an email is registered — same generic error and same response timing for unknown-email and wrong-password."
- **Question**: A2 surfaces a distinct "account inactive" message, which (since it is reachable only on correct credentials) discloses that the email exists and the password was right. Is that disclosure intended (so a deactivated user is told to contact an admin), or should A2 collapse into the generic "invalid email or password" to honour the non-disclosure rule?
- **Answer**: Keep A2 as a distinct "account inactive" message. The non-disclosure rule is scoped to credential validity (unknown-email and wrong-password must be indistinguishable); it does not extend to a deactivated-but-valid account. A deactivated internal user should be told to contact an admin rather than left guessing, so A2 is exempt from the generic-error rule.

## Q5 · Minimum password length / policy — UC-01
- **From**: "Password (required, free text, min 8 chars to even attempt)."
- **Question**: Is 8 the agreed minimum password length? Is it purely a pre-flight gate (reject the attempt before hitting the store), or a stated password policy? Any other policy for v1 (max length, complexity), or is length-8 the only rule?
- **Answer**: 8 is the committed minimum length, enforced both as a pre-flight gate (reject before hitting the store) and as the stated policy. No maximum and no complexity rules in v1 — length-8 is the only rule.

## Q6 · Self-service password reset stays out of v1 — UC-01
- **From**: "Password reset / 'forgot password' is intentionally not in v1 — a forgetful user is handled by an admin editing the account. Flag for a future UC if self-service reset is ever prioritized."
- **Question**: Confirm reset stays deferred (forgetful users handled by an admin editing the account), so the refined UC carries no reset flow.
- **Answer**: Confirmed — reset stays deferred; forgetful users are handled by an admin editing the account. The refined UC carries no reset flow.

## Q7 · Second factor (OTP) stays out of v1 — UC-01
- **From**: "A second factor (OTP) is out of scope for v1 but likely a fast follow — keep the login response shaped so a challenge step could slot in later without breaking clients."
- **Question**: Confirm OTP / second factor stays out of v1. (Keeping the login response shaped so a challenge step can slot in later is the architect's concern, not a product decision.)
- **Answer**: Confirmed — OTP / second factor stays out of v1.
