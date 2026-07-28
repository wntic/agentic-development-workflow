#!/usr/bin/env python3
"""criteria_guard.py — PreToolUse(Edit|Write) ergonomics: file ownership, then criteria policy.

THIS IS ERGONOMICS — a fast, explained denial so the agent learns "why not" *before*, not
after. The trust anchor is gate.py's integrity check against the git baseline (S8): a hook
bypass (Bash, conftest, editing the gate itself) only gets the result invalidated at the gate.

TWO policies, in this order:

1. **Role lane (T06d's table, on the Edit|Write path).** A role may write only the trees it
   owns: test-author -> tests/** + pyproject.toml/uv.lock; implementer -> src/**;
   evaluator -> criteria.md/verdict.md. A write to a protected tree the acting role does not
   own is denied. The lane table is IMPORTED from `bash_guard`, never restated (C7: one home) —
   so the shell path and the editor path cannot drift apart.

   Why this policy lives here at all. Until this change the three cycle roles carried
   path-scoped `disallowedTools` entries (`Write(tests/**)`, …) that were believed to enforce
   the lanes. They did not: the harness reads only the tool NAME, not the glob, so a
   path-scoped entry drops `Write`/`Edit` WHOLESALE. The measured consequence was that the
   roles had no editor at all, wrote every file through `cat >` heredocs, and this hook's
   `Edit|Write` matcher could never fire for the very agents it was written for. Removing
   those entries gives the roles their editor back — and moves the lane question here, where
   the payload carries a literal `file_path` and there is no shell grammar to tokenise (which
   is the whole false-positive class bash_guard has paid for seven times, A5).

   Deliberate asymmetry with bash_guard: when `agent_type` is ABSENT this guard allows, where
   bash_guard denies. An unidentified caller is the main session — the human's own hands and
   `/adw:spec`, whose lane IS spec prose. Denying the editor there is not ergonomics but
   obstruction, and it would block `/adw:spec` from authoring the change dir. The lanes exist
   to keep two SUBAGENTS out of each other's trees (D3/D4); nothing is unprotected either way,
   because the gate diffs the protected trees against the baseline regardless (S8).

2. **criteria.md content policy (spec §5.2)**, applied after the lane check passes:
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

# The sibling hook, imported for the role/lane table and the one implementation of
# "owned overrides protected" (C7 — the table has exactly one home, `bash_guard.ROLE_OWNED`).
# `hooks/` is sys.path[0] whenever this file is run as a script, which is the only way a hook
# ever runs — including under `-S`, which the stdlib-only test uses. Imported at module scope on
# purpose: if it cannot be imported, this hook must fail LOUDLY (a visible hookError) rather
# than silently degrade to allowing every foreign-lane write (notes/19 — an unanswerable check
# must never read as "nothing is wrong"). Both files are anchored, so a missing one is also RED.
import bash_guard

DESCRIBE = (
    "criteria_guard.py: PreToolUse(Edit|Write) — denies a write to a protected tree the acting "
    "role does not own, then allows only checkbox state flips in criteria.md; reword/renumber "
    "-> /spec; creation only before the baseline tag (ergonomics, trust is gate.py, S8)."
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
    if not file_path:
        return 0  # nothing named — allow

    # --- policy 1: the role lane ---------------------------------------------------------
    # `adw:implementer` and `implementer` are one role (T15/D1). A role of None is the main
    # session — the human and /adw:spec — and is NOT lane-checked; see the module docstring for
    # why this is deliberately the opposite of bash_guard's default.
    role = bash_guard.acting_role(payload.get("agent_type"))
    if role is not None:
        frag = bash_guard.path_offence(file_path, role, cwd=payload.get("cwd"))
        if frag is not None:
            deny(
                f"write to a protected path ({frag}) denied for role '{role}'. Owned write "
                "paths: test-author -> tests/** + pyproject.toml/uv.lock; implementer -> "
                "src/**; evaluator -> criteria.md/verdict.md; spec prose via /adw:spec. Do not "
                "route around this through Bash — bash_guard applies the same table, and the "
                "gate diffs these trees against the baseline regardless (S8). If the contract "
                "genuinely does not fit, raise a CONTRACT-CHANGE instead of a workaround."
            )

    # --- policy 2: criteria.md content ---------------------------------------------------
    if not is_criteria(file_path):
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
