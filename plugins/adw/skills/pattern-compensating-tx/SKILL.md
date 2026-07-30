---
name: pattern-compensating-tx
description: The catch → undo → re-raise pattern — the only sanctioned `try/except` in `application/`. For a command handler that performs an external side effect (blob upload, third-party POST, file write) before the DB write recording it, and must undo that side effect when a later step fails.
when_to_use: Shaping a command handler whose external side effect precedes the DB write and needs a compensating undo.
paths: src/**/application/**
---

# Compensating Transactions

A pattern applied inside a command handler when it has already done something the outside world can see (an upload, a webhook, a file) before a later step (usually the DB write) can still fail. The handler must undo the visible side effect before letting the exception propagate.

This skill produces **no new file** — it shapes a command handler's `execute` body (the form `application-command` writes when compensation is required): the try → undo → re-raise structure around the visible side effect.

## When to use vs. neighbours

- The handler creates an external side effect (blob upload, third-party POST, file write) **before** a DB write that can still fail, and the side effect must be undone on failure → this skill.
- The handler performs writes across multiple repositories atomically → `pattern-unit-of-work` (the patterns nest: compensation outside, UoW inside).
- The handler has no external side effect, only a DB write → no compensation needed; the default `application-command` shape (no `try/except`) suffices.
- The side effect is harmless if left behind (cache warm-up), is the *last* step (nothing after to fail), or can be reordered after the DB write → skip this skill.

## Template — single side effect

```python
async def execute(self, cmd: UpsertFooCommand) -> uuid.UUID:
    # validation that doesn't depend on the side effect goes BEFORE the upload
    ...

    storage_key = await self._storage.put(cmd.data, ...)

    try:
        await self._repo.create(Foo(..., storage_key=storage_key))
    except Exception:
        await self._storage.delete_many_best_effort([storage_key])
        raise

    # caller_id is logged only when the command carries it (authenticated form);
    # an auth-less command has no caller_id field — drop it (see application-command DTO rule 2).
    logger.info("foo_created", foo_id=str(foo.id), caller_id=str(cmd.caller_id))
    return foo.id
```

## Template — multi-step side effects

Accumulate work-to-undo in a list so partial progress is also cleaned:

```python
uploaded_keys: list[str] = []
try:
    items = await self._upload_items(uploads, foo_id, uploaded_keys)
    foo = _build_foo(cmd, items)
    await self._repo.create(foo)
except Exception:
    await self._storage.delete_many_best_effort(uploaded_keys)
    raise
```

The helper appends to `uploaded_keys` after each successful upload, so a failure mid-loop still rolls back what already landed.

## Successful-path cleanup is **not** compensation

When an upsert *replaces* a previous resource, the old one is cleaned **after** the DB commit:

```python
previous_key = await self._repo.upsert_foo(...)
# ... try/except wraps only the upsert above ...

if previous_key is not None:
    await self._storage.delete_many_best_effort([previous_key])
```

That trailing call is normal cleanup, not compensation — it runs only on success and disposes of the *old* resource. Don't conflate the two.

## Rules

1. **The `try/except Exception` block is the ONLY `try/except` allowed in a handler.** If you need another, the design is wrong — push the catch into infrastructure or remove it.
2. **Catch `Exception`, not specific exceptions.** Compensation must run regardless of failure cause.
3. **The compensation must never let its OWN failure mask the original error** — the undo is best-effort. Two sanctioned shapes, the architect's choice (do not assume one):
   - a dedicated **`*_best_effort` method** on the protocol (e.g. `delete_many_best_effort`) that swallows its internal errors — call it directly, as the templates show; **or**
   - the **plain protocol method** (`delete` / `revert`) wrapped in a nested swallow at the call site when no `*_best_effort` variant is modelled:
     ```python
     except Exception:
         try:
             await self._storage.delete(storage_key)
         except Exception:
             pass  # best-effort — the undo's own failure must not mask the original error
         raise
     ```
   Never call a raising `delete` / `revert` *unguarded* in the `except` — if it raises, the original error is lost. If the undo is called often enough to deserve a first-class name, the architect models a `*_best_effort` method; until then the call-site swallow is correct and needs no new protocol method.
4. **Bare `raise` at the end of `except`.** Never `raise NewException(...)`, never `raise ... from exc`. The original exception propagates unchanged.
5. **No logging inside `except`.** The central error handler logs once.
6. **The side effect runs *outside* the `try`.** Only the fallible *next* step is inside.
7. **Pre-side-effect validation runs *before* the upload.** Fail fast without compensation when possible.
8. **Compensation pairs with `pattern-unit-of-work` cleanly** — compensation wraps the UoW; the patterns nest: try / async with uow / commit / except / undo / raise.

## Hard stops

- The capability protocol lacks a `*_best_effort` cleanup method → stop, update the protocol via `domain-capability-protocol` first.
- The compensation method can itself raise non-trivially (e.g. it calls a flaky third-party DELETE) → stop, the protocol contract is wrong; the method must internally swallow its own errors.
- The handler needs to compensate across two unrelated backends (Postgres + Redis) → stop, this is a saga, not a single compensating-tx. Out of scope for this skill.
