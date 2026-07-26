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

Repo-root anchored (T06e). A protected fragment (`tests/`, `specs/`, `criteria.md`, …) is a
path *relative to the repo root*, so the match must be too. Each resolved target is made
absolute (a relative target against the acting `cwd`) and the guard fires ONLY when that
absolute path falls **under the repo root** AND its repo-relative form matches a protected
fragment. A write whose target is outside the repo tree — a `/tmp` scratch dir, the user's
home, a sibling repo — never fires, even if the path merely *contains* `tests/` somewhere.
The root is `CLAUDE_PROJECT_DIR` (set by settings.json in production) or the git toplevel of
the cwd; when neither can be resolved the guard degrades to the pre-T06e root-insensitive
match on the raw target token — a documented conservative fallback, never a guess at the
root (the gate backstops either way, S8).

`cd`-aware resolution (T06f). "Relative to the repo root" is only meaningful once a relative
target is resolved against the cwd the write actually happens in, and the `cwd` in the
PreToolUse payload is the **session** cwd — not the effective one after `cd /tmp/scratch &&`.
So the tokeniser tracks the command's effective cwd across the `cd <dir> && …` / `pushd`
idiom agents emit; a relative target is resolved against that, which lets a write into a
scratch copy of the tree fall outside the repo and never fire (it twice denied the mutation
pass of an adversarial evaluator, which then rerouted — the guard training the bypass reflex
it exists to prevent). This is NOT a shell: whenever the effective cwd cannot be determined
with confidence — a bare `cd`, `cd -`, an expansion/glob in the directory, `popd`, or a `cd`
inside a subshell / command substitution — the relative target is **dropped, not guessed**
(T06b precision bias). Absolute targets are unaffected, so T06e's anchoring is intact, and
`cd .. && … > <repo>/tests/x` still resolves back into the repo and still fires: this narrows
resolution, never ownership.

Heredoc **bodies** are not part of the command (T06g). `git commit -F - <<'EOF' … EOF` is how
every agent here writes a multi-line message, and the body is data: a `>` in the prose is not a
redirect. So the bodies of `<<TAG` / `<<'TAG'` / `<<"TAG"` / `<<-TAG` (any number of them, in
the order bash reads them) are removed before tokenising, up to the terminating `TAG` line —
while the heredoc's own command line stays, so a real redirect there (`cat > tests/x.py <<'EOF'`,
`cat <<'EOF' > tests/x.py`) still fires. An unterminated heredoc leaves the whole remainder as
body: nothing fires (precision bias again — the gate backstops, S8). `<<<` is a herestring, a
different construct, and is left alone.

Fragments match on **component boundaries**, never as bare substrings (T06f). A fragment is
a path relative to the repo root, so `change.md` matches `…/change.md` but not
`fixtures/users-002-change.md`, and `pyproject.toml` does not match `pyproject.toml.bak` —
otherwise the guard dictates filenames, and its explanation misnames the real reason for a
denial (that misnaming is what sent a builder renaming a fixture that was in fact denied for
living under `.claude/tools`).

Write ops understood: `>`/`>>` redirections (fd-prefixed forms too; fd duplication excluded),
`rm`, `mv`, `tee`, in-place `sed -i`, `git checkout -- <paths>`, `git restore <paths>`.
Protected paths: tests/**, specs/<ctx>/*.md, changes/*/criteria.md|change.md|verdict.md,
.claude/tools|hooks/**, .claude/settings.json, pyproject.toml.

Role-aware owned-tree write path (T06d). The cycle subagents have NO Write/Edit tool at all
(a path-scoped `disallowedTools: Write(...)` entry drops the tool wholesale in a subagent —
the harness reads only the tool NAME, not the glob), so the shell is their ONLY write path to
the very trees they own. Denying it deadlocked them into a hook bypass on every /implement run.
So the guard reads the acting role from the PreToolUse payload's `agent_type` (the base hook
input carries it, same field SubagentStop uses, F-2 — namespaced as `adw:<role>` when the
workflow is installed as a plugin, bare when loaded from project config, T15/D1) and does NOT
fire when the target is that role's OWNED tree: test-author -> tests/** + pyproject.toml/uv.lock;
implementer -> src/**;
evaluator -> criteria.md/verdict.md. A write to a NON-owned protected tree still fires (T06b
precision). `src/**` is additionally closed to the two protected-tree agents (D4: src is the
implementer's lane) — but stays open to the implementer and to an unidentified/default session,
so the implementer's critical write path never depends on agent_type resolving. When `agent_type`
is absent the guard degrades to the pre-T06d behavior (every protected tree fires), which is
safe: it re-opens the friction, it never opens a foreign tree.

Stdin: the PreToolUse payload. Stdout: nothing on allow; a permissionDecision=deny JSON on
a denied command. `--describe` prints a one-line self-description.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DESCRIBE = (
    "bash_guard.py: PreToolUse(Bash) — best-effort, role-aware deny of shell writes to "
    "protected paths UNDER the repo root (never fires on the acting role's OWNED tree, nor "
    "outside the repo); ergonomics, trust is gate.py (S8)."
)

# Protected-path fragments. Component-wise match against the target's *repo-relative* path
# (T06e + T06f): the fragment is anchored to the repo root, so a `/tmp/.../tests/x` outside the
# tree never fires, and it matches whole path components, so a filename that merely *contains*
# `change.md` is not a change.md. Deliberately loose about depth within the repo — a fragment
# matches at any level — because this is the best-effort tier.
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

# The owned-tree write path (T06d). Per acting role (`agent_type`), the fragments of a target
# that the role legitimately writes — a target matching one is allowed even if it also matches
# a PROTECTED_FRAGMENTS entry (owned overrides protected). Role names match the agent
# frontmatter `name`s (and subagent_stop.py's IMPLEMENTER_AGENT) — BARE names: the payload's
# plugin namespace is stripped by acting_role() before the lookup (T15/D1).
ROLE_OWNED = {
    "test-author": ("tests/", "pyproject.toml", "uv.lock"),
    "evaluator": ("criteria.md", "verdict.md"),
    "implementer": ("src/",),
}

# `src/**` is the implementer's lane (D4). It is NOT in PROTECTED_FRAGMENTS (so the implementer
# and the default session write it freely, no agent_type dependency), but it IS closed to the
# other two cycle roles — a test-author or evaluator writing src is denied.
SRC_CLOSED_TO = ("test-author", "evaluator")
SRC_FRAGMENT = "src/"

# A redirection token: optional fd digits, `>` or `>>`, then an optional glued target.
# Anchored at ^ so a stray `>` inside a word (e.g. a `<brackets>` in a commit message that
# shlex merged into one token) does NOT read as a redirect.
REDIRECT = re.compile(r"^(\d*)(>>?)(.*)$")

# Shell control operators — a write op's argument list stops here.
CONTROL = frozenset({"|", "||", "&&", ";", "&", "|&"})

# `cd`-awareness (T06f). Builtins that move the cwd (`cd <dir>`, `pushd <dir>`) and the one that
# pops a stack this guard does not model (`popd` → cwd indeterminate).
CD_BUILTINS = frozenset({"cd", "pushd"})
CD_OPAQUE = frozenset({"popd"})

# Grouping / substitution punctuation. `(cd x && …)` scopes the cd to a subshell and `$(cd …)`
# hides it entirely — beyond this guard's one-line model, so a `cd` in such a command makes the
# effective cwd indeterminate for the whole command (relative targets are then dropped).
GROUPING = re.compile(r"[(){}`]|\$\(")

# A `cd` argument that cannot be evaluated without a shell: expansion, glob, `~`, backtick.
OPAQUE_DIR = re.compile(r"[$*?`~]")

# A heredoc opener at a given offset: `<<`, an optional tab-stripping `-`, then the delimiter
# either quoted (`'TAG'` / `"TAG"`, body not expanded) or bare (optionally backslash-escaped).
HEREDOC_OPEN = re.compile(r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\?([A-Za-z_][\w.\-]*))")


@dataclass(frozen=True)
class WriteTarget:
    """A write op's target token plus the cwd a RELATIVE token resolves against (T06f).

    `cwd is None` means the effective cwd is indeterminate (an unhandled `cd` idiom): the
    relative target is then dropped rather than guessed (precision bias — the gate backstops,
    S8). An ABSOLUTE token ignores `cwd`, so cd-tracking never loosens T06e's anchoring.
    """

    token: str
    cwd: str | None


def _heredoc_tags(line: str) -> list[tuple[str, bool]]:
    """The heredoc delimiters opened on `line`, in the order bash reads their bodies.

    Each entry is `(tag, strips_tabs)` — `strips_tabs` for the `<<-TAG` form, whose terminator
    may be indented. Quoting is tracked so a `<<` inside a quoted argument is not read as an
    opener; `<<<` (herestring) is skipped, it is a different construct. Per line only: this is
    a tokeniser, not a shell.
    """
    tags: list[tuple[str, bool]] = []
    quote: str | None = None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if quote is not None:
            quote = None if ch == quote else quote
            i += 1
        elif ch in "'\"":
            quote = ch
            i += 1
        elif ch == "\\":
            i += 2
        elif line.startswith("<<<", i):
            i += 3  # herestring — already one shlex word, no body follows
        elif line.startswith("<<", i):
            m = HEREDOC_OPEN.match(line, i)
            if m is None:
                i += 2  # not a delimiter this guard recognises (`<<` alone, an expansion, …)
                continue
            tag = next(g for g in m.groups()[1:] if g is not None)
            tags.append((tag, bool(m.group(1))))
            i = m.end()
        else:
            i += 1
    return tags


def _strip_heredoc_bodies(command: str) -> str:
    """`command` with every heredoc body (and its terminator line) removed (T06g).

    A heredoc body is data, not command: the `>` in a commit message's prose is not a redirect.
    The opener's own line is KEPT, so a redirect sitting there still reads as one. An
    unterminated heredoc swallows the remainder of the command — precision bias, the gate
    backstops the miss (S8).
    """
    if "<<" not in command:
        return command
    kept: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in command.split("\n"):
        if pending:
            tag, strips_tabs = pending[0]
            if (line.strip() if strips_tabs else line.rstrip()) == tag:
                pending.pop(0)
            continue  # body lines and the terminator are not part of the command
        kept.append(line)
        pending.extend(_heredoc_tags(line))
    return "\n".join(kept)


def _slice_until_control(tokens: list[str], start: int) -> list[str]:
    out: list[str] = []
    for tok in tokens[start:]:
        if tok in CONTROL:
            break
        out.append(tok)
    return out


def _cd_target(cwd: str | None, args: list[str]) -> str | None:
    """The cwd after a `cd`/`pushd`, or None when it cannot be determined with confidence.

    None for a bare `cd` (the home directory), `cd -` (the previous directory), an argument
    holding an expansion/glob/`~`, or a `cd` whose own starting point is already lost.
    """
    dirs = [a for a in args if not a.startswith("-")]
    if cwd is None or len(dirs) != 1 or OPAQUE_DIR.search(dirs[0]):
        return None
    return dirs[0] if Path(dirs[0]).is_absolute() else str(Path(cwd) / dirs[0])


def _write_targets(command: str, cwd: str) -> list[WriteTarget]:
    """Best-effort list of write targets for the command, each with its effective cwd.

    Empty when nothing writes, or when the command cannot be tokenised with confidence
    (unbalanced quotes) — precision bias: do not fire, the gate catches a miss (S8).
    """
    command = _strip_heredoc_bodies(command)  # a heredoc body is data, not command (T06g)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []

    # A `cd` inside a subshell / command substitution is scoped in ways this guard does not
    # model, so its effect on the cwd is unknowable from the token stream: give up on relative
    # resolution for the whole command rather than resolve against the wrong directory.
    eff: str | None = cwd
    if GROUPING.search(command) and any(tok.strip("(){}") in CD_BUILTINS | CD_OPAQUE for tok in tokens):
        eff = None

    targets: list[WriteTarget] = []
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]

        # Directory changes: the effective cwd for every relative target that follows.
        if tok in CD_BUILTINS:
            eff = _cd_target(eff, _slice_until_control(tokens, i + 1))
            i += 1
            continue
        if tok in CD_OPAQUE:
            eff = None
            i += 1
            continue

        # Redirections: `>` `>>` `1>` `2>>` ... with the target glued or in the next token.
        m = REDIRECT.match(tok)
        if m and (m.group(1) or tok.startswith(">")):
            rest = m.group(3)
            if rest.startswith("&"):
                pass  # fd duplication (`2>&1`, `>&2`) — not a file write
            elif rest:
                targets.append(WriteTarget(rest, eff))
            elif i + 1 < n and tokens[i + 1] not in CONTROL:
                targets.append(WriteTarget(tokens[i + 1], eff))
                i += 1
            i += 1
            continue

        # Explicit mutators — the target is an argument, not the mere presence of the word.
        if tok in ("rm", "mv", "tee"):
            targets.extend(WriteTarget(a, eff) for a in _slice_until_control(tokens, i + 1) if not a.startswith("-"))
        elif tok == "sed":
            args = _slice_until_control(tokens, i + 1)
            if any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
                targets.extend(WriteTarget(a, eff) for a in args if not a.startswith("-"))
        elif tok == "git" and i + 1 < n and tokens[i + 1] == "checkout":
            args = _slice_until_control(tokens, i + 2)
            if "--" in args:  # `git checkout -- <paths>` restores files; a plain branch switch does not
                targets.extend(WriteTarget(a, eff) for a in args[args.index("--") + 1 :] if not a.startswith("-"))
        elif tok == "git" and i + 1 < n and tokens[i + 1] == "restore":
            targets.extend(WriteTarget(a, eff) for a in _slice_until_control(tokens, i + 2) if not a.startswith("-"))

        i += 1

    return targets


def _repo_root(cwd: str) -> str | None:
    """The repo root: `CLAUDE_PROJECT_DIR` (production) or the git toplevel of `cwd`.

    None when neither can be resolved — the caller then degrades to the pre-T06e
    location-insensitive substring match (a documented conservative fallback, not a guess).
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _repo_relative(target: WriteTarget, repo_root: str) -> str | None:
    """`target` as a POSIX path relative to `repo_root`, or None if it falls outside the repo.

    A relative target is resolved against the command's effective cwd (shell semantics, T06f);
    when that cwd is indeterminate the target is dropped — the same "do not fire" answer as a
    target outside the tree. Symlinks are canonicalised so a macOS `/tmp` (→ `/private/tmp`)
    scratch dir is correctly seen as outside the repo tree.
    """
    try:
        abs_target = Path(target.token)
        if not abs_target.is_absolute():
            if target.cwd is None:
                return None  # effective cwd unknown — never guess (T06f)
            abs_target = Path(target.cwd) / abs_target
        rel = abs_target.resolve().relative_to(Path(repo_root).resolve())
    except (ValueError, OSError):
        return None  # ValueError: not under the repo root — do not fire
    return rel.as_posix()


def _matches(frag: str, candidate: str) -> bool:
    """True when `candidate` (a POSIX path) contains `frag` as a run of whole components.

    A fragment is a path relative to the repo root, so it matches on component boundaries and
    never as a bare substring (T06f): `change.md` matches `specs/x/changes/001-y/change.md`
    but not `fixtures/users-002-change.md`; `pyproject.toml` does not match `pyproject.toml.bak`.
    A trailing slash marks a DIRECTORY fragment — it matches only with something below it, so
    `tests/` fires on `tests/x.py` at any depth but not on a file merely named `tests`.
    """
    want = [p for p in frag.split("/") if p]
    parts = [p for p in candidate.split("/") if p and p != "."]
    tail = 1 if frag.endswith("/") else 0  # a directory fragment needs a component below it
    return any(parts[i : i + len(want)] == want for i in range(len(parts) - len(want) - tail + 1))


def acting_role(agent_type: str | None) -> str | None:
    """The BARE role name behind a payload's `agent_type` (T15/D1).

    Shipped as a plugin, an agent arrives namespaced — `adw:test-author` — while a
    project-config load reports the bare `test-author`. Both name the same role, so the lookup
    keys on the last `:`-separated segment. Comparing the whole string would be silently wrong
    exactly where it matters: installed, ROLE_OWNED would miss for every cycle role and all
    three would lose their owned-tree write path (T06d), which is the only write path they
    have — and no test in the workflow's own repo, which loads via project config, would see it.
    """
    if not agent_type:
        return None
    return agent_type.rsplit(":", 1)[-1] or None


def _protected_for(role: str | None) -> tuple[str, ...]:
    """The protected fragments that apply to the acting role.

    Universal set for everyone; `src/**` is added for the two protected-tree agents so the
    implementer's lane is closed to them (it stays open to the implementer and the default).
    """
    if role in SRC_CLOSED_TO:
        return PROTECTED_FRAGMENTS + (SRC_FRAGMENT,)
    return PROTECTED_FRAGMENTS


def offending(
    command: str,
    role: str | None = None,
    *,
    repo_root: str | None = None,
    cwd: str | None = None,
) -> str | None:
    """Return the matched protected fragment, or None if no write hits a protected path.

    The match is anchored to `repo_root` (T06e): a target is checked by its repo-relative path
    — a relative one resolved against the command's effective cwd (T06f) — and a target outside
    the repo tree never fires. When `repo_root` is None the guard degrades to the pre-T06e
    root-insensitive match on the raw target token (conservative fallback).

    A target the acting `role` OWNS is never offending (owned overrides protected, T06d) — so
    the owner reaches its tree through the shell instead of a hook bypass.
    """
    owned = ROLE_OWNED.get(role or "", ())
    protected = _protected_for(role)
    cwd = cwd or os.getcwd()
    for target in _write_targets(command, cwd):
        if repo_root is None:
            candidate = target.token  # fallback: the raw token, root-insensitive
        else:
            rel = _repo_relative(target, repo_root)
            if rel is None:
                continue  # outside the repo tree, or unresolvable — never fires (T06e/T06f)
            candidate = rel
        if any(_matches(frag, candidate) for frag in owned):
            continue  # the acting role owns this tree — sanctioned write path
        for frag in protected:
            if _matches(frag, candidate):
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
    role = acting_role(payload.get("agent_type"))  # `adw:implementer` and `implementer` are one role
    cwd = payload.get("cwd") or os.getcwd()
    frag = offending(command, role, repo_root=_repo_root(cwd), cwd=cwd)
    if frag is not None:
        deny(
            f"shell write to a protected path ({frag}) denied for role "
            f"'{role or 'default'}'. Owned write paths: test-author -> tests/** + "
            "pyproject.toml/uv.lock; implementer -> src/**; evaluator -> "
            "criteria.md/verdict.md; spec prose via /adw:spec. This is only ergonomics — the "
            "gate diffs these trees against the baseline regardless (S8)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
