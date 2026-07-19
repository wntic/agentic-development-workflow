# UC-15: Search meetings by content

**Actor**: Member, Admin (any signed-in user)
**Module**: Meetings / Search

## Description

Beyond the structured library filters (UC-14), users want to ask "which meeting was that where we
talked about the Q3 pricing change?" — semantic search over what was actually *said*, not just titles.
This is why UC-13 embeds each transcript into a vector store: a search query is embedded the same way
and matched by similarity against the workspace's indexed transcripts.

The user types a natural-language query; the system embeds it, finds the most similar meeting
transcripts in the workspace, and returns those meetings ranked by relevance. It's a discovery tool,
not an exact-match filter.

A few things are unsettled. **How many results** to return (top-k) — product floated "top 10", call it
config. Whether to apply a **similarity threshold** so weak matches are dropped (else every query
returns 10 results even if none are relevant) — **TBD with ML**, lean toward a configurable threshold.
And whether to eventually do **hybrid** (semantic + keyword) search — out of scope for v1, semantic
only. Discuss with ML team.

## Main flow

1. User types a search query (free text).
2. System embeds the query text into a vector.
3. System searches the workspace's vector index for the most similar transcripts (top-k), getting back
   meeting ids and similarity scores.
4. System loads those meetings and returns them ranked best-first: each result carries the meeting id,
   title, status, and the similarity score.

## Alternative flows

- **A1**: Nothing is similar (or the workspace has no indexed meetings yet). System returns an empty
  result list — not an error.
- **A2**: A meeting matched in the vector index but its row was since deleted (race). **TBD** — skip
  it silently from the results; deletion isn't even a UC yet, so this is mostly theoretical.
- **A3**: The query is empty/whitespace. System rejects with a validation error (don't embed empty
  text).

## Business Rules

- Search is tenant-scoped: the vector index is queried with the token's `workspace_id`, so results
  never cross workspaces (the index entries were written tenant-scoped in UC-13).
- Results are ranked by similarity, best first; a configurable top-k bounds the count.
- Only READY meetings have transcripts indexed, so only they can match (UPLOADED/PROCESSING/FAILED
  were never indexed).

## Notes

- top-k and the optional similarity threshold are config, not hard-coded (see Description TBDs).
- This read hits the vector store (a client-style store), not the relational filter path of UC-14 —
  they're deliberately different mechanisms.
- Out of scope: hybrid search, highlighting the matching passage, search-within-a-meeting. Later UCs.
