---
name: general-imports-conventions
description: Apply when adding or modifying any import statement, or when restructuring `__init__.py` re-exports. Enforces relative imports up to two dots within a package, absolute imports beyond, the same-package collapse rule (one `from X import (A, B, C)` line — not many), and the `from .module import *` re-export contract that every subpackage `__init__.py` must satisfy so collapsed absolute imports work.
---

# Imports Conventions

Imports follow three rules: how far you reach with relative dots, how you collapse multiple symbols from the same package, and how `__init__.py` re-exports underwrite the collapsed form.

## When to use vs. neighbours

- Adding or modifying any import statement → consult this skill.
- Restructuring `__init__.py` re-exports → consult both this skill (re-export contract) and `general-python-package` (package mechanics).
- Choosing `frozenset` vs `set` or `X | None` vs `Optional[X]` → `general-typing-conventions`.
- Layer boundaries (what each layer may import) → `general-layered-architecture`.

## Relative vs absolute

- **Within a package, use relative imports up to two dots** (`from .sibling import X`, `from ..parent import Y`).
- **Three or more dots → use absolute.** `from ...thing import Z` is banned; write `from myapp.subpkg.thing import Z`.
- **Cross-package boundaries → absolute.** Anything reaching from `application/` into `domain/`, or `restapi/` into `application/`, is absolute regardless of dot count.

```python
# inside application/foos/create_foo_handler.py
from .create_foo_command import CreateFooCommand   # same dir — relative
from ..bars.create_bar_command import CreateBarCommand            # one level up — relative
from myapp.domain.foos import IFooRepository    # cross-package — absolute
from myapp.domain.auth import CurrentUser                      # cross-package — absolute
```

The two-dot ceiling exists to keep relative imports readable; once you'd be writing `...` or more, the absolute path is shorter and clearer.

## Collapse same-package imports

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
- One-symbol imports stay on a single line: `from myapp.domain.foos import Foo`.

## `__init__.py` re-exports

For the collapsed-import form to work, **every subpackage `__init__.py` must re-export everything its submodules expose**:

```python
# domain/foos/__init__.py
from .foo import *
from .foo_category import *
from .foo_pattern import *
from .i_foo_repository import *
```

Rules:

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

## Import order inside a module

Standard PEP 8 grouping, with a blank line between groups:

1. `__future__` — **disallowed in this project** (see `general-typing-conventions`); this slot stays empty.
2. Standard library (`uuid`, `datetime`, `collections.abc`, ...).
3. Third-party (`pydantic`, `fastapi`, `sqlalchemy`, ...).
4. First-party absolute (`myapp.domain...`, `myapp.application...`).
5. First-party relative (`from .sibling import X`, `from ..parent import Y`).

Ruff/isort handle this automatically; don't fight the formatter, but understand the groupings so manually written imports land in the right block.

## Re-exporting domain protocols and entities

Subpackages designed to be the public face of a subdomain (the typical `domain/<subdomain>/` and `application/<subdomain>/` packages) must re-export:

- All entities, value objects, enums, type aliases.
- All `i_*_repository.py` and `i_can_*.py` protocols.
- All policies.
- All commands, queries, results, handlers (in `application/<subdomain>/`).

If a symbol isn't re-exported, the collapsed-import form breaks at the first call site — and any contributor who adds a new symbol later will hit confusing import errors. Adding a new module means: declare `__all__` in the module, then add `from .<module> import *` to the subpackage `__init__.py` and append `<module>.__all__` to the package's own `__all__`.

## Hard stops

- `from myapp.domain.foos.foo import Foo` (importing from the inner module rather than the subpackage) → stop, import from the subpackage instead. Bypassing `__init__.py` forces every reader to know the file layout.
- `from foo import *` outside `__init__.py` → stop, wildcard imports inside regular modules pollute namespaces and break linting.
- Three-or-more-dot relative imports → stop, switch to absolute.
- `import myapp.domain.foos as fs` followed by `fs.Foo` → stop, use `from ... import` everywhere; module aliases hide what's actually used.
- Imports inside function/method bodies to break a circular import → stop, the cycle almost always points to a layering violation (see `general-layered-architecture`); fix the structure.
- `if TYPE_CHECKING:` imports purely to dodge a circular import → stop, refactor the cycle.
