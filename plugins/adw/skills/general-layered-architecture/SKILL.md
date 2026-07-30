---
name: general-layered-architecture
description: The four-layer split — domain, application, infrastructure, entrypoints — with the inward-only dependency direction and what each layer may import.
when_to_use: Deciding which layer a module belongs to, moving code between layers, or laying out a new feature.
---

# Layered Architecture

A project is split into four layers. Three are core (`domain/`, `application/`, `infrastructure/`); the fourth is one or more entrypoint packages (`restapi/`, `cli/`, `worker/`, …). The split exists so the business rules in `domain/` stay independent of databases, HTTP frameworks, and SDKs — and so the dependency graph stays acyclic.

## When to use vs. neighbours

- Laying out a new feature or deciding where a module belongs → consult this skill.
- Producing a specific artifact at a given layer → the per-layer skill (`domain-entity`, `application-command`, `infra-sqlalchemy-repository`, `restapi-endpoint`, …). This skill defines the boundary; the per-layer skills define the file shape.
- An "imports may cross this boundary?" question → this skill.
- Package mechanics inside a layer → `general-python-package`.

## The shape

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

## What each layer may import

### `domain/`

- Allowed: stdlib (`dataclasses`, `datetime`, `enum`, `uuid`, `typing`), other domain modules.
- Forbidden: anything else. No third-party libraries (no SQLAlchemy, no Pydantic, no httpx, no boto3, no FastAPI). No `application/`, no `infrastructure/`, no entrypoint imports.
- Defines: entities, value objects, enums, filter records, domain protocols (`I*` / `ICan*`), domain policies, domain exceptions, type aliases.
- Zero IO. No file reads, no network, no database, no logging.

### `application/`

- Allowed: stdlib, `structlog`, domain modules.
- Forbidden: third-party libraries beyond `structlog`. No `infrastructure/` imports. No entrypoint imports.
- Defines: commands, queries, handlers, result DTOs (see `cqrs`).
- Depends on infrastructure capabilities only through domain protocols. Receives concrete adapters via DI.

### `infrastructure/`

- Allowed: stdlib, any third-party library, domain modules (for protocol types and entities).
- Forbidden: `application/` imports, entrypoint imports.
- Defines: adapters that implement domain protocols (Postgres repositories, S3 storage, JWT verifiers, file renderers).
- Translates between external representations (DB rows, HTTP JSON, queue messages) and domain objects. Translation happens *inside* the adapter — never leaks raw rows or SDK objects upward.

### Entrypoint packages (`restapi/`, future `cli/` / `worker/`)

- Allowed: everything. This is the composition root.
- Defines: HTTP routes / CLI commands / queue consumers, request/response Pydantic models, the central error handler, the DI wiring.
- Wires `containers.py` at startup, resolves handlers, translates transport ↔ application DTOs.

## Top-level layout

```
src/myapp/
├── containers.py        # DI wiring (the composition root's dependency graph)
├── domain/              # pure business model
├── application/         # CQRS orchestration
├── infrastructure/      # adapters
└── restapi/             # HTTP entrypoint
```

`domain/` and `application/` mirror the same subdomain partition: `domain/foos/`, `application/foos/`. **`infrastructure/` groups by external tech, not by subdomain** — `infrastructure/postgres/`, `infrastructure/qdrant/`, `infrastructure/openai/`, `infrastructure/jwt/` (the derivation lives in `conventions` block A). A new subdomain adds a folder under `domain/` and `application/`; a new external technology adds one under `infrastructure/`.

## Rules

### Direction

- `application/` may import from `domain/` only. Never from `infrastructure/` or entrypoints.
- `infrastructure/` may import from `domain/` only. Never from `application/` or entrypoints.
- `domain/` may not import from anything outside `domain/`.
- Entrypoints may import from all three core layers.
- No circular imports. Ever — between modules, between subpackages, between layers.

### Where new code goes

- Pure logic that depends only on data → `domain/`.
- A rule that needs a repository or capability → `domain/` (as a service, see `domain-service`).
- Orchestration of domain + protocols, ID generation, logging business events → `application/`.
- Anything that talks to a database, a file system, an HTTP API, or an SDK → `infrastructure/`.
- Anything that knows about HTTP / CLI / queues → an entrypoint package.

If you're tempted to import `infrastructure` from `application`, you're wiring a concrete adapter where a protocol belongs. Stop and define a protocol in `domain/` instead.

If you're tempted to import `application` from `infrastructure`, you have an adapter that knows about a use case. Move the orchestration up to a handler.

### Composition root

- DI wiring lives in `containers.py` at the package root. It is the only place that imports concrete adapters from `infrastructure/` and binds them to domain protocol types consumed by `application/` handlers.
- Wire dependencies at startup, not at import time. Never use module-level singletons for stateful objects (DB connections, HTTP clients) — inject them.
- Entrypoint packages call into the container at request time to resolve handlers; they don't construct adapters themselves.

### Protocols vs. concrete

- Application handlers depend on **domain protocol types** in their constructor signatures (`repo: IFooRepository`), never on concrete classes (`repo: PostgresFooRepository`).
- Infrastructure adapters do not explicitly inherit from protocols (structural subtyping; see `domain-protocols`).

## How to apply

1. When adding a feature, decide the entry path: HTTP route → `restapi/...`, scheduled job → `worker/...`, etc.
2. Sketch the use case as a CQRS handler in `application/<subdomain>/` (see `cqrs`).
3. List what the handler needs from the outside world. Each of those is a protocol in `domain/<subdomain>/` (see `domain-protocols`).
4. Implement each protocol as an adapter under `infrastructure/<tech>/` — grouped by the external technology (`postgres/`, `qdrant/`, `jwt/`), never by subdomain (see `conventions` block A). Adapters import domain types, translate raw payloads, raise domain exceptions (see `domain-exceptions`).
5. Wire the adapters in `containers.py` and resolve the handler in the entrypoint.
6. Verify the dependency direction by scanning the new files' imports — `domain/` files must import only stdlib + domain; `application/` files must not import `infrastructure/`; `infrastructure/` must not import `application/`.

### When moving code between layers

- Moving from `domain/` to `application/` usually means the rule needed a protocol — extract a protocol first, then move the orchestrator.
- Moving from `application/` to `domain/` is rare and only correct when the logic was pure all along (no IO, no protocol calls).
- Moving from `infrastructure/` to `application/` almost never happens — if you feel the urge, you probably want to move the orchestration up but leave the adapter behind.
- Moving from an entrypoint into `application/` is correct when the same logic is needed by a second entrypoint. Pull it into a handler; the entrypoint becomes a thin translator.

## Hard stops

- `infrastructure/` imports `application/` → stop, that's the wrong direction; move the orchestration up to a handler.
- `application/` imports `infrastructure/` → stop, that wires a concrete adapter where a protocol belongs; define a protocol in `domain/` and inject the adapter via DI.
- `domain/` imports anything outside `domain/` or stdlib → stop, the domain layer is pure data + invariants only.
- A circular import between modules / subpackages / layers → stop, it always indicates a layering violation; fix the structure (don't paper over with `TYPE_CHECKING` or in-function imports).
- An entrypoint module instantiates a concrete adapter directly → stop, the DI container in `containers.py` is the only place that binds concrete classes.
