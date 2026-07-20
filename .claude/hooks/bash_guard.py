#!/usr/bin/env python3
"""bash_guard.py — PreToolUse(Bash) best-effort write-pattern denial (workflow v3, §5.2).

THIS IS ERGONOMICS — the trust anchor is gate.py (S8). A shell is Turing-complete; this
guard cannot and does not try to catch every mutation. Its job is a fast, explained "no"
for the obvious shell edits of protected paths (so the agent reaches for the owned path
instead of hand-editing). Anything that slips past is caught post-hoc: the gate diffs the
protected trees and the test inventory against the git baseline (§5.1, S8).

Fires only when a write operation's **resolved target** is a protected path — the command
is tokenised (`shlex`, quote-aware) and each write op is matched to *its* target, not to the
mere presence of `>`/`rm`/`mv` somewhere on the line. So `2>&1` (fd duplication, target
`&1`) and a `>` inside a quoted `-m "…"` message are not writes to a protected path and do
not fire. Because the guard is ergonomics and its cardinal sin is the false positive (a guard
that cries wolf on `git commit` trains the operator toward `--no-verify`), when a target
cannot be resolved with confidence it does **not** fire — the gate backstops the miss (S8).

Write ops understood: `>`/`>>` redirections (fd-prefixed forms too; fd duplication excluded),
`rm`, `mv`, `tee`, in-place `sed -i`, `git checkout -- <paths>`, `git restore <paths>`.
Protected paths: tests/**, specs/<ctx>/*.md, changes/*/criteria.md|change.md|verdict.md,
.claude/tools|hooks/**, .claude/settings.json, pyproject.toml.

Stdin: the PreToolUse payload. Stdout: nothing on allow; a permissionDecision=deny JSON on
a denied command. `--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

DESCRIBE = (
    "bash_guard.py: PreToolUse(Bash) — best-effort deny of shell writes to protected paths "
    "(tests, specs, .claude/tools|hooks, pyproject); ergonomics, trust is gate.py (S8)."
)

# Protected-path fragments. Substring match against a *resolved target* token (not the whole
# command line) — deliberately loose, best-effort tier.
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

# A redirection token: optional fd digits, `>` or `>>`, then an optional glued target.
# Anchored at ^ so a stray `>` inside a word (e.g. a `<brackets>` in a commit message that
# shlex merged into one token) does NOT read as a redirect.
REDIRECT = re.compile(r"^(\d*)(>>?)(.*)$")

# Shell control operators — a write op's argument list stops here.
CONTROL = frozenset({"|", "||", "&&", ";", "&", "|&"})


def _slice_until_control(tokens: list[str], start: int) -> list[str]:
    out: list[str] = []
    for tok in tokens[start:]:
        if tok in CONTROL:
            break
        out.append(tok)
    return out


def _write_targets(command: str) -> list[str]:
    """Best-effort list of resolved write-target tokens for the command.

    Empty when nothing writes, or when the command cannot be tokenised with confidence
    (unbalanced quotes) — precision bias: do not fire, the gate catches a miss (S8).
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []

    targets: list[str] = []
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]

        # Redirections: `>` `>>` `1>` `2>>` ... with the target glued or in the next token.
        m = REDIRECT.match(tok)
        if m and (m.group(1) or tok.startswith(">")):
            rest = m.group(3)
            if rest.startswith("&"):
                pass  # fd duplication (`2>&1`, `>&2`) — not a file write
            elif rest:
                targets.append(rest)
            elif i + 1 < n and tokens[i + 1] not in CONTROL:
                targets.append(tokens[i + 1])
                i += 1
            i += 1
            continue

        # Explicit mutators — the target is an argument, not the mere presence of the word.
        if tok in ("rm", "mv", "tee"):
            targets.extend(a for a in _slice_until_control(tokens, i + 1) if not a.startswith("-"))
        elif tok == "sed":
            args = _slice_until_control(tokens, i + 1)
            if any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
                targets.extend(a for a in args if not a.startswith("-"))
        elif tok == "git" and i + 1 < n and tokens[i + 1] == "checkout":
            args = _slice_until_control(tokens, i + 2)
            if "--" in args:  # `git checkout -- <paths>` restores files; a plain branch switch does not
                targets.extend(a for a in args[args.index("--") + 1 :] if not a.startswith("-"))
        elif tok == "git" and i + 1 < n and tokens[i + 1] == "restore":
            targets.extend(a for a in _slice_until_control(tokens, i + 2) if not a.startswith("-"))

        i += 1

    return targets


def offending(command: str) -> str | None:
    """Return the matched protected fragment, or None if no write hits a protected path."""
    for target in _write_targets(command):
        for frag in PROTECTED_FRAGMENTS:
            if frag in target:
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
