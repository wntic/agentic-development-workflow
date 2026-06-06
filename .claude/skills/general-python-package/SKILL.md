---
name: general-python-package
description: Apply when **creating** a new module file, a new `__init__.py`, or restructuring a package's public surface (adding/removing modules, reorganizing wildcard re-exports). Do **not** apply for ordinary edits to an existing module's body — the layer-specific skill (e.g. `domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, `restapi-schema`) owns content rules. This skill only governs package mechanics: one class per module, `__all__` placement, and the `from .module import *` re-export contract that `general-imports-conventions` depends on.
---

# Python Package Structure

This skill governs **package mechanics** only — the file layout and `__init__.py` re-export contract that lets the project's collapsed-import convention work. It does not say anything about *what* goes inside a module; that's the layer-specific skill's job.

## When to use vs. neighbours

This skill fires when **package mechanics change** — a new `.py` module is created, a new `__init__.py` is scaffolded, an existing `__init__.py`'s re-export surface is changed (module added/renamed/removed), or a package is restructured (modules split or merged).

- Editing the body of an existing module (adding a method, tightening a signature) → defer to the layer skill (`domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, …). The layer skill knows the package conventions it relies on.
- What types go in `domain/` vs `application/` vs `infrastructure/` → `general-layered-architecture`.
- How to *consume* the re-exports (relative-vs-absolute, collapse rule) → `general-imports-conventions`.
- How to write a protocol / handler / repository / router / schema body → the matching layer skill.

## Rules

- One class per module file.
- Module name matches class name in snake_case (`manager.py` → `Manager`).
- In module files: `__all__` goes **after** imports and **before** the class definition, never at the very top.
- In `__init__.py`: always `from .module import *`, never `from .module import ClassName`.
- In `__init__.py`: always `__all__ = module.__all__` (or `+`-joined across modules), never `__all__ = ["ClassName"]`.
- Never add an extra `from . import module_name` — `from .module import *` already binds `module` in the package namespace.
- Subpackages are directories with their own `__init__.py`; only the top-level package's `__init__.py` carries a `__version__`.

## Named exceptions to "one class per module"

The rule is binding everywhere **except** for these two named files, each of which deliberately holds multiple classes because the classes co-evolve and splitting them would harm readability without any decoupling benefit:

1. **`<root>/domain/exceptions.py`** — `DomainError` plus every subclass live in this single file (the error catalogue stays auditable). See `domain-exception` for the file's structure.
2. **`<root>/restapi/schemas/<resource>.py`** — the four Pydantic wire schemas for one HTTP resource (`<Resource>Response`, `<Resource>ListResponse`, `<Resource>CreateRequest`, `<Resource>UpdateRequest`) sit in one file because they describe the same wire contract from different angles. See `restapi-schema` for the file's structure.

These are the **only** exceptions. The carve-out is by exact file path, not by directory or category — adding a third domain entity to a `domain/foos/foo.py` is still wrong; bundling two adapters into one `infrastructure/postgres/repositories/` module is still wrong; combining a command and its handler in one `application/` file is still wrong.

Route modules (`restapi/routers/<resource>.py`) contain multiple **functions**, not classes, so they don't break this rule at all. No carve-out needed for them.

## Snippets

**A module file** (`manager.py` → `Manager`):

```python
# imports


__all__ = ["Manager"]


class Manager:
    pass
```

**A subpackage `__init__.py`** (re-exports a single module `manager`):

```python
from .manager import *

__all__ = manager.__all__
```

For multiple modules, repeat the `from .<module> import *` line per module and concatenate the `__all__` lists with `+`.

**A top-level package `__init__.py`** additionally carries a version string:

```python
from .manager import *

__version__ = "0.1.0"
__all__ = manager.__all__
```

## Example layout

```
package_name/
├── __init__.py          # top-level: re-export + __version__
├── case.py              # → class Case
└── config/
    ├── __init__.py      # subpackage: re-export only
    └── manager.py       # → class Manager
```

## Hard stops

- A new module file with two top-level classes → stop, split into two files (named exceptions: `domain/exceptions.py`, `restapi/schemas/<resource>.py` only).
- A module filename that doesn't match its class in snake_case (`utils.py` containing `class FooHelper`) → stop, rename the file.
- `__all__` placed at the top of a module before the imports → stop, `__all__` goes after imports and before the class.
- An `__init__.py` containing `from .module import ClassName` rather than `from .module import *` → stop, use the wildcard so the package `__all__` can be `+`-joined.
- An `__init__.py` containing class definitions, constants, or logic → stop, `__init__.py` is imports + `__all__` only.
- A `from . import module_name` line added alongside `from .module import *` → stop, the wildcard already binds `module` in the package namespace; the explicit `import` is redundant.
