# <context>/NNN — <short change name>

Class: behavioral    <!-- behavioral (default) | bugfix | invisible (spec §3.1).
                          behavioral, removal flavour: list the removed behaviour explicitly —
                          this change's test-author then owns deleting/reworking obsolete tests.
                          bugfix: the code diverged from an ALREADY recorded capability invariant;
                          AC = a reference to that invariant + a regression test.
                          invisible: refactor/deps/perf — behaviour unchanged; AC = "behaviour
                          unchanged", proof = full green gate + empty before/after OpenAPI diff
                          (+ the perf metric, if one was claimed). -->
Affects: <capability files>    <!-- brownfield: optional — delete the line and accept.py derives it
                                    (the context's single capability file). FIRST change of a context:
                                    there is no capability file yet, so accept.py births the one named
                                    in overview.md's Capabilities list (else, if none, the change slug
                                    with its NNN- prefix stripped); name it here explicitly to override. -->
Companion: <context>/NNN       <!-- only for a paired cross-context change, delete otherwise;
                                    accept.py accepts both or neither -->

## Context
<!-- M/L only. Why: 1–3 paragraphs; link the use cases / capability files this grows out of. -->

## Task
<!-- What to do, in plain words. For S depth this may be the entire spec. -->

## Out of scope
<!-- Optional. What this change explicitly does NOT do (scope-creep protection). -->

## Interface sketch
<!-- M/L only. Module/class names + ctor dependencies that tests and code MUST share.
     BINDING — the one published contract the test-author and the implementer both write
     against; it changes only through the contract-change protocol (spec §6), never silently.
     Written in the /adw:spec session: the agent proposes, the human approves.
     FIRST change of a context: the standard app shell is ALWAYS-PRESENT substrate, not a
     business layer. create_app() + the central DomainError handler (mandated by the restapi
     skill) drag in a domain-exception base (domain/exceptions.py), the error translator
     (restapi/error_handler.py) and its error schema (restapi/schemas/errors.py) — the
     implementer writes them as behaviorless shell. So scope the sketch as "no BUSINESS
     domain / application / infrastructure — the standard app shell only"; never a blanket
     "no domain/application/infrastructure layers". The blanket phrasing contradicts the shell
     the skill ships and makes a correct first implementation read as out-of-scope drift (a
     false V-09 the human must read past). -->


## Design notes
<!-- L only. Approach choices, agreements. NON-BINDING — where this diverges from the code,
     the code wins; the evaluator ignores this section when judging conformance. -->

## Acceptance criteria
<!-- MANDATORY — the only mandatory section. Observable behaviour of the RUNNING system,
     never a property of the code ("POST /meetings with a file >25 MiB returns 413 with code
     `request_too_large`", NOT "the middleware is configured correctly"). Given/When/Then is
     welcome but optional — prose for the human, not a DSL. Mirrored 1:1 as AC-n items in
     criteria.md, which is the flip-only inventory. -->

## Verification
<!-- How to run the proof: commands, the e2e scenario, AND the environment provisioning for
     live runs (seed data, docker, tokens). A criterion whose environment is not provisioned
     here is not required to be proven live — its ac-marked test remains the proof. A spec
     with no answer to "how do we prove it is done" is not accepted into work (M/L; for S
     depth the fast-lane answer is implicit: gate.py --criteria over ac-marked tests). -->
