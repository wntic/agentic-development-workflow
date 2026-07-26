# <context> / <capability>

<!-- The LIVING spec of one capability, 50–300 lines — it compounds as changes are accepted
     (spec §2). Written for the human and for agent orientation: what already exists, so a
     brownfield agent does not hallucinate requirements onto existing behaviour. It is NOT
     a schema and is never rendered into code. Past ~300 lines — cut (spec §2.1).
     Canonical-file writes happen only via accept.py and the /spec session. -->

## Behaviour
<!-- The capability's operations as observable behaviour of the running system: endpoints,
     inputs, outcomes, failure modes. Prose, and it belongs to the /spec session.
     It is EMPTY right after an acceptance births this file, and that is the intended state:
     accept.py merges criteria, criteria are already observable-behaviour statements (S3), so
     the Invariants below are the behaviour record until a human-led /spec writes the
     narrative around them. A script does not invent prose no gate can check (A3), and
     copying the change's Task here would be the second copy of history S6 forbids. -->

## Invariants
<!-- Merged in from accepted change criteria by accept.py. One line per invariant: the
     observable statement, then its provenance mark in parentheses — the words `verified by:`
     followed by the node id of the test that pins it, or the bare word MANUAL for one a
     human accepted by hand. gate.py greps those marks and checks that the named tests still
     exist. This paragraph therefore describes the form instead of showing a specimen: a
     specimen here used to be read as a real, rotted reference (T10j). -->
