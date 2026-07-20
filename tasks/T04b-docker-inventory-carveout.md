# T04b — Docker-skip carve-out in the inventory check

## Goal
Implement the design ruling on T04 finding 2: the strict "skipped baseline test = RED"
reading made a Docker-less machine permanently un-GREEN once a change carries integration
tests, contradicting the spec's loud-but-legal `DOCKER SKIPPED`. The exemption keys on the
gate's OWN daemon probe (an environment fact), never on a skip-reason string an agent could
imitate.

## Depends on
T04.

## Read first
- Spec §5.1 — the amended test-inventory bullet (the ruling, verbatim).
- `.claude/tools/gate.py` — the inventory check + the existing Docker-tier daemon probe.
- The T04 report, finding 2 (context) and finding 4 (the deselect bypass the inventory
  check exists to catch — the carve-out must not reopen it).

## Deliverables
- `.claude/tools/gate.py` — amended inventory check.
- `.claude/tools/test_gate.py` — new cases.

## Steps
1. Reuse the Docker-tier's daemon probe result (one probe per run, one truth).
2. Exemption = (probe: daemon absent) ∧ (baseline node-id path under the integration test
   directory). Exempted node-ids are LISTED in the `DOCKER SKIPPED` verdict block — loud,
   never silent.
3. Daemon present → no exemption whatsoever. Non-integration skipped baseline test → RED
   regardless of Docker state.

## Verification
- `uv run pytest .claude/tools/test_gate.py` green, including new cases:
  - skipped integration baseline test + probe-absent → GREEN with the node-id listed under
    DOCKER SKIPPED;
  - same tree + probe-present (simulated) → RED;
  - skipped NON-integration baseline test + probe-absent → RED;
  - a unit test whose skip-reason STRING claims "docker unavailable" → RED (the string
    must not be the key).

## Out of scope / Escalate if
- accept.py's surfacing of DOCKER SKIPPED at acceptance is T05's concern (already pinned
  there). If the integration-directory boundary is ambiguous in a real tree, use the
  pinned pytest rootdir convention and record the decision — don't widen the exemption.
