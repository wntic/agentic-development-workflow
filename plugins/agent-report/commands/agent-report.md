---
description: "Analyze a Claude Code session — the main/orchestrator log AND the subagents it spawned: which ran, how long, tool activity, and blockers (denied/rejected tool calls) — into structured Markdown, optionally bundled with raw transcripts"
argument-hint: "[session|latest|all] [--include-main|--main-only] [--raw] [--out DIR] [--blob-cap N]"
---

# /agent-report [session] [scope-flags]

Generate a structured Markdown report of a Claude Code session: the **main/orchestrator
session** and/or the **subagents it spawned** — which ran and how many, execution time
(including per-resume segments), tool-call activity, and — the point of the exercise —
every **bottleneck and blocker** (denied or rejected tool calls, errored results, stop
reasons). Optionally archives the **raw JSONL** transcripts too, for later deep analysis.

`$ARGUMENTS` (all optional; pass a session selector and/or flags):
- session: empty or `latest` → most recent session; a session id / unique prefix; or `all`.
- `--include-main` → also render the main/orchestrator transcript (not just subagents).
- `--main-only` → render ONLY the main session (use when you want "what the main session did").
- `--raw` → also copy the source `.jsonl` into `<out>/raw/` (full-fidelity archive).
- `--out DIR` → write to DIR (e.g. to build one consolidated bundle).
- `--blob-cap N` → cap chars per tool input/result in the full log (default 6000; `0` = unabridged).

## What to do

1. Decide scope from the request. Default is subagents of the latest session. If the user
   wants the main session or a full archive, add the flags. Run the analyzer (it derives the
   project from `--cwd`):

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_report.py" --cwd "$PWD" --session "${ARGUMENTS:-latest}"
   ```

   It reads `~/.claude/projects/<slug>/<session>.jsonl` (main) and
   `~/.claude/projects/<slug>/<session>/subagents/agent-*.jsonl` (subagents), writing to
   `~/.claude/projects/<slug>/agent-reports/<session>/` (or `--out`):
   - `SUMMARY.md` — (1) which agents ran + counts, (2) execution time (`span` = first→last
     incl. idle waits between resumes; `active` = Σ per-segment compute), (3) blockers —
     denials with their reason and errored results with the line that failed — plus tool-call
     distribution and stop reasons, (4) **what the run produced**: every file written or
     edited, by which agents, with a churn flag, and (5) the **toolchain timeline**: every
     test/type-check/lint run in order, with the tool's own verdict line and red/green.
   - `log-<type>-<id>.md` — full readable log per agent/session (every instruction, assistant
     turn, tool call + input, tool result, each `⛔ TOOL DENIED` marker + reason).
   - `raw/*.jsonl` — the source transcripts, when `--raw` is given.

   Output lives **outside** the repo working tree on purpose, so it never dirties the working
   tree of whatever project you are in (some workflows require a clean tree to proceed).

   **Full archive for later analysis** (main session + its subagents + raw), e.g.:
   ```
   B=~/.claude/projects/<slug>/agent-reports/BUNDLE-<label>
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_report.py" --cwd "$PWD" --session <id> --main-only --raw --out "$B/orchestrator"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_report.py" --cwd "$PWD" --session <sub-session> --include-main --raw --out "$B/subagents"
   ```
   (A conversation resumed as a background job may split across two session ids — the fuller
   main narrative and the subagents' parent session can differ; bundle both.)

2. Read the generated `SUMMARY.md` and relay: the output directory path, the roster with
   counts and active time, the blockers found (agent, tool, denial kind, reason), **what the
   run produced** (the churned files especially — a file three agents rewrote is where the run
   struggled), and **how the toolchain moved** (how many reds, and whether each went green
   inside its own dispatch or only after a later one). Point the user at the `log-*.md` (and
   `raw/`) for full transcripts.

3. Say plainly what the report cannot answer. It measures the run, not the code: a clean
   roster and a green timeline mean the cycle worked, not that what it wrote is any good.
   If the user is asking about quality, read the diff of the files in section 4 and say
   what is actually in them — the report's job is to point at the code, not to stand in
   for reading it.

4. If nothing is found for the scope, say so plainly.

## Notes
- If the analyzer path above came through unexpanded (a `python3: can't open file '/scripts/…'`
  error), locate the installed script instead:
  `ls ~/.claude/plugins/cache/*/agent-report/*/scripts/agent_report.py`
- Some projects run a Bash-guard hook that false-positives on the literal string
  `.claude/tools` or `.claude/plugins` in a compound command with a write verb (`rm`/`mkdir`);
  if denied, run the `mkdir` and the analyzer as separate Bash calls.
- A resumed agent (continued via SendMessage) shows one segment per resume; a long `span`
  with a small `active` means it sat idle waiting for the orchestrator, not computing.
- The analyzer is stdlib-only Python; it reads transcripts and writes Markdown, nothing else.
  Fork the repo and edit `scripts/agent_report.py` to change what the report extracts.
