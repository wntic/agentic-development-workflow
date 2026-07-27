#!/usr/bin/env python3
"""criteria_guard.py — PreToolUse ergonomics for criteria.md (workflow v3, spec §5.2).

THIS IS ERGONOMICS — a fast, explained denial so the agent learns "why not" *before*, not
after. The trust anchor is gate.py's integrity check against the git baseline (S8): a hook
bypass (Bash, whole-file Write that dodges this matcher, conftest, editing the gate itself)
only gets the result invalidated at the gate — criteria.md is a protected tree there.

Policy (spec §5.2):
  - editing an existing criteria.md is allowed ONLY as a checkbox state flip in place
    (`[ ]` <-> `[x]`; `[m]` is deferred — a PreToolUse hook cannot tell a subagent from the
    human, F-2, so the [m] legitimacy check lives in gate.py --criteria / the verdict);
  - rewording / renumbering / adding or removing criteria is the /spec session's job (S3);
  - creating criteria.md is legal only before a `baseline/<context>-NNN` tag exists (E-03).

Reads the Write payload's file from disk and line-diffs (Write carries no old_string, F-1);
for Edit it compares old_string/new_string when both are present. Paths are canonicalised
realpath+casefold (E-10: APFS is case-insensitive; symlink and `..` evasions).

Stdin: the PreToolUse payload. Stdout: nothing on allow; a permissionDecision=deny JSON
object on a denied edit. `--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

DESCRIBE = (
    "criteria_guard.py: PreToolUse(Edit|Write) — allows only checkbox state flips in "
    "criteria.md; reword/renumber -> /spec; creation only before the baseline tag "
    "(ergonomics, trust is gate.py, S8)."
)

# A criteria checkbox line: leading marker `- [ ]` / `- [x]` / `- [m]` (case-insensitive).
CHECKBOX = re.compile(r"^(\s*[-*]\s*\[)[ xXmM](\].*)$")


def canonical(path: str) -> str:
    """realpath + casefold — defeats `..` and APFS case-insensitive evasions (E-10)."""
    return os.path.realpath(path).casefold()


def is_criteria(path: str) -> bool:
    return os.path.basename(canonical(path)) == "criteria.md"


def normalize_flip(line: str) -> str:
    """Blank out a checkbox marker so two lines compare equal iff they differ only in state."""
    m = CHECKBOX.match(line)
    if m:
        return m.group(1) + "?" + m.group(2)
    return line


def state_flip_only(old_text: str, new_text: str) -> tuple[bool, str]:
    """(ok, reason). True iff old->new is purely checkbox state flips, line-for-line."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    if len(old_lines) != len(new_lines):
        return False, (
            f"line count changed ({len(old_lines)} -> {len(new_lines)}): criteria may be "
            "added or removed only by the /spec session"
        )
    # `strict=True` (B905): a truncating zip here would compare two criteria lists of different
    # lengths line-for-line and report the shorter one as flip-only — the guard's whole question.
    # It cannot happen today, because the length check three lines up returns first; strict makes
    # that dependency explicit instead of load-bearing-by-adjacency.
    for old, new in zip(old_lines, new_lines, strict=True):
        if old == new:
            continue
        if normalize_flip(old) == normalize_flip(new) and CHECKBOX.match(old) and CHECKBOX.match(new):
            continue
        return False, f"line rewritten beyond a state flip:\n  - {old!r}\n  + {new!r}"
    return True, ""


def baseline_tag_for(path: str) -> str | None:
    """Derive `baseline/<context>-NNN` from a .../<context>/changes/NNN-slug/criteria.md path."""
    parts = os.path.realpath(path).split(os.sep)
    try:
        ci = parts.index("changes")
    except ValueError:
        return None
    if ci == 0 or ci + 1 >= len(parts):
        return None
    context = parts[ci - 1]
    change_dir = parts[ci + 1]
    m = re.match(r"(\d{3})", change_dir)
    if not m:
        return None
    return f"baseline/{context}-{m.group(1)}"


def tag_exists(tag: str) -> bool:
    proc = subprocess.run(["git", "tag", "--list", tag], capture_output=True, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


LEGAL = (
    " Legal paths: flip a checkbox in place, or route the wording change through the "
    "/spec session (criteria.md is human-owned prose; agents only flip state, S3). The "
    "gate checks criteria.md against the baseline regardless of this hook (S8)."
)


def main() -> int:
    if "--describe" in sys.argv[1:]:
        print(DESCRIBE)
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # ergonomics only: never block on a malformed payload — the gate is the anchor

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path or not is_criteria(file_path):
        return 0  # not our file — allow

    real = os.path.realpath(file_path)

    if not os.path.exists(real):
        # creation — legal only before the change has a red-tests baseline tag (E-03)
        tag = baseline_tag_for(file_path)
        if tag and tag_exists(tag):
            deny(
                f"criteria.md creation denied: the change already has a baseline ({tag}); "
                "the criteria list is frozen at the red commit." + LEGAL
            )
        return 0  # no baseline yet -> /spec is authoring it

    tool_name = payload.get("tool_name", "")
    if tool_name == "Write":
        new_text = tool_input.get("content", "")
        old_text = _read(real)
        ok, reason = state_flip_only(old_text, new_text)
        if not ok:
            deny("criteria.md Write denied: " + reason + LEGAL)
        return 0

    if tool_name == "Edit":
        old_s = tool_input.get("old_string")
        new_s = tool_input.get("new_string")
        if old_s is None or new_s is None:
            return 0  # no fields to compare (F-1 PARTIAL) — defer to the gate
        ok, reason = state_flip_only(old_s, new_s)
        if not ok:
            deny("criteria.md Edit denied: " + reason + LEGAL)
        return 0

    return 0


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
