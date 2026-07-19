# Verdict — <context>/NNN-<slug>

<!-- Written ONLY by the evaluator, from a fresh context, after a full gate.py run
     (spec §4, §6). Design notes in change.md are ignored when judging. Every AC gets a
     block — none is skipped silently. -->

Gate: <GREEN | RED> · SHA: <git SHA of the evaluated commit> · junit: <report of this run>

## Per-criterion verdicts

- AC-n: <PASS | FAIL | MANUAL-candidate>
  - state: <[ ] | [x] | [m]>  <!-- mirrors criteria.md after this evaluator's flips -->
  - proof: <ac-test: <test-id> | live-run: <Verification scenario executed> | manual: <the
           human's reason, for [m]>>  <!-- which method proved THIS criterion — a live run
           is required only where the Verification section provisioned the environment;
           silently substituting a pytest quote for a due live run is forbidden -->
  - sha: <git SHA the proof was produced at>
  <!-- On FAIL: add the concrete failure (assertion, log line, repro command) — this block
       is the work order for the next implementer dispatch. -->

## Out-of-scope diff
<!-- src changes outside this change's area (Affects + Interface sketch) — reported loudly,
     not forbidden. Write "None" when empty. -->

## Adversarial review
<!-- Slot for the adversarial pass: a fresh agent runs the assert-strength recipes over the
     test diff and reports here. Mandatory for M/L changes and for the first change of a
     capability — accept.py checks this section's presence by change class. For S depth:
     filled only when run with --adversarial, otherwise write "N/A (S)". -->
