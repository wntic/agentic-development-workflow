# UC-11: View my workspace and plan

**Actor**: Member, Admin (any registered user)
**Module**: Accounts / Workspace

## Description

A signed-in user can see the workspace they belong to: its name, the plan it's on, and their own role
in it. This is the small "who am I / what am I paying for" panel in the corner of the app. It's a
read-only convenience screen — nothing here mutates state.

The interesting product question is **how much usage information to show**. Product wants a "you've
used 7 of 20 meetings this month" meter right here. Engineering pushed back: the meeting count lives
in the Meetings side of the system, not with the account, and wiring the account screen to reach into
the meetings store felt wrong. We tentatively decided this screen shows the **plan tier and the
workspace identity only**, and the live usage meter is a separate Meetings concern shown elsewhere
(out of scope for this UC). **Revisit with the architect** — if the usage number must appear here, we
need to decide who owns it.

## Main flow

1. User opens the workspace panel (or the client requests it on load).
2. System returns:
   - **Workspace name**.
   - **Plan** — one of Free, Pro, Enterprise.
   - **My role** — Member or Admin.

## Alternative flows

- **A1**: The token is missing or invalid/expired. System returns 401 — same as every authenticated
  endpoint (see UC-10 A-rules).
- **A2**: (Considered) showing the monthly usage meter here. **TBD / out of scope** — see Description;
  if added later it's a Meetings-owned number surfaced into this panel, not an Accounts query.

## Business Rules

- Read-only; tenant-scoped — a user only ever sees their own workspace, derived from the token's
  `workspace_id`, never from a request parameter.
- Plan tier is a property of the workspace, set during provisioning / billing (billing is out of
  scope; the plan is just a stored attribute here).

## Notes

- Plans (Free / Pro / Enterprise) gate the monthly meeting quota enforced at upload (see UC-12). The
  actual per-tier numbers are a deployment config, not shown on this screen in v1.
- The role here is the same role enum the token carries and that authorization uses everywhere.
