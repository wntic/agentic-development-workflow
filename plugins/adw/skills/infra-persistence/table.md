# Infrastructure SQLAlchemy Table

Produces the SQLAlchemy **Core** `Table`. Column types are a **design decision** (jsonb/pgvector/check/FK), not a mechanical transcription of the entity's fields — that is why this guide leads with the column-type rules. The Alembic migration is **not** part of this file — Alembic owns the revision chain (`alembic revision`); a schema change is a coordinated pair (the `Table` here + a new revision), but only the `Table` is this skill's output, and a later field change is reconciled by authoring a **new** revision, never by rewriting a prior one. Naming follows the project metadata `naming_convention` so that integrity-error translation can dispatch on `constraint_name`.

## When to use vs. neighbours

- Adding/modifying/dropping a persistent table → this skill.
- The repository adapter that queries this table → `repository.md`.
- A data-only migration (`backfill_*`, `seed_*`) with no DDL → its own migration file under `alembic/versions/`; this skill covers only DDL.
- Updating the integrity-error → domain-exception map after a constraint changes → `repository.md`.

## File layout

```
src/<root>/infrastructure/postgres/
├── metadata.py                    # already exists, shared MetaData with naming_convention
└── tables/
    ├── __init__.py                # update to re-export the new module
    └── foos.py                    # this skill's output — the Table module

alembic/versions/
└── 0042_create_foos.py            # NOT this skill's output — authored via `alembic revision`
                                   # (Alembic owns the chain); template + rules below are the reference
```

## Naming convention (load-bearing — do not deviate)

Defined in `infrastructure/postgres/metadata.py`:

```python
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})
```

Generated names that `repository.md`'s integrity-error translator matches on:

- PK: `pk_foos`
- Unique on `name`: `uq_foos_name`
- Index on `author_id`: `ix_foos_author_id`
- FK `foos.bar_id → bars.id`: `fk_foos_bar_id_bars`
- Check with `name="category_xor"`: `ck_foos_category_xor`

**For `CheckConstraint`, `name=` is the suffix.** SQLAlchemy prepends `ck_<table>_`. Pick a stable, descriptive suffix — renaming is a breaking change because the repository grep-matches on it.

## Template — table file

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

## Template — Alembic migration (authored via `alembic revision`, not generated here)

This is the **reference** for the revision authored with `alembic revision` — Alembic assigns the real `revision` / `down_revision` (from the current head), then the draft is hand-edited to match the rules below. It is not this skill's output and is never emitted declaratively (the table is a desired-schema snapshot, not a revision journal).

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
            sa.ForeignKey("bars.id", name="fk_foos_bar_id_bars", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_foos_name"),
        sa.CheckConstraint("char_length(name) > 0", name="ck_foos_name_non_empty"),
    )
    op.create_index("ix_foos_bar_id", "foos", ["bar_id"])
    op.create_index("ix_foos_created_at", "foos", ["created_at"])

def downgrade() -> None:
    op.drop_index("ix_foos_created_at", table_name="foos")
    op.drop_index("ix_foos_bar_id", table_name="foos")
    op.drop_table("foos")
```

`downgrade()` is mandatory and reverses operations in opposite order. The test environment uses it.

## Rules — column types

- **UUID:** `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`. Never plain `UUID()`.
- **Timestamps:** `DateTime(timezone=True)` with `server_default=func.now()` for `created_at` / `updated_at`. Never naive.
- **Text:** `Text`, not `String(n)`. No length-bounded varchars.
- **Integers:** `Integer`; `SmallInteger` only when the domain is bounded.
- **Booleans:** `Boolean`.
- **Enums:** `Text` + `CheckConstraint` listing valid values — **not** Postgres `ENUM`. Matches the domain `StrEnum` pattern.

## Rules — FK `ondelete`

- `RESTRICT` — FK target is a **referenced lookup** (e.g. `bars`). The repository translates the resulting `IntegrityError` to `InUseError`.
- `CASCADE` — FK target is the **parent of an owned child** (`foo_children.foo_id → foos.id`).
- `SET NULL` — only when the column is nullable and absence has domain meaning. Rare.

Pick once; document the consequence in the repository's `delete` method.

## Rules — indexes

- Index every FK column you filter or join on. SQLAlchemy does **not** create FK indexes automatically.
- Index columns used in `ORDER BY` of list endpoints (e.g. `created_at`) and in `WHERE` of filter records.
- Single-column index name: `ix_<table>_<col>`. Composite indexes are named explicitly with the same prefix.
- **A bare string argument to `Index` is a COLUMN NAME, not an expression.** `Index("ix_users_email_lower", "lower(email)")` makes SQLAlchemy look for a column literally named `lower(email)` and raises `ConstraintColumnNotFoundError` when the `MetaData` is constructed (mypy + ruff stay green — only constructing the table catches it). A **functional / expression index** wraps the SQL in `text(...)`: `Index("ix_users_email_lower", text("lower(email)"))`. Import `text` from `sqlalchemy`.

## Rules — constraint names (load-bearing)

- **Never pass `name=` for primary keys, FKs, uniques, or indexes in the `Table` definition** — let the metadata convention generate them.
- **Always pass `name=` (the suffix) for `CheckConstraint`** so the convention can prepend `ck_<table>_`.
- **In Alembic migrations, write the full conventional name yourself** (`name="fk_foos_bar_id_bars"`, `name="uq_foos_name"`, `name="ck_foos_name_non_empty"`). Alembic doesn't read the `Table`'s `MetaData` convention; it serializes what you write.
- The full name is what `_map_integrity_error` matches on. Renaming is a breaking change — update the repository's map in the same commit.

## Rules — junction and owned-children tables

- **Junction table:** composite primary key across both FKs, no surrogate `id`; both columns `primary_key=True`; index the non-leading FK column.
- **Owned-children table:** surrogate `id`, FK to parent with `ondelete="CASCADE"`, plus a unique constraint on natural identity (e.g. `UniqueConstraint("foo_id", "position", name="uq_foo_children_foo_position")`).

## Rules — server vs application defaults

- `created_at` / `updated_at` use `server_default=func.now()` so existing rows behave correctly during migration.
- Application-managed `updated_at` on update: the repository sets it explicitly via `sqlfunc.now()` in the `UPDATE` statement — server default fires only on `INSERT`.
- Domain-meaningful defaults use `server_default="..."`. **Keep the value identical** between table definition and migration.

## Coordinated change (the Table scaffold + an Alembic revision)

A schema change is two coordinated edits: the `Table` here (this skill's output) and an Alembic revision authored separately via `alembic revision` (Alembic owns the chain — the table never carries migrations). The two land in the same commit. `alembic revision --autogenerate` is only a draft — it misses naming-convention nuance, partial indexes, and seed data — so hand-edit it against the rules above after generating.

## Inlined typing / import rules

- `Table`, `Column`, `ForeignKey`, `Index`, `CheckConstraint`, `UniqueConstraint`, type imports from `sqlalchemy`.
- `UUID` from `sqlalchemy.dialects.postgresql`.
- `func` from `sqlalchemy.sql`.
- `metadata` from `..metadata`.
- No `from __future__ import annotations`. No comments unless a non-obvious *why*.

## Package wiring

The `tables/__init__.py` must re-export the new module — `from . import foos` + `from .foos import *` — otherwise Alembic autogenerate cannot see the table. Follow `architecture` §Python Package Structure for the mechanics.

## Hard stops

- Spec asks for a Postgres `ENUM` type → stop, use `Text` + `CheckConstraint`.
- Spec asks for `String(n)` length-bounded varchars → stop, use `Text`.
- Spec changes a constraint name → stop, this is a breaking change; the repository's `_map_integrity_error` must be updated in the same commit (`repository.md`).
- Spec includes a data migration (`backfill_*`, `seed_*`) → stop, that's a separate migration file; this skill handles DDL only.
- About to pass a SQL expression to `Index`/`CheckConstraint` as a bare string (`Index("ix", "lower(email)")`) → stop, a bare string is a column NAME; wrap an expression in `text(...)` or it raises `ConstraintColumnNotFoundError` at table-construct time (green under mypy/ruff).
