#!/usr/bin/env python3
"""subagent_stop.py — SubagentStop gate for the implementer (workflow v3, spec §5.3).

Holds the implementer subagent while gate.py is RED on the change branch: emits
`{"decision":"block","reason":<failed checks>}` so the agent keeps working toward green.
ONLY the implementer is held-and-counted — the SubagentStop payload carries `agent_type`
(F-2), so any other agent's stop (test-author, whose deliverable IS a red gate; evaluator)
passes straight through with no gate run and no counter change. When the block ceiling is
hit, THE HOOK ITSELF writes `changes/NNN-slug/ESCALATE` (E-08: escalation is a material
file, not a line in an ephemeral report) and then allows the stop so the session can surface
it to the human. Respects `stop_hook_active` and a configurable ceiling (F-4/5: the
documented anti-loop field is `stop_hook_active`; the numeric ceiling is tracked in a
git-ignored `.gate/` counter — see the report's finding on this drift).

This hook is ergonomics + escalation plumbing; the trust anchor is still gate.py itself,
which it simply re-runs (S8). Stdin: the SubagentStop payload. Stdout: a block JSON while
red under ceiling, otherwise nothing. `--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DESCRIBE = (
    "subagent_stop.py: SubagentStop — re-runs gate.py; blocks the implementer while RED, "
    "writes an ESCALATE file at the block ceiling then allows stop (E-08, §5.3)."
)

DEFAULT_CEILING = 3
COUNTER_REL = Path(".gate") / "subagent-stop-count"
IMPLEMENTER_AGENT = "implementer"  # matches .claude/agents/implementer.md frontmatter name


def find_change_dir(root: Path) -> Path | None:
    """The single specs/<ctx>/changes/NNN-*/ directory under root, or None if ambiguous."""
    matches = [p for p in root.glob("specs/*/changes/*") if p.is_dir()]
    return matches[0] if len(matches) == 1 else None


def read_count(root: Path) -> int:
    try:
        return int((root / COUNTER_REL).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def write_count(root: Path, value: int) -> None:
    counter = root / COUNTER_REL
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(f"{value}\n", encoding="utf-8")


def run_gate(root: Path) -> tuple[bool, list[str]]:
    """Run gate.py on root. Return (green, failed_check_ids)."""
    gate = root / ".claude" / "tools" / "gate.py"
    subprocess.run(
        [sys.executable, str(gate), str(root)],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    verdict_path = root / ".gate" / "verdict.json"
    try:
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ["gate produced no verdict.json"]
    return verdict.get("result") == "GREEN", list(verdict.get("failed") or [])


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

    # Only the implementer is held-and-counted while red; the test-author's deliverable IS a
    # red gate, and the evaluator merely reports. Any non-implementer stop passes through
    # untouched — no gate run, no counter change (F-2: SubagentStop carries agent_type).
    if payload.get("agent_type") != IMPLEMENTER_AGENT:
        return 0

    root = Path(payload.get("cwd") or os.getcwd()).resolve()
    ceiling = int(os.environ.get("WORKFLOW_STOP_CEILING", DEFAULT_CEILING))

    green, failed = run_gate(root)
    if green:
        write_count(root, 0)  # cycle succeeded — reset the counter
        return 0  # allow stop

    count = read_count(root)
    if count < ceiling:
        write_count(root, count + 1)
        block(
            f"gate.py is RED (block {count + 1}/{ceiling}): {', '.join(failed) or 'see .gate/verdict.json'}. "
            "Keep working src/** to green — SubagentStop holds you while the gate is red (§5.3)."
        )

    # ceiling reached — the hook writes the ESCALATE file (E-08) and lets the stop through
    change_dir = find_change_dir(root)
    if change_dir is not None:
        escalate = change_dir / "ESCALATE"
        escalate.write_text(
            "# ESCALATE (hook-authored, spec §5.3 / E-08)\n\n"
            f"gate.py stayed RED after {ceiling} implementer passes.\n"
            f"Failed checks: {', '.join(failed) or 'see .gate/verdict.json'}\n\n"
            "accept.py denies while this file exists; only a human removes it.\n",
            encoding="utf-8",
        )
    write_count(root, 0)
    # allow the stop; surface the escalation (not a block — the human takes over)
    print(
        json.dumps(
            {
                "systemMessage": (
                    f"iteration ceiling ({ceiling}) reached; gate still RED "
                    f"({', '.join(failed) or 'see .gate/verdict.json'}). ESCALATE written — a human must intervene."
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
