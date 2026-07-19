# <context> / <capability>

<!-- The LIVING spec of one capability, 50–300 lines — it compounds as changes are accepted
     (spec §2). Written for the human and for agent orientation: what already exists, so a
     brownfield agent does not hallucinate requirements onto existing behaviour. It is NOT
     a schema and is never rendered into code. Past ~300 lines — cut (spec §2.1).
     Canonical-file writes happen only via accept.py and the /spec session. -->

## Behaviour
<!-- The capability's operations as observable behaviour of the running system: endpoints,
     inputs, outcomes, failure modes. -->

## Invariants
<!-- Merged in from accepted change criteria by accept.py. EVERY invariant carries its
     provenance mark:
       - <invariant> (verified by: <test-id>)
       - <invariant> (MANUAL)
     gate.py checks by grep that tests referenced by invariants still exist. -->
