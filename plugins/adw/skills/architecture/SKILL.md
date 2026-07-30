---
name: architecture
description: Where code lives and how it imports — the four-layer split (domain, application, infrastructure, entrypoints) with its inward-only dependency direction, Python package mechanics (one class per module, `__all__` placement, the `__init__.py` re-export contract), and the import conventions that contract underwrites.
when_to_use: Deciding which layer a module belongs to, creating a new module or `__init__.py`, moving code between layers, or resolving an import question. Consult before writing any new source file.
---

# Architecture

Three questions with one answer between them: which layer a thing belongs to, how its module is
packaged, and how another module reaches it. They are inseparable — the collapsed import form only works
because of the `__init__.py` re-export contract, and the re-export contract only makes sense against the
layer boundaries.

This skill defines boundaries and mechanics. What goes *inside* a module is the artifact skill's job.

## When to use vs. neighbours

- Deciding where a module belongs, or whether an import may cross a boundary → this skill.
- Creating a new module or `__init__.py`, or restructuring a package's public surface → this skill.
- Editing the body of an existing module → the artifact skill (`domain-model`, `application`,
  `infra-persistence`, `restapi-endpoint`, …). It already knows the mechanics it relies on.
- Choosing an annotation form, a collection type, or where to log → `python-style`.
- Deriving a concrete path or class name from an identifier → `conventions`.

## The four layers

Three are core — `domain/`, `application/`, `infrastructure/`; the fourth is one or more entrypoint
packages (`restapi/`, `cli/`, `worker/`). The split exists so the business rules in `domain/` stay
independent of databases, HTTP frameworks and SDKs, and so the dependency graph stays acyclic.

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
        │                                        │   services
        └────────────▲───────────────────────────┘
                     │ implements protocols
                     │
        ┌────────────┴───────────────────────────┐
        │           infrastructure/              │   adapters, repositories,
        │   (third-party SDKs, IO)               │   tables (SQLAlchemy Core), clients
        └────────────────────────────────────────┘
```

Dependency direction: **`application → domain ← infrastructure`**, and **entrypoints → all three**. No
other arrow is legal.

### What each layer may import

**`domain/`**

- Allowed: stdlib (`dataclasses`, `datetime`, `enum`, `uuid`, `typing`), other domain modules.
- Forbidden: everything else. No third-party libraries — no SQLAlchemy, no Pydantic, no httpx, no boto3,
  no FastAPI. No `application/`, no `infrastructure/`, no entrypoint imports.
- Defines: entities, value objects, enums, filter records, domain protocols (`I*` / `ICan*`), domain
  services, domain exceptions, type aliases.
- Zero IO. No file reads, no network, no database, no logging.

**`application/`**

- Allowed: stdlib, `structlog`, domain modules.
- Forbidden: third-party libraries beyond `structlog`. No `infrastructure/` imports, no entrypoint
  imports.
- Defines: commands, queries, handlers, result DTOs.
- Depends on infrastructure capabilities only through domain protocols, and receives concrete adapters
  via DI.

**`infrastructure/`**

- Allowed: stdlib, any third-party library, domain modules for protocol types and entities.
- Forbidden: `application/` imports, entrypoint imports.
- Defines: adapters implementing domain protocols — Postgres repositories, S3 storage, JWT verifiers,
  file renderers.
- Translates between external representations (DB rows, HTTP JSON, queue messages) and domain objects.
  Translation happens *inside* the adapter; a raw row or SDK object never leaks upward.

**Entrypoint packages** (`restapi/`, and later `cli/` / `worker/`)

- Allowed: everything. This is the composition root.
- Defines: HTTP routes, CLI commands or queue consumers; request and response Pydantic models; the
  central error handler; the DI wiring.
- Wires `containers.py` at startup, resolves handlers, translates transport ↔ application DTOs.

### Top-level layout

```
src/myapp/
├── containers.py        # DI wiring (the composition root)
├── domain/              # pure business model
├── application/         # CQRS orchestration
├── infrastructure/      # adapters
└── restapi/             # HTTP entrypoint
```

`domain/` and `application/` mirror the same subdomain partition — `domain/foos/`, `application/foos/`.
**`infrastructure/` groups by external tech, not by subdomain**: `infrastructure/postgres/`,
`infrastructure/qdrant/`, `infrastructure/openai/`, `infrastructure/jwt/` (the derivation is
`conventions` block A). A new subdomain adds a folder under `domain/` and `application/`; a new external
technology adds one under `infrastructure/`.

## Package mechanics

- **One class per module file**, and the module name matches the class in snake_case (`manager.py` →
  `Manager`).
- **`__all__` goes after the imports and before the class definition**, never at the top of the file.
- **In an `__init__.py`: always `from .module import *`**, never `from .module import ClassName`; and
  always `__all__ = module.__all__` (or `+`-joined across modules), never `__all__ = ["ClassName"]`.
- **Precede the wildcards with one `from . import <module>, …` line** naming every re-exported submodule,
  alphabetically. The wildcard binds the submodule at runtime, but **mypy does not model that side
  effect** — without the explicit `from . import …`, the `__all__ = module.__all__` reference fails
  type-checking with `name-defined`. The explicit import is what makes the contract type-check; it is
  **required, not redundant**.
- **An `__init__.py` contains only imports and `__all__`.** No class definitions, no constants, no logic.
- Subpackages are directories with their own `__init__.py`. Only the top-level package's `__init__.py`
  carries a `__version__`.
- **A package re-exports its immediate children — direct modules *and* child subpackages — except the
  three carve-outs below.** A layer package re-exports its subdomain subpackages, not only its direct
  modules: `from . import auth, support` + `from .auth import *` + `from .support import *` +
  `__all__ = auth.__all__ + support.__all__`. An **empty layer `__init__.py` that has children is
  wrong** — re-export them so `from <root>.domain import X` resolves.

**Carve-out 1 — the package root stays minimal.** The top-level `<root>/__init__.py` of a layered app
carries only `__version__`; it does **not** wildcard the layer subpackages. Aggregating them to the root
would make `import <root>` transitively pull infrastructure and entrypoint third-party dependencies on
every use, and would break the dependency-free `domain` / `application` import path. Re-export stops at
the layer and subdomain level; it does not climb to the root.

**Carve-out 2 — entrypoint packages stay minimal.** A package whose `__init__` would wildcard a module
with **import-time side effects** stays minimal. The case today is `restapi/__init__.py`: do **not**
`from .main import *`, because importing `main.py` builds the FastAPI app. Re-export only the
side-effect-free surface, or leave it empty. Likewise `restapi/routers/__init__.py` stays **empty** —
router modules are consumed by explicit aliased import in `main.py`
(`from .routers.foos import router as foos_router`), not through the collapse-import surface, and each
exports a colliding `router` object a wildcard would clash on. This carve-out is **specific to
routers**: `restapi/middleware/__init__.py` is **not** exempt, because middleware class names are
distinct, so it re-exports them normally and `main.py` imports them via the collapsed package form
(`from .middleware import MaxRequestSizeMiddleware, RequestIdMiddleware`).

**Carve-out 3 — wildcard only class-modules.** `from .x import *` is for a module that declares `__all__`
— a class module. A module whose public name is a bare object rather than a class, such as
`infrastructure/postgres/metadata.py` exposing the `metadata` `MetaData()` instance, is **not**
wildcarded into its package `__init__` (the wildcard would bind a `metadata` name shadowing the
submodule); reach it by explicit relative import, `from ..metadata import metadata`.

### Named exceptions to "one class per module"

The rule binds everywhere **except** two named files, each of which deliberately holds several classes
because they co-evolve and splitting them would cost readability with no decoupling gain:

1. **`<root>/domain/exceptions.py`** — `DomainError` plus every subclass, so the error catalog stays
   auditable. Its structure is `domain-exception`.
2. **`<root>/restapi/schemas/<resource>.py`** — the four Pydantic wire schemas for one HTTP resource,
   which describe the same wire contract from different angles. Its structure is `restapi-schema`.

These are the **only** exceptions, and the carve-out is by exact file path, not by directory or
category. A third entity in `domain/foos/foo.py` is still wrong; two adapters in one repository module
are still wrong; a command and its handler in one file are still wrong.

Route modules (`restapi/routers/<resource>.py`) hold multiple **functions**, not classes, so they do not
engage this rule at all.

### Snippets

A module file (`manager.py` → `Manager`):

```python
# imports


__all__ = ["Manager"]


class Manager:
    pass
```

A subpackage `__init__.py` re-exporting a single module:

```python
from . import manager
from .manager import *

__all__ = manager.__all__
```

For several modules, name them all in the `from . import …` line, repeat the wildcard per module, and
concatenate the `__all__` lists:

```python
from . import command, handler
from .command import *
from .handler import *

__all__ = command.__all__ + handler.__all__
```

A layered app root (`<root>/__init__.py`, carve-out 1) carries only:

```python
__version__ = "0.1.0"
```

## Imports

### Relative vs absolute

- **Inside a package, relative imports up to two dots** — `from .sibling import X`,
  `from ..parent import Y`.
- **Same package → one dot, never up-and-back-down.** A module importing a sibling in its **own** package
  uses `.sibling`. Routing through the parent back into the same package
  (`from ..pkg.sibling import X` while already inside `pkg/`) resolves but reads as a cross-package
  reach. The toolchain does **not** flag it — the import is valid Python — so it is on the author.
- **Three or more dots → absolute.** `from ...thing import Z` is banned; write
  `from myapp.subpkg.thing import Z`.
- **Across package boundaries → absolute**, regardless of dot count. Anything reaching from
  `application/` into `domain/`, or `restapi/` into `application/`, is absolute.

```python
# inside application/foos/create_foo_handler.py
from .create_foo_command import CreateFooCommand          # same dir — relative
from ..bars.create_bar_command import CreateBarCommand    # one level up — relative
from myapp.domain.foos import IFooRepository              # cross-package — absolute
from myapp.domain.bars import Bar                         # cross-package — absolute

# inside infrastructure/postgres/engine.py importing infrastructure/postgres/settings.py
from .settings import DbSettings                          # same package — one dot
# NOT: from ..postgres.settings import DbSettings         # up-and-back-down into the same package
```

The two-dot ceiling keeps relative imports readable: once it would be `...`, the absolute path is both
shorter and clearer.

### Collapse same-package imports

Importing several symbols from the same place is **one statement**:

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

- One symbol per line inside the parens, alphabetically sorted, trailing comma on the last entry. A
  one-symbol import stays on a single line.
- Import from the **subpackage**, not from an individual module — which is exactly what the re-export
  contract above underwrites.
- **"Subpackage" means the package that DIRECTLY contains the defining module — never a grandparent.**
  Reach a symbol through **one** `from .module import *` hop. Do not reach it through a *grandparent*
  that would re-export it across a second hop: the intermediate package's `__all__` is a **computed**
  concatenation (`a.__all__ + b.__all__`) that mypy cannot evaluate through a `from .subpkg import *`,
  so the name resolves at runtime while mypy reports `[attr-defined]` — "Module X has no attribute Y".
  Concretely, a repository class comes from its **`repositories` subpackage**:
  `from myapp.infrastructure.postgres.repositories import MeetingRepository` (one hop —
  `repositories/__init__` wildcards `meeting_repository`), **not**
  `from myapp.infrastructure.postgres import MeetingRepository` (two hops, the middle `__all__`
  computed). A class sitting *directly* under the tech package — an adapter in
  `infrastructure/openai/openai_embedder.py`, or `engine` / `settings` under `postgres/` — is one hop
  from the tech package, so `from myapp.infrastructure.openai import OpenaiEmbedder` is correct.

### Import order inside a module

PEP 8 grouping, one blank line between groups:

1. `__future__` — **disallowed in this project** (`python-style`); this slot stays empty.
2. Standard library.
3. Third-party.
4. First-party absolute (`myapp.domain…`, `myapp.application…`).
5. First-party relative (`from .sibling import X`).

Ruff and isort handle this automatically. Do not fight the formatter, but know the groupings so
hand-written imports land in the right block.

### What a subdomain package must re-export

A package that is the public face of a subdomain — the typical `domain/<subdomain>/` and
`application/<subdomain>/` — re-exports all of its entities, value objects, enums and type aliases; all
`i_*_repository.py` and `i_can_*.py` protocols; all domain services; and, in `application/`, all
commands, queries, results and handlers.

If a symbol is not re-exported, the collapsed form breaks at the first call site, and whoever adds a
symbol later hits a confusing import error. Adding a module means four edits: declare `__all__` in the
module, add it to the `from . import …` line, add its `from .<module> import *`, and append
`<module>.__all__` to the package's own `__all__`.

## Rules

### Direction

- `application/` may import from `domain/` only. Never `infrastructure/`, never an entrypoint.
- `infrastructure/` may import from `domain/` only. Never `application/`, never an entrypoint.
- `domain/` may not import anything outside `domain/` and stdlib.
- Entrypoints may import all three core layers.
- **No circular imports.** Ever — between modules, between subpackages, between layers.

### Where new code goes

- Pure logic depending only on data → `domain/`.
- A rule needing a repository or a capability → `domain/`, as a service (`domain-service`).
- Orchestration of domain plus protocols, id generation, logging business events → `application/`.
- Anything talking to a database, file system, HTTP API or SDK → `infrastructure/`.
- Anything that knows about HTTP, CLI or queues → an entrypoint package.

If you are tempted to import `infrastructure` from `application`, you are wiring a concrete adapter where
a protocol belongs — define the protocol in `domain/` instead. If you are tempted to import
`application` from `infrastructure`, you have an adapter that knows a use case — move the orchestration
up to a handler.

### Composition root

- DI wiring lives in `containers.py` at the package root. It is the only place that imports concrete
  adapters from `infrastructure/` and binds them to the domain protocol types `application/` handlers
  consume.
- Wire dependencies at startup, not at import time. Never a module-level singleton for a stateful object
  — a DB connection, an HTTP client. Inject them.
- Entrypoints resolve handlers from the container at request time; they do not construct adapters.

### Protocols vs concrete

- Application handlers depend on **domain protocol types** in their constructor signatures
  (`repo: IFooRepository`), never on concrete classes (`repo: PostgresFooRepository`).
- Infrastructure adapters do not explicitly inherit from protocols — satisfaction is structural
  (`domain-ports`).

## How to apply

1. Decide the entry path: an HTTP route → `restapi/…`, a scheduled job → `worker/…`.
2. Sketch the use case as a CQRS handler in `application/<subdomain>/` (`application`).
3. List what the handler needs from the outside world. Each is a protocol in `domain/<subdomain>/`
   (`domain-ports`).
4. Implement each protocol as an adapter under `infrastructure/<tech>/`, grouped by the external
   technology and never by subdomain (`conventions` block A). Adapters import domain types, translate
   raw payloads, and raise domain exceptions (`domain-exception`).
5. Wire the adapters in `containers.py` (`infra-wiring`) and resolve the handler in the entrypoint.
6. Verify the direction by scanning the new files' imports: `domain/` imports only stdlib and domain;
   `application/` does not import `infrastructure/`; `infrastructure/` does not import `application/`.

### When moving code between layers

- `domain/` → `application/` usually means the rule needed a protocol. Extract the protocol first, then
  move the orchestrator.
- `application/` → `domain/` is rare, and correct only when the logic was pure all along: no IO, no
  protocol calls.
- `infrastructure/` → `application/` almost never happens. If you feel the urge, you probably want to
  move the orchestration up and leave the adapter behind.
- An entrypoint → `application/` is correct when a second entrypoint needs the same logic. Pull it into a
  handler; the entrypoint becomes a thin translator.

## Hard stops

- `infrastructure/` imports `application/` → stop, wrong direction; move the orchestration up to a
  handler.
- `application/` imports `infrastructure/` → stop, that wires a concrete adapter where a protocol
  belongs; define the protocol in `domain/` and inject the adapter via DI.
- `domain/` imports anything outside `domain/` and stdlib → stop, the domain layer is data plus
  invariants only.
- A circular import between modules, subpackages or layers → stop, it always signals a layering
  violation. Fix the structure; do not paper over it with `TYPE_CHECKING` or an in-function import.
- An entrypoint module instantiates a concrete adapter directly → stop, `containers.py` is the only place
  that binds concrete classes.
- A new module file with two top-level classes → stop, split it. The only exceptions are
  `domain/exceptions.py` and `restapi/schemas/<resource>.py`.
- A module filename that does not match its class in snake_case — `utils.py` holding `class FooHelper` →
  stop, rename the file.
- `__all__` placed above the imports → stop, it goes after the imports and before the class.
- An `__init__.py` with `from .module import ClassName` instead of the wildcard → stop, use the wildcard
  so the package `__all__` can be `+`-joined.
- An `__init__.py` holding class definitions, constants or logic → stop, imports and `__all__` only.
- An `__init__.py` referencing `module.__all__` with no matching `from . import module` line → stop, add
  the explicit submodule import; the wildcard alone does not bind the name for mypy.
- `from myapp.domain.foos.foo import Foo` — importing the inner module rather than the subpackage → stop,
  import from the subpackage. Bypassing `__init__.py` forces every reader to know the file layout.
- `from foo import *` outside an `__init__.py` → stop, a wildcard inside a regular module pollutes the
  namespace and breaks linting.
- A three-or-more-dot relative import → stop, switch to absolute.
- `import myapp.domain.foos as fs` followed by `fs.Foo` → stop, use `from … import` everywhere; a module
  alias hides what is actually used.
- An import inside a function body to break a cycle → stop, the cycle points at a layering violation.
- `if TYPE_CHECKING:` used purely to dodge a cycle → stop, refactor the cycle.
