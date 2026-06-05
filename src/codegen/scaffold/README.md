# Scaffold — reference-app files copied verbatim (spec §8)

These are **not templates and not generated from the manifest**. They are real,
package-agnostic reference-app source files that the generator **copies byte-for-byte**
into the target project's `infrastructure/db/` on first `/generate` (spec §8: the
project scaffold is taken from the reference application, not synthesized from the
manifest).

They are package-agnostic — relative imports only, no import-root substitution — which
is exactly why they can be copied rather than rendered. Anything that needs the package
name (e.g. `restapi/dependencies.py` with its `{{PKG}}` substitution) stays in the
generator, not here.

| Scaffold source | Copied to (in the target package) |
|---|---|
| `metadata.py`    | `infrastructure/db/metadata.py` |
| `db_settings.py` | `infrastructure/db/settings.py` |
| `db_engine.py`   | `infrastructure/db/engine.py`   |

Edit these as ordinary Python. They are linted as part of `ruff check` and must stay
house-quality, because their content is what lands in every generated project.
