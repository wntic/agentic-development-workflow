# <context>/NNN — <short change name>

Class: behavioral    <!-- behavioral (default) | bugfix | invisible | hardening (spec §3.1).
                          behavioral, REMOVED: the removal flavour (spec §3.1) — write the marker
                          verbatim, `Class: behavioral, REMOVED`, and fill the `## Removed`
                          section below; this change's test-author then owns deleting/reworking
                          the obsolete tests. That marker and that section are the only wording
                          accept.py's orphan sweep reads: any other phrasing ("removal flavour",
                          "removes the export endpoint") is FLAGGED for the human, never guessed.
                          bugfix: the code diverged from an ALREADY recorded capability invariant;
                          AC = a reference to that invariant + a regression test.
                          invisible: refactor/deps/perf — behaviour unchanged; AC = "behaviour
                          unchanged", proof = full green gate + empty before/after OpenAPI diff
                          (+ the perf metric, if one was claimed).
                          hardening: the TESTS get stronger while behaviour stays identical — the
                          change an adversarial pass earns when it finds a mutation the suite did
                          not kill. Its tests pass on arrival, so there is no red phase: redness is
                          replaced by a stronger pair (every ac-marked test passes against the
                          unmutated code AND fails under each declared mutation), and the
                          `## Mutations` section below becomes MANDATORY. -->
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

## Removed
<!-- `Class: behavioral, REMOVED` ONLY — and MANDATORY there; delete the whole section for every
     other change. This is the machine-readable half of spec §3.1's "change явно перечисляет
     отменяемое поведение", and two checks read it:

     - accept.py's orphan sweep (V-02, §5.4) harvests ONLY this section, and out of it only
       `backticked` identifiers and the `::name` tail of a node-id — prose is never harvested, so
       a symbol named in a sentence alone is invisible to the sweep. Acceptance FAILs while any
       harvested name still lives in `src/**` or in a capability file.
     - the gate's baseline test-inventory (E-05) treats a baseline test as legally removed only
       when its node-id appears somewhere in this change.md, so an obsolete test deleted without
       its node-id listed here is RED for the whole cycle.

     Written HERE, in the /adw:spec session, before the baseline: change.md is frozen against the
     baseline commit (E-12), so the list cannot be back-filled once the cycle has started, and no
     agent inside the cycle may edit it (D4). A gap found later is a CONTRACT-CHANGE, not a patch.

     One bullet per removed thing — the behaviour in words, the symbol/node-id in backticks:

     - `<RemovedClassOrFunction>` — what disappears with it (its route, its table, its config key).
     - `tests/<file>.py::<test_name>` — obsolete with that behaviour; deleted by this change's
       test-author. (Node-ids are written out in full: the gate matches the string.)

     If the removed behaviour genuinely has no symbol to name (a route string, a feature flag),
     say so in a bullet anyway — the sweep then reports that it had nothing to check, and the
     human confirms in review that nothing is orphaned. -->

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

## Mutations
<!-- `Class: hardening` ONLY — and MANDATORY there: this section is that class's whole baseline
     proof, replacing the red phase its tests cannot have. Delete the section for every other
     class (red_check reads it only for hardening).

     One fenced unified diff per mutation — the wrong code the strengthened tests must catch —
     each naming the AC ids it must kill in the text above its fence (a `### M-n — …` heading or
     a plain sentence; both parse). Written by the HUMAN in the /adw:spec session, lifted from the
     `## Adversarial review` table of the change that found the surviving mutation. Never written
     by the agent that also writes the tests, and never invented to fit tests already written.

     What red_check enforces before it will tag the baseline: every AC in criteria.md is named by
     at least one mutation; every named AC exists in criteria.md; each diff applies at the
     baseline commit with `git apply` and patches `src/**` only (mutating a test would make the
     suite fail for a reason that proves nothing); every ac-marked test passes against the
     unmutated code; and every AC a mutation names goes RED with that mutation applied.

     Shape:

     ### M-1 — must kill AC-8, AC-9
     ```diff
     --- a/src/app/infrastructure/postgres/users.py
     +++ b/src/app/infrastructure/postgres/users.py
     @@ -41,7 +41,6 @@
              update(users)
     -        .where(users.c.id == user.id)
              .values(name=user.name)
     ```
-->

