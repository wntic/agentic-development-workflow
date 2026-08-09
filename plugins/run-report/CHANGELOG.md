# Changelog

## 2.0.0

The name said "a report about an agent". The thing reports on a **run** — which agents ran,
where the time went, what got written, what got in the way — so it is now `run-report`, and it
ships from the `wntic-adw` marketplace alongside the workflow it was built to watch. The
single-plugin marketplace it used to come from is retired.

If you are on 1.1.2, three things change and none of them migrate themselves:

```
/plugin marketplace add wntic/agentic-development-workflow
/plugin uninstall agent-report@wntic-agent-report
/plugin install run-report@wntic-adw
```

- **The command is `/run-report`.** `/agent-report` is gone, and the old plugin id does not
  resolve against the new marketplace — it fails with `Plugin agent-report not found`.
- **The analyzer is `scripts/run_report.py`.** Only matters if you invoke it directly rather
  than through the command.
- **Reports land in `~/.claude/projects/<slug>/run-reports/<session>/`.** Bundles written
  before this release stay under `agent-reports/`; nothing moves them and new ones do not mix
  in with them, so look in the old directory for old runs.

The plugin also stops shipping its own `LICENSE`, `.gitignore` and marketplace manifest — those
belonged to the repository it used to be, not to a plugin. Licensing is unchanged (MIT); the
file now lives at the marketplace repository's root and covers everything there.

**What the report contains did not change.** The sections, the numbers and their meanings are
exactly 1.1.2's. This release is the rename and nothing else.

## 1.1.2

The toolchain timeline counted `Bash` calls and called them check runs. On a real run one row
read `🔴 9 failed, 5 passed in 8.34s; 3 failed, 22 passed in 7.42s` — one call with two `pytest`
runs inside it — so the count was low wherever an agent chained commands, and a single colour
stood for two different outcomes.

- **One row per tool run.** A call chained with `;` or `&&` becomes one row per run, each with
  its own verdict line and its own mark. `N check run(s)` counts rows. On a saved six-agent run
  the figure went from 42 to 58.
- **A pipeline, a redirect and a plain command are still one run.** `pytest … | tail -20` is one
  run whose output was filtered, and `make check` is one row — one call, one process, one
  green/red decision — showing the four tool summaries its output carries.
- **Verdict lines go to rows by the order the runs ran in and by which tool's wording the line
  is** — mypy counts the files it checked, ruff does not, and a sentence either could have
  written claims neither. Nothing here reads the agent or the role.
- **A run with no recognised verdict keeps its row** and says `_(no summary line matched)_`.
  Splitting surfaced two such runs the old single row had hidden behind a neighbour's green.

## 1.1.1

The toolchain timeline no longer prints one total of red checks. On a real run, a third of the
reds were an adversarial pass catching deliberately broken implementations — successes — and the
single number read as "this run went badly" while saying the opposite of the truth; the person
reading the report had to explain the figure by hand.

- **Reds are broken out by agent** in the "Toolchain timeline" header: how many check runs each
  agent made and how many of those were red. The run-wide "M of them red" is gone. The total run
  count stays — it distorts nothing.
- No guessing by agent name. Nothing in a transcript separates a check red against a deliberately
  broken implementation from a check red against a real defect, so the report says who went red
  and leaves the reading to the reader.
- Per-row 🔴/🟢 marks and verbatim verdict lines are unchanged.

## 1.1.0

The report stopped answering only "did the cycle work" and started saying what the run put on
disk. A roster and a stopwatch tell you the machinery ran; they say nothing about the output,
and that is the question people actually bring to a run report.

- **What the run produced** — a new SUMMARY section: every file written or edited, by which
  agents, with write-call counts and chars of new text. A churn flag marks a file rewritten
  three or more times or touched by more than one agent.
- **Toolchain timeline** — a new SUMMARY section: every pytest / mypy / ruff / make check /
  jest / cargo / go test invocation in chronological order, with the tool's own verdict line
  lifted verbatim and a red/green mark, so a run's red→green trajectory is readable at a glance.
- **Errored tool results now show what failed**, not just how many there were.
- Roster gains a `files` column; paths are shown relative to the project, and scratchpad work
  is marked `<scratch>/` rather than passed off as part of the output.
- The report says out loud what it cannot do: it points at the code, it does not judge it.

## 1.0.0

First release as a plugin. Previously a personal `~/.claude/commands/agent-report.md` plus
`~/.claude/tools/agent_report.py`; packaged here so it installs from a marketplace and the
command finds its analyzer via `${CLAUDE_PLUGIN_ROOT}` instead of a hardcoded home path.

- `/agent-report` — session roster, per-segment execution time, tool-call distribution,
  denied/errored tool calls, stop reasons.
- Scope flags: `--include-main`, `--main-only`, `--raw`, `--out`, `--blob-cap`.
- Session selectors: `latest` (default), a session id or unique prefix, or `all`.
