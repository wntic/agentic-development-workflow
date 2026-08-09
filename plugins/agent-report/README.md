# agent-report

A Claude Code plugin that turns session transcripts into a report you can actually read.

Claude Code writes a JSONL transcript for every session and for every subagent it spawns. That
is the whole record of a run — but it is line-delimited JSON, and the interesting parts (which
agents ran, where the time went, which tool calls got denied) are scattered across thousands of
records. `/agent-report` reads those transcripts and emits structured Markdown: a summary plus
one full readable log per agent.

It is built for **bottleneck and blocker analysis** — the question "why did that run take
twenty minutes and what got in its way?"

## Install

```
/plugin marketplace add wntic/claude-agent-report
/plugin install agent-report@wntic-agent-report
```

Then restart the session (or `/plugin` → enable) and the `/agent-report` command is available.

Requires `python3` (3.10+, for the `X | None` type syntax). No pip packages, no network access.

## Use

```
/agent-report                      # subagents of the most recent session in this project
/agent-report latest --include-main # ...plus the main/orchestrator transcript
/agent-report --main-only          # only what the main session itself did
/agent-report 4f3c9a2b --raw       # a specific session id (or unique prefix), archive raw JSONL
/agent-report all                  # every session under this project
```

Flags, all optional:

| Flag | Effect |
|---|---|
| `--include-main` | Also render the main/orchestrator transcript, not just subagents. |
| `--main-only` | Render **only** the main session. |
| `--raw` | Copy the source `.jsonl` files into `<out>/raw/` for full-fidelity archiving. |
| `--out DIR` | Write somewhere else — useful for building one consolidated bundle. |
| `--blob-cap N` | Cap chars per tool input/result blob in the full logs (default `6000`, `0` = unabridged). Text and thinking are never capped. |

The script is also usable directly, outside Claude Code:

```bash
python3 scripts/agent_report.py --cwd "$PWD" --session latest --include-main
```

## What you get

Output goes to `~/.claude/projects/<project-slug>/agent-reports/<session>/` — deliberately
**outside** your repo, so a report never dirties the working tree of the project you were
analyzing.

**`SUMMARY.md`**

1. **Which agents ran** — one row per agent: type, short id, model, segment count, assistant
   turns, tool calls, output tokens, blocker count.
2. **Execution time** — `span` (first→last timestamp, *including* idle waits between resumes)
   versus `active` (Σ per-segment wall-clock, i.e. actual compute). A long span with a small
   active time means the agent sat waiting on its orchestrator, not working. Broken down
   per segment, where a segment is the initial dispatch or one `SendMessage` resume.
3. **Bottlenecks & blockers** — every denied or rejected tool call with its `toolDenialKind`
   and the reason text; errored tool results with **the line that failed**, not just a count,
   since an error an agent fixed inside its own dispatch is the cheapest evidence of where it
   struggled; and a table of stop reasons. Then the tool-call distribution across all agents.
4. **What the run produced** — every file written or edited, which agents touched it, how many
   write calls it took and how many chars of new text, sorted by edit count. A **churn** flag
   marks a file rewritten three or more times or touched by more than one agent: that is the
   run telling you where it fought, or where two roles met over the same file.
5. **Toolchain timeline** — every test, type-check and lint command the run invoked, in order,
   with the tool's own verdict line lifted verbatim and a red/green mark. Red→green inside one
   agent is self-correction; a red that survives into the next agent is rework. Reds are counted
   **per agent and never summed**: red from a test author, red from a reviewer and red from an
   adversarial pass mean different things — a check that goes red against a deliberately broken
   implementation is the suite working, not the run failing. A transcript does not separate
   those, so the report does not guess; it says who went red, and how often.

   One row is **one tool run, not one `Bash` call**, and `N check run(s)` counts rows. A chained
   call — `ruff check && mypy src`, `pytest tests; pytest -k new` — is several runs, so it
   becomes several rows, each with its own verdict and its own colour; one row can otherwise
   carry two outcomes that disagree behind a single mark. What is *not* a separator: a pipe
   (`pytest … | tail -20` is one run whose output was filtered), a redirect, and nothing at all
   — so **`make check` is one row**, one call and one green/red decision, showing the four
   summaries its output carries. Verdict lines are handed to rows by the order the runs ran in
   and by which tool's wording each line is, and by nothing else. A run whose verdict is not
   recognised says `_(no summary line matched)_` and keeps its row: an unrecognised outcome is
   reported as unrecognised, never filled in by inference.

Sections 4 and 5 exist because a roster and a stopwatch answer "did the cycle work", and that
is not the question anyone actually has. **The report still cannot judge the code** — it says
where the code is and how hard the run fought to get there. Read the diff of the files in
section 4 before concluding anything about quality.

**`log-<agent-type>-<id>.md`** — one per agent: every instruction, assistant turn, thinking
block (folded into `<details>`), tool call with its full input, every tool result, and each
`⛔ TOOL DENIED` marker inline where it happened.

**`raw/*.jsonl`** — the untouched source transcripts, when you pass `--raw`.

## How it reads a transcript

A few decisions worth knowing, since they determine what the numbers mean:

- **Segments.** A user record starts a new segment if it is the dispatch prompt, or a
  `SendMessage` resume (an `isMeta` message beginning `The coordinator sent a message…`).
  Tool-result carriers, interrupt markers, and attachments are not boundaries.
- **`active` excludes idle.** A segment's end is the last activity timestamp *inside* it, so
  the gap between finishing one segment and being resumed is never counted as compute.
- **Agent type** comes from the most common `attributionAgent` on the transcript's records.
- **Denials** are attributed to a tool by matching `tool_use_id` back to the `tool_use` block
  that requested it, so the report names the tool, not just the id.

## Privacy

The analyzer is read-only and offline: stdlib-only Python, no network calls, no telemetry. It
reads transcripts under `~/.claude/projects/` and writes Markdown next to them.

That Markdown contains **your transcripts** — prompts, code, tool inputs and outputs. Treat a
generated report, and especially a `--raw` bundle, as sensitive. Nothing is uploaded anywhere
by this plugin; if you share a report, that is on you.

## Layout

```
.claude-plugin/
  plugin.json          # the plugin manifest
  marketplace.json     # single-plugin marketplace, source "./"
commands/
  agent-report.md      # the /agent-report command
scripts/
  agent_report.py      # the analyzer (stdlib only)
```

The command locates the analyzer via `${CLAUDE_PLUGIN_ROOT}`, so it works from any install path.

## License

MIT — see [LICENSE](LICENSE).
