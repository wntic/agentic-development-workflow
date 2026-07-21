#!/usr/bin/env python3
"""session_stop.py — Stop gate for the main /implement session (workflow v3, spec §5.3).

The main session's turn is not finished while the change is not resolved: blocks the Stop
while criteria.md still has an unchecked `[ ]`, OR verdict.md is missing, OR an ESCALATE
file is present. The ESCALATE case ends only by an explicit human turn — a hook cannot
observe that turn, so it uses `stop_hook_active` as the proxy: the first Stop attempt with
ESCALATE present blocks (surface it to the human); once we are already in a stop-hook
continuation (`stop_hook_active`), it allows the stop so the human can act (only a human
removes ESCALATE, §5.3).

§5.3 scopes this hook to "Stop на главной сессии в /implement" — it must fire ONLY during
an active cycle. The deterministic proxy is the current git branch: a `change/<ctx>-NNN`
branch means a cycle is live; on the base/build branch the hook passes through, so a stale
ESCALATE floating as an untracked file never deadlocks an ordinary design turn.

This is ergonomics/orchestration plumbing; conformance is still gate.py + accept.py (S8).
Stdin: the Stop payload. Stdout: a block JSON while unresolved, otherwise nothing.
`--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DESCRIBE = (
    "session_stop.py: Stop — blocks the /implement session (on a change/<ctx>-NNN branch) "
    "while criteria has [ ], verdict.md is missing, or ESCALATE is present (§5.3)."
)

UNCHECKED = re.compile(r"^\s*[-*]\s*\[ \]", re.MULTILINE)
# `change/<context>-NNN` — the branch that carries an active /implement cycle (S9).
CHANGE_BRANCH = re.compile(r"^change/.+-\d+$")


def current_branch(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def find_change_dir(root: Path) -> Path | None:
    matches = [p for p in root.glob("specs/*/changes/*") if p.is_dir()]
    return matches[0] if len(matches) == 1 else None


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main() -> int:
    if "--describe" in sys.argv[1:]:
        print(DESCRIBE)
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    root = Path(payload.get("cwd") or os.getcwd()).resolve()
    stop_hook_active = bool(payload.get("stop_hook_active"))

    # Only fire mid-cycle: on the base/build branch a stale ESCALATE must not deadlock turns.
    branch = current_branch(root)
    if branch is None or not CHANGE_BRANCH.match(branch):
        return 0

    change_dir = find_change_dir(root)
    if change_dir is None:
        return 0  # nothing (or too much) in flight — not this hook's call

    escalate = change_dir / "ESCALATE"
    if escalate.exists():
        if stop_hook_active:
            return 0  # already surfaced; let the human take over (only a human removes ESCALATE)
        block(
            "ESCALATE is present: the change hit its iteration ceiling. Surface this to the "
            "human — accept.py denies while ESCALATE exists, and only a human removes it (§5.3)."
        )

    reasons: list[str] = []
    criteria = change_dir / "criteria.md"
    if criteria.exists() and UNCHECKED.search(criteria.read_text(encoding="utf-8")):
        reasons.append("criteria.md still has unchecked `[ ]` items")
    if not (change_dir / "verdict.md").exists():
        reasons.append("verdict.md has not been written by the evaluator")

    if reasons:
        block(
            "the change is not resolved: "
            + "; ".join(reasons)
            + ". Run the cycle to completion (implementer -> fresh evaluator) before stopping (§5.3)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
