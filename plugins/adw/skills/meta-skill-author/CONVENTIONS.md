# Skill conventions

Shared vocabulary used by every skill in `skills/`. When a skill needs a worked example, it draws from this vocabulary so the same names recur and the reader can carry a mental model from one skill to the next.

## Placeholder aggregates

| Role | Name | snake_case | plural | Use for |

Derived names follow mechanically (the authoritative, exhaustive derivation registry — path/class/suffix, store profiles, the stack substrate — lives in the `conventions` reference skill; these examples only anchor the shared vocabulary):

- Module: `foo.py`, `bar.py`
- Subdomain package: `domain/foos/`, `application/foos/`, `infrastructure/postgres/repositories/foo_repository.py` (infra groups by tech)
- Table: `foos_table`, file `infrastructure/postgres/tables/foos.py`
- Protocol: `IFooRepository` in `i_foo_repository.py`; capability `ICan<Verb>` in `i_can_<verb>.py`
- Commands / queries: `CreateFooCommand`, `ListFoosQuery`, `CreateFooHandler`, `ListFoosResult`
- REST schemas: `FooResponse`, `FooListResponse`, `FooCreateRequest`, `FooUpdateRequest`
- REST router: `restapi/routers/foos.py`, prefix `/foos`

## Project root package

Examples use `myapp` as the project's root Python package (e.g. `from myapp.domain.foos import IFooRepository`). Substitute your real root package name when adopting these skills in a new project.
