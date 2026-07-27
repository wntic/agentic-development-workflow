# <context> — overview

<!-- The context map (spec §2, §2.1): what the whole context sees, not any one capability.
     Anti-anticipation litmus: a fact moves up here only if ≥2 capabilities see it NOW.
     Past ~300 lines — split out glossary.md / invariants.md as equally canonical files.
     Canonical-file writes happen only via accept.py and the /adw:spec session. -->

## Purpose
<!-- Why this bounded context exists; its domain language in two-three sentences. -->

## Capabilities
<!-- One line per capability file in this folder. A capability = what a stakeholder would
     call one ability of the system, cut by cohesion-of-change (spec §2.1). -->
- `<capability>.md` — <one-line summary>

## Cross-cutting invariants and domain terms
<!-- Aggregates/terms visible to several capabilities; context-level invariants
     (multi-tenancy, quotas, ...). Carried invariants keep their provenance marks, same as
     in capability files. -->

## Integrations
<!-- The neighbour map: which contexts this one talks to, through which explicit interfaces. -->
