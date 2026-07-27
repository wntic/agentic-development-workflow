---
name: application
description: "House style for the application (CQRS) layer: command handlers (frozen command DTO + handler returning `UUID | None`, success-only logging), query handlers (frozen query DTO + optional `*Result` DTO), the compensating-transaction pattern (the sanctioned try/except: catch external side-effect, undo, re-raise), and the unit-of-work pattern (one atomic commit across two or more repositories)."
when_to_use: Producing an application command or query handler, or shaping a handler that needs a compensating undo or a multi-repository atomic commit.
---
# Application — CQRS handlers & sanctioned try/except

This theme covers 4 related artifacts, each carried by its own topic file next to this one. A topic
file holds the full *When to use / Template(s) / Rules / Hard stops* body for its artifact; this
router only routes. Read the file matching what you are producing, plus the handler-body rules
below, which govern every handler in this layer.

## When to use vs. neighbours

- Writing a mutation use case — frozen command DTO plus a handler returning `UUID | None`, with
  success-only logging → **read `command.md` now**.
- Writing a read use case — query DTO, handler, and the optional `*Result` read-model DTO →
  **read `query.md` now**.
- Shaping a command handler that must undo an already-visible external side effect when a later
  step fails (the sanctioned `try/except`) → **read `compensating-tx.md` now**.
- A handler that must write to two or more repositories in one transaction →
  **read `unit-of-work.md` now**.
- The entity, filter record or exception the handler consumes → `domain-model`; the repository or
  capability protocol it depends on → `domain-ports`; the route that dispatches it → `restapi`.

## Harvested handler-body rules

Two rules govern a handler's body, carried over from the v2 implementer prompt (notes/16 I2, I3):

- **Don't duplicate a guarantee the called method already gives.** No defensive pre-check that re-asserts a declared `raises`: if `delete(id)` is documented to raise `NotFoundError`, call it directly — never precede it with a `get_by_id(id)` whose only purpose is to trigger the same error. Load-then-act is only for a mutation that genuinely needs the entity in hand (to read a field, to compute the next state).
- **A blocked contract is the signal of a contract defect, not a workaround.** When the handler cannot be written cleanly against the current protocol — e.g. a lookup typed to *raise* `NotFoundError` where this use case treats not-found as a normal outcome — the fix is upstream: change the protocol to a `T | None` return, never bury a `try/except` in the handler or add a default argument to please a test. This is exactly the signal that the Interface sketch needs the contract-change protocol, never a silent local patch.
