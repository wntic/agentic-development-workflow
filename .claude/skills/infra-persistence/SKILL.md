---
name: infra-persistence
description: "House style for persistence adapters under polyglot storage: relational repositories on SQLAlchemy Core (never the ORM) with an IntegrityError-to-domain-exception translator, the write-once `Table` scaffold, client-style store repositories (vector / cache / document), and the Alembic revision discipline the implementer owns."
when_to_use: Producing a repository adapter (relational or client-style store), a SQLAlchemy `Table`, or authoring the Alembic revision that pairs with a schema change.
---
# Infrastructure — persistence

This merged skill covers 3 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from infra-sqlalchemy-repository -->

## Infrastructure SQLAlchemy Repository

Produces one repository class that adapts a domain repository protocol to SQLAlchemy Core + Postgres. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract.

### When to use vs. neighbours

- The protocol file (`i_foo_repository.py`) → `domain-repository-protocol`.
- The table + Alembic migration → `infra-sqlalchemy-table`.
- The DI provider that constructs this repository → `infra-di-provider`.
- The UoW protocol/impl/integration when the repo joins multi-repo transactions → `pattern-unit-of-work`.

### Pick the constructor style

- **Standalone (`session_factory`-injected).** Default. CRUD on a single aggregate; opens its own session, commits per call.
- **UoW-managed (`session`-injected).** Joins a Unit of Work (multi-repo atomicity, audit writes). Receives a live session, **never commits**.

The two forms are mutually exclusive for one class. If both call-styles are genuinely needed, write two adapters.

### File layout

```
src/<root>/infrastructure/postgres/repositories/
├── __init__.py            # update to re-export the new module
└── foo_repository.py      # this skill writes this file
```

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

# Translate the filter's sort key (a domain enum) to an ordered column — this
# mapping IS the "sort-key → column" translation domain-filter Rule 6 delegates
# here. One entry per FooSort member; the member encodes both column and
# direction. `created_at.desc()` is just this aggregate's default, not a baked-in
# universal order.
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

### Template — UoW-managed form

Only the constructor and method bodies differ. Methods use `self._session.execute(...)` directly and **never call `commit()`** — the UoW owns the transaction.

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

### Rules

#### Form

1. **One class per module.** Filename: `<aggregate_snake>_repository.py`. Class: `<Aggregate>Repository`.
2. **No explicit `(IFooRepository)` inheritance.** Structural subtyping.
3. **Method signatures match the protocol exactly**, including keyword-only markers (`*, filter: FooListFilter`). All public methods are `async`.

#### Session

4. **Standalone:** each method opens its own session (`async with self._sf() as session:`); mutations `await session.commit()`, reads don't.
5. **UoW-managed:** the session is passed in `__init__`; methods use it directly; **never call `commit()` or `rollback()`** in a UoW repo.
6. **No instance state holding a session.** Don't pass a session across methods (multi-statement reads share one `async with` block instead).

#### Reads

7. `get_by_id(id)` raises `NotFoundError` when absent (never returns `None`).
8. `get_by_<other>(value)` returns `Entity | None` via `result.one_or_none()`.
9. `list(*, filter)` returns `Sequence[Entity]`; always include `order_by`, and derive it from `filter.sort` — a module-level `_SORT_COLUMNS` map from each sort-enum member to its ordered column (`.asc()` / `.desc()`). This is the sort-key→column translation `domain-filter` Rule 6 delegates to the adapter; never hardcode a single `created_at.desc()` that ignores the caller's chosen sort.
10. `count(*, filter)` returns `int` from `select(func.count()).select_from(table)`.
11. Multi-field filter logic extracts to a module-level `_apply_filter(stmt, filter)`.

#### Mutations

12. `create(entity)` returns `None`. Handler generates the ID. Wrap in `try/except IntegrityError`.
13. `update(entity)` returns `None`. `rowcount == 0` → `NotFoundError`. Use `func.now()` for `updated_at`.
14. `delete(id)` returns `None` (or a list of related keys when needed for compensation). `rowcount == 0` → `NotFoundError`. FK `IntegrityError` → `InUseError`, not generic `ConflictError`.
14a. **Reading `rowcount` is mypy-clean only via a cast.** `AsyncSession.execute` is typed `Result[Any]`, which has no `rowcount`. Wrap the DML execute exactly once: `result = cast(CursorResult[object], await session.execute(...))`. One canonical form — never reach for `# type: ignore` instead.

#### IntegrityError translation

15. **Every `IntegrityError` is translated** before escaping the repository. Use `raise _map_integrity_error(exc) from exc` (or an inline mapping for 1–2 cases).
16. **Mandatory mapper fallback.** The mapper must end by raising a domain exception (`ConflictError("integrity violation", {"constraint": constraint or "unknown", "pgcode": pgcode or "unknown"})`) when no specific case matches. **Never `return exc`** — letting `IntegrityError` leak out of the repository breaks the no-framework-exceptions-cross-layer rule and produces a 500 instead of a 409 at the entrypoint.
17. **Pick the most specific exception.** Domain subclass beats `ConflictError`. `InUseError` beats `ConflictError` for FK-on-delete.
18. **Populate `context` with the offending field and the constraint name.** Always include `"constraint": constraint` (the full conventional name) so the entrypoint and tests can assert on it. Field/value keys are added on top; the raise site and its handler test simply agree on them (see `domain-exception`).
19. **The constraint full names are load-bearing.** They must match what `infra-sqlalchemy-table` declared. A constraint rename is a breaking change — update this file in the same commit.
20. **Driver assumption:** the mapper reads `exc.orig.__cause__.constraint_name` (asyncpg) and `exc.orig.pgcode` (Postgres SQLSTATE). The project is locked to asyncpg + Postgres; changing the driver requires updating the access path here.

#### Row → entity mapper

21. Pure functions, no IO, no logging. Convert naive DB datetimes to UTC-aware (`dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt`).
22. Simple aggregate (single row → entity): `_row_to_entity` as a private method.
23. Composite aggregate (multiple rows → one entity): module-level `_rows_to_entity(row, child_rows_a, child_rows_b)` + per-child helpers.

### Evolution — when to extract a shared integrity-error mapper

The per-repo `_map_integrity_error` + `_FK_FIELD_MAP` pattern is the default. When ≥3 repositories carry overlapping pgcode handlers (`23503` / `23505` / `23514`), extract a shared module:

```
src/<root>/infrastructure/postgres/integrity_error_mapper.py
```

The shared module:

- Owns the pgcode → exception-family default mapping (`23503 → NotFoundError`, `23505 → ConflictError`, `23514 → ValidationError`) plus the mandatory fallback.
- Exposes `map_integrity_error(exc, *, constraint_map: Mapping[str, ConstraintRule]) -> Exception` where each repo registers only its constraint-name-specific overrides.
- A `ConstraintRule` is `(DomainErrorClass, message, context_fn)` so per-repo customization stays declarative.

Don't introduce this preemptively. Add it the first time a third repository forces the same pgcode boilerplate. Document the move in a single commit that migrates all current repositories at once — partial adoption causes drift.

### Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.foos import Foo`). Table imports relative (`from ..tables.foos import foos_table`). **Never import the protocol the adapter satisfies** (`IFooRepository`) — structural subtyping needs no import (Rule 2); importing it is a dead F401.
- Rows are read via `.mappings()` → `RowMapping`; the mapper is typed `_row_to_entity(self, row: RowMapping)` and accesses columns by **key** (`row["id"]`). This is mypy-clean with **no** `# type: ignore` (the `Any` key value is consumed as a constructor argument, never returned). Never type a row as `object` + attribute access — that forces a `# type: ignore[attr-defined]` at every column.
- Parameters keep domain types — never downcast to `dict`.
- No `from __future__ import annotations`. Full annotations on every method.

### Package wiring

The `repositories/__init__.py` must re-export the new module via `from .foo_repository import *`. Follow `general-python-package`.

### Hard stops

- Spec asks for the SQLAlchemy ORM, declarative base, or relationships → stop, this codebase uses Core only.
- Spec asks the repository to commit inside a UoW-managed form → stop, that breaks atomicity.
- Spec asks the repository to log → stop, repositories never log; the central error handler or the calling handler owns logging.
- Spec asks for ID generation inside the repository → stop, the application handler generates IDs.
- The constraint full names in the spec don't match the table file → stop, fix the alignment before writing the repository.


<!-- merged from infra-sqlalchemy-table -->

## Infrastructure SQLAlchemy Table

Produces the SQLAlchemy **Core** `Table`. Column types are a **design decision** (jsonb/pgvector/check/FK), not a mechanical transcription of the entity's fields — that is why this guide leads with the column-type rules. The Alembic migration is **not** part of this file — Alembic owns the revision chain (`alembic revision`); a schema change is a coordinated pair (the `Table` here + a new revision), but only the `Table` is this skill's output, and a later field change is reconciled by authoring a **new** revision, never by rewriting a prior one. Naming follows the project metadata `naming_convention` so that integrity-error translation can dispatch on `constraint_name`.

### When to use vs. neighbours

- Adding/modifying/dropping a persistent table → this skill.
- The repository adapter that queries this table → `infra-sqlalchemy-repository`.
- A data-only migration (`backfill_*`, `seed_*`) with no DDL → its own migration file under `alembic/versions/`; this skill covers only DDL.
- Updating the integrity-error → domain-exception map after a constraint changes → `infra-sqlalchemy-repository`.

### File layout

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

### Naming convention (load-bearing — do not deviate)

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

Generated names that `infra-sqlalchemy-repository`'s integrity-error translator matches on:

- PK: `pk_foos`
- Unique on `name`: `uq_foos_name`
- Index on `author_id`: `ix_foos_author_id`
- FK `foos.bar_id → bars.id`: `fk_foos_bar_id_bars`
- Check with `name="category_xor"`: `ck_foos_category_xor`

**For `CheckConstraint`, `name=` is the suffix.** SQLAlchemy prepends `ck_<table>_`. Pick a stable, descriptive suffix — renaming is a breaking change because the repository grep-matches on it.

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

### Template — Alembic migration (authored via `alembic revision`, not generated here)

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

### Rules — column types

- **UUID:** `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`. Never plain `UUID()`.
- **Timestamps:** `DateTime(timezone=True)` with `server_default=func.now()` for `created_at` / `updated_at`. Never naive.
- **Text:** `Text`, not `String(n)`. No length-bounded varchars.
- **Integers:** `Integer`; `SmallInteger` only when the domain is bounded.
- **Booleans:** `Boolean`.
- **Enums:** `Text` + `CheckConstraint` listing valid values — **not** Postgres `ENUM`. Matches the domain `StrEnum` pattern.

### Rules — FK `ondelete`

- `RESTRICT` — FK target is a **referenced lookup** (e.g. `bars`). The repository translates the resulting `IntegrityError` to `InUseError`.
- `CASCADE` — FK target is the **parent of an owned child** (`foo_children.foo_id → foos.id`).
- `SET NULL` — only when the column is nullable and absence has domain meaning. Rare.

Pick once; document the consequence in the repository's `delete` method.

### Rules — indexes

- Index every FK column you filter or join on. SQLAlchemy does **not** create FK indexes automatically.
- Index columns used in `ORDER BY` of list endpoints (e.g. `created_at`) and in `WHERE` of filter records.
- Single-column index name: `ix_<table>_<col>`. Composite indexes are named explicitly with the same prefix.
- **A bare string argument to `Index` is a COLUMN NAME, not an expression.** `Index("ix_users_email_lower", "lower(email)")` makes SQLAlchemy look for a column literally named `lower(email)` and raises `ConstraintColumnNotFoundError` when the `MetaData` is constructed (mypy + ruff stay green — only constructing the table catches it). A **functional / expression index** wraps the SQL in `text(...)`: `Index("ix_users_email_lower", text("lower(email)"))`. Import `text` from `sqlalchemy`.

### Rules — constraint names (load-bearing)

- **Never pass `name=` for primary keys, FKs, uniques, or indexes in the `Table` definition** — let the metadata convention generate them.
- **Always pass `name=` (the suffix) for `CheckConstraint`** so the convention can prepend `ck_<table>_`.
- **In Alembic migrations, write the full conventional name yourself** (`name="fk_foos_bar_id_bars"`, `name="uq_foos_name"`, `name="ck_foos_name_non_empty"`). Alembic doesn't read the `Table`'s `MetaData` convention; it serializes what you write.
- The full name is what `_map_integrity_error` matches on. Renaming is a breaking change — update the repository's map in the same commit.

### Rules — junction and owned-children tables

- **Junction table:** composite primary key across both FKs, no surrogate `id`; both columns `primary_key=True`; index the non-leading FK column.
- **Owned-children table:** surrogate `id`, FK to parent with `ondelete="CASCADE"`, plus a unique constraint on natural identity (e.g. `UniqueConstraint("foo_id", "position", name="uq_foo_children_foo_position")`).

### Rules — server vs application defaults

- `created_at` / `updated_at` use `server_default=func.now()` so existing rows behave correctly during migration.
- Application-managed `updated_at` on update: the repository sets it explicitly via `sqlfunc.now()` in the `UPDATE` statement — server default fires only on `INSERT`.
- Domain-meaningful defaults use `server_default="..."`. **Keep the value identical** between table definition and migration.

### Coordinated change (the Table scaffold + an Alembic revision)

A schema change is two coordinated edits: the `Table` here (this skill's output) and an Alembic revision authored separately via `alembic revision` (Alembic owns the chain — the table never carries migrations). The two land in the same commit. `alembic revision --autogenerate` is only a draft — it misses naming-convention nuance, partial indexes, and seed data — so hand-edit it against the rules above after generating.

### Inlined typing / import rules

- `Table`, `Column`, `ForeignKey`, `Index`, `CheckConstraint`, `UniqueConstraint`, type imports from `sqlalchemy`.
- `UUID` from `sqlalchemy.dialects.postgresql`.
- `func` from `sqlalchemy.sql`.
- `metadata` from `..metadata`.
- No `from __future__ import annotations`. No comments unless a non-obvious *why*.

### Package wiring

The `tables/__init__.py` must re-export the new module — `from . import foos` + `from .foos import *` — otherwise Alembic autogenerate cannot see the table. Follow `general-python-package` for the mechanics.

### Hard stops

- Spec asks for a Postgres `ENUM` type → stop, use `Text` + `CheckConstraint`.
- Spec asks for `String(n)` length-bounded varchars → stop, use `Text`.
- Spec changes a constraint name → stop, this is a breaking change; the repository's `_map_integrity_error` must be updated in the same commit (`infra-sqlalchemy-repository`).
- Spec includes a data migration (`backfill_*`, `seed_*`) → stop, that's a separate migration file; this skill handles DDL only.
- About to pass a SQL expression to `Index`/`CheckConstraint` as a bare string (`Index("ix", "lower(email)")`) → stop, a bare string is a column NAME; wrap an expression in `text(...)` or it raises `ConstraintColumnNotFoundError` at table-construct time (green under mypy/ruff).


<!-- merged from infra-store-repository -->

## Infrastructure Store Repository

Produces one repository class that adapts a domain repository protocol to a client-style datastore — any store reached through an injected SDK client rather than the shared SQLAlchemy bootstrap. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract. The skill is **vendor-agnostic** the same way `infra-capability-adapter` is: the pattern (client injection, record↔entity mapping, boundary error translation) is fixed here; the vendor rides in via the injected client type, the store's settings, and the spec's notes.

### When to use vs. neighbours

- The aggregate's store is the relational bootstrap store (SQLAlchemy/Postgres) → `infra-sqlalchemy-repository`.
- The protocol file (`i_foo_repository.py`) → `domain-repository-protocol`.
- A single-action `ICan<Verb>` port (not an aggregate's collection) → `infra-capability-adapter`.
- The settings class the store's connection factory consumes → `infra-settings`.
- The DI provider that constructs this repository → `infra-di-provider`.
- An in-memory test stand-in for handler unit tests → `test-fake-repository`.
- The integration contract test that drives this adapter against the real store → `test-store-repository-contract`.

### File layout

```
src/<root>/infrastructure/<store-kind>/   # qdrant/, redis/, <vendor>/ — infra groups by tech
├── __init__.py
├── connection.py          # create_<store>_client(settings) — the datastore's factory, not this skill
├── settings.py            # infra-settings
└── repositories/
    ├── __init__.py        # update to re-export the new module
    └── foo_repository.py  # this skill writes this file
```

### Template — key-value / document form

```python
import json
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from myapp.domain.exceptions import NotFoundError, UpstreamError
# Never import IFooRepository — the adapter does NOT inherit the protocol (structural
# subtyping at the DI site is the contract, Rule 2). Importing it leaves a dead F401.
from myapp.domain.foos import Foo

from ..settings import FoosStoreSettings

__all__ = ["FooRepository"]


class FooRepository:
    def __init__(self, client: Redis, settings: FoosStoreSettings) -> None:
        self._client = client
        self._prefix = settings.key_prefix   # the store's container token (Rule 5)

    def _key(self, foo_id: UUID) -> str:
        return f"{self._prefix}:{foo_id}"

    def _record_to_entity(self, record: dict[str, object]) -> Foo:
        return Foo(id=UUID(str(record["id"])), name=str(record["name"]))

    async def add(self, foo: Foo) -> None:
        record = {"id": str(foo.id), "name": foo.name}
        try:
            await self._client.set(self._key(foo.id), json.dumps(record))
        except RedisError as exc:
            raise UpstreamError(
                "store write failed",
                {"key": self._key(foo.id), "reason": exc.__class__.__name__},
            ) from exc

    async def get_by_id(self, foo_id: UUID) -> Foo:
        try:
            raw = await self._client.get(self._key(foo_id))
        except RedisError as exc:
            raise UpstreamError(
                "store read failed",
                {"key": self._key(foo_id), "reason": exc.__class__.__name__},
            ) from exc
        if raw is None:
            raise NotFoundError("Foo not found", {"id": str(foo_id)})
        return self._record_to_entity(json.loads(raw))

    async def delete(self, foo_id: UUID) -> None:
        try:
            removed = await self._client.delete(self._key(foo_id))
        except RedisError as exc:
            raise UpstreamError(
                "store delete failed",
                {"key": self._key(foo_id), "reason": exc.__class__.__name__},
            ) from exc
        if removed == 0:
            raise NotFoundError("Foo not found", {"id": str(foo_id)})
```

### Template — vector-collection form

```python
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from myapp.domain.exceptions import UpstreamError
from myapp.domain.foos import Foo

from ..settings import FoosVectorSettings

__all__ = ["FooRepository"]


class FooRepository:
    def __init__(self, client: AsyncQdrantClient, settings: FoosVectorSettings) -> None:
        self._client = client
        self._collection = settings.collection

    async def add_many(self, foos: tuple[Foo, ...]) -> None:
        points = [
            PointStruct(
                id=str(foo.id),
                vector=foo.vector,
                payload={"bar_id": str(foo.bar_id), "text": foo.text},
            )
            for foo in foos
        ]
        try:
            await self._client.upsert(collection_name=self._collection, points=points)
        # qdrant's SDK has no single exception root — the boundary broad-catch is
        # sanctioned HERE because every path translates before re-raising (Rule 9).
        except Exception as exc:
            raise UpstreamError(
                "vector upsert failed",
                {"collection": self._collection, "reason": exc.__class__.__name__},
            ) from exc

    async def search(
        self, query_vector: list[float], k: int
    ) -> tuple[tuple[Foo, float], ...]:
        try:
            response = await self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                limit=k,
                with_payload=True,
                with_vectors=True,  # each entity carries its OWN vector, never the query's
            )
        except Exception as exc:
            raise UpstreamError(
                "vector search failed",
                {"collection": self._collection, "reason": exc.__class__.__name__},
            ) from exc
        # The store computed a similarity score per hit — return it alongside the entity
        # (the protocol's pair shape exists precisely so the score is not discarded).
        return tuple(
            (self._point_to_entity(point), point.score) for point in response.points
        )

    async def delete_by_bar(self, bar_id: UUID) -> None:
        selector = FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="bar_id", match=MatchValue(value=str(bar_id)))]
            )
        )
        try:
            await self._client.delete(
                collection_name=self._collection, points_selector=selector
            )
        except Exception as exc:
            raise UpstreamError(
                "vector delete failed",
                {
                    "collection": self._collection,
                    "bar_id": str(bar_id),
                    "reason": exc.__class__.__name__,
                },
            ) from exc

    def _point_to_entity(self, point: object) -> Foo:
        payload = point.payload or {}  # type: ignore[attr-defined]
        return Foo(
            id=UUID(str(point.id)),  # type: ignore[attr-defined]
            bar_id=UUID(str(payload["bar_id"])),
            text=str(payload["text"]),
            vector=list(point.vector or []),  # type: ignore[attr-defined]
        )
```

### Rules

#### Form

1. **One class per module.** Filename: `<aggregate_snake>_repository.py`. Class: `<Aggregate>Repository` — **no vendor in the class name** (the directory carries the tech; an aggregate has exactly one home store, unlike a capability port that several vendors may implement).
2. **No explicit `(IFooRepository)` inheritance.** Structural subtyping.
3. **Method signatures match the protocol exactly**, including async mode, keyword-only markers, and compound return shapes (a `tuple[tuple[Foo, float], ...]` of scored hits is returned as pairs — never flattened to bare entities with the score discarded).

#### Client & settings

4. **Inject the SDK client and the settings class.** Both come from `containers.py`; the client is built once by the datastore's `create_<store>_client(settings)` factory and injected as a `Singleton`. Never construct a client inline in a method, and never swap the injected client type for a different flavor of the SDK.
5. **Stash only what the methods need** — typically the store's *container token* (collection / key-prefix / index / bucket name) read from settings in `__init__`.

#### Records ↔ entities

6. **Private, pure mapping helpers** (`_record_to_entity` / `_point_to_entity` / `_entity_to_record`): no IO, no logging. IDs serialize as strings unless the SDK is UUID-native.
7. **The record shape is a design decision, not a transcription.** What becomes the key, what goes into the payload, what the store indexes — the client-store analogue of "column types are judgment" in `infra-sqlalchemy-table`. The spec's notes guide it.
8. **An entity is reconstructed from its own stored data.** Never substitute query-side values for stored ones (e.g. a search result's vector is the point's own, not the query's); when the read path doesn't consume a stored field, omit it explicitly rather than faking it.

#### Exception translation

9. **Catch the SDK's exception family at the boundary and raise a domain exception** with `raise <DomainException>(...) from exc`. When the SDK has no single exception root (qdrant), a broad `except Exception` immediately around the client call is sanctioned — every path must translate. The SDK's exception types never escape the repository.
10. **Mandatory fallback:** `UpstreamError` for network / unknown store failures. An absent record on `get_by_id` is **not** an SDK error — detect it (a `None`, an empty result, a zero count) and raise `NotFoundError`.
11. **Populate `context`** with the container token (`collection` / `key` / `index`), the identifying inputs, and the upstream code or exception class name.

#### Vendor & semantics

12. **Vendor semantics come from the SDK + the spec's notes, not from this skill.** Query API, filter DSL, batching, consistency options — read them from the SDK and the node's notes. A **new vendor is a store-profile row plus `requires_packages` on the node — never a fork of this skill** (the same way `infra-capability-adapter` serves boto3, httpx, PyJWT, and openai with one skill).
13. **No provisioning.** The repository never creates collections, indexes, buckets, or schemas — provisioning is a deployment/bootstrap concern.
14. **Ordering is explicit.** A `list`/`search` that promises an order must produce it deliberately (the store's score order, an explicit sort key) — never rely on insertion accident.
15. **No logging, no retries, no caching, no domain reasoning.** Same thinness contract as every adapter (see `infra-capability-adapter` rules 13–15).

### Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.foos import Foo`); the sibling settings module relative (`from ..settings import FoosStoreSettings`). **Never import the protocol the adapter satisfies** — structural subtyping needs no import (Rule 2); importing it is a dead F401.
- SDK types stay inside the adapter; method signatures use domain types or primitives only.
- Raw SDK payloads may be `dict[str, Any]` / `object` at the immediate boundary — convert to the domain type in the mapping helper, never return them.
- No `from __future__ import annotations`. Full annotations on every method.

### Package wiring

The `repositories/__init__.py` must re-export the new module via `from .foo_repository import *`. Follow `general-python-package`.

### Hard stops

- The aggregate's store is the relational bootstrap store (profile `uses_bootstrap`) → stop, use `infra-sqlalchemy-repository`.
- Spec asks for SQL, SQLAlchemy, or a `Table` for this aggregate → stop, that is the relational path (`infra-sqlalchemy-repository` + `infra-sqlalchemy-table`).
- Spec asks the repository to create or migrate the collection/index/bucket → stop, provisioning is not the repository's concern.
- Spec asks for atomicity across this store and another (two stores in one transaction) → stop, there is no cross-store transaction; compensation lives in the handler (`pattern-compensating-tx`).
- Spec asks the repository to log → stop, repositories never log.
- The port is a single-action capability (`ICan<Verb>`), not an aggregate's collection → stop, use `infra-capability-adapter`.


## Declaring `ConflictError` on a first unique-insert (catalog side)

When a change first inserts or renames against a **unique constraint**, the error catalog must declare `ConflictError` (`code: CONFLICT`, HTTP 409) so the relational repository's `IntegrityError` translator (above) can map to it. Omit it and a duplicate surfaces as a bare `DomainError` → **HTTP 500 instead of 409**. Phrased for the spec-author / test-author reader: a unique constraint introduced by the change implies a `ConflictError` in `domain/exceptions.py` and a 409 acceptance test. The same earn-per-need rule governs `NotFoundError` / `ValidationError` / `InUseError` — declare each the first time a behaviour needs it, never as a blanket catalog. (Harvested from notes/16 R1.)
