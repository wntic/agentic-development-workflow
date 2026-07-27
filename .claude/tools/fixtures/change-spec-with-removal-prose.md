# demo/002 — user CRUD over HTTP

Class: behavioral
Affects: user-management.md

## Context

This is the first change of the `users` context: it stands up the bounded context, its app
shell, and the whole account collection as one slice. It supersedes the abandoned `users/001`
(create + read only, tag `abandoned/users-001`), which is why the vertical slice here is the
full set of five operations rather than a single path — the human asked for a simple users CRUD
application, and a half-CRUD context would immediately need a second change to be useful.

A user is identified by a server-assigned id and carries an email — its natural unique key —
and a display name. Audit `created_at` is surfaced on reads but is a DB-managed table
convention, never a domain field. Users live in Postgres: email uniqueness is the one invariant
that must hold under concurrency, and the store is the only place that can hold it.

## Task

Create the `users` context with the five CRUD operations over a real store, all endpoints
unauthenticated:

- `POST /users` accepts an email and a name, assigns an id, persists the user, returns it.
- `GET /users/{id}` reads one user back, including its `created_at`.
- `GET /users` lists every user, oldest first.
- `PATCH /users/{id}` partially edits a user: a body may carry `email`, `name`, or both; an
  omitted field is left untouched. An empty body is a no-op that returns the user unchanged.
- `DELETE /users/{id}` removes the user's row (a hard delete — no tombstone, no marker column).

Failure modes across the operations: an email already held by another user is rejected at the
store (409 `duplicate_email`, on create and on update alike); a malformed email is rejected at
the edge (422); addressing a user that does not exist is a 404 `user_not_found` on read, update
and delete alike.

## Out of scope

- Any authentication, authorization, roles, or sessions.
- Pagination, filtering, or any list ordering other than `created_at` ascending.
- Soft delete / tombstones, and any restore of a deleted user.
- `PUT /users/{id}` full replacement — `PATCH` is the only edit verb.
- Email verification, passwords or credentials, and any user attribute beyond `email` and `name`.
- Bulk create / bulk delete.

## Interface sketch

The standard app shell is always-present substrate, not a business layer: `create_app()`, the
central `DomainError` handler (`restapi/error_handler.py`) and the error schema
(`restapi/schemas/errors.py`) are written by the implementer as behaviorless `src/**`. No
BUSINESS domain / application / infrastructure exists before this change beyond that shell.
The business layers this slice introduces:

**domain/**
- `domain/users/user.py` — `User` entity: `id: UUID`, `email: Email`, `name: str`; identity
  equality on `id`.
- `domain/users/email.py` — `Email` value object: frozen, validates format in `__post_init__`,
  raises `InvalidEmailError` on a malformed value.
- `domain/users/user_read_model.py` — `UserReadModel` frozen DTO: `id: UUID`, `email: str`,
  `name: str`, `created_at: datetime`. It lives in the domain because the repository protocol
  below returns it; the dependency direction forbids a domain port referencing `application/`.
- `domain/users/i_user_repository.py` — `IUserRepository` protocol:
  - `async add(user: User) -> None` — raises `DuplicateEmailError` on an email conflict;
  - `async find(user_id: UUID) -> User | None` — the write-model entity, for edit flows;
  - `async get(user_id: UUID) -> UserReadModel | None` — the read model, with `created_at`;
  - `async list_all() -> tuple[UserReadModel, ...]` — ordered by ascending `created_at`;
  - `async save(user: User) -> None` — persists a modified entity; raises `DuplicateEmailError`;
  - `async delete(user_id: UUID) -> bool` — `True` when a row was removed, `False` when no user
    held that id.
- `domain/exceptions.py` — `DomainError` (base), `InvalidEmailError`, `DuplicateEmailError`,
  `UserNotFoundError`.

**application/** — one module per command / query / handler under `application/users/`:
- `CreateUserCommand(email: str, name: str)` + `CreateUserHandler.handle(cmd) -> UUID`.
- `GetUserQuery(user_id: UUID)` + `GetUserHandler.handle(query) -> UserReadModel | None`.
- `ListUsersQuery()` + `ListUsersHandler.handle(query) -> tuple[UserReadModel, ...]`.
- `UpdateUserCommand(user_id: UUID, email: str | None, name: str | None)` +
  `UpdateUserHandler.handle(cmd) -> UUID | None` — a `None` field means "leave untouched";
  the return is `None` when no user holds `user_id`. Read-modify-write over `find` + `save`.
- `DeleteUserCommand(user_id: UUID)` + `DeleteUserHandler.handle(cmd) -> UUID | None` — the
  removed id, or `None` when no user held it.

**infrastructure/postgres/**
- `tables/users.py` — `users` table: `id` (PK), `email` (UNIQUE, NOT NULL), `name` (NOT NULL),
  `created_at` (timezone-aware, NOT NULL, server default `now()`).
- `repositories/user_repository.py` — `PostgresUserRepository` implements `IUserRepository` on
  SQLAlchemy Core; translates the unique-violation `IntegrityError` into `DuplicateEmailError`.
- `settings.py` + `engine.py`; container wiring in `containers.py` for the repository and all
  five handlers.
- The Alembic scaffold (`alembic.ini` + `migrations/`, DSN from `DATABASE_URL`) and the revision
  creating the `users` table are implementer-owned and **committed** — an untracked migration
  makes the Docker tier unreproducible.

**restapi/**
- `routers/users.py` — `POST ""` (201), `GET "/{id}"` (200), `GET ""` (200), `PATCH "/{id}"`
  (200), `DELETE "/{id}"` (204). A missing user raises `UserNotFoundError`; the central handler
  maps `UserNotFoundError` → 404 `user_not_found` and `DuplicateEmailError` → 409
  `duplicate_email`.
- `schemas/users.py` — `CreateUserRequest(email: str, name: str)`;
  `UpdateUserRequest(email: str | None = None, name: str | None = None)`, both validating email
  format through the `Email` value object so a malformed value surfaces as 422;
  `UserResponse(id, email, name, created_at)`.

## Acceptance criteria

- AC-1: `POST /users` with a valid, previously-unused email and a name returns 201 and a JSON
  body carrying a server-assigned `id`, the submitted `email`, the submitted `name`, and a
  non-null `created_at`.
- AC-2: `GET /users/{id}` for the id returned by AC-1 returns 200 and a JSON body whose `id`,
  `email`, `name`, and `created_at` equal those from the AC-1 response.
- AC-3: `POST /users` with an email equal to that of an already-created user returns 409 and a
  JSON body with error code `duplicate_email`.
- AC-4: `POST /users` with a malformed email (e.g. `not-an-email`) returns 422.
- AC-5: `GET /users/{id}` for an id that no user has returns 404 and a JSON body with error
  code `user_not_found`.
- AC-6: `GET /users` after three users have been created returns 200 and a JSON array holding
  exactly those three users, ordered by ascending `created_at`.
- AC-7: `GET /users` when no user exists returns 200 and an empty JSON array.
- AC-8: `PATCH /users/{id}` with a body carrying only `name` returns 200 and a JSON body with
  the submitted `name` and the user's prior `email`; a following `GET /users/{id}` returns that
  same `name`.
- AC-9: `PATCH /users/{id}` with a body carrying only a valid, previously-unused `email`
  returns 200 and a JSON body with the submitted `email` and the user's prior `name`; a
  following `GET /users/{id}` returns that same `email`.
- AC-10: `PATCH /users/{id}` with an `email` already held by a different user returns 409 and a
  JSON body with error code `duplicate_email`, and a following `GET /users/{id}` returns the
  `email` the user held before the request.
- AC-11: `PATCH /users/{id}` for an id that no user has returns 404 and a JSON body with error
  code `user_not_found`.
- AC-12: `PATCH /users/{id}` with a malformed `email` (e.g. `not-an-email`) returns 422.
- AC-13: `DELETE /users/{id}` for an existing user returns 204 with an empty body; a following
  `GET /users/{id}` returns 404, and that user is absent from the `GET /users` array.
- AC-14: `DELETE /users/{id}` for an id that no user has returns 404 and a JSON body with error
  code `user_not_found`.

## Verification

Run `uv run .claude/tools/gate.py --criteria`.

- AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-13 and AC-14 run as
  integration tests against a real Postgres provisioned by testcontainers; the schema is applied
  by `alembic upgrade head` from the committed `migrations/`, with the test DSN passed as
  `DATABASE_URL`. Per-test transaction rollback gives each test an empty table — which is what
  makes AC-7's empty-array assertion and AC-6's exactly-three assertion hold.
- AC-4 and AC-12 are DB-free edge tests on the request schemas / the `Email` value object.
- AC-2, AC-8, AC-9, AC-10 and AC-13 chain their follow-up request onto the id from the request
  before it, inside one test flow.
- No seed data, external tokens, or manual environment provisioning are required.
- A reachable Docker daemon is required to prove the integration-backed criteria: without one
  the Docker tier skips loudly (`DOCKER SKIPPED`), those tests do not pass, and the gate's
  criteria cross-check therefore cannot flip them.
