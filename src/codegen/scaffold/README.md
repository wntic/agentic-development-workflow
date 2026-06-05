# Scaffold — reference-app files copied verbatim (spec §8)

These are **not templates and not generated from the manifest**. They are real,
package-agnostic reference-app source files that the generator **copies byte-for-byte**
into the target project's relational-store subpackage (`infrastructure/<postgres>/`) on
first `/generate` (spec §8: the project scaffold is taken from the reference application,
not synthesized from the manifest).

They are package-agnostic — relative imports only, no import-root substitution — which
is exactly why they can be copied rather than rendered. Anything that needs the package
name (e.g. `restapi/dependencies.py` with its `{{PKG}}` substitution) stays in the
generator, not here.

| Scaffold source | Copied to (in the target package) |
|---|---|
| `metadata.py`    | `infrastructure/<relational>/metadata.py` |

The SQLAlchemy bootstrap that used to live here as verbatim scaffolds is gone:
`DbSettings` is now an **ordinary manifest-declared settings node** (the `main` datastore
references it, the engine builds the DSN from its fields), and `engine.py` is a
**parameterized template** (`templates/db_engine.py.j2`) that imports the declared
settings class by name. Only the SQLAlchemy `MetaData` (naming convention) remains
package-agnostic enough to copy verbatim.

Edit `metadata.py` as ordinary Python. It is linted as part of `ruff check` and must stay
house-quality, because its content is what lands in every generated project.
