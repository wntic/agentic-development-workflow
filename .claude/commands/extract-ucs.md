---
description: "Stage 1 — Extract use cases from a PDF into specs/use-cases/UC-NNN.md"
argument-hint: <pdf-path>
---

Use the `uc-extractor` agent on the PDF at: $ARGUMENTS

If $ARGUMENTS is empty, stop and ask which PDF to extract from (the default location is `specs/use-cases.pdf`).

After the agent finishes, summarize its report (files created, files flagged, anomalies) in one short paragraph.
