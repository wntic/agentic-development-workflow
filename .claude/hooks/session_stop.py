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
an active cycle. That takes TWO deterministic signals together: (1) we are on the
`change/<ctx>-NNN` branch that carries the cycle (S9) — on the base/build branch an ordinary
design turn, or a stale ESCALATE / lingering change dir left by another branch's cycle, must
never deadlock; AND (2) the red-baseline tag `baseline/<ctx>-NNN` exists — the test-author
creates it in /implement step 1, so its absence means /spec has just authored the change and
the spec-author session legitimately ends with criteria still `[ ]` and no verdict.md (F6).

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
    "session_stop.py: Stop — blocks the /implement session (on a change/<ctx>-NNN branch once "
    "its baseline tag exists) while criteria has [ ], verdict.md is missing, or ESCALATE is "
    "present (§5.3)."
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


def baseline_tag_for(change_dir: Path) -> str | None:
    """Derive `baseline/<context>-NNN` from a .../specs/<context>/changes/NNN-slug dir."""
    parts = change_dir.parts
    try:
        ci = parts.index("changes")
    except ValueError:
        return None
    if ci == 0 or ci + 1 >= len(parts):
        return None
    context = parts[ci - 1]
    m = re.match(r"(\d{3})", parts[ci + 1])
    if not m:
        return None
    return f"baseline/{context}-{m.group(1)}"


def tag_exists(root: Path, tag: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "tag", "--list", tag],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


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

    # Signal 1: on the change branch. Off it (base/build branch) an ordinary design turn — or
    # a stale ESCALATE / lingering change dir from another branch's cycle — must not deadlock.
    branch = current_branch(root)
    if branch is None or not CHANGE_BRANCH.match(branch):
        return 0

    change_dir = find_change_dir(root)
    if change_dir is None:
        return 0  # nothing (or too much) in flight — not this hook's call

    # Signal 2: the test-author's red-baseline tag exists (§5.3). After /spec but before
    # /implement there is a change branch but no baseline yet, so the spec-author session ends
    # cleanly with criteria legitimately still `[ ]`. (F6)
    baseline = baseline_tag_for(change_dir)
    if baseline is None or not tag_exists(root, baseline):
        return 0

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
