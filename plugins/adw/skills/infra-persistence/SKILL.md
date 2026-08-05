---
name: infra-persistence
description: The house forms for relational persistence on SQLAlchemy **Core**, never the ORM — the `Table` under `infrastructure/postgres/tables/`, the repository adapter under `repositories/` with its row-to-entity mapper and `IntegrityError` translator, and the Alembic revision that pairs with a schema change.
when_to_use: Producing or editing a relational repository adapter, a persistent table, its constraints or indexes, or the Alembic revision that goes with a schema change.
paths: src/**/infrastructure/**
---

# Infrastructure Persistence (relational)

The table, the repository that queries it, and the migration that ships it. They live together because
**the constraint names are one contract across all three**: the `Table` declares them through the
metadata naming convention, the repository's `_map_integrity_error` matches on them to produce the right
domain exception, and the Alembic revision writes them out in full. Rename one and all three change, in
the same commit.

For a non-relational store — a vector, cache or document backend — use `infra-store-repository` instead.
The store profile decides which applies (`conventions` block C).

## When to use vs. neighbours

- A persistent table, its columns, constraints or indexes → the **Table** section.
- The adapter satisfying a domain repository protocol on a relational store → the **repository** section.
- The migration pairing with a schema change → the **Alembic revision** section.
- The protocol the adapter satisfies (`i_foo_repository.py`) → `domain-ports`.
- A repository on a client-style store (qdrant, redis, …) → `infra-store-repository`.
- The DI provider constructing this repository → `infra-wiring`.
- The unit-of-work protocol and implementation, when the repository joins multi-repository transactions →
  `patterns`.
- A data-only migration (`backfill_*`, `seed_*`) with no DDL → its own revision file; this skill covers
  DDL only.

## File layout

```
src/<root>/infrastructure/postgres/
├── metadata.py                    # already exists — the shared MetaData with naming_convention
├── tables/
│   ├── __init__.py                # re-export the new module
│   └── foos.py                    # the Table
└── repositories/
    ├── __init__.py                # re-export the new module
    └── foo_repository.py          # the adapter

alembic/versions/
└── 0042_create_foos.py            # authored via `alembic revision`, hand-edited to the rules below
```

## The `Table`

Column types are a **design decision** — jsonb, pgvector, a check constraint, a foreign key — not a
mechanical transcription of the entity's fields. That is why the column-type rules come first.

### Naming convention (load-bearing — do not deviate)

Defined once in `infrastructure/postgres/metadata.py`:

```python
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})
```

The names it generates are exactly what the repository's translator matches on:

- PK: `pk_foos`
- unique on `name`: `uq_foos_name`
- index on `author_id`: `ix_foos_author_id`
- FK `foos.bar_id → bars.id`: `fk_foos_bar_id_bars`
- check with `name="category_xor"`: `ck_foos_category_xor`

**For a `CheckConstraint`, `name=` is the suffix** — SQLAlchemy prepends `ck_<table>_`. Pick a stable,
descriptive suffix.

### Template — table file

```python
# src/<root>/infrastructure/postgres/tables/foos.py
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Table, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from ..metadata import metadata

__all__ = ["foos_table"]

foos_table: Table = Table(
    "foos",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column(
        "bar_id",
        UUID(as_uuid=True),
        ForeignKey("bars.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("char_length(name) > 0", name="name_non_empty"),
    Index("ix_foos_bar_id", "bar_id"),
    Index("ix_foos_created_at", "created_at"),
)
```

### Rules — column types

- **UUID:** `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`. Never plain `UUID()`.
- **Timestamps:** `DateTime(timezone=True)` with `server_default=func.now()` for `created_at` /
  `updated_at`. Never naive.
- **Text:** `Text`, not `String(n)`. No length-bounded varchars.
- **Integers:** `Integer`; `SmallInteger` only when the domain is genuinely bounded.
- **Booleans:** `Boolean`.
- **Enums:** `Text` plus a `CheckConstraint` listing the valid values — **not** a Postgres `ENUM`. This
  matches the domain `StrEnum` (`domain-model`).

### Rules — FK `ondelete`

- `RESTRICT` — the target is a **referenced lookup** (`bars`). The repository translates the resulting
  `IntegrityError` to `InUseError`.
- `CASCADE` — the target is the **parent of an owned child** (`foo_children.foo_id → foos.id`).
- `SET NULL` — only when the column is nullable and absence carries domain meaning. Rare.

Pick once, and document the consequence in the repository's `delete`.

### Rules — indexes

- Index every FK column you filter or join on. SQLAlchemy does **not** create FK indexes automatically.
- Index columns used in a list endpoint's `ORDER BY` (`created_at`) and in a filter record's `WHERE`.
- Single-column index name: `ix_<table>_<col>`. A composite index is named explicitly with the same
  prefix.
- **A bare string argument to `Index` is a COLUMN NAME, not an expression.**
  `Index("ix_users_email_lower", "lower(email)")` makes SQLAlchemy look for a column literally named
  `lower(email)` and raise `ConstraintColumnNotFoundError` when the `MetaData` is constructed — lint and
  type-check stay green, only constructing the table catches it. A **functional index** wraps the SQL:
  `Index("ix_users_email_lower", text("lower(email)"))`, with `text` imported from `sqlalchemy`.

### Rules — constraint names (load-bearing)

- **Never pass `name=` for a primary key, FK, unique or index in the `Table`** — let the metadata
  convention generate it.
- **Always pass `name=` (the suffix) for a `CheckConstraint`** so the convention can prepend
  `ck_<table>_`.
- **The same two rules hold inside an Alembic revision's `op.create_table`** — no `name=` for the
  primary key, FK or unique constraint, the suffix for a `CheckConstraint`. `env.py` hands Alembic the
  shared metadata as `target_metadata`, so `op.create_table` builds on the convention exactly as the
  `Table` does. Writing the full name for a check yields `ck_foos_ck_foos_name_non_empty`, because the
  `ck` convention interpolates whatever you pass as its `%(constraint_name)s`.
- Renaming one is a breaking change: the repository's map changes in the same commit.

### Rules — junction and owned-children tables

- **Junction table:** a composite primary key across both FKs and no surrogate `id`; both columns
  `primary_key=True`; index the non-leading FK column.
- **Owned-children table:** a surrogate `id`, an FK to the parent with `ondelete="CASCADE"`, and a unique
  constraint on the natural identity —
  `UniqueConstraint("foo_id", "position", name="uq_foo_children_foo_position")`.

### Rules — server vs application defaults

- `created_at` / `updated_at` use `server_default=func.now()`, so existing rows behave correctly during a
  migration.
- Application-managed `updated_at` on update: the repository sets it explicitly with `func.now()` in the
  `UPDATE`. A server default fires only on `INSERT`.
- A domain-meaningful default uses `server_default="…"`, and the value stays **identical** between the
  table definition and the revision.

## The repository adapter

One class adapting a domain repository protocol to SQLAlchemy Core plus Postgres. The adapter does not
inherit from the protocol — structural subtyping at the DI injection site is the contract.

### Pick the constructor style

- **Standalone (`session_factory`-injected).** The default. CRUD on a single aggregate: opens its own
  session, commits per call.
- **Unit-of-work-managed (`session`-injected).** Joins a unit of work for multi-repository atomicity.
  Receives a live session and **never commits**.

The two forms are mutually exclusive for one class. If both call styles are genuinely needed, write two
adapters.

### Template — standalone form

```python
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, RowMapping, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Import only the domain exceptions THIS repository actually raises — not the whole
# catalog. (Here all four are raised: unique → ConflictError, FK-on-delete → InUseError,
# missing row → NotFoundError, check violation → ValidationError. A repo that raises
# fewer imports fewer.)
from myapp.domain.exceptions import (
    ConflictError, InUseError, NotFoundError, ValidationError,
)
# Never import IFooRepository — the adapter does NOT inherit the protocol (structural
# subtyping at the DI site is the contract, Rule 2). Importing it leaves a dead F401.
from myapp.domain.foos import Foo, FooListFilter, FooSort

from ..tables.foos import foos_table

__all__ = ["FooRepository"]

# Translate the filter's sort key (a domain enum) to an ordered column — this is the
# "sort-key → column" translation the filter record delegates here. One entry per
# FooSort member; the member encodes both column and direction. `created_at.desc()`
# is just this aggregate's default, not a baked-in universal order.
_SORT_COLUMNS = {
    FooSort.CREATED_AT_DESC: foos_table.c.created_at.desc(),
    FooSort.CREATED_AT_ASC: foos_table.c.created_at.asc(),
    FooSort.NAME_ASC: foos_table.c.name.asc(),
}

# _FK_FIELD_MAP + the FK branch in _map_integrity_error exist ONLY because Foo carries a
# foreign key (bar_id). An aggregate with NO foreign keys omits BOTH the map and the
# `pgcode == "23503"` branch — never carry an empty `_FK_FIELD_MAP = {}`.
_FK_FIELD_MAP = {
    "fk_foos_bar_id_bars": "bar_id",
}

def _map_integrity_error(exc: IntegrityError) -> Exception:
    cause = exc.orig.__cause__ if exc.orig else None
    constraint = getattr(cause, "constraint_name", None) if cause else None
    pgcode = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)

    if constraint == "uq_foos_name":
        return ConflictError("foo name already exists", {"constraint": constraint})
    if pgcode == "23503" and constraint:
        field = _FK_FIELD_MAP.get(constraint, constraint)
        return NotFoundError(f"Referenced {field} not found", {"field": field, "constraint": constraint})
    if pgcode == "23514" and constraint and "name_non_empty" in constraint:
        return ValidationError("name cannot be empty", {"field": "name", "constraint": constraint})

    # Mandatory fallback: never let IntegrityError escape unmapped.
    return ConflictError(
        "integrity violation",
        {"constraint": constraint or "unknown", "pgcode": pgcode or "unknown"},
    )

class FooRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    def _row_to_entity(self, row: RowMapping) -> Foo:
        # Rows come from `.mappings()` → RowMapping; access columns by KEY. `row["id"]` is
        # Any, but it is consumed as a constructor argument (not returned), so Foo(...) is a
        # concrete return — mypy-clean with NO `# type: ignore`.
        return Foo(id=row["id"], name=row["name"])

    async def get_by_id(self, id: UUID) -> Foo:
        async with self._sf() as session:
            row = (
                await session.execute(select(foos_table).where(foos_table.c.id == id))
            ).mappings().one_or_none()
        if row is None:
            raise NotFoundError("Foo not found", {"id": str(id)})
        return self._row_to_entity(row)

    async def get_by_name(self, name: str) -> Foo | None:
        async with self._sf() as session:
            row = (
                await session.execute(select(foos_table).where(foos_table.c.name == name))
            ).mappings().one_or_none()
        return self._row_to_entity(row) if row is not None else None

    async def list(self, *, filter: FooListFilter) -> Sequence[Foo]:
        stmt = _apply_filter(select(foos_table), filter).order_by(_SORT_COLUMNS[filter.sort])
        stmt = stmt.limit(filter.limit).offset(filter.offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [self._row_to_entity(r) for r in rows]

    async def count(self, *, filter: FooListFilter) -> int:
        stmt = _apply_filter(select(func.count()).select_from(foos_table), filter)
        async with self._sf() as session:
            total: int = (await session.execute(stmt)).scalar_one()
        return total

    async def create(self, foo: Foo) -> None:
        try:
            async with self._sf() as session:
                await session.execute(
                    foos_table.insert().values(id=foo.id, name=foo.name)
                )
                await session.commit()
        except IntegrityError as exc:
            raise _map_integrity_error(exc) from exc

    async def update(self, foo: Foo) -> None:
        try:
            async with self._sf() as session:
                # cast to CursorResult so `.rowcount` type-checks — AsyncSession.execute is
                # typed Result[Any], which has no `rowcount`. This is the one canonical form;
                # do not mix in `# type: ignore`.
                result = cast(
                    CursorResult[object],
                    await session.execute(
                        foos_table.update()
                        .where(foos_table.c.id == foo.id)
                        .values(name=foo.name, updated_at=func.now())
                    ),
                )
                if result.rowcount == 0:
                    raise NotFoundError("Foo not found", {"id": str(foo.id)})
                await session.commit()
        except IntegrityError as exc:
            raise _map_integrity_error(exc) from exc

    async def delete(self, id: UUID) -> None:
        try:
            async with self._sf() as session:
                result = cast(
                    CursorResult[object],
                    await session.execute(
                        foos_table.delete().where(foos_table.c.id == id)
                    ),
                )
                if result.rowcount == 0:
                    raise NotFoundError("Foo not found", {"id": str(id)})
                await session.commit()
        except IntegrityError as exc:
            # FK on delete → InUseError instead of generic ConflictError
            raise InUseError("Foo is referenced", {"id": str(id)}) from exc

def _apply_filter(stmt: object, filter: FooListFilter) -> object:
    if filter.parent_ids:
        stmt = stmt.where(foos_table.c.bar_id.in_(filter.parent_ids))
    return stmt
```

### Template — unit-of-work-managed form

Only the constructor and the method bodies differ: methods use `self._session.execute(...)` directly and
**never call `commit()`** — the unit of work owns the transaction.

```python
class FooRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, foo: Foo) -> None:
        try:
            await self._session.execute(
                foos_table.insert().values(id=foo.id, name=foo.name)
            )
        except IntegrityError as exc:
            raise _map_integrity_error(exc) from exc
```

### Rules — form

1. **One class per module.** File `<aggregate_snake>_repository.py`, class `<Aggregate>Repository`.
2. **No explicit `(IFooRepository)` inheritance.** Structural subtyping.
3. **Method signatures match the protocol exactly**, keyword-only markers included
   (`*, filter: FooListFilter`). Every public method is `async`.

### Rules — session

4. **Standalone:** each method opens its own session (`async with self._sf() as session:`); a mutation
   `await session.commit()`, a read does not.
5. **Unit-of-work-managed:** the session arrives in `__init__` and is used directly; **never** call
   `commit()` or `rollback()`.
6. **No instance state holding a session.** Do not pass one across methods — a multi-statement read
   shares a single `async with` block instead.

### Rules — reads

7. `get_by_id(id)` raises `NotFoundError` when absent, never returns `None`.
8. `get_by_<other>(value)` returns `Entity | None` via `result.one_or_none()`.
9. `list(*, filter)` returns `Sequence[Entity]`, always with an `order_by` derived from `filter.sort` — a
   module-level `_SORT_COLUMNS` map from each sort-enum member to its ordered column. This is the
   sort-key-to-column translation the filter record delegates here; never hardcode one
   `created_at.desc()` that ignores the caller's chosen sort.
10. `count(*, filter)` returns `int` from `select(func.count()).select_from(table)`.
11. Multi-field filter logic extracts to a module-level `_apply_filter(stmt, filter)`.

### Rules — mutations

12. `create(entity)` returns `None`; the handler generated the id. Wrap in
    `try/except IntegrityError`.
13. `update(entity)` returns `None`. `rowcount == 0` → `NotFoundError`. Use `func.now()` for
    `updated_at`.
14. `delete(id)` returns `None`, or a list of related keys when compensation needs them.
    `rowcount == 0` → `NotFoundError`. An FK `IntegrityError` → `InUseError`, not a generic
    `ConflictError`.
15. **Reading `rowcount` is mypy-clean only via a cast.** `AsyncSession.execute` is typed `Result[Any]`,
    which has no `rowcount`. Wrap the DML execute exactly once:
    `result = cast(CursorResult[object], await session.execute(...))`. One canonical form — never a
    `# type: ignore` instead.

### Rules — `IntegrityError` translation

16. **Every `IntegrityError` is translated** before it escapes the repository:
    `raise _map_integrity_error(exc) from exc`, or an inline mapping for one or two cases.
17. **The mapper's fallback is mandatory.** It ends by returning a domain exception —
    `ConflictError("integrity violation", {"constraint": constraint or "unknown", "pgcode": pgcode or "unknown"})`
    — when no specific case matches. **Never `return exc`**: letting `IntegrityError` leak breaks the
    no-framework-exceptions-across-layers rule and produces a 500 where the entrypoint should give a 409.
18. **Pick the most specific exception.** A domain subclass beats `ConflictError`; `InUseError` beats
    `ConflictError` for an FK on delete.
19. **Populate `context` with the offending field and the constraint name.** Always include
    `"constraint": constraint` — the full conventional name — so the entrypoint and the tests can assert
    on it. Field and value keys are added on top, and the raise site and its test agree on them
    (`domain-exception`).
20. **The full constraint names are load-bearing** and must match what the `Table` declared. See the
    naming convention above; a rename is a breaking change touching both halves of this file.
21. **Driver assumption:** the mapper reads `exc.orig.__cause__.constraint_name` (asyncpg) and
    `exc.orig.pgcode` (Postgres SQLSTATE). The project is locked to asyncpg plus Postgres; changing
    driver means changing this access path.

### Rules — row-to-entity mapper

22. Pure functions: no IO, no logging. Convert a naive DB datetime to UTC-aware —
    `dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt`.
23. A simple aggregate (one row → one entity) uses `_row_to_entity` as a private method.
24. A composite aggregate (several rows → one entity) uses a module-level
    `_rows_to_entity(row, child_rows_a, child_rows_b)` plus per-child helpers.

### Evolution — when to extract a shared integrity-error mapper

The per-repository `_map_integrity_error` plus `_FK_FIELD_MAP` is the default. When **three or more**
repositories carry overlapping pgcode handlers (`23503` / `23505` / `23514`), extract
`src/<root>/infrastructure/postgres/integrity_error_mapper.py`, which:

- owns the pgcode-to-exception-family defaults (`23503 → NotFoundError`, `23505 → ConflictError`,
  `23514 → ValidationError`) plus the mandatory fallback;
- exposes `map_integrity_error(exc, *, constraint_map: Mapping[str, ConstraintRule]) -> Exception`, where
  each repository registers only its own constraint-name overrides;
- defines `ConstraintRule` as `(DomainErrorClass, message, context_fn)` so per-repository customization
  stays declarative.

Do not introduce it preemptively. Add it the first time a third repository forces the same boilerplate,
and migrate every existing repository in that one commit — partial adoption causes drift.

## The Alembic revision

Alembic owns the revision chain: `alembic revision` assigns the id and `down_revision` from the current
head. A schema change is a coordinated pair — the `Table` above and a new revision — landing in the same
commit. A later field change is reconciled by authoring a **new** revision, never by rewriting a prior
one. `alembic revision --autogenerate` produces only a draft: it misses naming-convention nuance, partial
indexes and seed data, so hand-edit it against the rules above.

```python
# alembic/versions/0042_create_foos.py  (id + down_revision assigned by `alembic revision`)
"""create foos"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "foos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "bar_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bars.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
        # A check constraint's `name` is the SUFFIX: `env.py` hands Alembic the shared metadata, whose
        # convention prepends `ck_foos_`. The full name written here would come out doubled.
        sa.CheckConstraint("char_length(name) > 0", name="name_non_empty"),
    )
    op.create_index("ix_foos_bar_id", "foos", ["bar_id"])
    op.create_index("ix_foos_created_at", "foos", ["created_at"])

def downgrade() -> None:
    op.drop_index("ix_foos_created_at", table_name="foos")
    op.drop_index("ix_foos_bar_id", table_name="foos")
    op.drop_table("foos")
```

`downgrade()` is mandatory and reverses the operations in the opposite order — the test environment uses
it.

## Inlined typing / import rules

Table module:

- `Table`, `Column`, `ForeignKey`, `Index`, `CheckConstraint`, `UniqueConstraint` and the type names from
  `sqlalchemy`; `UUID` from `sqlalchemy.dialects.postgresql`; `func` from `sqlalchemy.sql`; `metadata`
  from `..metadata`.

Repository module:

- Domain imports absolute (`from myapp.domain.foos import Foo`); the table relative
  (`from ..tables.foos import foos_table`). **Never import the protocol the adapter satisfies** — dead
  F401, and structural subtyping needs no import.
- Rows are read via `.mappings()` → `RowMapping`, and the mapper is typed
  `_row_to_entity(self, row: RowMapping)` accessing columns by **key** (`row["id"]`). Mypy-clean with
  **no** `# type: ignore`. Never type a row as `object` with attribute access — that forces a
  `# type: ignore[attr-defined]` at every column.
- Parameters keep their domain types; never downcast to `dict`.

Both:

- No `from __future__ import annotations`. Full annotations on every method. No comments unless the *why*
  is non-obvious.

## Package wiring

`tables/__init__.py` must re-export the new table module — `from . import foos` + `from .foos import *` —
otherwise Alembic autogenerate cannot see the table. `repositories/__init__.py` must re-export the new
adapter the same way. Mechanics: `architecture`.

## Hard stops

- Spec asks for the SQLAlchemy ORM, a declarative base, or relationships → stop, this codebase uses Core
  only.
- Spec asks for a Postgres `ENUM` type → stop, use `Text` plus a `CheckConstraint`.
- Spec asks for `String(n)` length-bounded varchars → stop, use `Text`.
- Spec changes a constraint name → stop, that is a breaking change; the `Table`, the repository's
  `_map_integrity_error` and the revision all change in the same commit.
- About to pass a SQL expression to `Index` or `CheckConstraint` as a bare string —
  `Index("ix", "lower(email)")` → stop, a bare string is a column NAME; wrap the expression in `text(...)`
  or it raises `ConstraintColumnNotFoundError` at table-construct time, with lint and type-check green.
- Spec asks the repository to commit inside the unit-of-work-managed form → stop, that breaks atomicity.
- Spec asks the repository to log → stop, a repository never logs; the central error handler or the
  calling handler owns that (`python-style`).
- Spec asks for id generation inside the repository → stop, the application handler generates ids.
- Spec includes a data migration (`backfill_*`, `seed_*`) → stop, that is a separate revision file; this
  skill covers DDL only.
