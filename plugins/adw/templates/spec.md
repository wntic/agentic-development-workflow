# <NNN> — <short title of the change>

<!-- A delta: what this change adds, alters or retires. It describes the CHANGE, never the system as
     a whole — on acceptance it is merged into the living spec and deleted.
     Every hint in this file is an angle-bracket placeholder or an HTML comment. Fill the first,
     delete the second. -->

Affects: <capability>.md

<!-- The living spec this delta merges into. A change that creates a capability names the file it
     will create. More than two files named here usually means the delta is too wide to review as
     one thing. -->

Depth: <S | M | L>

<!-- S — one behaviour, a bugfix: `Changes` and nothing else.
     M — a typical feature: adds `Why`, `Out of scope`, `Verification`.
     L — adds `Design`, when the change carries a cross-cutting structural decision.
     A section the chosen depth does not carry is DELETED, not kept as an empty heading. Empty
     headings are how a form turns back into a manifest with mandatory fields. -->

## Why

<!-- M/L only. One to three paragraphs: what is wrong or missing now, and what changes for whoever
     uses the system. Not a plan, not a design — the reason. -->

## Changes

<!-- Behaviour only, observable from outside the process. This is the one section every depth
     carries, and the one the merge on acceptance reads. A heading below with nothing under it is
     deleted. -->

### ADDED

- <behaviour that did not exist before, one line, in the vocabulary of whoever uses it>
  - WHEN <what happens and under which precondition>
  - THEN <what is observable afterwards: response, status, stored state, message sent>
  - WHEN <the edge, the refusal, the second time the same call arrives>
  - THEN <what is observable then>

<!-- One or more WHEN … THEN pairs per item. Both halves stay observable from outside: a status
     code, a persisted state, a message that leaves. "THEN the handler is called" is not a
     scenario — it is an implementation guess. -->

### MODIFIED

- <behaviour that already exists>: <what is different about it, from → to>

<!-- Name it the way the living spec names it, so the merge has a target to replace. -->

### REMOVED

- <behaviour that stops existing>: <what a caller relying on it sees instead>

## Out of scope

<!-- M/L, and only when there is a real risk of over-reach: what a reader might reasonably expect
     from the above and is deliberately NOT part of this change. One line each. -->

## Design

<!-- Present ONLY when this change carries a cross-cutting structural decision — one whose radius
     reaches files the change does not appear to touch, and which the toolchain cannot see (a type
     checker is equally green on a badly drawn boundary). If no such decision is involved, this
     section is absent entirely, and local structure — module placement, a value object versus a
     primitive, a handler's name — is decided while the code is written, not here.

     The section binds in one part and not in the other, and the difference matters:
     - BINDING where it names shared names: modules, classes, constructor dependencies that the
       tests and the code must read identically. Those are a published contract. A binding name that
       turns out wrong is changed by returning to this spec — never by a silent workaround such as a
       default argument or a second name that means the same thing.
     - NON-BINDING everywhere else: the approach chosen, the options rejected, the reasoning. If
       that part and the code disagree, the code is right, and a verdict on the change ignores it. -->

## Verification

<!-- M/L only. How the criteria of this change are proven: the commands to run, the environment they
     need, the seed data, which criteria need a really running application and what makes it
     runnable. A criterion whose environment is not covered here cannot be proven live — it will be
     accepted by hand, and that is a decision made here rather than discovered later. -->
