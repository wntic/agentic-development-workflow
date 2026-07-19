# Questions for the BA — Epic 02 Meetings

Product questions only — decisions for the product owner / BA. Architecture questions are not here
(they stay in `epic.md` under "Raised for the architect"). Answer inline under each question; leave
everything else as-is. When every answer is filled, re-run `/refine-usecases 02-meetings` to fold them
into the refined use cases.

## Q1 · Quota unit — UC-12
- **From**: "Plans cap usage per month, but **by what unit?** Product wanted "minutes of audio per month", but we don't know a recording's duration until it's transcribed (UC-13) ... So for v1 we propose counting **number of meetings created this calendar month** ... **TBD, revisit when we have duration earlier in the pipeline.**"
- **Question**: For v1, do we cap usage by **number of meetings created in the calendar month** (the proposed workaround, since audio duration isn't known until after processing)? Or do you need a different unit for v1?
- **Answer**: Yes — v1 caps by **number of meetings created in the calendar month** (per the user's workspace plan). Count resets at the start of each calendar month (UTC month boundaries for v1 — per-workspace timezone is out of scope). Minutes-of-audio is the eventual target but is deferred until duration is known earlier in the pipeline; the cap is checked **before** the upload is stored (UC-12).

## Q2 · Max file size and accepted audio formats — UC-12
- **From**: "**A4**: File too large or wrong format. **TBD with product** — max size and accepted formats aren't finalized (we floated 500 MB and wav/mp3/m4a). For v1 assume the platform's request-size middleware caps it and we don't sniff format yet."
- **Question**: What is the maximum upload size, and which audio formats do we accept for v1 (floated: 500 MB; wav/mp3/m4a)? Is it acceptable that v1 relies on a general request-size limit and does **not** validate/sniff the file format, or must we enforce an explicit allowed-formats list?
- **Answer**: **Max size 500 MB**, enforced by the platform's request-size middleware (an over-limit upload is rejected with 413; the value is config, not hard-coded). For v1 we do **not** sniff or validate the format — no allowed-formats list, no magic-byte check. If a non-audio or unsupported file is uploaded, transcription simply fails downstream (UC-13 → FAILED, see Q5), which is acceptable for v1. An explicit allowed-formats list (wav/mp3/m4a) is a fast-follow once we see real misuse.

## Q3 · Explicit vs. automatic processing trigger — UC-12 / UC-13
- **From** (UC-12 Notes): "We discussed kicking off processing automatically — **deferred**, the client calls UC-13 explicitly for v1."
- **From** (UC-13 Description): "For v1 this is a **synchronous** operation the client triggers explicitly after upload ... **Flag for an async UC.**"
- **Question**: Confirm the v1 behavior: after a successful upload, processing is **not** started automatically — the client makes a separate, explicit call to start it. (We are only confirming the v1 product scope here; whether processing later becomes automatic/async is a future UC.)
- **Answer**: Confirmed — upload (UC-12) and processing (UC-13) are **two separate, explicit calls** in v1. Upload only stores the recording and creates the meeting in UPLOADED; the client then explicitly triggers processing. Auto-kickoff and async/background processing are firmly deferred to a future UC.

## Q4 · Re-processing an already-READY meeting — UC-13
- **From**: "**A2**: The meeting is already READY (already processed). **TBD** — re-process and overwrite, or refuse? For v1 we propose refusing unless it's in FAILED (retry). Confirm with product."
- **Question**: If a user triggers processing on a meeting that is already READY, should the system **refuse** (the proposed v1 behavior — only FAILED meetings may be re-processed as a retry), or should it **re-process and overwrite** the existing summary, transcript, and action items?
- **Answer**: **Refuse.** Only meetings in UPLOADED (first run) or FAILED (retry) may be processed. Triggering processing on a READY meeting is a validation error (nothing is overwritten) — we don't want to silently destroy an existing summary/transcript/action items, and re-summarizing on demand isn't a v1 need. Overwrite/re-process-on-demand is a future UC if customers ask.

## Q5 · Empty / silent transcription outcome — UC-13
- **From**: "**A4**: Transcription returns empty (silent/corrupt audio). **TBD** — treat as FAILED, or READY with an empty summary? Lean FAILED for v1."
- **Question**: When transcription comes back empty (e.g. silent or corrupt audio), should the meeting be marked **FAILED** (the lean — the user can re-upload/retry), or marked **READY with an empty summary**?
- **Answer**: **FAILED.** An empty transcription means we have nothing useful to show, so marking it READY with an empty summary would look like a successful-but-blank meeting and confuse the user. FAILED is honest and lets them retry (UC-13 retry path) or re-upload a better recording. This also covers the non-audio/unsupported-file case from Q2.

## Q6 · Default page size for the library — UC-14
- **From**: "**Default page size is TBD** — product said "20ish"; make it config-ish, not magic."
- **Question**: What default page size should the meeting library use when the client does not specify one (product floated ~20)? Confirm the number; it will be made configurable, not hard-coded.
- **Answer**: **20** is the default page size. Make it configurable (deployment config). Cap the client-supplied page size at a sane maximum (**100**) so a caller can't request an unbounded page — also config.

## Q7 · Out-of-range page behavior — UC-14
- **From**: "**A3**: An out-of-range page (past the end). **TBD** — empty page vs error; lean empty page."
- **Question**: If a user requests a page beyond the last page of results, should the system return an **empty page** (the lean — with total count, no error) or return an **error**?
- **Answer**: **Empty page**, not an error. Return an empty items list with the real `total` count so the client can tell it overshot and recompute. A page past the end is a normal navigation state, not a failure.

## Q8 · Default number of search results (top-k) — UC-15
- **From**: "**How many results** to return (top-k) — product floated "top 10", call it config."
- **Question**: How many search results should a content search return by default (product floated 10)? Confirm the number; it will be made configurable.
- **Answer**: **10** (top-k). Make it configurable (deployment config). This is the upper bound on results; with the Q9 relevance cutoff applied, a query may legitimately return fewer than 10 (or zero).

## Q9 · Similarity threshold for weak search matches — UC-15
- **From**: "Whether to apply a **similarity threshold** so weak matches are dropped (else every query returns 10 results even if none are relevant) — **TBD with ML**, lean toward a configurable threshold."
- **Question**: From a product standpoint: should a search that finds nothing genuinely relevant return **fewer or zero results** (by applying a relevance/similarity cutoff so weak matches are dropped), or is it acceptable for v1 to **always return up to the top-k matches** even when none are strongly relevant? (The exact cutoff value is an ML calibration detail — we only need the product-visible behavior here.)
- **Answer**: Apply a cutoff — a search with nothing genuinely relevant should return **fewer or zero results**, not 10 weak ones. Returning irrelevant matches erodes trust in search worse than an honest "no results". So: drop matches below a relevance threshold (an empty result set is a valid, non-error outcome — see Q10's empty-result handling). The threshold **value** is a config knob for ML to calibrate; the product-visible behavior is "only show what's actually relevant."

## Q10 · Search hitting a since-deleted meeting — UC-15
- **From**: "**A2**: A meeting matched in the vector index but its row was since deleted (race). **TBD** — skip it silently from the results; deletion isn't even a UC yet, so this is mostly theoretical."
- **Question**: Meeting deletion is not yet a v1 feature, so this is largely theoretical — but to confirm scope: if a search ever matches a meeting whose record no longer exists, is it acceptable to **silently skip it** from the results (no error shown to the user)?
- **Answer**: Yes — **silently skip** any matched meeting whose record no longer exists; never surface an error to the user for it. A search hit pointing at a missing row is an internal consistency gap, not something the searcher did wrong. (Deletion isn't a v1 feature, so this is defensive; it also covers the index-vs-row race generally.)
