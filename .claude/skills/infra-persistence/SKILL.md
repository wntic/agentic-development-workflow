---
name: infra-persistence
description: "House style for persistence adapters under polyglot storage: relational repositories on SQLAlchemy Core (never the ORM) with an IntegrityError-to-domain-exception translator, the write-once `Table` scaffold, client-style store repositories (vector / cache / document), and the Alembic revision discipline the implementer owns."
when_to_use: Producing a repository adapter (relational or client-style store), a SQLAlchemy `Table`, or authoring the Alembic revision that pairs with a schema change.
---
# Infrastructure — persistence

This theme covers 3 related artifacts, each carried by its own topic file next to this one. A topic
file holds the full *When to use / Template(s) / Rules / Hard stops* body for its artifact; this
router only routes. Read the file matching what you are producing.

## When to use vs. neighbours

- Writing or changing a relational repository adapter on SQLAlchemy Core — the constructor-style
  choice, the `IntegrityError`-to-domain-exception translator, the constraint-name map →
  **read `repository.md` now**.
- Adding, modifying or dropping a persistent table, plus the Alembic revision that pairs with the
  schema change → **read `table.md` now**.
- Writing a repository adapter over a client-style store reached through an injected SDK client
  (vector / cache / document) → **read `store-repository.md` now**.
- A single-action `ICan<Verb>` capability adapter, the settings class a store's connection factory
  consumes, or the DI provider that constructs a repository → `infra-integration`, not this theme.

## Declaring `ConflictError` on a first unique-insert (catalog side)

When a change first inserts or renames against a **unique constraint**, the error catalog must declare `ConflictError` (`code: CONFLICT`, HTTP 409) so the relational repository's `IntegrityError` translator (`repository.md`) can map to it. Omit it and a duplicate surfaces as a bare `DomainError` → **HTTP 500 instead of 409**. Phrased for the spec-author / test-author reader: a unique constraint introduced by the change implies a `ConflictError` in `domain/exceptions.py` and a 409 acceptance test. The same earn-per-need rule governs `NotFoundError` / `ValidationError` / `InUseError` — declare each the first time a behaviour needs it, never as a blanket catalog. (Harvested from notes/16 R1.)
