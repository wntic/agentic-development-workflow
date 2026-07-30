---
name: restapi-file-transfer
description: Apply when a route accepts a multipart upload (`UploadFile`) or returns a streaming/binary download (`StreamingResponse`). Defines the upload pattern (UploadFile + Form companions, bounded by `MaxRequestSizeMiddleware`, advertise 413), the **only sanctioned `try/except` in a route body** for the mixed multipart+JSON case (`data: Annotated[str, Form()]` + `model_validate_json` with `PydanticValidationError → ValidationError`), and the streaming download pattern (`StreamingResponse(iter([bytes]), media_type=..., Content-Disposition`). Used together with `restapi-endpoint` for the non-file parts of the route.
---

# REST API File Transfer

File transfer breaks the otherwise-uniform CRUD shape: routes accept multipart bodies or return raw bytes. The conventions below must be repeated verbatim in any new file-transfer route — they encode several non-obvious rules and the single route-body `try/except` exemption.

The non-file-specific rules — parameter order, handler resolution via `request.app.state.container`, route ordering vs `/{id}`, the "no `try/except`, no logging, no business logic in routes" prohibitions — are owned by `restapi-endpoint`. Read that skill first; this one only adds the upload/download specializations on top. **Auth follows `restapi-endpoint`'s authed/public idiom:** the templates below show the authenticated form; a public route (`auth: anonymous`) — or any route in an app that declares no auth — drops the auth dependency, its `domain.auth`/`..dependencies` imports, the `401`/`403`, and the `caller_id`. The auth dependency is never a frozen role; it is the slot `restapi-auth-dependency` fills.

## When to use vs. neighbours

- Multipart upload route or streaming-binary download route → this skill.
- A regular JSON CRUD route → `restapi-endpoint` (this skill does not apply).
- The handler that consumes the bytes (upload) or produces them (download) → `application-command` / `application-query`. The handler's capability protocol for storage lives in `domain-capability-protocol`.
- The route's auth dependency (or none) → `restapi-auth-dependency`; it is not pre-wired here. Wiring `MaxRequestSizeMiddleware` and CORS `expose_headers` lives in `restapi/main.py`; this skill only extends `expose_headers` if a new response header is added.

## Upload templates

### Pure file upload (`slot: single`)

```python
@router.post(
    "/import/xlsx",
    response_model=ImportFoosResponse,
    responses=error_responses(401, 403, 413, 422),
)
async def import_xlsx(
    request: Request,
    file: UploadFile,
    bar_id: UUID = Form(...),
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> ImportFoosResponse:
    data = await file.read()
    handler: ImportFoosXlsxHandler = (
        request.app.state.container.import_foos_xlsx_handler()
    )
    result = await handler.execute(
        ImportFoosXlsxCommand(caller_id=user.id, bar_id=bar_id, file_data=data),
    )
    return ImportFoosResponse(...)
```

Rules:

- `file: UploadFile` for the file slot. Companion scalar/UUID fields use `= Form(...)` — they share the same multipart envelope.
- `await file.read()` loads the body into memory. This is bounded **only** when the app declares a request-size cap middleware (`restapi-middleware`'s `MaxRequestSizeMiddleware`), which rejects oversize requests before the route runs. A request-size cap is a per-app `restapi.middlewares` choice, not a given: if the app declares none, the body is unbounded and `file.read()` is **not** safe — the app must add a size cap (or the route must stream-and-bound the read) before relying on it. The templates here assume the app declares such a cap.
- **Advertise `413`** in `responses=error_responses(...)` **only when the app declares a request-size cap middleware** — 413 is produced by that middleware (its code registered in `MIDDLEWARE_ERRORS`), not by a domain exception, so an app without one has no 413 to advertise, and the OpenAPI discovery check (`test-discovery-invariants`) would reject the orphan code. The `413` shown in the decorator templates is present because those templates assume a size-capped app; drop it for an app that declares no size middleware.
- The route does not parse the file — pass bytes to the handler via the command DTO (`file_data: bytes`).

### Multiple optional uploads (`slot: optional-many`)

```python
attachments: list[UploadFile] | None = None,
...
attachment_inputs: list[CreateFooAttachment] = []
for f in attachments or []:
    raw = await f.read()
    attachment_inputs.append(CreateFooAttachment(data=raw, mime=f.content_type or ""))
```

- Slot type `list[UploadFile] | None = None` handles "no files attached" cleanly.
- Build a list of application input dataclasses inside the route; capture both `data` and `f.content_type or ""`. The empty-string fallback is deliberate — domain validates the mime and an empty value triggers a clear `ValidationError` rather than `None` slipping through.

### Mixed multipart + JSON (`slot: mixed-multipart-json`) — the only sanctioned `try/except` in a route body

```python
@router.post(
    "",
    status_code=201,
    response_model=FooResponse,
    responses=error_responses(401, 409, 413, 422),
)
async def create_foo(
    request: Request,
    data: Annotated[str, Form()],
    attachments: list[UploadFile] | None = None,
    user: CurrentUser = Depends(require_role(Role.<MIN_RANK>)),
) -> FooResponse:
    try:
        payload = CreateFooPayload.model_validate_json(data)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    ...
```

Rules:

- `data: Annotated[str, Form()]` receives the JSON blob as a string. Pydantic does not automatically validate it because the slot type is `str` — validation is explicit.
- `<Schema>.model_validate_json(data)` parses and validates.
- **The `try/except PydanticValidationError → raise ValidationError(str(exc)) from exc` is the single sanctioned `try/except` in a route body** in this codebase. It exists because Pydantic's exception is not a `DomainError` and would otherwise produce FastAPI's default 422 instead of an `ErrorResponse`-shaped body. **Use this pattern verbatim — no other forms of error catching belong in a route.**
- Always re-raise with `from exc` to preserve the chain.

This pattern is reserved for the multipart+JSON case. **Do not generalize it.** A JSON-only route uses `body: <Schema>` and lets FastAPI's normal validation flow through the central handler.

## Download template — streaming binary response

```python
@router.post("/export", responses=error_responses(401, 422))
async def export_foos(
    body: ExportFoosFilterRequest,
    request: Request,
    _: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    handler: ExportFoosHandler = request.app.state.container.export_foos_handler()
    data = await handler.execute(ExportFoosQuery(filter=_to_filter(body)))
    filename = _export_filename("csv")  # the extension this export actually produces
    return StreamingResponse(
        iter([data]),
        # The real content type the handler produces — csv / pdf / xlsx / … — not a
        # fixed format frozen from one app. Don't fall back to octet-stream for a known type.
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Rules:

- **Return annotation: `-> StreamingResponse`.** No `response_model` — FastAPI does not serialize the body.
- `StreamingResponse(iter([bytes]), media_type=..., headers={...})` is the canonical shape. `iter([data])` wraps already-materialized bytes in a single-chunk iterator. If the handler produces a true `AsyncIterator[bytes]`, pass it directly without `iter([...])`.
- **`media_type` is the real content type** (xlsx / docx / pdf MIME). Don't use `application/octet-stream` for known formats — clients render based on this.
- `Content-Disposition: attachment; filename="..."` triggers download instead of inline. Filename is double-quoted; a plain ASCII filename is the simplest default, and if you need RFC 5987 encoding for non-ASCII, document it inline.

### `_export_filename` helper

```python
def _export_filename(ext: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"myapp-foos-{ts}.{ext}"
```

- Module-level helper named `_<purpose>_filename`. Underscore-prefixed because it's private to the router module.
- The shape shown (UTC timestamp `YYYYMMDD-HHMMSS`, a `<project>-<resource>` prefix, an extension parameter) is a reasonable default, not a fixed canon. The exact filename format — timestamp style, prefix, ASCII vs RFC 5987 — is an app-level choice; keep it consistent within one app, but don't freeze this particular shape as mandatory across apps.
- Filename construction lives in the route, not the handler. The handler returns content; the route names the artifact.

### CORS `expose_headers`

`Content-Disposition` is not a default CORS-exposed header, so a browser strips it from the response visible to JS. **If the app has CORS configured** (`restapi-app-bootstrap`), a download route must ensure its response header is in the CORS middleware's `expose_headers` list — the bootstrap leaves that list **empty** by default, so a download route adds `"Content-Disposition"` (and any other non-default header it sets, e.g. `X-Total-Count`) there:

```python
expose_headers=["Content-Disposition"],
```

An app with no CORS configured has no such list to extend. **Verify `expose_headers` whenever you add a headered download response** (when CORS is enabled).

## Handler contract for downloads

- The handler returns **raw bytes** (or an `AsyncIterator[bytes]` for true streaming). It does not return a Pydantic model, a Response, or a file path.
- The route does not transform the bytes — it only wraps them in `StreamingResponse` and attaches the filename / `Content-Disposition`.
- Authorization, filtering, and content generation all live in the handler. The route is a transport adapter.

## What never goes in a file-transfer route

- **Writing the upload to disk inside the route.** Pass bytes (or an `UploadFile`) to the handler; storage is an infrastructure concern (`infra-sqlalchemy-repository`-style capability adapters).
- **Computing or enforcing a per-route size limit.** `MaxRequestSizeMiddleware` is the single chokepoint. If a specific route needs a tighter cap, add it as an application-layer rule that raises `ValidationError` after parsing.
- **Streaming without `media_type`.** Browsers and clients rely on it.
- **Catching exceptions other than the one sanctioned `PydanticValidationError → ValidationError` translation in mixed-multipart-json mode.** Do not extend the `try/except`.
- **Returning `FileResponse` from a path on disk.** All file content originates from the handler's bytes. The API does not serve filesystem paths.
- **`response_model` on a streaming route.** Meaningless and confuses OpenAPI.

## Inlined typing / import rules

- `from typing import Annotated`, `from uuid import UUID`, `from datetime import datetime, UTC`.
- `from fastapi import UploadFile, Form` (in addition to the standard `APIRouter, Depends, Query, Request`).
- `from fastapi.responses import StreamingResponse`.
- `from pydantic import ValidationError as PydanticValidationError` — alias so the import doesn't shadow the domain `ValidationError`.
- Full annotations on every parameter and return type.

## Hard stops

- Spec asks for a `try/except` other than the mixed-multipart-json one → stop, no other `try/except` belongs in a route body.
- Spec wants the route to compute file size limits → stop, that's the middleware's job.
- Spec wants the route to parse the file content → stop, that's the handler's job; the route passes bytes.
- Spec adds a download response header beyond `Content-Disposition` without updating CORS `expose_headers` (when CORS is configured) → stop, update both in the same change.
