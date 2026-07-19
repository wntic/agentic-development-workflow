# Epic 02 — Meetings

**Module(s)**: Meetings / Upload, Meetings / Processing, Meetings / Library, Meetings / Search
**Member use cases**: UC-12, UC-13, UC-14, UC-15
**Status**: refined

## Scope

The core of MeetingMind: the lifecycle of a `Meeting` from raw audio to a searchable, summarized
record. A user uploads an audio recording — bytes to blob storage, a row to the relational DB, status
`UPLOADED` (UC-12). An explicit, synchronous processing pass transcribes the audio, summarizes it,
extracts action items, indexes the transcript in a vector store, and flips the meeting to `READY`
(UC-13). Users then browse a paged, structured-filtered library and open a meeting's detail (UC-14),
and run semantic content search over the indexed transcripts (UC-15). All four UCs mutate or read the
single `Meeting` aggregate (with its child `ActionItem`), which is why they form one epic; the polyglot
storage (Postgres + blob + vector store) is an infrastructure choice for the architect, not an
aggregate boundary.

## Backend filter

### UC-12 — Upload a meeting recording
- **Backend**: multipart upload — `file` (audio `UploadFile`) + `title` (3–200 chars, trimmed);
  enforce the workspace's monthly quota *by meeting count per calendar month* against the plan limit,
  checked at upload (config-tunable per-tier numbers); upload bytes to blob storage → get a key; create
  a `Meeting` (fresh id, title, blob key, status `UPLOADED`, `created_by` + `workspace_id` from the
  token); return the new meeting id; **compensating transaction** — if the DB write fails after the
  blob upload, delete the just-uploaded blob (no orphan blob, no row pointing at a missing blob);
  quota-exceeded refused with no blob and no row; `created_by`/`workspace_id` never from the request
  body.
- **Dropped (UI only)**: "user picks an audio file", "the client then triggers processing".
- **Raised as question**: quota *unit* (meetings vs minutes — A1/Description); HTTP code for quota
  exceeded (402 vs 403 — A1, flagged for the architect); max file size + accepted formats (A4).

### UC-13 — Process a recording into a summary and action items
- **Backend**: load a meeting the caller owns (tenant-scoped); must be `UPLOADED` (or `FAILED` for
  retry); mark `PROCESSING`; fetch audio by stored key; transcribe (capability), summarize +
  extract action-item titles in one round-trip (capability returns summary text + zero-or-more titles),
  embed the transcript and index it tenant-scoped in the vector store (capability); on success set
  `READY`, store summary + transcript, create one `ActionItem` per title (status `OPEN`, linked to the
  meeting); on any AI-step failure mark `FAILED` and surface a processing error (no partial summary);
  404 for cross-tenant / missing meeting (indistinguishable); lifecycle `UPLOADED → PROCESSING → READY`
  with `→ FAILED` from `PROCESSING` and retry `FAILED → PROCESSING` (no rigid state-machine guard table
  in v1); action items created only by this pipeline in v1.
- **Dropped (UI only)**: "the user hits process and waits".
- **Raised as question**: re-process an already-`READY` meeting — refuse or overwrite (A2); empty
  transcription → `FAILED` or `READY`-with-empty-summary (A4); embedding chunking strategy (Description,
  ML — v1 = one vector per transcript); the **two-store partial-failure** policy (flagged for the
  architect).

### UC-14 — Browse and open meetings
- **Backend**: list read — optional filters: `status` (multi-valued over UPLOADED/PROCESSING/READY/
  FAILED), `created after`/`created before` dates, `sort` (newest-first default, or title A–Z from a
  closed set), pagination (page/size); return matching meetings for the token's workspace, paged, with
  the total count; each row = id, title, status, created-at, created-by, action-item count; detail read
  by id — full meeting (id, title, status, created-at, created-by, summary, list of action items each
  id/title/status); every read tenant-scoped to the token's `workspace_id`; 404 for cross-tenant /
  missing on detail; empty page (total 0) is not an error.
- **Dropped (UI only)**: "the home screen", "render pagination", "lands on the library".
- **Raised as question**: default page size ("~20", config — Description); out-of-range page → empty
  vs error (A3, lean empty).

### UC-15 — Search meetings by content
- **Backend**: embed the free-text query; search the workspace's vector index for the most-similar
  transcripts (top-k), getting meeting ids + similarity scores; load those meetings and return them
  ranked best-first (each = meeting id, title, status, similarity score); tenant-scoped — index queried
  with the token's `workspace_id`; only `READY` meetings are indexed and thus matchable; empty result
  is not an error; reject empty/whitespace query with a validation error (don't embed empty text).
- **Dropped (UI only)**: "the user types a query" (presentation framing).
- **Raised as question**: top-k default ("top 10", config); whether to apply a similarity threshold to
  drop weak matches (ML, lean configurable threshold); deleted-row-race skip (A2, theoretical).

## Aggregates touched (grouping rationale, not a design)

- UC-12: creates `Meeting` (+ blob reference); reads `Workspace.plan` for quota.
- UC-13: mutates `Meeting` (status, summary, transcript); creates child `ActionItem`s; writes a vector
  index entry.
- UC-14: reads `Meeting` + its `ActionItem`s (list + detail).
- UC-15: reads `Meeting` via the vector index.

A single `Meeting` aggregate with a child `ActionItem`, plus a `MeetingStatus` enum, runs through all
four UCs — the connectedness that clusters them. Storage is polyglot (relational + blob + vector); the
architect owns the bounded-context split and the store modeling.

## Cross-epic edges (candidates)

- **→ Accounts** (Epic 01): every UC is tenant-scoped by the token's `workspace_id` and stamps
  `created_by` from the token's `user_id`; UC-12's quota check reads `Workspace.plan`. Notation
  hypothesis: `accounts:IWorkspaceRepository` (plan lookup), `accounts:IUserRepository` / `accounts:Role`
  (identity + authorization). The architect formalizes the notation and decides whether the quota read
  crosses contexts or is denormalized.

## Open product questions (seeds for refinement)

- **UC-12 Description/A1** — quota unit: confirm v1 counts *number of meetings created this calendar
  month* (vs minutes of audio, which needs duration only known after processing).
- **UC-12 A4** — max file size and accepted audio formats (floated 500 MB, wav/mp3/m4a; v1 leans on the
  request-size middleware, no format sniffing).
- **UC-13 A2** — re-processing an already-`READY` meeting: refuse (lean) or re-process and overwrite?
- **UC-13 A4** — empty/silent transcription: mark `FAILED` (lean) or `READY` with an empty summary?
- **UC-14 Description** — default page size (product said "20ish"; make it config).
- **UC-14 A3** — out-of-range page: empty page (lean) or error?
- **UC-15 Description** — default top-k (product floated 10; config).
- **UC-15 Description** — apply a similarity threshold to drop weak matches? (ML, lean configurable).

### Raised for the architect (not the BA)
- **UC-12 A1** — HTTP status for quota exceeded (402 Payment Required vs 403) — API-contract choice.
- **UC-13 Description/A3/Notes** — two-store partial failure (Postgres row + vector index) with no
  distributed transaction; proposed v1 = mark `FAILED` on any failure, retry may re-index. Architect to
  confirm.
- **UC-13 Description** — embedding chunking strategy (v1 = whole transcript as one vector; long-
  recording chunking a later refinement).
