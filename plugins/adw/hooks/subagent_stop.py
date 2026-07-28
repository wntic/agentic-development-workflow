#!/usr/bin/env python3
"""subagent_stop.py — SubagentStop gate for the implementer (workflow v3, spec §5.3).

Holds the implementer subagent while gate.py is RED on the change branch: emits
`{"decision":"block","reason":<failed checks>}` so the agent keeps working toward green.
ONLY the implementer is held-and-counted — the SubagentStop payload carries `agent_type`
(F-2), so any other agent's stop (test-author, whose deliverable IS a red gate; evaluator)
passes straight through with no gate run and no counter change. That name is NAMESPACED when
the workflow is installed as a plugin (`adw:implementer`) and bare when it is loaded from
project config, so the role is read off the last `:`-separated segment (T15/D1). When the block ceiling is
hit, THE HOOK ITSELF writes `changes/NNN-slug/ESCALATE` (E-08: escalation is a material
file, not a line in an ephemeral report) and then allows the stop so the session can surface
it to the human. Respects `stop_hook_active` and a configurable ceiling (F-4/5: the
documented anti-loop field is `stop_hook_active`; the numeric ceiling is tracked in a
git-ignored `.gate/` counter — see the report's finding on this drift). That write is followed
by a PATH-SCOPED commit of the file alone (T06h): an untracked ESCALATE is invisible to
`gate.py` and to any acceptance run in a fresh worktree, so committing it is what makes §5.3's
human-only lock checkable at all. A commit that fails never costs the escalation — the file
stays on disk and the failure is surfaced verbatim.

A gate that CANNOT RUN is not a RED (T06j). gate.py exits 2 with a sentence and writes no
verdict.json when a precondition it cannot judge fails (the project's environment is missing
mypy/ruff/pytest, an unresolvable --baseline). Reading only verdict.json turned that sentence
into `gate produced no verdict.json`, three times, then an ESCALATE — the implementer burning
its whole ceiling on something no `src/**` edit can fix. The hook now captures the gate's own
output, releases the implementer WITHOUT spending a block, and surfaces the sentence verbatim.

One RED never counts toward the ceiling: when gate.py reports `red_localized_to == "tests"`
(the whole failure is the static toolchain over tests/**, clean over src/ alone), the
implementer structurally cannot clear it (src/** is its lane, D4). The hook releases it
immediately — no block, no counter, no ESCALATE — and emits a systemMessage telling /implement
to hand back to the test-author (notes/18: the users/001 seam this closes).

This hook is ergonomics + escalation plumbing; the trust anchor is still gate.py itself,
which it simply re-runs (S8). Stdin: the SubagentStop payload. Stdout: a block JSON while
red under ceiling, otherwise nothing. `--describe` prints a one-line self-description.

gate.py is meant to run under the project's uv venv (`uv run "${CLAUDE_PLUGIN_ROOT}/bin/adw.py"
gate`, T15/D4); this
hook, however, is launched by Claude Code with the ambient system python, which lacks the
app's deps (fastapi, ...) and would fail every src-import-dependent check with a false RED
(F7). So the gate is re-run through the project's `.venv` interpreter when one is present,
falling back to the launching interpreter otherwise (e.g. test fixtures with no venv).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

DESCRIBE = (
    "subagent_stop.py: SubagentStop — re-runs gate.py; blocks the implementer while RED, "
    "writes an ESCALATE file at the block ceiling then allows stop (E-08, §5.3)."
)

DEFAULT_CEILING = 3
COUNTER_REL = Path(".gate") / "subagent-stop-count"
IMPLEMENTER_AGENT = "implementer"  # matches .claude/agents/implementer.md frontmatter name


def is_implementer(agent_type: str | None) -> bool:
    """True when `agent_type` names the implementer, namespaced or bare (T15/D1).

    Shipped as a plugin, an agent's `agent_type` arrives NAMESPACED — `adw:implementer` —
    while a project-config load reports the bare `implementer`. Both name the same role, so
    the comparison is on the last `:`-separated segment. Comparing the whole string would be
    silently wrong exactly where it matters: installed, the implementer would never be held
    on a RED gate (T06c dead), and no test in the workflow's own repo — which loads via
    project config — would notice.
    """
    if not agent_type:
        return False
    return agent_type.rsplit(":", 1)[-1] == IMPLEMENTER_AGENT


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


def gate_python(root: Path) -> str:
    """The interpreter that can import the app's deps when re-running gate.py (F7).

    gate.py runs its toolchain (mypy/ruff/pytest) and construct-smoke under `sys.executable`,
    so it must itself be launched by an interpreter that has the app's substrate installed.
    The hook's own `sys.executable` is the ambient system python Claude Code used to launch
    it — it lacks fastapi/etc., so every src-import check would falsely go RED. Prefer the
    project's uv `.venv` interpreter; fall back to the launching interpreter (test fixtures
    have a pyproject but no venv, so the fallback keeps them running exactly as before).
    """
    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = root / ".venv" / rel
        if candidate.exists():
            return str(candidate)
    return sys.executable


MESSAGE_TAIL_LINES = 20


class GateRun(NamedTuple):
    """What the gate answered — or, when `ran` is False, why it could not answer at all."""

    ran: bool
    green: bool
    failed: list[str]
    localized: str | None
    message: str  # the gate's own output; only populated when ran is False


def unrunnable_message(returncode: int, stdout: str, stderr: str) -> str:
    """The gate's own words for a run that produced no verdict — never swallowed (T06j).

    Exit 2 is gate.py's deliberate "I cannot judge this" abort and its stderr already carries a
    sentence naming the fix; any other code with no verdict.json is a crash, whose tail is the
    only clue there is. Both are reported; the hook does not need to act on them differently,
    but a human reading the message does."""
    detail = (stderr or "").strip() or (stdout or "").strip()
    tail = "\n".join(detail.splitlines()[-MESSAGE_TAIL_LINES:]) or "(gate.py produced no output)"
    kind = (
        "gate.py aborted (exit 2) — a precondition it cannot judge"
        if returncode == 2
        else f"gate.py produced no .gate/verdict.json (exit {returncode})"
    )
    return f"{kind}:\n{tail}"


def gate_path(root: Path) -> Path:
    """Where gate.py lives: `$CLAUDE_PLUGIN_ROOT/tools`, else a checked-out location (T15/D4).

    Installed as a plugin, the gate is NOT in the project — a `<root>/…/tools/gate.py` simply
    does not exist there, and the hook would report "the gate could not answer" on every stop.
    Claude Code gives a plugin's hooks `CLAUDE_PLUGIN_ROOT`, so that wins when it names an actual
    tools directory; a relative value (the workflow's own repo sets `.`) is resolved against the
    acting root, and anything unusable falls back to a checked-out location — the plugin root at
    the repository root first (this repo since the marketplace move), then a `.claude/` one (the
    pre-move layout, and a consumer that attaches the workflow there). The last candidate is
    returned even when absent, so `run_gate` reports a missing gate rather than guessing.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    bases = []
    if env:
        base = Path(env).expanduser()
        bases.append(base if base.is_absolute() else root / base)
    bases += [root, root / ".claude"]
    for base in bases:
        candidate = base / "tools" / "gate.py"
        if candidate.is_file():
            return candidate
    return bases[-1] / "tools" / "gate.py"


def run_gate(root: Path) -> GateRun:
    """Run gate.py on root and report its answer, or the reason there is none."""
    gate = gate_path(root)
    proc = subprocess.run(
        [gate_python(root), str(gate), str(root)],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    verdict_path = root / ".gate" / "verdict.json"
    try:
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # No verdict = the gate could not answer. gate.py deletes any stale verdict.json before
        # it runs, so this can never be a previous run's answer read as this one's.
        return GateRun(
            ran=False,
            green=False,
            failed=[],
            localized=None,
            message=unrunnable_message(proc.returncode, proc.stdout, proc.stderr),
        )
    return GateRun(
        ran=True,
        green=verdict.get("result") == "GREEN",
        failed=list(verdict.get("failed") or []),
        localized=verdict.get("red_localized_to"),
        message="",
    )


def commit_escalate(root: Path, rel: str) -> str | None:
    """Commit the ESCALATE at `rel`, scoped to that one path. None on success, else the reason.

    E-08 says the escalation is MATERIAL, not a line in an ephemeral report — and an untracked
    file is not material enough: git retains nothing about it, so its later deletion is invisible
    to `gate.py`, and a fresh `git worktree` (how acceptance is often run) never carries it at all.
    Committing it is what turns §5.3's "only a human removes it" from prose into a rule the gate
    can check (T06h).

    Two properties matter and both are in the command shape:
      * `git add -- <path>` first, because `git commit -- <path>` alone refuses a path git does
        not yet know ("did not match any file known to git");
      * the commit is PATH-SCOPED, never `-A`: partial-commit mode ignores the rest of the index
        and the work tree, so the implementer's uncommitted `src/**` — which at an escalation is
        exactly what is lying around unfinished — is not swept into a commit it does not own (D4).

    Nothing here may cost the escalation: a repo with no `user.email`, no git at all, or a commit
    hook of its own returns a sentence the caller surfaces, and the ESCALATE file stays written.
    """
    message = (
        f"chore(escalate): iteration ceiling reached — {rel}\n\n"
        "Hook-authored (SubagentStop, spec §5.3/E-08). Only a human clears this lock; clearing it "
        "means committing the removal and re-baselining over it (red_check.py --clear-escalate)."
    )
    for args in (["add", "--", rel], ["commit", "-q", "-m", message, "--", rel]):
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"git {args[0]} failed: {exc}"
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return f"git {args[0]} failed: {detail[-1] if detail else f'exit {proc.returncode}'}"
    return None


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
    # The name may be plugin-namespaced (`adw:implementer`) or bare (T15/D1).
    if not is_implementer(payload.get("agent_type")):
        return 0

    root = Path(payload.get("cwd") or os.getcwd()).resolve()
    ceiling = int(os.environ.get("WORKFLOW_STOP_CEILING", DEFAULT_CEILING))

    run = run_gate(root)
    failed, localized = run.failed, run.localized
    if run.green:
        write_count(root, 0)  # cycle succeeded — reset the counter
        return 0  # allow stop

    # The gate could not run at all (T06j): there is no GREEN/RED, so there is nothing the
    # implementer can work toward. Blocking would spend the ceiling on a message no `src/**`
    # edit can change — the T09f deadlock shape — and end in an ESCALATE that blames the change
    # for an environment defect. Release immediately and pass the gate's own sentence through,
    # verbatim, to the one who can act on it. The counter is left EXACTLY as it was: not spent
    # (this was not an iteration), and not reset either (a run that cannot answer must not be a
    # way to clear blocks already earned).
    if not run.ran:
        print(
            json.dumps(
                {
                    "systemMessage": (
                        "SubagentStop: no verdict — "
                        + run.message
                        + "\n\nThis is not a code defect and not an ESCALATE: no src/** edit can clear it, so the "
                        "implementer was released without spending a block (ceiling untouched). /implement must "
                        "stop the cycle and surface this to the human — fix the environment, then re-run the step."
                    )
                }
            )
        )
        return 0  # allow stop; control returns to /implement, which must not re-dispatch

    # Tests-localized RED (notes/18): the gate is red ONLY on the static toolchain over tests/**,
    # which the implementer cannot edit (src/** is its lane, D4). Blocking it here just burns the
    # ceiling on an unwinnable hold and ends in a spurious ESCALATE. Instead release immediately —
    # no block, no count, no ESCALATE — and tell /implement to hand back to the test-author. The
    # counter is reset so a later, genuinely implementer-fixable red starts its ceiling fresh.
    if localized == "tests":
        write_count(root, 0)
        print(
            json.dumps(
                {
                    "systemMessage": (
                        "gate RED localized to tests/** "
                        f"({', '.join(failed) or 'see .gate/verdict.json'}) — implementer-unfixable. "
                        "Not an ESCALATE: /implement must hand back to the test-author (D4). "
                        "SubagentStop released the implementer without spending a block (notes/18)."
                    )
                }
            )
        )
        return 0  # allow stop; control returns to /implement for the handback

    count = read_count(root)
    if count < ceiling:
        write_count(root, count + 1)
        block(
            f"gate.py is RED (block {count + 1}/{ceiling}): {', '.join(failed) or 'see .gate/verdict.json'}. "
            "Keep working src/** to green — SubagentStop holds you while the gate is red (§5.3)."
        )

    # ceiling reached — the hook writes AND COMMITS the ESCALATE file (E-08, T06h) and lets the
    # stop through
    change_dir = find_change_dir(root)
    commit_failure: str | None = None
    if change_dir is not None:
        escalate = change_dir / "ESCALATE"
        escalate.write_text(
            "# ESCALATE (hook-authored, spec §5.3 / E-08)\n\n"
            f"gate.py stayed RED after {ceiling} implementer passes.\n"
            f"Failed checks: {', '.join(failed) or 'see .gate/verdict.json'}\n\n"
            "accept.py denies while this file exists; only a human removes it.\n"
            "Clearing it is a recorded act: commit the removal, then move the baseline over it\n"
            "(`red_check.py --change <context>/NNN --clear-escalate`).\n",
            encoding="utf-8",
        )
        # The file first, the commit second, and a failing commit never unwrites the file: the
        # escalation must reach the human even in a tree git cannot commit in (finding T06j's
        # rule — a precondition failure must be legible to whoever can act on it).
        commit_failure = commit_escalate(root, str(escalate.relative_to(root)))
    write_count(root, 0)
    # allow the stop; surface the escalation (not a block — the human takes over)
    message = (
        f"iteration ceiling ({ceiling}) reached; gate still RED "
        f"({', '.join(failed) or 'see .gate/verdict.json'}). ESCALATE written — a human must intervene."
    )
    if commit_failure:
        message += (
            f"\n\nWARNING: the ESCALATE file could not be COMMITTED ({commit_failure}). It is on disk, but "
            "until it is committed the lock is invisible to gate.py and to a worktree-based acceptance "
            "(§5.3/E-08) — commit it by hand: git add -- <path> && git commit -- <path>."
        )
    print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
