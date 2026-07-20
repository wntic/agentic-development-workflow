---
name: architecture
description: House style for where code lives and how it imports. The four-layer split (domain / application / infrastructure / entrypoints) and the allowed inward dependency direction; Python package mechanics (one class per module, `__all__` placement, subpackage `__init__.py` re-export contract); and import conventions (relative vs absolute, the collapsed same-package form, importing a re-exported name from its immediate parent and never a grandparent).
when_to_use: Scaffolding a new feature, moving code between layers, deciding where a module belongs, or resolving an import or packaging question. Consult before writing any new source file so it lands in the right layer with its package wired correctly.
---
# Architecture — layers, packages, imports

This merged skill covers 3 related artifacts. Each `## …` section below is one artifact's house style, keeping its own *When to use / Template(s) / Rules / Hard stops* structure. Consult the section matching what you are producing.


<!-- merged from general-layered-architecture -->

## Layered Architecture

A project is split into four layers. Three are core (`domain/`, `application/`, `infrastructure/`); the fourth is one or more entrypoint packages (`restapi/`, `cli/`, `worker/`, …). The split exists so the business rules in `domain/` stay independent of databases, HTTP frameworks, and SDKs — and so the dependency graph stays acyclic.

### When to use vs. neighbours

- Scaffolding a new feature or deciding where a module belongs → consult this skill.
- Producing a specific artifact at a given layer → the per-layer skill (`domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, …). This skill defines the boundary; the per-layer skills define the file shape.
- An "imports may cross this boundary?" question → this skill.
- Package mechanics inside a layer → `general-python-package`.

### The shape

```
                    ┌──────────────────┐
                    │  entrypoints     │   restapi/, cli/, worker/
                    │  (composition    │   wires containers, translates
                    │   root)          │   transport ↔ application
                    └────────┬─────────┘
                             │ may import all three core layers
                             ▼
        ┌────────────────────────────────────────┐
        │            application/                │   commands, queries,
        │   (orchestration, no business logic)   │   handlers (CQRS)
        └────────────┬───────────────────────────┘
                     │ imports domain only
                     ▼
        ┌────────────────────────────────────────┐
        │              domain/                   │   entities, VOs, enums,
        │   (pure logic, stdlib only)            │   protocols, exceptions,
        │                                        │   policies
        └────────────▲──────────────────────────┘
                     │ implements protocols
                     │
        ┌────────────┴───────────────────────────┐
        │           infrastructure/              │   adapters, repositories,
        │   (third-party SDKs, IO)               │   tables (SQLAlchemy Core), clients
        └────────────────────────────────────────┘
```

Dependency direction: **`application → domain ← infrastructure`**, and **entrypoints → all three**. No other arrow is legal.

### What each layer may import

#### `domain/`

- Allowed: stdlib (`dataclasses`, `datetime`, `enum`, `uuid`, `typing`), other domain modules.
- Forbidden: anything else. No third-party libraries (no SQLAlchemy, no Pydantic, no httpx, no boto3, no FastAPI). No `application/`, no `infrastructure/`, no entrypoint imports.
- Defines: entities, value objects, enums, filter records, domain protocols (`I*` / `ICan*`), domain policies, domain exceptions, type aliases.
- Zero IO. No file reads, no network, no database, no logging.

#### `application/`

- Allowed: stdlib, `structlog`, domain modules.
- Forbidden: third-party libraries beyond `structlog`. No `infrastructure/` imports. No entrypoint imports.
- Defines: commands, queries, handlers, result DTOs (see `cqrs`).
- Depends on infrastructure capabilities only through domain protocols. Receives concrete adapters via DI.

#### `infrastructure/`

- Allowed: stdlib, any third-party library, domain modules (for protocol types and entities).
- Forbidden: `application/` imports, entrypoint imports.
- Defines: adapters that implement domain protocols (Postgres repositories, S3 storage, JWT verifiers, file renderers).
- Translates between external representations (DB rows, HTTP JSON, queue messages) and domain objects. Translation happens *inside* the adapter — never leaks raw rows or SDK objects upward.

#### Entrypoint packages (`restapi/`, future `cli/` / `worker/`)

- Allowed: everything. This is the composition root.
- Defines: HTTP routes / CLI commands / queue consumers, request/response Pydantic models, the central error handler, the DI wiring.
- Wires `containers.py` at startup, resolves handlers, translates transport ↔ application DTOs.

### Top-level layout

```
src/myapp/
├── containers.py        # DI wiring (the composition root's dependency graph)
├── domain/              # pure business model
├── application/         # CQRS orchestration
├── infrastructure/      # adapters
└── restapi/             # HTTP entrypoint
```

`domain/` and `application/` mirror the same subdomain partition: `domain/foos/`, `application/foos/`. **`infrastructure/` groups by external tech, not by subdomain** — `infrastructure/postgres/`, `infrastructure/qdrant/`, `infrastructure/openai/`, `infrastructure/jwt/` (the derivation lives in `conventions` block A). A new subdomain adds a folder under `domain/` and `application/`; a new external technology adds one under `infrastructure/`.

### Rules

#### Direction

- `application/` may import from `domain/` only. Never from `infrastructure/` or entrypoints.
- `infrastructure/` may import from `domain/` only. Never from `application/` or entrypoints.
- `domain/` may not import from anything outside `domain/`.
- Entrypoints may import from all three core layers.
- No circular imports. Ever — between modules, between subpackages, between layers.

#### Where new code goes

- Pure logic that depends only on data → `domain/`.
- A rule that needs a repository or capability → `domain/` (as a service, see `domain-service`).
- Orchestration of domain + protocols, ID generation, logging business events → `application/`.
- Anything that talks to a database, a file system, an HTTP API, or an SDK → `infrastructure/`.
- Anything that knows about HTTP / CLI / queues → an entrypoint package.

If you're tempted to import `infrastructure` from `application`, you're wiring a concrete adapter where a protocol belongs. Stop and define a protocol in `domain/` instead.

If you're tempted to import `application` from `infrastructure`, you have an adapter that knows about a use case. Move the orchestration up to a handler.

#### Composition root

- DI wiring lives in `containers.py` at the package root. It is the only place that imports concrete adapters from `infrastructure/` and binds them to domain protocol types consumed by `application/` handlers.
- Wire dependencies at startup, not at import time. Never use module-level singletons for stateful objects (DB connections, HTTP clients) — inject them.
- Entrypoint packages call into the container at request time to resolve handlers; they don't construct adapters themselves.

#### Protocols vs. concrete

- Application handlers depend on **domain protocol types** in their constructor signatures (`repo: IFooRepository`), never on concrete classes (`repo: PostgresFooRepository`).
- Infrastructure adapters do not explicitly inherit from protocols (structural subtyping; see `domain-protocols`).

### How to apply

1. When adding a feature, decide the entry path: HTTP route → `restapi/...`, scheduled job → `worker/...`, etc.
2. Sketch the use case as a CQRS handler in `application/<subdomain>/` (see `cqrs`).
3. List what the handler needs from the outside world. Each of those is a protocol in `domain/<subdomain>/` (see `domain-protocols`).
4. Implement each protocol as an adapter under `infrastructure/<tech>/` — grouped by the external technology (`postgres/`, `qdrant/`, `jwt/`), never by subdomain (see `conventions` block A). Adapters import domain types, translate raw payloads, raise domain exceptions (see `domain-exceptions`).
5. Wire the adapters in `containers.py` and resolve the handler in the entrypoint.
6. Verify the dependency direction by scanning the new files' imports — `domain/` files must import only stdlib + domain; `application/` files must not import `infrastructure/`; `infrastructure/` must not import `application/`.

#### When moving code between layers

- Moving from `domain/` to `application/` usually means the rule needed a protocol — extract a protocol first, then move the orchestrator.
- Moving from `application/` to `domain/` is rare and only correct when the logic was pure all along (no IO, no protocol calls).
- Moving from `infrastructure/` to `application/` almost never happens — if you feel the urge, you probably want to move the orchestration up but leave the adapter behind.
- Moving from an entrypoint into `application/` is correct when the same logic is needed by a second entrypoint. Pull it into a handler; the entrypoint becomes a thin translator.

### Hard stops

- `infrastructure/` imports `application/` → stop, that's the wrong direction; move the orchestration up to a handler.
- `application/` imports `infrastructure/` → stop, that wires a concrete adapter where a protocol belongs; define a protocol in `domain/` and inject the adapter via DI.
- `domain/` imports anything outside `domain/` or stdlib → stop, the domain layer is pure data + invariants only.
- A circular import between modules / subpackages / layers → stop, it always indicates a layering violation; fix the structure (don't paper over with `TYPE_CHECKING` or in-function imports).
- An entrypoint module instantiates a concrete adapter directly → stop, the DI container in `containers.py` is the only place that binds concrete classes.


<!-- merged from general-python-package -->

## Python Package Structure

This skill governs **package mechanics** only — the file layout and `__init__.py` re-export contract that lets the project's collapsed-import convention work. It does not say anything about *what* goes inside a module; that's the layer-specific skill's job.

### When to use vs. neighbours

This skill fires when **package mechanics change** — a new `.py` module is created, a new `__init__.py` is scaffolded, an existing `__init__.py`'s re-export surface is changed (module added/renamed/removed), or a package is restructured (modules split or merged).

- Editing the body of an existing module (adding a method, tightening a signature) → defer to the layer skill (`domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, …). The layer skill knows the package conventions it relies on.
- What types go in `domain/` vs `application/` vs `infrastructure/` → `general-layered-architecture`.
- How to *consume* the re-exports (relative-vs-absolute, collapse rule) → `general-imports-conventions`.
- How to write a protocol / handler / repository / router / schema body → the matching layer skill.

### Rules

- One class per module file.
- Module name matches class name in snake_case (`manager.py` → `Manager`).
- In module files: `__all__` goes **after** imports and **before** the class definition, never at the very top.
- In `__init__.py`: always `from .module import *`, never `from .module import ClassName`.
- In `__init__.py`: always `__all__ = module.__all__` (or `+`-joined across modules), never `__all__ = ["ClassName"]`.
- In `__init__.py`: **precede the wildcards with one `from . import <module>, …` line** naming every re-exported submodule (alphabetical). The wildcard binds the submodule at runtime, but **mypy does not model that side effect** — without the explicit `from . import …`, the `__all__ = module.__all__` reference fails type-checking (`name-defined`). The explicit import is what makes the re-export contract type-check; it is **required, not redundant**.
- Subpackages are directories with their own `__init__.py`; only the top-level package's `__init__.py` carries a `__version__`.
- **A package re-exports its immediate children — direct modules AND child subpackages — except the three carve-outs below.** A layer package (`domain/`, `application/`, `infrastructure/`) re-exports its subdomain subpackages, not only its direct modules: `from . import auth, support` + `from .auth import *` + `from .support import *` + `__all__ = auth.__all__ + support.__all__`. An **empty layer `__init__.py` that has children is wrong** — re-export them so `from <root>.domain import X` resolves.
- **Carve-out 1 — the package root stays minimal.** The top-level package `__init__.py` of a layered app (`<root>/__init__.py`) carries only `__version__`; it does **not** wildcard the layer subpackages. Aggregating them to the root would make `import <root>` transitively pull in `infrastructure`/entrypoint third-party deps on every use and break the dependency-free `domain`/`application` import path. Re-export stops at the layer + subdomain level — it does not climb to the root.
- **Carve-out 2 — entrypoint packages stay minimal.** A package whose `__init__` would wildcard a module with **import-time side effects** stays minimal. The case today is `restapi/__init__.py` — do **not** `from .main import *` (importing `main.py` builds the FastAPI app); re-export only the side-effect-free public surface, or leave it empty. Likewise `restapi/routers/__init__.py` stays **empty**: router modules are consumed by **explicit aliased import** in `main.py` (`from .routers.foos import router as foos_router`), not via the collapse-import surface, and each exports a colliding `router` object that a wildcard would clash on. This carve-out is **specific to routers** — `restapi/middleware/__init__.py` is **not** exempt: middleware class names are distinct (no collision), so it re-exports them normally (`from .max_request_size import *` …) and `main.py` imports them via the collapsed package form (`from .middleware import MaxRequestSizeMiddleware, RequestIdMiddleware`), per the same-package collapse rule — never per-submodule.
- **Carve-out 3 — wildcard only class-modules.** `from .x import *` is for a module that defines `__all__` (a class module). A module whose public name is a bare object/instance rather than a class — e.g. `infrastructure/postgres/metadata.py` exposing the `metadata` `MetaData()` instance — is **not** wildcarded into its package `__init__` (the wildcard binds a `metadata` name that shadows the submodule); reach it by explicit relative import (`from ..metadata import metadata`) where needed.

### Named exceptions to "one class per module"

The rule is binding everywhere **except** for these two named files, each of which deliberately holds multiple classes because the classes co-evolve and splitting them would harm readability without any decoupling benefit:

1. **`<root>/domain/exceptions.py`** — `DomainError` plus every subclass live in this single file (the error catalogue stays auditable). See `domain-exception` for the file's structure.
2. **`<root>/restapi/schemas/<resource>.py`** — the four Pydantic wire schemas for one HTTP resource (`<Resource>Response`, `<Resource>ListResponse`, `<Resource>CreateRequest`, `<Resource>UpdateRequest`) sit in one file because they describe the same wire contract from different angles. See `restapi-schema` for the file's structure.

These are the **only** exceptions. The carve-out is by exact file path, not by directory or category — adding a third domain entity to a `domain/foos/foo.py` is still wrong; bundling two adapters into one `infrastructure/postgres/repositories/` module is still wrong; combining a command and its handler in one `application/` file is still wrong.

Route modules (`restapi/routers/<resource>.py`) contain multiple **functions**, not classes, so they don't break this rule at all. No carve-out needed for them.

### Snippets

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

### Example layout

```
package_name/
├── __init__.py          # top-level: re-export + __version__
├── case.py              # → class Case
└── config/
    ├── __init__.py      # subpackage: re-export only
    └── manager.py       # → class Manager
```

### Hard stops

- A new module file with two top-level classes → stop, split into two files (named exceptions: `domain/exceptions.py`, `restapi/schemas/<resource>.py` only).
- A module filename that doesn't match its class in snake_case (`utils.py` containing `class FooHelper`) → stop, rename the file.
- `__all__` placed at the top of a module before the imports → stop, `__all__` goes after imports and before the class.
- An `__init__.py` containing `from .module import ClassName` rather than `from .module import *` → stop, use the wildcard so the package `__all__` can be `+`-joined.
- An `__init__.py` containing class definitions, constants, or logic → stop, `__init__.py` is imports + `__all__` only.
- An `__init__.py` that references `module.__all__` (in its own `__all__`) without a matching `from . import module` line → stop, add the explicit submodule import; the wildcard alone does not bind the name for mypy (`name-defined`), so the re-export contract won't type-check.


<!-- merged from general-imports-conventions -->

## Imports Conventions

Imports follow three rules: how far you reach with relative dots, how you collapse multiple symbols from the same package, and how `__init__.py` re-exports underwrite the collapsed form.

### When to use vs. neighbours

- Adding or modifying any import statement → consult this skill.
- Restructuring `__init__.py` re-exports → consult both this skill (re-export contract) and `general-python-package` (package mechanics).
- Choosing `frozenset` vs `set` or `X | None` vs `Optional[X]` → `general-typing-conventions`.
- Layer boundaries (what each layer may import) → `general-layered-architecture`.

### Relative vs absolute

- **Within a package, use relative imports up to two dots** (`from .sibling import X`, `from ..parent import Y`).
- **Same package → one dot, never up-and-back-down.** A module importing a sibling in its **own** package uses `.sibling` — never route through the parent back into the same package (`from ..pkg.sibling import X` when you are already inside `pkg/` is wrong; it resolves but reads as a cross-package reach). The toolchain does **not** flag this (the import is valid Python), so it is on the author.
- **Three or more dots → use absolute.** `from ...thing import Z` is banned; write `from myapp.subpkg.thing import Z`.
- **Cross-package boundaries → absolute.** Anything reaching from `application/` into `domain/`, or `restapi/` into `application/`, is absolute regardless of dot count.

```python
# inside application/foos/create_foo_handler.py
from .create_foo_command import CreateFooCommand   # same dir — relative
from ..bars.create_bar_command import CreateBarCommand            # one level up — relative
from myapp.domain.foos import IFooRepository    # cross-package — absolute
from myapp.domain.bars import Bar                             # cross-package — absolute

# inside infrastructure/postgres/engine.py importing infrastructure/postgres/settings.py
from .settings import DbSettings             # same package — one dot
# NOT: from ..postgres.settings import DbSettings   # up-and-back-down into the same package
```

The two-dot ceiling exists to keep relative imports readable; once you'd be writing `...` or more, the absolute path is shorter and clearer.

### Collapse same-package imports

When you import multiple symbols from the same module or subpackage, **collapse them into one statement**:

```python
# yes
from myapp.domain.foos import (
    Foo,
    FooCategory,
    FooPattern,
    IFooRepository,
)

# no
from myapp.domain.foos.foo import Foo
from myapp.domain.foos.foo_category import FooCategory
from myapp.domain.foos.foo_pattern import FooPattern
from myapp.domain.foos.i_foo_repository import IFooRepository
```

Rules for the collapsed form:

- One symbol per line inside the parens, alphabetically sorted, trailing comma on the last entry.
- Import from the **subpackage**, not from individual modules — i.e. `from myapp.domain.foos import ...`, not `from myapp.domain.foos.foo import ...`. The subpackage `__init__.py` must re-export the symbol (next section).
- **"Subpackage" means the package that DIRECTLY contains the defining module — never a grandparent.** Import a symbol from the package whose `__init__` wildcards its module in **one** `from .module import *` hop. Do **not** reach it through a *grandparent* package that would re-export it across a second hop, because the intermediate package's `__all__` is a **computed** concatenation (`a.__all__ + b.__all__`) that mypy cannot evaluate for a `from .subpkg import *` — the name resolves at runtime but mypy reports `[attr-defined]` ("Module X has no attribute Y"). Concretely, for the nested infra layout a repository class is imported from its **`repositories` subpackage**, not the tech package: `from myapp.infrastructure.postgres.repositories import MeetingRepository` (✅, one hop — `repositories/__init__` wildcards `meeting_repository`), **not** `from myapp.infrastructure.postgres import MeetingRepository` (❌ — that crosses `postgres ← repositories ← meeting_repository`, two hops, the middle `__all__` computed). A class sitting *directly* under the tech package (an adapter in `infrastructure/openai/openai_embedder.py`, `engine` / `settings` under `postgres/`) is one hop from the tech package, so `from myapp.infrastructure.openai import OpenaiEmbedder` is correct.
- One-symbol imports stay on a single line: `from myapp.domain.foos import Foo`.

### `__init__.py` re-exports

For the collapsed-import form to work, **every subpackage `__init__.py` must re-export everything its submodules expose**:

```python
# domain/foos/__init__.py
from . import foo, foo_category, foo_pattern, i_foo_repository
from .foo import *
from .foo_category import *
from .foo_pattern import *
from .i_foo_repository import *
```

Rules:

- Precede the wildcards with one `from . import <module>, …` line naming every submodule (alphabetical). It binds the submodule names so the `__all__ = module.__all__` concatenation below type-checks under mypy — `from .module import *` binds them at runtime but **not** for the type-checker (`name-defined`). See `general-python-package`.
- One `from .module import *` per submodule, in alphabetical order.
- Every module being wildcarded must declare `__all__` listing its public symbols (see `general-python-package`). Wildcard imports without `__all__` leak private helpers.
- The package's own `__all__` is the concatenation of submodule `__all__`s, e.g.:

  ```python
  __all__ = (
      foo.__all__
      + foo_category.__all__
      + foo_pattern.__all__
      + i_foo_repository.__all__
  )
  ```

  This is what `restapi/schemas/__init__.py` does — see `restapi-schema` for the pattern.

- `__init__.py` files contain **only imports and `__all__`**. No class definitions, no constants, no logic.

### Import order inside a module

Standard PEP 8 grouping, with a blank line between groups:

1. `__future__` — **disallowed in this project** (see `general-typing-conventions`); this slot stays empty.
2. Standard library (`uuid`, `datetime`, `collections.abc`, ...).
3. Third-party (`pydantic`, `fastapi`, `sqlalchemy`, ...).
4. First-party absolute (`myapp.domain...`, `myapp.application...`).
5. First-party relative (`from .sibling import X`, `from ..parent import Y`).

Ruff/isort handle this automatically; don't fight the formatter, but understand the groupings so manually written imports land in the right block.

### Re-exporting domain protocols and entities

Subpackages designed to be the public face of a subdomain (the typical `domain/<subdomain>/` and `application/<subdomain>/` packages) must re-export:

- All entities, value objects, enums, type aliases.
- All `i_*_repository.py` and `i_can_*.py` protocols.
- All policies.
- All commands, queries, results, handlers (in `application/<subdomain>/`).

**Layer packages re-export their subdomains too.** The same contract applies one level up: `domain/__init__.py`, `application/__init__.py`, and `infrastructure/__init__.py` re-export their child subpackages (`from . import bars, foos` + `from .bars import *` + … + `__all__ = bars.__all__ + foos.__all__`), so `from <root>.domain import X` resolves and `__all__` aggregates to the layer root. An empty layer `__init__.py` that has children is a gap. The lone exception is the entrypoint package `restapi/__init__.py`, kept minimal because wildcarding `main.py` would trigger app construction at import (see `general-python-package`).

If a symbol isn't re-exported, the collapsed-import form breaks at the first call site — and any contributor who adds a new symbol later will hit confusing import errors. Adding a new module means: declare `__all__` in the module, then add it to the `from . import …` line, add `from .<module> import *` to the subpackage `__init__.py`, and append `<module>.__all__` to the package's own `__all__`.

### Hard stops

- `from myapp.domain.foos.foo import Foo` (importing from the inner module rather than the subpackage) → stop, import from the subpackage instead. Bypassing `__init__.py` forces every reader to know the file layout.
- `from foo import *` outside `__init__.py` → stop, wildcard imports inside regular modules pollute namespaces and break linting.
- Three-or-more-dot relative imports → stop, switch to absolute.
- `import myapp.domain.foos as fs` followed by `fs.Foo` → stop, use `from ... import` everywhere; module aliases hide what's actually used.
- Imports inside function/method bodies to break a circular import → stop, the cycle almost always points to a layering violation (see `general-layered-architecture`); fix the structure.
- `if TYPE_CHECKING:` imports purely to dodge a circular import → stop, refactor the cycle.
