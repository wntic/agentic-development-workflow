#!/usr/bin/env python3
"""bash_guard.py — PreToolUse(Bash) best-effort write-pattern denial (workflow v3, §5.2).

THIS IS ERGONOMICS — the trust anchor is gate.py (S8). A shell is Turing-complete; this
guard cannot and does not try to catch every mutation. Its job is a fast, explained "no"
for the obvious shell edits of protected paths (so the agent reaches for the owned path
instead of hand-editing). Anything that slips past is caught post-hoc: the gate diffs the
protected trees and the test inventory against the git baseline (§5.1, S8).

Denies when a write-op token (`sed -i`, `>`/`>>`, `rm`, `mv`, `tee`, `git checkout --`)
co-occurs with a protected path (tests/**, specs/<ctx>/*.md, changes/*/criteria.md|change.md,
.claude/tools|hooks/**, pyproject.toml). Best-effort: a false negative is expected and
covered by the gate; a false positive just asks the agent to use the owned path.

Stdin: the PreToolUse payload. Stdout: nothing on allow; a permissionDecision=deny JSON on
a denied command. `--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import re
import sys

DESCRIBE = (
    "bash_guard.py: PreToolUse(Bash) — best-effort deny of shell writes to protected paths "
    "(tests, specs, .claude/tools|hooks, pyproject); ergonomics, trust is gate.py (S8)."
)

# Write-op tokens. `>`/`>>` covers redirections; the rest are explicit mutators.
WRITE_OP = re.compile(
    r"(\bsed\s+-i\b)|(>>?)|(\brm\b)|(\bmv\b)|(\btee\b)|(\bgit\s+checkout\s+--)|(\bgit\s+restore\b)",
)

# Protected-path fragments. Substring match is deliberately loose (best-effort tier).
PROTECTED_FRAGMENTS = (
    "tests/",
    "specs/",
    "changes/",
    "criteria.md",
    "change.md",
    "verdict.md",
    ".claude/tools",
    ".claude/hooks",
    ".claude/settings.json",
    "pyproject.toml",
)


def offending(command: str) -> str | None:
    """Return the matched protected fragment, or None if the command looks benign."""
    if not WRITE_OP.search(command):
        return None
    for frag in PROTECTED_FRAGMENTS:
        if frag in command:
            return frag
    return None


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


def main() -> int:
    if "--describe" in sys.argv[1:]:
        print(DESCRIBE)
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # ergonomics only — never block on a malformed payload

    command = (payload.get("tool_input") or {}).get("command", "")
    frag = offending(command)
    if frag is not None:
        deny(
            f"shell write to a protected path ({frag}) denied. Owned paths: tests/** via "
            "the test-author, src/** via the implementer, criteria/change/verdict via the "
            "cycle, spec prose via /spec. This is only ergonomics — the gate diffs these "
            "trees against the baseline regardless (S8)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
