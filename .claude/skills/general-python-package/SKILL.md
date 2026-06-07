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
- In `__init__.py`: **precede the wildcards with one `from . import <module>, …` line** naming every re-exported submodule (alphabetical). The wildcard binds the submodule at runtime, but **mypy does not model that side effect** — without the explicit `from . import …`, the `__all__ = module.__all__` reference fails type-checking (`name-defined`). The explicit import is what makes the re-export contract type-check; it is **required, not redundant**.
- Subpackages are directories with their own `__init__.py`; only the top-level package's `__init__.py` carries a `__version__`.
- **A package re-exports its immediate children — direct modules AND child subpackages — except the three carve-outs below.** A layer package (`domain/`, `application/`, `infrastructure/`) re-exports its subdomain subpackages, not only its direct modules: `from . import auth, support` + `from .auth import *` + `from .support import *` + `__all__ = auth.__all__ + support.__all__`. An **empty layer `__init__.py` that has children is wrong** — re-export them so `from <root>.domain import X` resolves.
- **Carve-out 1 — the package root stays minimal.** The top-level package `__init__.py` of a layered app (`<root>/__init__.py`) carries only `__version__`; it does **not** wildcard the layer subpackages. Aggregating them to the root would make `import <root>` transitively pull in `infrastructure`/entrypoint third-party deps on every use and break the dependency-free `domain`/`application` import path. Re-export stops at the layer + subdomain level — it does not climb to the root.
- **Carve-out 2 — entrypoint packages stay minimal.** A package whose `__init__` would wildcard a module with **import-time side effects** stays minimal. The case today is `restapi/__init__.py` — do **not** `from .main import *` (importing `main.py` builds the FastAPI app); re-export only the side-effect-free public surface, or leave it empty.
- **Carve-out 3 — wildcard only class-modules.** `from .x import *` is for a module that defines `__all__` (a class module). A module whose public name is a bare object/instance rather than a class — e.g. `infrastructure/postgres/metadata.py` exposing the `metadata` `MetaData()` instance — is **not** wildcarded into its package `__init__` (the wildcard binds a `metadata` name that shadows the submodule); reach it by explicit relative import (`from ..metadata import metadata`) where needed.

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
from . import manager
from .manager import *

__all__ = manager.__all__
```

For multiple modules, list them all in the `from . import …` line, repeat the `from .<module> import *` line per module, and concatenate the `__all__` lists with `+`:

```python
from . import command, handler
from .command import *
from .handler import *

__all__ = command.__all__ + handler.__all__
```

**A top-level package `__init__.py`** carries `__version__`. A **layered app root** (`<root>/__init__.py`, carve-out 1) carries *only* that:

```python
__version__ = "0.1.0"
```

A flat single-package library root may additionally re-export its own modules:

```python
from . import manager
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
- An `__init__.py` that references `module.__all__` (in its own `__all__`) without a matching `from . import module` line → stop, add the explicit submodule import; the wildcard alone does not bind the name for mypy (`name-defined`), so the re-export contract won't type-check.
