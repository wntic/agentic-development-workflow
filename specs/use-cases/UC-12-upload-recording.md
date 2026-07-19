# UC-12: Upload a meeting recording

**Actor**: Member, Admin (any signed-in user)
**Module**: Meetings / Upload

## Description

The core of MeetingMind: a user uploads an audio recording of a meeting, and the system stashes the
file and creates a meeting record that the AI pipeline (UC-13) will later enrich. This UC is just the
**ingest** half — get the bytes safely stored and a row created; transcription/summary happen in UC-13.

Storage is split deliberately: the raw audio is large and binary, so it goes to blob storage (S3 or
compatible), and only a reference (the blob key) plus metadata live in the relational database. The
team was firm that we must not end up with a database row pointing at a blob that failed to upload, or
a blob with no row — so the upload-then-record sequence has to undo the blob if the row write fails.

There's an unresolved quota question. Plans cap usage per month, but **by what unit?** Product wanted
"minutes of audio per month", but we don't know a recording's duration until it's transcribed (UC-13),
which happens after upload. So for v1 we propose counting **number of meetings created this calendar
month** against the plan's limit, checked at upload time. Product isn't thrilled (a 3-hour meeting and
a 2-minute one count the same) — **TBD, revisit when we have duration earlier in the pipeline.**

## Main flow

1. User picks an audio file and uploads it (multipart form: the file plus a title).
   - **File** (required, audio; an `UploadFile`).
   - **Title** (required, 3–200 chars after trimming).
2. System checks the workspace is within its monthly quota for its plan (see Business Rules + UC-11).
3. System uploads the audio bytes to blob storage and gets back a storage key.
4. System creates a meeting record: a fresh id, the title, the blob key, status **UPLOADED**, the
   uploader as `created_by`, and the workspace from the token. Duration/transcript/summary are empty
   until UC-13.
5. System returns the new meeting id (the client then triggers processing, UC-13).

## Alternative flows

- **A1**: The workspace is over its monthly quota. System refuses with a "quota exceeded" error
  (HTTP 402 Payment Required feels right, but **TBD** — could be 403). No blob is uploaded, no row.
- **A2**: The blob upload to storage fails. System surfaces an "upload failed" error; nothing is
  recorded (there's nothing to undo yet).
- **A3**: The blob uploaded but the database write then fails. System **deletes the just-uploaded
  blob** (so we don't leak an orphan) and surfaces the error. This compensating step is mandatory.
- **A4**: File too large or wrong format. **TBD with product** — max size and accepted formats aren't
  finalized (we floated 500 MB and wav/mp3/m4a). For v1 assume the platform's request-size middleware
  caps it and we don't sniff format yet.

## Business Rules

- The uploader's identity (`created_by`) and the `workspace_id` come from the authenticated token,
  never from the request body (the reporter-stamp rule, applies everywhere).
- A meeting always belongs to exactly one workspace; every later query is scoped by it.
- Quota is enforced at upload, by meeting count per calendar month per workspace, against the plan's
  limit (see Description's TBD). The per-tier numbers are deployment config, not hard-coded.
- No database row may reference a blob that isn't stored, and no stored blob may lack a row (A3).

## Notes

- The plan→limit numbers must be tunable from config (security/billing retune them without a deploy).
- Synchronous vs async: the upload returns as soon as the row is created; the heavy AI work is a
  separate call (UC-13). We discussed kicking off processing automatically — **deferred**, the client
  calls UC-13 explicitly for v1.
- Out of scope: resumable/chunked uploads, virus scanning. Flag for later.
