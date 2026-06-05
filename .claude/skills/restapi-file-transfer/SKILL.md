---
name: restapi-file-transfer
description: Apply when a route accepts a multipart upload (`UploadFile`) or returns a streaming/binary download (`StreamingResponse`). Defines the upload pattern (UploadFile + Form companions, bounded by `MaxRequestSizeMiddleware`, advertise 413), the **only sanctioned `try/except` in a route body** for the mixed multipart+JSON case (`data: Annotated[str, Form()]` + `model_validate_json` with `PydanticValidationError → ValidationError`), and the streaming download pattern (`StreamingResponse(iter([bytes]), media_type=..., Content-Disposition`). Used together with `restapi-endpoint` for the non-file parts of the route.
---

# REST API File Transfer

File transfer breaks the otherwise-uniform CRUD shape: routes accept multipart bodies or return raw bytes. The conventions below must be repeated verbatim in any new file-transfer route — they encode several non-obvious rules and the single route-body `try/except` exemption.

The non-file-specific rules — parameter order, handler resolution via `request.app.state.container`, route ordering vs `/{id}`, the "no `try/except`, no logging, no business logic in routes" prohibitions — are owned by `restapi-endpoint`. Read that skill first; this one only adds the upload/download specializations on top.

## When to use vs. neighbours

- Multipart upload route or streaming-binary download route → this skill.
- A regular JSON CRUD route → `restapi-endpoint` (this skill does not apply).
- The handler that consumes the bytes (upload) or produces them (download) → `application-command` / `application-query`. The handler's capability protocol for storage lives in `domain-capability-protocol`.
- Wiring `MaxRequestSizeMiddleware`, CORS `expose_headers`, and the JWT verifier → already done in `restapi/main.py`; this skill only extends `expose_headers` if a new response header is added.

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
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
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
- `await file.read()` loads the body into memory. **Safe only because** `MaxRequestSizeMiddleware` caps the request before the route runs. Do not stream-and-validate-size in the route.
- **Always advertise `413`** in `responses=error_responses(...)` for any route that accepts a body. 413 comes from the middleware, not from a domain exception, but its code is registered in `MIDDLEWARE_ERRORS`.
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
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
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
@router.post("/export/xlsx", responses=error_responses(401, 422))
async def export_xlsx(
    body: ExportFoosFilterRequest,
    request: Request,
    _: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    handler: ExportFoosXlsxHandler = (
        request.app.state.container.export_foos_xlsx_handler()
    )
    data = await handler.execute(ExportFoosXlsxQuery(filter=_to_filter(body)))
    filename = _export_filename("xlsx")
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Rules:

- **Return annotation: `-> StreamingResponse`.** No `response_model` — FastAPI does not serialize the body.
- `StreamingResponse(iter([bytes]), media_type=..., headers={...})` is the canonical shape. `iter([data])` wraps already-materialized bytes in a single-chunk iterator. If the handler produces a true `AsyncIterator[bytes]`, pass it directly without `iter([...])`.
- **`media_type` is the real content type** (xlsx / docx / pdf MIME). Don't use `application/octet-stream` for known formats — clients render based on this.
- `Content-Disposition: attachment; filename="..."` triggers download instead of inline. Filename is double-quoted; if you need RFC 5987 encoding for non-ASCII, document it inline — the default convention is ASCII timestamps.

### `_export_filename` helper

```python
def _export_filename(ext: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"myapp-foos-{ts}.{ext}"
```

- Module-level helper named `_<purpose>_filename`. Underscore-prefixed because it's private to the router module.
- UTC timestamp `YYYYMMDD-HHMMSS`, prefix `<project>-<resource>`, extension parameter. Reuse this exact shape across routers — clients' file managers sort and dedupe based on it.
- Filename construction lives in the route, not the handler. The handler returns content; the route names the artifact.

### CORS `expose_headers`

`Content-Disposition` is not in the default CORS-exposed headers, so browsers strip it from the response visible to JS. The CORS middleware in `restapi/main.py` already lists it:

```python
expose_headers=["Content-Disposition"],
```

If a new download route exposes a different non-default header (e.g. `X-Total-Count`), append it to `expose_headers`. **Verify this list whenever you add a new headered response.**

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
- Spec adds a download response header beyond `Content-Disposition` without updating CORS `expose_headers` → stop, update both in the same change.
