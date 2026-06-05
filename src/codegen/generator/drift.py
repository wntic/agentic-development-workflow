"""Schema-drift detection (redesign Stage 5).

A relational table is a WRITE-ONCE scaffold the implementer fills with `Column(...)`s
(§3/§4) — the manifest no longer carries the column list. So a field change can't be caught
by regeneration (the table file is never overwritten) and mypy can't see a missing column.
The deterministic trigger is this check: compare each postgres-backed entity's DECLARED
fields (the manifest snapshot — desired) against the columns actually present in its table
file on disk (reality). A field with no matching column is drift — the scaffold is either
still unfilled or a delta added a field the implementer hasn't migrated yet.

This is the §4 split applied to storage: DETECTION is deterministic (here), the FIX
(adding the column + an Alembic migration) is the implementer's. It is one-directional:
extra columns (audit timestamps, denormalized projections) are allowed and not reported.
Column name == entity field name (the table convention); the type is the implementer's.
"""

import re
from pathlib import Path

from ..manifest.schema import Manifest
from ..manifest.validator import ValidationReport
from . import naming
from .store_profiles import kind_of, profile_for

# Matches the column NAME in a SQLAlchemy Core `Column("name", ...)` / `Column('name', ...)`.
_COLUMN_RE = re.compile(r"""Column\(\s*["']([A-Za-z_]\w*)["']""")


def check_schema_drift(manifest: Manifest, package_root: str | Path) -> ValidationReport:
    """Report `schema_drift` for every relational entity whose table scaffold does not yet
    cover its declared fields (missing file = not generated; missing columns = unfilled or
    drifted). Non-relational stores have no SQL table and are skipped. Findings are warnings:
    they are an implementer TRIGGER, not a manifest-validity gate."""
    root = Path(package_root)
    report = ValidationReport()
    entities = {e.name: e for e in manifest.domain.entities}
    for repo in manifest.infrastructure.repositories:
        kind = kind_of(manifest.infrastructure.datastores, repo.store)
        if not profile_for(kind).uses_bootstrap:
            continue  # only relational (postgres) stores have a SQLAlchemy table to drift
        entity = entities.get(repo.backs)
        if entity is None:
            continue
        table_file = root / naming.table_path(repo.backs, kind)
        table = naming.table_name(repo.backs)
        if not table_file.exists():
            report.add("warning", "schema_drift", f"table {table!r} for {entity.name} is not generated yet")
            continue
        columns = set(_COLUMN_RE.findall(table_file.read_text()))
        missing = [f.name for f in entity.fields if f.name not in columns]
        if missing:
            report.add(
                "warning",
                "schema_drift",
                f"table {table!r} is missing column(s) {missing} for {entity.name} field(s) — fill the "
                f"scaffold or author a migration (implementer); extra columns are fine",
            )
    return report
