---
name: restapi
description: "House style for the whole FastAPI REST layer: the one-shot app bootstrap shell (`main.py`, central `DomainError` handler, CORS, DI wiring), thin endpoints in `routers/`, Pydantic request/response schemas, the auth-dependency decision (`get_current_user` vs `require_role`), route-level error advertisement, multipart upload / streaming download, and custom middleware ordering."
when_to_use: "Producing or editing any REST-layer artifact: the app shell, an endpoint, a schema, the auth dependency, error responses, a file-transfer route, or a middleware."
---
# REST API

This theme covers 7 related artifacts, each carried by its own topic file next to this one. A topic
file holds the full *When to use / Template(s) / Rules / Hard stops* body for its artifact; this
router only routes. Read the file matching what you are producing.

## When to use vs. neighbours

- First-time setup of the app skeleton — `main.py`, `error_handler.py`, `schemas/errors.py`,
  `dependencies.py` — or registering a new router in `main.py` → **read `bootstrap.md` now**.
- Adding or changing an endpoint: the router function, its status code, parameter order, route
  ordering → **read `endpoint.md` now**.
- Writing a resource's Pydantic request/response models → **read `schema.md` now**.
- Choosing the auth dependency a route attaches (`get_current_user` vs `require_role`) →
  **read `auth-dependency.md` now**.
- Deciding which HTTP codes a route advertises via `error_responses(...)`, or registering a
  middleware-only status → **read `error-responses.md` now**.
- A multipart upload or a streaming download route, with the one sanctioned route-body
  `try/except` → **read `file-transfer.md` now**, on top of `endpoint.md`.
- Writing an ASGI middleware for a cross-cutting request/response concern →
  **read `middleware.md` now**.
- Business logic, orchestration or persistence → not this theme: `application` for the handler the
  route dispatches, `infra-persistence` / `infra-integration` for the adapters behind it.
