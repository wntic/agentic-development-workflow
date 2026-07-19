# Questions for the BA — Epic 01 Accounts (Identity & Workspace)

Product questions only — decisions for the product owner / BA. Architecture questions are not here.
Answer inline under each question; leave everything else as-is. When every answer is filled, re-run
`/refine-usecases 01-accounts` to fold them into the refined use cases.

## Q1 · Account lockout — in v1 scope at all? — UC-10
- **From**: "After several failures in a short window the account is locked for a cool-off period. (We want this, but the exact numbers are **TBD with security** — 5 in 10 min, lock 15 min is a starting proposal, must be config not hard-coded.)"
- **Question**: Is the failed-login lockout a v1 feature, or is it deferred to a later release? (If deferred, sign-in in v1 simply keeps returning the generic "invalid email or password" with no lock.)
- **Answer**: Yes — lockout ships in v1. It's our baseline brute-force protection and security will not sign off on a public login without it. The lock must not leak account existence: a locked account returns the same generic "invalid email or password" as any other failure (see Q2 for the numbers).

## Q2 · Account lockout — thresholds and cool-off — UC-10
- **From**: "5 in 10 min, lock 15 min is a starting proposal, must be config not hard-coded."
- **Question**: If lockout is in v1 (Q1), what are the final numbers — how many failed attempts, within what window, and how long does the lock last? Please confirm these should be deployment config rather than fixed in code, and note that the values need a sign-off from security.
- **Answer**: Security signed off on the starting proposal as the v1 default: **5 failed attempts within a 10-minute rolling window** trips the lock, and the account is locked for **15 minutes**, after which the counter resets and sign-in is allowed again. All three numbers (threshold, window, lock duration) are **deployment config, not hard-coded** — security wants to tune them per environment without a release. A successful sign-in resets the failure counter immediately.

## Q3 · Bearer token lifetime (TTL) — UC-10
- **From**: "Discuss with platform: token TTL. The previous product used 1h; ML folks asked for longer-lived tokens for batch jobs but that's out of scope here. **TBD.**"
- **Question**: What is the token's lifetime for v1? (The previous product used 1 hour; the longer-lived batch tokens are confirmed out of scope.) Should this be a fixed value or deployment config?
- **Answer**: **1 hour**, matching the previous product — long enough for a working session, short enough that a leaked token expires quickly. Make it **deployment config** (same rationale as the lockout numbers — tunable per environment). No refresh-token flow in v1: when the token expires the user signs in again. The longer-lived batch/ML tokens stay out of scope.

## Q4 · Password reset — confirm out of v1 — UC-10
- **From**: "Password reset is **not** in v1 — an admin re-sets it. Flag for a future UC."
- **Question**: Please confirm password reset stays out of v1 and that the only way a forgotten password is recovered is a workspace admin re-setting it (no self-service reset flow, no "forgot password" email).
- **Answer**: Confirmed — **no self-service password reset in v1**: no "forgot password" link, no reset email, no reset token. The only recovery path is a **workspace admin re-setting the password** for the user (an admin capability, tracked as its own future UC — not part of this sign-in UC). Self-service reset is a flagged fast-follow.

## Q5 · SSO / Google login — confirm deferred past v1 — UC-10
- **From**: "We considered SSO / Google login but pushed it past v1 (discuss with the platform team — likely the first fast-follow)."
- **Question**: Please confirm SSO / Google login is out of v1 (email + password only), so the architect can treat the credential model as the single sign-in path for now.
- **Answer**: Confirmed — **v1 is email + password only**. SSO / Google login is deferred (likely the first fast-follow after launch), so the architect can model email+password as the single sign-in path and not generalize the credential model for other providers yet.

## Q6 · One workspace per user — confirm for v1 — UC-10
- **From**: "We decided **one workspace per user for v1** — multi-workspace membership is a real future need but it complicates the token and every query's tenant scoping, so it's deferred."
- **Question**: Please confirm that for v1 a user belongs to exactly one workspace (the token carries a single `workspace_id`) and that multi-workspace membership is firmly deferred, so the architect can model the token and tenant scoping around a single workspace.
- **Answer**: Confirmed — **one workspace per user in v1**. The token carries exactly one `workspace_id`, and every tenant-scoped query derives the tenant from that single claim (never from a request parameter). Multi-workspace membership is a real future need but is **firmly deferred** — the architect should model the token and tenant scoping around a single workspace and not build the multi-workspace switching machinery now.
