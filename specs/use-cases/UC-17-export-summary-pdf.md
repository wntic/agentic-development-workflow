# UC-17: Export a meeting summary as a PDF

**Actor**: Member, Admin (any signed-in user)
**Module**: Meetings / Export

## Description

Users want to share a meeting's outcome with people who aren't in MeetingMind — so they need to
download the summary and action items as a self-contained file. This UC adds a "Download PDF" action on
a processed meeting: the system renders the meeting's summary and its action items into a PDF and
streams it back as a file download.

This is a new capability for the system — it's never produced a binary document before. The rendering
is behind an interface (so the PDF library is swappable), and the endpoint streams the bytes back with
the right content type and a download filename, rather than returning JSON.

Format is **TBD with design** — for v1 a plain, unbranded layout (title, date, summary prose, then a
checklist of action items with their status) is fine; branded templates are later. Whether to include
the **full transcript** in the export was debated — decided **no** for v1 (summaries are shareable,
raw transcripts are noisy and sometimes sensitive). Revisit if customers ask.

## Main flow

1. User clicks "Download PDF" on a READY meeting (by meeting id).
2. System loads the meeting and its action items (must be in the caller's workspace, must be READY).
3. System renders a PDF document: the title, created date, the summary text, and the list of action
   items (each with its title and OPEN/DONE status).
4. System streams the PDF back as a file download (content type `application/pdf`, a
   `Content-Disposition: attachment` filename derived from the title).

## Alternative flows

- **A1**: The meeting id doesn't exist or is in another workspace. System returns 404.
- **A2**: The meeting isn't READY yet (still UPLOADED/PROCESSING, or FAILED — no summary to export).
  System refuses with a validation error ("nothing to export yet"). **TBD** — 409 vs 422; lean 422.
- **A3**: PDF rendering fails (a rendering-library error). System surfaces a 500-ish error; nothing is
  streamed.

## Business Rules

- Only a READY meeting (one with a summary) can be exported.
- Tenant-scoped: you can only export a meeting in your workspace.
- The export contains the summary + action items, **not** the raw transcript (v1 decision).

## Notes

- New capability: render a PDF (behind an interface, library swappable — we floated WeasyPrint /
  ReportLab, **TBD**).
- This is a streaming binary download, unlike every other endpoint which returns JSON — the response
  is the file bytes with a download disposition.
- Out of scope: branded templates, including the transcript, other formats (docx/markdown). Later UCs.
