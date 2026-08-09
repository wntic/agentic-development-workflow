#!/usr/bin/env python3
"""run_report.py — analyze Claude Code subagent transcripts for a project/session.

Reads the JSONL transcripts Claude Code writes for every spawned subagent
(`~/.claude/projects/<project-slug>/<session>/subagents/agent-*.jsonl`) and emits
structured Markdown: a SUMMARY.md (which agents ran, how many, execution time, tool
activity, blockers) plus one full readable log per agent.

Designed for bottleneck/blocker analysis: it surfaces every denied or rejected tool
call (`toolDenialKind`), errored tool results, stop reasons, and per-segment timing
(a resumed agent — continued via SendMessage — shows each resume as its own segment
with its own wall-clock, so idle gaps between resumes are not mistaken for compute).

Usage:
    run_report.py [--project-dir DIR] [--session ID|latest|all]
                  [--out DIR] [--blob-cap N] [--cwd PATH]

  --project-dir  the ~/.claude/projects/<slug> dir. Default: derived from --cwd.
  --cwd          working dir used to derive the project slug (default: $PWD).
  --session      a session id, "latest" (most recent session that has subagents,
                 default), or "all" (every session under the project).
  --out          output dir for the Markdown. Default: <project-dir>/run-reports/<session>.
                 Kept OUTSIDE the repo working tree on purpose so it never dirties the
                 working tree of the project being analyzed.
  --blob-cap     max chars rendered per tool input/result blob in the full log
                 (default 6000; 0 = unlimited). Text/thinking are never capped.

Stdlib only. Prints the output paths it wrote.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Tools that put bytes on disk, and where each keeps the path and the new text.
WRITE_TOOLS = {"Write": "content", "Edit": "new_string", "MultiEdit": None, "NotebookEdit": "new_source"}

# A Bash command that runs the project's checks. Matching is deliberately loose —
# a run's own toolchain is whatever it invokes, and missing one is worse than an
# extra row in the timeline.
CHECK_CMD = re.compile(
    r"\b(pytest|mypy|ruff|make\s+(?:check|test|lint)|tox|nox|"
    r"npm\s+(?:test|run\s+(?:test|lint|typecheck))|yarn\s+test|pnpm\s+test|"
    r"jest|vitest|eslint|tsc\b|cargo\s+(?:test|clippy|check)|go\s+(?:test|vet))\b"
)

# …but a commit message that quotes "make check green" is not a check. Commands whose
# runner match lives inside prose are dropped rather than mis-colouring the timeline.
# …and neither is a search over source that happens to contain the runner's name:
# `grep -rn "pytest.mark.ac(" tests/` reads code, it does not run it.
NOT_A_CHECK = re.compile(
    r"^git\b|\bgit\s+(?:commit|tag|notes)\b|^echo\b|^cat\s*<<|"
    r"^(?:grep|rg|ag|sed|awk|find|ls|cat|head|tail|wc|diff)\b"
)

# Verdict lines worth lifting out of a check's output, as (regex, tone, tier, printer).
# Tier 1 is a tool's own summary — one line that stands for the whole run. Tier 2 is a
# single failing item, useful only when no summary was printed (a `| tail -5` that cut it
# off, a `-x` that stopped early). A run with a summary shows the summary and nothing
# else, so one truncated pytest call cannot fill the table with test ids.
# `printer` names the tool whose wording the line is, and exists for one purpose: handing
# each run of a chained command its own verdict. Where two tools print the same sentence
# ("Found 3 errors" is both ruff and mypy) the printer is None and the line fits anywhere.
VERDICT_PATTERNS = [
    (re.compile(r"^=+.*\b\d+\s+(?:passed|failed|error|skipped).*=+$"), None, 1, "pytest"),
    (re.compile(r"^Success: no issues found in \d+ source files?"), "green", 1, "mypy"),
    (re.compile(r"^All checks passed!"), "green", 1, "ruff-check"),
    # mypy counts the files it checked ("Found 3 errors in 1 file (checked 62 source
    # files)"); ruff says only "Found 3 errors." — so the longer shape names its printer
    # and the bare one, which either tool may have written, claims neither.
    (re.compile(r"^Found\s+\d+\s+errors?\s+in\s+\d+\s+files?\b"), "red", 1, "mypy"),
    (re.compile(r"^Found\s+(\d+)\s+errors?\b"), "red", 1, None),
    (re.compile(r"^\d+\s+files? (?:already formatted|left unchanged)"), "green", 1, "ruff-format"),
    (re.compile(r"^\d+\s+files? reformatted"), None, 1, "ruff-format"),
    (re.compile(r"\b\d+\s+failed\b"), "red", 1, "pytest"),
    (re.compile(r"\b\d+\s+passed\b"), "green", 1, "pytest"),
    (re.compile(r"^(?:FAILED|ERROR)\b"), "red", 2, "pytest"),
    (re.compile(r"^\s*E\s+\w*(?:Error|Exception)\b"), "red", 2, "pytest"),
]

# The runner a command invokes, in the same vocabulary as the printers above. A wrapper
# drives several tools and so claims none of them: `make check` is ONE run — one call, one
# process, one green/red decision — whose output carries four tools' summaries, and it
# accepts all of them rather than being split four ways.
RUN_TOOLS = [
    (re.compile(r"\bruff\s+format\b"), "ruff-format"),
    (re.compile(r"\bruff\b"), "ruff-check"),
    (re.compile(r"\b(?:pytest|jest|vitest)\b"), "pytest"),
    (re.compile(r"\b(?:mypy|tsc)\b"), "mypy"),
]


def _slug_for(cwd: str) -> str:
    """~/.claude/projects encodes a project by its abs path with '/'→'-'."""
    return "-" + cwd.strip("/").replace("/", "-")


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _blocks(content):
    return content if isinstance(content, list) else []


def load(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


COORDINATOR_PREFIX = "The coordinator sent a message"


def is_instruction(rec: dict) -> bool:
    """A user record that starts a segment: the initial dispatch prompt, or a
    SendMessage resume. Resumes arrive as isMeta user messages beginning with
    "The coordinator sent a message while you were working:". Tool-result carriers,
    interrupt markers, and attachments are not boundaries."""
    if rec.get("type") != "user":
        return False
    txt = _text_of(rec.get("message", {}).get("content")).strip()
    if not txt or txt.startswith("[Request interrupted"):
        return False
    if rec.get("isMeta"):
        return txt.startswith(COORDINATOR_PREFIX)  # a SendMessage resume
    if rec.get("toolUseResult") is not None:
        return False
    return True  # a non-meta dispatch prompt


def _written_paths(name: str, inp: dict) -> list[tuple[str, int]]:
    """(path, chars written) for one write-ish tool call. Chars are the NEW text
    only — an Edit that replaces two lines counts two lines, not the whole file."""
    if name not in WRITE_TOOLS or not isinstance(inp, dict):
        return []
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return []
    if name == "MultiEdit":
        edits = inp.get("edits") or []
        n = sum(len(str(e.get("new_string", ""))) for e in edits if isinstance(e, dict))
        return [(path, n)]
    field = WRITE_TOOLS[name]
    return [(path, len(str(inp.get(field, ""))))]


def _verdict_hits(text: str) -> list[dict]:
    """Every verdict line in a check's output, in the order it was printed, tagged with
    tone, tier and the tool that printed it. The tool's words are kept verbatim — this
    reports what the toolchain said, it does not re-judge it."""
    hits: list[dict] = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or len(ln) > 200:
            continue
        for pat, tone, tier, printer in VERDICT_PATTERNS:
            if not pat.search(ln):
                continue
            if tone is None:
                # A pytest banner carries its own verdict: "140 passed" is green,
                # "5 failed, 52 passed" is not, and the same line shape says both.
                low = ln.lower()
                tone = "red" if ("failed" in low or "error" in low) else ("green" if "passed" in low else None)
            hits.append({"line": ln, "tone": tone, "tier": tier, "printer": printer})
            break
    return hits


def _split_runs(cmd: str) -> list[str]:
    """One Bash call can be a chain of tool runs — `ruff check && mypy src`,
    `pytest tests; pytest -k new` — and each link is its own run with its own verdict.
    Split on top-level `;` and `&&`, keeping the links that are checks in their own right.

    What is deliberately NOT a separator: a pipe (`pytest … | tail -20` is one run whose
    output was filtered), a redirect (`2>&1` is not `&&`), and nothing at all — a command
    with no separator is one run however many tools it drives, which is what makes
    `make check` a single row. Quotes are respected, so a `-k "a or b"` filter survives.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(cmd):
                buf.append(cmd[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        if cmd[i : i + 2] == "&&":
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    runs = [p.strip() for p in parts if p.strip() and CHECK_CMD.search(p) and not NOT_A_CHECK.search(p.strip())]
    return runs or [cmd]


def _run_tool(cmd: str) -> str | None:
    for pat, tool in RUN_TOOLS:
        if pat.search(cmd):
            return tool
    return None


def _assign_verdicts(hits: list[dict], runs: list[str]) -> list[tuple[list[str], str]]:
    """Hand each run of a chain its own verdict lines and its own colour.

    A chain prints one blob of output, so attribution rests on two mechanical facts and
    nothing else: the order the runs ran in, and which tool's wording each line is. A
    summary line goes to the earliest run that could have printed it and does not have that
    tool's summary yet; a per-item line (tier 2) may repeat, so it stays with the run it
    landed on. A line no run claims stays with the current run rather than being dropped, and
    a line repeated inside one run's own share is shown once. A run left with nothing reports
    itself unmatched — an unrecognised verdict is reported as unrecognised, never filled in
    by inference.

    Nothing here looks at the agent, the role, or what the check was for.
    """
    n = len(runs)
    buckets: list[list[dict]] = [[] for _ in range(n)]
    if n == 1:
        buckets[0] = list(hits)
    else:
        tools = [_run_tool(c) for c in runs]
        cursor = 0
        for h in hits:
            target = None
            for k in range(cursor, n):
                if tools[k] is not None and h["printer"] is not None and tools[k] != h["printer"]:
                    continue
                if h["tier"] == 1 and any(x["tier"] == 1 and x["printer"] == h["printer"] for x in buckets[k]):
                    continue
                target = k
                break
            if target is None:
                target = min(cursor, n - 1)
            buckets[target].append(h)
            cursor = target
    out = []
    for bucket in buckets:
        seen: set[str] = set()
        bucket = [h for h in bucket if not (h["line"] in seen or seen.add(h["line"]))]
        tier1 = [h for h in bucket if h["tier"] == 1]
        shown = tier1[:4] if tier1 else [h for h in bucket if h["tier"] == 2][:2]
        colour = "?"
        if any(h["tone"] == "green" for h in bucket):
            colour = "green"
        if any(h["tone"] == "red" for h in bucket):
            colour = "red"
        out.append(([_clip(h["line"], 110) for h in shown], colour))
    return out


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _one_line(cmd: str, n: int = 110) -> str:
    """A shell command as one readable line, centred on the check itself. The first
    line alone would lie — a check is often the tail of a `mkdir … && cd … && uv run
    mypy` chain — and so would a plain head-truncation, which cuts the runner off."""
    flat = " ".join(cmd.split())
    m = CHECK_CMD.search(flat)
    if m and m.start() > 40:
        return "… " + _clip(flat[m.start() :], n - 2)
    return _clip(flat, n)


def _short_path(p: str, root: str | None) -> str:
    """Paths relative to the project when they are under it, and scratchpad work
    marked as such — a run's throwaway probe is not part of what it produced."""
    if "/scratchpad/" in p:
        return "<scratch>/" + p.rsplit("/scratchpad/", 1)[1]
    if root and p.startswith(root.rstrip("/") + "/"):
        return p[len(root.rstrip("/")) + 1 :]
    return p


def analyze(path: Path) -> dict:
    recs = load(path)
    agent_id = path.stem.replace("agent-", "")
    attribution = Counter()
    model = None
    effort = None
    tool_calls = Counter()
    denials = []  # {tool, kind, ts, prompt_text}
    errored_results = 0
    errors = []  # {tool, ts, line} — what actually failed, not just how often
    files = Counter()  # path -> write/edit calls
    file_chars = Counter()  # path -> chars of new text
    checks = []  # {ts, cmd, lines, colour} — the toolchain's own verdicts, in order
    cmd_by_id: dict[str, str] = {}  # tool_use_id -> Bash command, to pair with its result
    out_tokens = 0
    cache_read = 0
    cache_creation = 0
    stop_reasons = Counter()
    assistant_turns = 0
    all_ts = []
    segments = []  # {prompt, start, end, turns, tools:Counter, out_tokens, result_text, denials}
    cur = None

    # map tool_use_id -> tool name so we can attribute a denial/error to its tool
    tool_name_by_id: dict[str, str] = {}

    def close(seg):
        if seg is not None:
            segments.append(seg)

    for rec in recs:
        ts = _parse_ts(rec.get("timestamp"))
        if ts:
            all_ts.append(ts)
        if rec.get("attributionAgent"):
            attribution[rec["attributionAgent"]] += 1
        if rec.get("effort"):
            effort = rec["effort"]

        if is_instruction(rec):
            close(cur)
            cur = {
                "prompt": _text_of(rec["message"]["content"]).strip(),
                "start": ts,
                "end": ts,
                "turns": 0,
                "tools": Counter(),
                "out_tokens": 0,
                "result_text": "",
                "denials": [],
            }
        # segment end tracks the LAST activity ts within the segment, so idle waits
        # between a finished segment and the next resume are excluded from "active".
        elif cur is not None and ts is not None:
            cur["end"] = ts

        msg = rec.get("message")
        if isinstance(msg, dict):
            if msg.get("model"):
                model = msg["model"]
            if rec.get("type") == "assistant":
                assistant_turns += 1
                if cur:
                    cur["turns"] += 1
                usage = msg.get("usage") or {}
                ot = int(usage.get("output_tokens", 0) or 0)
                out_tokens += ot
                cache_read += int(usage.get("cache_read_input_tokens", 0) or 0)
                cache_creation += int(usage.get("cache_creation_input_tokens", 0) or 0)
                if cur:
                    cur["out_tokens"] += ot
                if msg.get("stop_reason"):
                    stop_reasons[msg["stop_reason"]] += 1
                txt = _text_of(msg.get("content"))
                if txt.strip() and cur is not None:
                    cur["result_text"] = txt.strip()
                for b in _blocks(msg.get("content")):
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = b.get("name", "?")
                        tool_calls[name] += 1
                        tool_name_by_id[b.get("id", "")] = name
                        if cur:
                            cur["tools"][name] += 1
                        inp = b.get("input") or {}
                        for fpath, nchars in _written_paths(name, inp):
                            files[fpath] += 1
                            file_chars[fpath] += nchars
                        if name == "Bash" and isinstance(inp, dict):
                            command = " ".join(str(inp.get("command", "")).split())
                            if CHECK_CMD.search(command) and not NOT_A_CHECK.search(command):
                                cmd_by_id[b.get("id", "")] = command

        # denial / rejection of a tool call, and errored tool results.
        kind = rec.get("toolDenialKind")
        content = msg.get("content") if isinstance(msg, dict) else None
        for b in _blocks(content):
            if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                continue
            tuid = b.get("tool_use_id", "")
            tool = tool_name_by_id.get(tuid, "?")
            body = b.get("content")
            reason = (body if isinstance(body, str) else _text_of(body)).strip().replace("\n", " ")
            if kind:
                d = {"tool": tool, "kind": kind, "ts": rec.get("timestamp"), "reason": reason[:160]}
                denials.append(d)
                if cur:
                    cur["denials"].append(d)
            elif b.get("is_error"):
                errored_results += 1
                errors.append({"tool": tool, "ts": rec.get("timestamp"), "line": reason[:200]})

            # A check's result: lift the toolchain's own verdict out of the output. One
            # call can be a chain of runs, and then it is one row per run — a chained
            # command otherwise hides runs from the count and puts two outcomes, which
            # may disagree, behind one colour.
            if tuid in cmd_by_id:
                body_text = body if isinstance(body, str) else _text_of(body)
                runs = _split_runs(cmd_by_id.pop(tuid))
                verdicts = _assign_verdicts(_verdict_hits(body_text), runs)
                rows = [
                    {"ts": rec.get("timestamp"), "cmd": _one_line(run), "lines": lines, "colour": colour}
                    for run, (lines, colour) in zip(runs, verdicts)
                ]
                # A non-zero exit says the chain failed, not which link did. The shell's
                # status is the last command that ran, so the red goes there — and only
                # when no run said red itself.
                if b.get("is_error") and rows and not any(r["colour"] == "red" for r in rows):
                    rows[-1]["colour"] = "red"
                checks.extend(rows)

    close(cur)

    start = min(all_ts) if all_ts else None
    end = max(all_ts) if all_ts else None
    span = (end - start).total_seconds() if start and end else 0.0
    active = sum((s["end"] - s["start"]).total_seconds() for s in segments if s["start"] and s["end"])
    return {
        "agent_id": agent_id,
        "path": str(path),
        "agent_type": attribution.most_common(1)[0][0] if attribution else "?",
        "model": model or "?",
        "effort": effort or "?",
        "records": len(recs),
        "assistant_turns": assistant_turns,
        "tool_calls": tool_calls,
        "tool_calls_total": sum(tool_calls.values()),
        "denials": denials,
        "errored_results": errored_results,
        "errors": errors,
        "files": files,
        "file_chars": file_chars,
        "checks": checks,
        "out_tokens": out_tokens,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "stop_reasons": dict(stop_reasons),
        "start": start,
        "end": end,
        "span_s": span,
        "active_s": active,
        "segments": segments,
        "recs": recs,  # kept for full-log rendering
    }


def _fmt_dur(s: float) -> str:
    s = int(round(s))
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m{s % 60:02d}s"


def _iso(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "?"


def render_summary(reports: list[dict], session: str, root: str | None = None) -> str:
    total_out = sum(r["out_tokens"] for r in reports)
    total_tools = sum(r["tool_calls_total"] for r in reports)
    total_denials = sum(len(r["denials"]) for r in reports)
    L = []
    L.append(f"# Agent run report — session `{session}`\n")
    L.append(
        f"- **Agents spawned:** {len(reports)}  ·  **assistant turns:** "
        f"{sum(r['assistant_turns'] for r in reports)}  ·  **tool calls:** {total_tools}\n"
        f"- **Output tokens:** {total_out:,}  ·  **blockers (denied/rejected tools):** {total_denials}\n"
    )
    L.append("## 1. Which agents ran\n")
    L.append("| # | Agent type | id (short) | model | segments | turns | tool calls | files | out tokens | blockers |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(sorted(reports, key=lambda r: r["start"] or datetime.max), 1):
        L.append(
            f"| {i} | **{r['agent_type']}** | `{r['agent_id'][:12]}` | {r['model']} | "
            f"{len(r['segments'])} | {r['assistant_turns']} | {r['tool_calls_total']} | "
            f"{len(r['files'])} | {r['out_tokens']:,} | {len(r['denials'])} |"
        )
    L.append("")
    L.append("## 2. Execution time\n")
    L.append(
        "`span` = first→last timestamp (includes idle waits between resumes). "
        "`active` = Σ per-segment wall-clock (compute time).\n"
    )
    L.append("| Agent type | id | start | end | span | active | segments |")
    L.append("|---|---|---|---|---|---|---|")
    for r in sorted(reports, key=lambda r: r["start"] or datetime.max):
        L.append(
            f"| {r['agent_type']} | `{r['agent_id'][:12]}` | {_iso(r['start'])} | {_iso(r['end'])} | "
            f"{_fmt_dur(r['span_s'])} | {_fmt_dur(r['active_s'])} | {len(r['segments'])} |"
        )
    L.append("")
    L.append("### Per-segment timing (dispatch + each SendMessage resume)\n")
    for r in sorted(reports, key=lambda r: r["start"] or datetime.max):
        L.append(f"**{r['agent_type']}** `{r['agent_id'][:12]}`")
        for j, s in enumerate(r["segments"], 1):
            dur = (s["end"] - s["start"]).total_seconds() if s["start"] and s["end"] else 0
            first_line = (s["prompt"].splitlines() or [""])[0][:90]
            flag = f"  ⛔ {len(s['denials'])} denial(s)" if s["denials"] else ""
            L.append(
                f"- seg {j}: {_fmt_dur(dur)} · {s['turns']} turns · {sum(s['tools'].values())} tools{flag} — “{first_line}”"
            )
        L.append("")
    L.append("## 3. Bottlenecks & blockers\n")
    any_block = False
    for r in sorted(reports, key=lambda r: r["start"] or datetime.max):
        if r["denials"] or r["errored_results"]:
            any_block = True
            L.append(f"### {r['agent_type']} `{r['agent_id'][:12]}`")
            for d in r["denials"]:
                L.append(f"- **DENIED** `{d['tool']}` — kind `{d['kind']}` @ {d['ts']}")
                if d.get("reason"):
                    L.append(f"  - reason: {d['reason']}")
            if r["errored_results"]:
                L.append(f"- non-denial errored tool results: {r['errored_results']}")
                # What failed, not just how often — an errored result the agent fixed
                # inside its own dispatch is the cheapest evidence of where it struggled.
                for e in r["errors"][:8]:
                    L.append(f"  - `{e['tool']}` @ {e['ts']}: {e['line']}")
                if len(r["errors"]) > 8:
                    L.append(f"  - …and {len(r['errors']) - 8} more (see the full log)")
            L.append("")
    if not any_block:
        L.append("_No denied/rejected tool calls or errored results recorded._\n")
    L.append("### Tool-call distribution (all agents)\n")
    agg = Counter()
    for r in reports:
        agg.update(r["tool_calls"])
    L.append("| tool | calls |")
    L.append("|---|---|")
    for name, n in agg.most_common():
        L.append(f"| `{name}` | {n} |")
    L.append("")
    L.append("### Stop reasons\n")
    L.append("| agent | " + " | ".join(sorted({k for r in reports for k in r["stop_reasons"]})) + " |")
    keys = sorted({k for r in reports for k in r["stop_reasons"]})
    L.append("|" + "---|" * (len(keys) + 1))
    for r in reports:
        L.append(
            f"| {r['agent_type']} `{r['agent_id'][:8]}` | "
            + " | ".join(str(r["stop_reasons"].get(k, 0)) for k in keys)
            + " |"
        )
    L.append("")
    L.extend(_render_produced(reports, root))
    L.extend(_render_checks(reports))
    L.append("---\nFull per-agent logs: see the `log-*.md` files in this directory.\n")
    return "\n".join(L)


def _render_produced(reports: list[dict], root: str | None = None) -> list[str]:
    """What the run put on disk. A run is judged by its output, and the transcript
    knows which files that was — so the reader can go read the diff instead of
    inferring quality from turn counts."""
    by_path_agents: dict[str, set[str]] = defaultdict(set)
    edits, chars = Counter(), Counter()
    for r in reports:
        for p, n in r["files"].items():
            by_path_agents[p].add(r["agent_type"])
            edits[p] += n
            chars[p] += r["file_chars"][p]
    L = ["## 4. What the run produced\n"]
    if not edits:
        L.append("_No file was written or edited in this scope._\n")
        return L
    L.append(
        f"{len(edits)} file(s) touched, {sum(edits.values())} write/edit call(s), "
        f"{sum(chars.values()):,} chars of new text. **Churn** flags a file rewritten three or "
        "more times, or touched by more than one agent — the run's own signal of where it "
        "struggled or where two roles met.\n"
    )
    L.append("| file | agents | edits | chars | churn |")
    L.append("|---|---|---|---|---|")
    for p, n in edits.most_common():
        who = ", ".join(sorted(by_path_agents[p]))
        churn = "⚠︎" if n >= 3 or len(by_path_agents[p]) > 1 else ""
        L.append(f"| `{_short_path(p, root)}` | {who} | {n} | {chars[p]:,} | {churn} |")
    L.append("")
    L.append(
        "> This report cannot judge the code — it only says where the code is. Read the diff "
        "of the files above before drawing conclusions about the run's quality; a clean roster "
        "and a green toolchain say the cycle worked, not that the code is good.\n"
    )
    return L


def _render_checks(reports: list[dict]) -> list[str]:
    """The toolchain's own verdicts, in the order the run got them. Red→green inside
    one dispatch is self-correction; red→green across dispatches is rework."""
    rows = []
    for r in reports:
        for c in r["checks"]:
            rows.append((c["ts"] or "", r["agent_type"], c))
    rows.sort(key=lambda t: t[0])
    L = ["## 5. Toolchain timeline\n"]
    if not rows:
        L.append("_No test, type-check or lint command was run in this scope._\n")
        return L
    # Red is reported per agent and never summed. One total says every red means the same
    # thing, and the transcript cannot tell a broken implementation from a deliberately
    # broken one — so the tool shows who went red and leaves the reading to the reader.
    runs, reds = Counter(), Counter()
    order: list[str] = []
    for _, agent, c in rows:
        if agent not in runs:
            order.append(agent)
        runs[agent] += 1
        if c["colour"] == "red":
            reds[agent] += 1
    L.append(f"{len(rows)} check run(s). Verdict lines are the tool's own words, lifted verbatim from its output.\n")
    L.append(
        "Red is broken out by agent and deliberately not summed: red from a test author, red "
        "from a reviewer and red from an adversarial pass mean different things — a check that "
        "goes red against a deliberately broken implementation is the suite working, not the run "
        "failing. Nothing in a transcript separates those, so this report does not guess; it says "
        "who.\n"
    )
    for agent in order:
        L.append(f"- **{agent}** — {runs[agent]} run(s), {reds[agent]} red")
    L.append("")
    L.append("| # | when | agent | command | verdict |")
    L.append("|---|---|---|---|---|")
    mark = {"green": "🟢", "red": "🔴", "?": "·"}
    for i, (ts, agent, c) in enumerate(rows, 1):
        verdict = "; ".join(c["lines"]) if c["lines"] else "_(no summary line matched)_"
        verdict = verdict.replace("|", "\\|")
        cmd = c["cmd"].replace("|", "\\|")
        L.append(f"| {i} | {ts[11:19] if len(ts) > 19 else ts} | {agent} | `{cmd}` | {mark[c['colour']]} {verdict} |")
    L.append("")
    return L


def _cap(s: str, cap: int) -> str:
    if cap and len(s) > cap:
        return s[:cap] + f"\n…[truncated {len(s) - cap} chars]"
    return s


def render_log(r: dict, cap: int) -> str:
    L = []
    L.append(f"# Full log — {r['agent_type']} `{r['agent_id']}`\n")
    L.append(
        f"- model `{r['model']}` · effort `{r['effort']}` · {r['assistant_turns']} turns · "
        f"{r['tool_calls_total']} tool calls · {r['out_tokens']:,} out tokens"
    )
    L.append(
        f"- span {_fmt_dur(r['span_s'])} ({_iso(r['start'])} → {_iso(r['end'])}) · active {_fmt_dur(r['active_s'])}"
    )
    L.append(f"- transcript: `{r['path']}`\n")
    seg_i = 0
    for rec in r["recs"]:
        msg = rec.get("message")
        if is_instruction(rec):
            seg_i += 1
            L.append(f"\n---\n\n## ▶ Segment {seg_i} — instruction ({rec.get('timestamp', '?')})\n")
            L.append("> " + _cap(_text_of(msg["content"]).strip(), cap).replace("\n", "\n> "))
            continue
        if not isinstance(msg, dict):
            continue
        role = rec.get("type")
        if role == "assistant":
            for b in _blocks(msg.get("content")):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    L.append(f"\n**assistant** ({rec.get('timestamp', '?')}):\n\n{b['text'].strip()}")
                elif b.get("type") == "thinking" and b.get("thinking", "").strip():
                    L.append(f"\n<details><summary>thinking</summary>\n\n{b['thinking'].strip()}\n\n</details>")
                elif b.get("type") == "tool_use":
                    inp = json.dumps(b.get("input", {}), ensure_ascii=False, indent=2)
                    L.append(f"\n🔧 **tool_use** `{b.get('name')}`:\n```json\n{_cap(inp, cap)}\n```")
        elif role == "user":
            for b in _blocks(msg.get("content")):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = b.get("content")
                    txt = body if isinstance(body, str) else _text_of(body)
                    err = " ⛔ERROR" if b.get("is_error") else ""
                    L.append(f"\n↩️ **tool_result**{err}:\n```\n{_cap(txt.strip(), cap)}\n```")
        kind = rec.get("toolDenialKind")
        if kind:
            L.append(f"\n⛔ **TOOL DENIED** — kind `{kind}` (tool_use_id `{rec.get('sourceToolUseID', '?')}`)")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--session", default="latest")
    ap.add_argument("--out")
    ap.add_argument("--blob-cap", type=int, default=6000)
    ap.add_argument(
        "--include-main",
        action="store_true",
        help="also render the main/orchestrator session transcript, not just subagents",
    )
    ap.add_argument(
        "--main-only", action="store_true", help="render ONLY the main session transcript (implies --include-main)"
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="also copy the source .jsonl transcripts into <out>/raw/ (full-fidelity archive)",
    )
    args = ap.parse_args()
    include_main = args.include_main or args.main_only

    home = Path.home()
    if args.project_dir:
        proj = Path(args.project_dir)
    else:
        proj = home / ".claude" / "projects" / _slug_for(args.cwd)
    if not proj.is_dir():
        print(f"project dir not found: {proj}")
        return 2

    # A session == a top-level <id>.jsonl main transcript; its subagents live in <id>/subagents/.
    main_files = sorted(proj.glob("*.jsonl"))
    if not main_files:
        print(f"no session transcripts under {proj}")
        return 3

    if args.session == "all":
        chosen = main_files
    elif args.session == "latest":
        chosen = [max(main_files, key=lambda p: p.stat().st_mtime)]
    else:
        chosen = [p for p in main_files if p.stem == args.session or p.stem.startswith(args.session)]
        if not chosen:
            print(f"session {args.session} not found; available: {[p.stem for p in main_files]}")
            return 4

    for mf in chosen:
        sess_name = mf.stem
        sub_dir = proj / sess_name / "subagents"
        transcripts = sorted(sub_dir.glob("agent-*.jsonl")) if sub_dir.is_dir() else []
        reports = [] if args.main_only else [analyze(t) for t in transcripts]
        reports = [r for r in reports if r["records"]]

        if include_main:
            mr = analyze(mf)
            if mr["records"]:
                mr["agent_type"] = "main-session"
                mr["agent_id"] = sess_name
                reports.append(mr)

        if not reports:
            print(
                f"session {sess_name}: nothing to report (no subagents"
                f"{'' if args.main_only else ' and --include-main not set'})"
            )
            continue

        out = Path(args.out) if args.out else (proj / "run-reports" / sess_name)
        out.mkdir(parents=True, exist_ok=True)
        (out / "SUMMARY.md").write_text(render_summary(reports, sess_name, args.cwd), encoding="utf-8")
        for r in reports:
            fn = f"log-{r['agent_type']}-{r['agent_id'][:12]}.md"
            (out / fn).write_text(render_log(r, args.blob_cap), encoding="utf-8")
        if args.raw:
            raw_dir = out / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            for r in reports:
                src = Path(r["path"])
                if src.exists():
                    (raw_dir / src.name).write_bytes(src.read_bytes())
        n_main = sum(1 for r in reports if r["agent_type"] == "main-session")
        print(f"session {sess_name}: {len(reports) - n_main} subagent(s){' + main session' if n_main else ''} → {out}/")
        print(f"  SUMMARY.md + {len(reports)} log-*.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
