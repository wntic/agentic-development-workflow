#!/usr/bin/env python3
"""Deterministic lint for a change's criteria.md (workflow v3, spec §3.3).

Every acceptance criterion must describe observable behaviour of the running
system: it must name at least one observable artifact (an HTTP status code or
class, an HTTP method, a URL path, an inline-code token, a snake_case field
name, or an ALL-CAPS state constant) and must not hide behind vagueness
markers ("works", "correctly", "as expected", ...). A vague criterion does not
enter work — loud degradation instead of silent. Vagueness detection is English
(the language every shipped artifact is written in); the observable-artifact
requirement below is language-neutral and carries the check regardless.

Stdlib-only. Usage: criteria_lint.py FILE [FILE ...]
Exit codes: 0 = all criteria pass · 1 = findings (one `path:line: reason` per
finding on stdout) · 2 = usage / unreadable file.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --- criteria line grammar (spec §3.3) --------------------------------------

# States: [ ] not proven · [x] machine-proven · [m] accepted manually by the human.
AC_LINE = re.compile(r"^- \[(?P<state>[ xm])\] (?P<acid>AC-\d+): (?P<text>\S.*)$")
# Anything that looks like an attempted checklist item but does not parse.
CHECKBOX_LIKE = re.compile(r"^\s*[-*]\s*\[")

# --- vagueness markers (spec §3.3: "works", "correctly", "as expected", ...) ---
# English only — the language every shipped artifact is written in. Negated/embedded forms
# ("incorrect password" describes an input, not a verdict) are NOT matched: `\bcorrect\b`
# does not fire inside "incorrect".

VAGUE_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in [
        (r"\bworks\b", '"works"'),
        (r"\bworking\b", '"working"'),
        (r"\bcorrectly\b", '"correctly"'),
        (r"\bcorrect\b", '"correct"'),
        (r"\bproperly\b", '"properly"'),
        (r"\bproper\b", '"proper"'),
        (r"\bas expected\b", '"as expected"'),
        (r"\bas intended\b", '"as intended"'),
        (r"\bappropriately\b", '"appropriately"'),
        (r"\bappropriate\b", '"appropriate"'),
        (r"\bgracefully\b", '"gracefully"'),
        (r"\bsuccessfully\b", '"successfully"'),
    ]
)

# --- observable-artifact tokens (HTTP code / field name / state assertion) ---

OBSERVABLE_TOKENS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[1-5]\d{2}\b"),  # HTTP status code (201, 404, 413)
    re.compile(r"\b[1-5]xx\b", re.IGNORECASE),  # HTTP status class (5xx)
    re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b"),  # HTTP method
    re.compile(r"(?<![\w`])/[A-Za-z0-9_{][A-Za-z0-9_{}./-]*"),  # URL path (/meetings/{id})
    re.compile(r"`[^`]+`"),  # inline-code token (field, command)
    re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),  # snake_case identifier (quota_exceeded)
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),  # ALL-CAPS state constant (DONE)
)

NO_ARTIFACT_REASON = (
    "names no observable artifact — name an HTTP status/method, a URL path, an "
    "`inline-code` token, a snake_case field, or an ALL-CAPS state constant"
)


@dataclass(frozen=True)
class Criterion:
    line_no: int
    state: str  # " " | "x" | "m"
    ac_id: str  # "AC-1"
    text: str


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_no}: {self.reason}"


def _strip_html_comments(lines: list[str]) -> list[str]:
    """Blank out <!-- ... --> spans (including multi-line) preserving line count."""
    out: list[str] = []
    in_comment = False
    for line in lines:
        kept: list[str] = []
        i = 0
        while i < len(line):
            if in_comment:
                end = line.find("-->", i)
                if end == -1:
                    i = len(line)
                else:
                    in_comment = False
                    i = end + 3
            else:
                start = line.find("<!--", i)
                if start == -1:
                    kept.append(line[i:])
                    i = len(line)
                else:
                    kept.append(line[i:start])
                    in_comment = True
                    i = start + 4
        out.append("".join(kept))
    return out


def iter_criteria(lines: list[str]) -> list[Criterion]:
    """Parse well-formed criteria lines (comments already expected to be stripped)."""
    criteria: list[Criterion] = []
    for line_no, line in enumerate(lines, start=1):
        match = AC_LINE.match(line)
        if match:
            criteria.append(Criterion(line_no, match.group("state"), match.group("acid"), match.group("text")))
    return criteria


def lint_lines(raw_lines: list[str], path: str = "criteria.md") -> list[Finding]:
    lines = _strip_html_comments(raw_lines)
    findings: list[Finding] = []
    seen_ids: dict[str, int] = {}
    criteria = iter_criteria(lines)
    parsed_line_nos = {c.line_no for c in criteria}

    for line_no, line in enumerate(lines, start=1):
        if CHECKBOX_LIKE.match(line) and line_no not in parsed_line_nos:
            findings.append(Finding(path, line_no, "malformed criteria line — expected '- [ |x|m] AC-n: <text>'"))

    for criterion in criteria:
        if criterion.ac_id in seen_ids:
            findings.append(
                Finding(
                    path,
                    criterion.line_no,
                    f"duplicate id {criterion.ac_id} (first defined on line {seen_ids[criterion.ac_id]}) — "
                    "ids must be unique, they key the ac-marked test cross-check",
                )
            )
        else:
            seen_ids[criterion.ac_id] = criterion.line_no

        for pattern, label in VAGUE_MARKERS:
            if pattern.search(criterion.text):
                findings.append(
                    Finding(
                        path,
                        criterion.line_no,
                        f"{criterion.ac_id}: vagueness marker {label} — state the observable "
                        "behaviour instead of asserting quality",
                    )
                )

        if not any(token.search(criterion.text) for token in OBSERVABLE_TOKENS):
            findings.append(Finding(path, criterion.line_no, f"{criterion.ac_id}: {NO_ARTIFACT_REASON}"))

    if not criteria:
        findings.append(
            Finding(path, 1, "no acceptance criteria found — expected at least one '- [ ] AC-n: <text>' line")
        )

    findings.sort(key=lambda f: f.line_no)
    return findings


def lint_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    return lint_lines(text.splitlines(), path=str(path))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: criteria_lint.py FILE [FILE ...]", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    for arg in args:
        path = Path(arg)
        try:
            findings = lint_file(path)
        except OSError as exc:
            print(f"error: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        all_findings.extend(findings)
        if not findings:
            criteria = iter_criteria(_strip_html_comments(path.read_text(encoding="utf-8").splitlines()))
            states = [c.state for c in criteria]
            print(
                f"OK: {path} — {len(criteria)} criteria "
                f"({states.count('x')} [x], {states.count('m')} [m], {states.count(' ')} open)"
            )

    for finding in all_findings:
        print(finding)
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
