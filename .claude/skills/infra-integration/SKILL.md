---
name: infra-integration
description: "House style for non-persistence infrastructure: capability adapters wrapping SDKs (`ICan<Verb>` implementations with an SDK-exception-to-domain-exception translator at the boundary), `pydantic-settings` classes (one per integration, env prefix stemming on the product), and `dependency-injector` container wiring (the `Singleton` vs `Factory` choice and declaration order)."
when_to_use: Producing a capability adapter, a settings class, or wiring a class into `containers.py`.
---
# Infrastructure — integration (adapters, settings, DI)

This theme covers 3 related artifacts, each carried by its own topic file next to this one. A topic
file holds the full *When to use / Template(s) / Rules / Hard stops* body for its artifact; this
router only routes. Read the file matching what you are producing.

## When to use vs. neighbours

- Writing or changing a capability adapter that wraps an SDK or HTTP client (an `ICan<Verb>`
  implementation, with SDK-exception translation at the boundary) → **read `adapter.md` now**.
- Writing or extending the `pydantic-settings` class that gives an integration its env-backed
  configuration → **read `settings.md` now**.
- Wiring a class into `src/<root>/containers.py` (the `Singleton` vs `Factory` choice, declaration
  order) → **read `container.md` now**.
- Aggregate-root CRUD over a relational store, the `Table`, or a client-style store repository →
  `infra-persistence`, not this theme.
