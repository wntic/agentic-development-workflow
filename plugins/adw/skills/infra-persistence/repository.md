# Infrastructure SQLAlchemy Repository

Produces one repository class that adapts a domain repository protocol to SQLAlchemy Core + Postgres. The adapter does not inherit from the protocol — structural subtyping at the DI injection site is the contract.

## When to use vs. neighbours

- The protocol file (`i_foo_repository.py`) → `domain-ports` §Domain Repository Protocol.
- The table + Alembic migration → `table.md`.
- The DI provider that constructs this repository → `infra-integration` `container.md`.
- The UoW protocol/impl/integration when the repo joins multi-repo transactions → `application` `unit-of-work.md`.

## Pick the constructor style

- **Standalone (`session_factory`-injected).** Default. CRUD on a single aggregate; opens its own session, commits per call.
- **UoW-managed (`session`-injected).** Joins a Unit of Work (multi-repo atomicity, audit writes). Receives a live session, **never commits**.

The two forms are mutually exclusive for one class. If both call-styles are genuinely needed, write two adapters.

## File layout

```
src/<root>/infrastructure/postgres/repositories/
├── __init__.py            # update to re-export the new module
└── foo_repository.py      # this skill writes this file
```

## Template — standalone form

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

## Template — UoW-managed form

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

## Rules

### Form

1. **One class per module.** Filename: `<aggregate_snake>_repository.py`. Class: `<Aggregate>Repository`.
2. **No explicit `(IFooRepository)` inheritance.** Structural subtyping.
3. **Method signatures match the protocol exactly**, including keyword-only markers (`*, filter: FooListFilter`). All public methods are `async`.

### Session

4. **Standalone:** each method opens its own session (`async with self._sf() as session:`); mutations `await session.commit()`, reads don't.
5. **UoW-managed:** the session is passed in `__init__`; methods use it directly; **never call `commit()` or `rollback()`** in a UoW repo.
6. **No instance state holding a session.** Don't pass a session across methods (multi-statement reads share one `async with` block instead).

### Reads

7. `get_by_id(id)` raises `NotFoundError` when absent (never returns `None`).
8. `get_by_<other>(value)` returns `Entity | None` via `result.one_or_none()`.
9. `list(*, filter)` returns `Sequence[Entity]`; always include `order_by`, and derive it from `filter.sort` — a module-level `_SORT_COLUMNS` map from each sort-enum member to its ordered column (`.asc()` / `.desc()`). This is the sort-key→column translation `domain-model` §Domain Filter Record Rule 6 delegates to the adapter; never hardcode a single `created_at.desc()` that ignores the caller's chosen sort.
10. `count(*, filter)` returns `int` from `select(func.count()).select_from(table)`.
11. Multi-field filter logic extracts to a module-level `_apply_filter(stmt, filter)`.

### Mutations

12. `create(entity)` returns `None`. Handler generates the ID. Wrap in `try/except IntegrityError`.
13. `update(entity)` returns `None`. `rowcount == 0` → `NotFoundError`. Use `func.now()` for `updated_at`.
14. `delete(id)` returns `None` (or a list of related keys when needed for compensation). `rowcount == 0` → `NotFoundError`. FK `IntegrityError` → `InUseError`, not generic `ConflictError`.
14a. **Reading `rowcount` is mypy-clean only via a cast.** `AsyncSession.execute` is typed `Result[Any]`, which has no `rowcount`. Wrap the DML execute exactly once: `result = cast(CursorResult[object], await session.execute(...))`. One canonical form — never reach for `# type: ignore` instead.

### IntegrityError translation

15. **Every `IntegrityError` is translated** before escaping the repository. Use `raise _map_integrity_error(exc) from exc` (or an inline mapping for 1–2 cases).
16. **Mandatory mapper fallback.** The mapper must end by raising a domain exception (`ConflictError("integrity violation", {"constraint": constraint or "unknown", "pgcode": pgcode or "unknown"})`) when no specific case matches. **Never `return exc`** — letting `IntegrityError` leak out of the repository breaks the no-framework-exceptions-cross-layer rule and produces a 500 instead of a 409 at the entrypoint.
17. **Pick the most specific exception.** Domain subclass beats `ConflictError`. `InUseError` beats `ConflictError` for FK-on-delete.
18. **Populate `context` with the offending field and the constraint name.** Always include `"constraint": constraint` (the full conventional name) so the entrypoint and tests can assert on it. Field/value keys are added on top; the raise site and its handler test simply agree on them (see `domain-model` §Domain Exception).
19. **The constraint full names are load-bearing.** They must match what `table.md` declared. A constraint rename is a breaking change — update this file in the same commit.
20. **Driver assumption:** the mapper reads `exc.orig.__cause__.constraint_name` (asyncpg) and `exc.orig.pgcode` (Postgres SQLSTATE). The project is locked to asyncpg + Postgres; changing the driver requires updating the access path here.

### Row → entity mapper

21. Pure functions, no IO, no logging. Convert naive DB datetimes to UTC-aware (`dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt`).
22. Simple aggregate (single row → entity): `_row_to_entity` as a private method.
23. Composite aggregate (multiple rows → one entity): module-level `_rows_to_entity(row, child_rows_a, child_rows_b)` + per-child helpers.

## Evolution — when to extract a shared integrity-error mapper

The per-repo `_map_integrity_error` + `_FK_FIELD_MAP` pattern is the default. When ≥3 repositories carry overlapping pgcode handlers (`23503` / `23505` / `23514`), extract a shared module:

```
src/<root>/infrastructure/postgres/integrity_error_mapper.py
```

The shared module:

- Owns the pgcode → exception-family default mapping (`23503 → NotFoundError`, `23505 → ConflictError`, `23514 → ValidationError`) plus the mandatory fallback.
- Exposes `map_integrity_error(exc, *, constraint_map: Mapping[str, ConstraintRule]) -> Exception` where each repo registers only its constraint-name-specific overrides.
- A `ConstraintRule` is `(DomainErrorClass, message, context_fn)` so per-repo customization stays declarative.

Don't introduce this preemptively. Add it the first time a third repository forces the same pgcode boilerplate. Document the move in a single commit that migrates all current repositories at once — partial adoption causes drift.

## Inlined typing / import rules

- Domain imports absolute (`from myapp.domain.foos import Foo`). Table imports relative (`from ..tables.foos import foos_table`). **Never import the protocol the adapter satisfies** (`IFooRepository`) — structural subtyping needs no import (Rule 2); importing it is a dead F401.
- Rows are read via `.mappings()` → `RowMapping`; the mapper is typed `_row_to_entity(self, row: RowMapping)` and accesses columns by **key** (`row["id"]`). This is mypy-clean with **no** `# type: ignore` (the `Any` key value is consumed as a constructor argument, never returned). Never type a row as `object` + attribute access — that forces a `# type: ignore[attr-defined]` at every column.
- Parameters keep domain types — never downcast to `dict`.
- No `from __future__ import annotations`. Full annotations on every method.

## Package wiring

The `repositories/__init__.py` must re-export the new module via `from .foo_repository import *`. Follow `architecture` §Python Package Structure.

## Hard stops

- Spec asks for the SQLAlchemy ORM, declarative base, or relationships → stop, this codebase uses Core only.
- Spec asks the repository to commit inside a UoW-managed form → stop, that breaks atomicity.
- Spec asks the repository to log → stop, repositories never log; the central error handler or the calling handler owns logging.
- Spec asks for ID generation inside the repository → stop, the application handler generates IDs.
- The constraint full names in the spec don't match the table file → stop, fix the alignment before writing the repository.
