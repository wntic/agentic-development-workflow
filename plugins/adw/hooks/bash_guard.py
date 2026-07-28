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
`fixtures/a-change-spec.md`, and `pyproject.toml` does not match `pyproject.toml.bak` —
otherwise the guard dictates filenames, and its explanation misnames the real reason for a
denial (that misnaming is what sent a builder renaming a fixture that was in fact denied for
living under `.claude/tools`).

A real tokeniser, not a slice-and-regex scan (T06i). Six point fixes into the old hand-rolled
tokeniser each closed one variant and left the next to be discovered by the agent it blocked, so
the shape changed rather than growing a seventh patch: the command is now (1) stripped of heredoc
bodies, (2) masked — every quoted span and backslash-escape becomes an opaque word placeholder, so
a `;` or `>` inside a quoted argument can never read as an operator, (3) lexed with
`shlex(punctuation_chars=…)`, which yields the shell operators as tokens of their own even when
glued to a quoted word (`rm -rf "$S"; cp a b` — the defect that made `rm`'s argument slice swallow
the following `cp`'s SOURCE path and then blame it), and (4) split into simple commands at the
control operators, each parsed for its redirects and — in COMMAND POSITION only, past any
assignments and wrapper words — its mutator arguments. Command-position anchoring is why
`grep -rn rm tests/` no longer reads as a removal. Two indeterminacy rules keep the precision bias
(T06b): an unterminated quote drops the whole command, and an expansion the guard cannot evaluate
(`$VAR`, `` `cmd` ``, a leading `~`) in a target's FIRST component drops that target — that is the
variant which read every out-of-repo `"$SCRATCH/specs/…"` as an in-repo write. An expansion further
down leaves the location anchored by the literal components before it, so `rm tests/$name.py`
still fires. The 130 cases of `.claude/tools/test_enforcement.py` are the specification of what
the guard means and all of them survived the rewrite unchanged.

Every write op carries its OWN argument rule (T06k). `mv`'s "every non-flag argument is a
target" is right only because `mv` writes both ends; applying it to `cp` would make
`cp .claude/tools/gate.py /tmp/backup.py` a denial naming a path the command merely READS —
variant 6 of the family above, re-created by the *inventory* instead of by the parser. So the
copy family writes its destination only (the last operand, or the `-t` directory), `dd` writes
its `of=` operand (`if=` is a read), and `truncate` writes its file operands (`-s` takes a size,
`-r` a reference file to read). What this costs is coverage, not trust: an operation the guard
does not model is a miss, and a miss is caught post-hoc by the gate (S8) — a false positive is
not, it trains the bypass reflex instead.

`git rm` is a write, `--cached` included (T06l). It was a *documented* instruction in this repo
("use `git rm` so the commit is reviewable"), so protected files have actually been removed with
it while plain `rm` on the same path was denied — an inventory gap, not a parser one: `git rm`'s
argument rule is `rm`'s, both ends are removals, so unlike `cp` it has no read direction to get
wrong. `--cached` is ruled a write because *tracked* state is what every integrity check compares
(see `_git_rm_targets`).

Write ops understood: output redirections `>` `>>` `>|` `&>` `&>>` (fd-prefixed forms too; fd
duplication `>&` and every input redirect excluded — an input file is a read), `rm`, `mv`, `tee`,
in-place `sed -i`, `git checkout -- <paths>`, `git restore <paths>`, `git rm [--cached] <paths>`,
`cp`, `install`, `dd of=`, `truncate`.
Protected paths: tests/**, specs/<ctx>/*.md, changes/*/criteria.md|change.md|verdict.md,
.claude/tools|hooks/**, .claude/settings.json, pyproject.toml.

Role-aware owned-tree write path (T06d). The shell is not the roles' only write path any more —
they carry `Write`/`Edit` again, and `criteria_guard.py` applies THIS SAME lane table on that
path via `path_offence()` (the two are one rule, `owned_or_offending`, per C7). It was for a
while: a path-scoped `disallowedTools: Write(tests/**)` entry drops the tool WHOLESALE in a
subagent (the harness reads only the tool NAME, not the glob), so the roles had no editor and
reached even their own trees through `cat >` heredocs. Denying the shell too deadlocked them
into a hook bypass on every /implement run — hence this owned-tree carve-out, which outlives
the entries that motivated it because the shell remains a legitimate write path.
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
    ".claude/settings.json",
    "pyproject.toml",
)

# The plugin's OWN trees, protected only where they are part of THIS repository — the same
# split `gate.py`'s `protected_paths()` makes, for the same reason. Root-anchored (the leading
# slash), because with the plugin root at a repository root these are the generic names
# `tools/` and `hooks/`: depth-loose, they would deny a consumer every write to its own
# `src/tools/…`, which is the false-positive class this guard has already paid for four times
# (A5). Empty when the plugin lives outside the repo, i.e. whenever it is installed — there a
# write to the plugin resolves outside the repo root and never fires anyway (T06e).
PLUGIN_SUBTREES = ("tools", "hooks")


def _plugin_subtree_fragments(repo_root: str | None) -> tuple[str, ...]:
    if repo_root is None:
        return ()
    root = Path(__file__).resolve().parent.parent  # the plugin root: the dir holding hooks/
    try:
        rel = root.relative_to(Path(repo_root).resolve()).as_posix()
    except (ValueError, OSError):
        return ()
    prefix = "" if rel == "." else f"{rel}/"
    # No trailing slash, exactly as the `.claude/tools` fragment these replace: the DIRECTORY
    # itself is a write target (`cp -t tools /tmp/x.py`), and a directory fragment would need a
    # component below it to fire.
    return tuple(f"/{prefix}{sub}" for sub in PLUGIN_SUBTREES)


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

# --- the tokeniser (T06i) ---------------------------------------------------------------
#
# Punctuation characters shlex splits off as tokens of their own (`punctuation_chars`), plus the
# newline. With these, `;` / `&&` / `|` are operators even when glued to a quoted word, and each
# line of a multi-line command is its own simple command.
PUNCTUATION = "();<>|&\n"

# One shell operator inside a run of punctuation characters, longest form first: shlex hands a
# whole run back as a single token (`&&\n`, `>&`), so the run is re-split here instead of guessed.
OPERATOR = re.compile(r"\n+|;;|&&|\|\||\|&|&>>|&>|>>|>&|>\||<<<|<<|<&|[;&|<>()]")

# Operators that redirect output INTO a file: the operand is a write target.
WRITE_OPS = frozenset({">", ">>", ">|", "&>", "&>>"})

# Operators whose operand is not a file this command writes — an fd duplication (`2>&1`), an
# input redirect, a heredoc/herestring delimiter. The operand is consumed, never read as an
# argument (so a heredoc tag is not mistaken for a path).
READ_OPS = frozenset({">&", "<&", "<", "<<", "<<<"})

# Every other operator (`;` `;;` `&&` `||` `|` `|&` `&` `(` `)` newline) ends a simple command.

# Item kinds in the lexed stream.
WORD, OP = "word", "op"

# A leading `VAR=value` assignment and the wrapper words that precede the real command — both
# are skipped when looking for the command in command position, so `sudo rm …` and a `then rm …`
# are still seen as `rm`.
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
WRAPPERS = frozenset({"sudo", "env", "time", "nohup", "command", "exec", "builtin", "xargs", "then", "else", "do", "!"})

# An unexpanded parameter/command expansion inside a write target, and the neutral component it
# is replaced by (a character no path fragment can contain, so it matches nothing).
EXPANSION = re.compile(r"\$\{[^}]*\}|\$[\w@*#?!$-]+|\$|`[^`]*`|`")
PLACEHOLDER = "\x01"

# The placeholder a masked quoted span leaves in the text (see `_mask_quoted`).
MASK = re.compile("\x00(\\d+)\x00")

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


def _mask_quoted(command: str) -> tuple[str, dict[str, str]] | None:
    """`command` with every quoted span and backslash-escape replaced by a word placeholder.

    Quoting is what separates command from data, and the guard's whole false-positive family is
    data read as command. shlex is quote-aware for *word splitting* but cannot say whether the
    token it produced was quoted — so a `-m ";"` or a `grep ">" tests/x.py` would still reach the
    operator classifier as a bare `;` / `>`. Masking first makes the answer structural: after it,
    every punctuation character left in the text is unquoted, hence a real operator.

    The placeholder is `\\x00<n>\\x00` — no whitespace, no punctuation character — so it glues to
    its neighbours exactly as the quoted span did (`"$S"/x` stays one word) and is restored to the
    span's *content* once the words are split. None on an unterminated quote (precision bias, S8).
    """
    spans: dict[str, str] = {}
    out: list[str] = []
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "$" and i + 1 < n and command[i + 1] in "'\"":
            i += 1  # `$'…'` / `$"…"` still quote their content; the `$` is not an expansion
            continue
        if ch in "'\"":
            j = i + 1
            buf: list[str] = []
            while j < n and command[j] != ch:
                if ch == '"' and command[j] == "\\" and j + 1 < n:
                    buf.append(command[j + 1])
                    j += 2
                    continue
                buf.append(command[j])
                j += 1
            if j >= n:
                return None  # unterminated quote — do not fire
            key = f"\x00{len(spans)}\x00"
            spans[key] = "".join(buf)
            out.append(key)
            i = j + 1
        elif ch == "\\" and i + 1 < n:
            key = f"\x00{len(spans)}\x00"
            spans[key] = command[i + 1]
            out.append(key)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out), spans


def _unmask(word: str, spans: dict[str, str]) -> str:
    """`word` with every placeholder restored to the span's content."""
    return MASK.sub(lambda m: spans.get(m.group(0), ""), word)


def _lex(command: str) -> list[tuple[str, str]] | None:
    """`command` as a stream of (WORD | OP, text) items, or None if it cannot be lexed.

    Two passes: quoted spans are masked out (so no quoted `;` / `>` can pass for an operator),
    then shlex splits words and hands back runs of punctuation, which `OPERATOR` re-splits into
    the individual shell operators. This is what makes `rm -rf "$S"; cp a b` two commands — the
    defect that let `rm`'s argument list swallow the following `cp`'s SOURCE path and blame it.
    """
    masked = _mask_quoted(command)
    if masked is None:
        return None
    text, spans = masked
    lexer = shlex.shlex(text, punctuation_chars=PUNCTUATION, posix=True)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"  # the newline is an operator here, not whitespace
    lexer.commenters = ""  # `#` introduces no comment for this guard (shlex.split's behaviour)
    try:
        raw = list(lexer)
    except ValueError:
        return None
    stream: list[tuple[str, str]] = []
    for tok in raw:
        if tok and set(tok) <= set(PUNCTUATION):
            stream.extend((OP, op) for op in OPERATOR.findall(tok))
        else:
            stream.append((WORD, _unmask(tok, spans)))
    return stream


def _simple_commands(stream: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """`stream` split into simple commands at every separator operator, in execution order."""
    out: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for kind, val in stream:
        if kind == OP and val not in WRITE_OPS and val not in READ_OPS:
            if current:
                out.append(current)
            current = []
        else:
            current.append((kind, val))
    if current:
        out.append(current)
    return out


def _split_redirects(segment: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """One simple command's (words, redirect write targets).

    Redirections are lifted out wherever they sit, so the redirect's operand never lands in the
    command's argument list (`rm -f /tmp/a > log` writes `log`, it does not remove it) and an fd
    prefix (`2` in `2>&1`) is dropped from the words instead of reading as an argument.
    """
    words: list[str] = []
    targets: list[str] = []
    i, n = 0, len(segment)
    while i < n:
        kind, val = segment[i]
        if kind == WORD:
            words.append(val)
            i += 1
            continue
        if words and words[-1].isdigit():
            words.pop()  # the fd prefix of this redirection, not an argument
        operand = segment[i + 1][1] if i + 1 < n and segment[i + 1][0] == WORD else None
        if val in WRITE_OPS and operand is not None:
            targets.append(operand)
        i += 2 if operand is not None else 1
    return words, targets


def _command_and_args(words: list[str]) -> tuple[str | None, list[str]]:
    """The command in command position and its arguments (leading assignments/wrappers skipped).

    A mutator is only a mutator in command position: `grep -rn rm tests/` searches, it does not
    remove, and reading the mere presence of the word `rm` anywhere in the command is how a
    read-only argument came to be reported as a write target.
    """
    i = 0
    while i < len(words) and (ASSIGNMENT.match(words[i]) or words[i] in WRAPPERS):
        i += 1
    if i >= len(words):
        return None, []
    return words[i], words[i + 1 :]


def _paths(args: list[str]) -> list[str]:
    return [a for a in args if a and not a.startswith("-")]


# --- the write-op inventory: one argument rule per operation (T06k) ----------------------
#
# `rm`/`mv`/`tee` take EVERY non-flag argument because every one of them is written or removed
# in effect. The copy family is asymmetric — the sources are reads — so it needs its own rule
# (see the module docstring for why reusing `mv`'s would re-create variant 6).
COPY_CMDS = frozenset({"cp", "install"})

# `-t <dir>` / `--target-directory=<dir>`: the destination is the flag's operand, and the
# positional arguments are then ALL sources.
TARGET_DIR_FLAGS = frozenset({"-t", "--target-directory"})

# Copy-family options whose value is a separate word. Consumed so a value never reads as a path
# operand and never counts toward the operand total (`install -m 644 x dest`). The long spellings
# are usually written `--opt=value`, which is one word and drops out as a flag anyway.
COPY_VALUE_FLAGS = frozenset(
    {"-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g", "--group", "--strip-program"}
)

# `truncate -s <size>` takes a size, and `-r <file>` a reference file the command READS — both
# operands must be consumed, or the size would read as a path and the reference as a target.
TRUNCATE_VALUE_FLAGS = frozenset({"-s", "--size", "-r", "--reference"})


def _flag_value(args: list[str], names: frozenset[str]) -> str | None:
    """The operand of the first `--name value` / `--name=value` option in `args`, or None."""
    for i, arg in enumerate(args):
        if arg in names:
            return args[i + 1] if i + 1 < len(args) else None
        for name in names:
            if name.startswith("--") and arg.startswith(f"{name}="):
                return arg[len(name) + 1 :] or None
    return None


def _operands(args: list[str], value_flags: frozenset[str]) -> list[str]:
    """`args`' non-flag words, with the separate operand of each value-taking option consumed.

    Only the `-o value` / `--opt value` spelling needs consuming; `--opt=value` is a single word
    and drops out as a flag. A clustered short form (`truncate -cs 0 f`) is not modelled: its
    value survives as an operand, which can at worst add a target matching no protected fragment.
    """
    out: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg.startswith("-") and arg != "-":
            skip = arg in value_flags
            continue
        if arg:
            out.append(arg)
    return out


def _copy_target(args: list[str]) -> list[str]:
    """The single path a `cp`/`install` writes: the `-t` directory, else the LAST operand.

    The sources are reads and are never targets — that asymmetry is the whole point of T06k.
    Fewer than two operands and no `-t` names no destination (`cp x` is malformed), so nothing
    is reported rather than the one operand guessed at. `install -d a b` (create directories)
    is a partial miss for the same reason — the last operand only — never a false positive,
    since under `-d` every operand is a destination.
    """
    target_dir = _flag_value(args, TARGET_DIR_FLAGS)
    if target_dir is not None:
        return [target_dir]
    operands = _operands(args, COPY_VALUE_FLAGS)
    return operands[-1:] if len(operands) >= 2 else []


def _dd_target(args: list[str]) -> list[str]:
    """`dd`'s output file — the `of=` operand only; `if=` is the input, i.e. a read."""
    return [arg[len("of=") :] for arg in args if arg.startswith("of=") and arg[len("of=") :]]


def _git_rm_targets(args: list[str]) -> list[str]:
    """`git rm`'s pathspecs — every non-flag operand, with `--` respected (T06l).

    `git rm`'s rule is plain `rm`'s (both ends are removals, so there is no read direction to
    get wrong), which is why the miss was an inventory gap and not a parser question. Past a
    `--` every operand is a pathspec even when it looks like a flag, so the filter stops there.

    **`--cached` counts as a write.** It leaves the file on disk but removes it from the index,
    and *tracked* state is exactly what every integrity check compares — `integrity.protected-
    trees` diffs tracked paths, so untracking a protected file shows up there as a deletion.
    There is no legitimate reason for a non-owning role to untrack a protected path, and the
    operands are the same either way, so this is one rule rather than two to get wrong. Do not
    "fix" it into a read.
    """
    if "--" in args:
        return [a for a in args[args.index("--") + 1 :] if a]
    return _paths(args)


def _mutator_targets(cmd: str | None, args: list[str]) -> list[str]:
    """The paths `cmd` writes/removes, for the explicit mutators this guard understands."""
    if cmd in ("rm", "mv", "tee"):
        return _paths(args)
    if cmd in COPY_CMDS:
        return _copy_target(args)
    if cmd == "dd":
        return _dd_target(args)
    if cmd == "truncate":
        return _operands(args, TRUNCATE_VALUE_FLAGS)
    if cmd == "sed" and any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
        return _paths(args)
    if cmd == "git":
        sub = next((a for a in args if not a.startswith("-")), None)
        if sub == "checkout" and "--" in args:  # a plain branch switch writes no listed path
            return _paths(args[args.index("--") + 1 :])
        if sub == "restore":
            return _paths(args[args.index(sub) + 1 :])
        if sub == "rm":
            return _git_rm_targets(args[args.index(sub) + 1 :])
    return []


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

    One pass per simple command (T06i): heredoc bodies out, quoted spans masked, the stream split
    at the real control operators, then each simple command's redirects and — in command position
    only — its mutator arguments. Empty when nothing writes, or when the command cannot be lexed
    with confidence (unterminated quote) — precision bias: do not fire, the gate catches a miss (S8).
    """
    command = _strip_heredoc_bodies(command)  # a heredoc body is data, not command (T06g)
    command = command.replace("\\\n", " ")  # a line continuation is one command, not two
    stream = _lex(command)
    if stream is None:
        return []

    # A `cd` inside a subshell / command substitution is scoped in ways this guard does not
    # model, so its effect on the cwd is unknowable from the token stream: give up on relative
    # resolution for the whole command rather than resolve against the wrong directory.
    eff: str | None = cwd
    if GROUPING.search(command) and any(val in CD_BUILTINS | CD_OPAQUE for kind, val in stream if kind == WORD):
        eff = None

    targets: list[WriteTarget] = []
    for segment in _simple_commands(stream):
        words, redirects = _split_redirects(segment)
        targets.extend(WriteTarget(t, eff) for t in redirects)
        cmd, args = _command_and_args(words)
        # A directory change sets the effective cwd for every relative target that follows it.
        if cmd in CD_BUILTINS:
            eff = _cd_target(eff, args)
        elif cmd in CD_OPAQUE:
            eff = None
        else:
            targets.extend(WriteTarget(t, eff) for t in _mutator_targets(cmd, args))
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


def _anchorable(token: str) -> str | None:
    """`token` with its expansions neutralised, or None when its LOCATION is unknowable (T06i).

    The guard cannot expand `$VAR` or `~`, and joining an unexpanded token onto the repo root is
    how every out-of-repo `"$SCRATCH/specs/…/ESCALATE"` was read as an in-repo write (and blamed a
    path the command never touched). So: an expansion (or a `~`) in the token's FIRST component
    makes the whole path indeterminate — dropped, exactly like T06f's unknown cwd. An expansion
    further down leaves the location anchored by the literal components before it, so
    `rm tests/$name.py` still fires on `tests/`; the expansion itself becomes a component that
    matches no fragment.
    """
    if token.startswith("~"):
        return None
    if EXPANSION.search(token.split("/", 1)[0]):
        return None
    return EXPANSION.sub(PLACEHOLDER, token)


def _repo_relative(token: str, cwd: str | None, repo_root: str) -> str | None:
    """`token` as a POSIX path relative to `repo_root`, or None if it falls outside the repo.

    A relative target is resolved against the command's effective cwd (shell semantics, T06f);
    when that cwd is indeterminate the target is dropped — the same "do not fire" answer as a
    target outside the tree. Symlinks are canonicalised so a macOS `/tmp` (→ `/private/tmp`)
    scratch dir is correctly seen as outside the repo tree.
    """
    try:
        abs_target = Path(token)
        if not abs_target.is_absolute():
            if cwd is None:
                return None  # effective cwd unknown — never guess (T06f)
            abs_target = Path(cwd) / abs_target
        rel = abs_target.resolve().relative_to(Path(repo_root).resolve())
    except (ValueError, OSError):
        return None  # ValueError: not under the repo root — do not fire
    return rel.as_posix()


def _matches(frag: str, candidate: str) -> bool:
    """True when `candidate` (a POSIX path) contains `frag` as a run of whole components.

    A fragment is a path relative to the repo root, so it matches on component boundaries and
    never as a bare substring (T06f): `change.md` matches `specs/x/changes/001-y/change.md`
    but not `fixtures/a-change-spec.md`; `pyproject.toml` does not match `pyproject.toml.bak`.
    A trailing slash marks a DIRECTORY fragment — it matches only with something below it, so
    `tests/` fires on `tests/x.py` at any depth but not on a file merely named `tests`.

    A LEADING slash marks a ROOT-ANCHORED fragment: `/tools` fires on `tools/gate.py` and on
    `tools` itself, and never on `src/tools/helper.py`. The depth-loose default is right for the names this
    workflow owns outright (`tests/`, `criteria.md`), and wrong for the generic names the
    plugin's own trees carry once the plugin root is a repository root (`tools`, `hooks`) —
    at depth those belong to whoever's project this is (see `_plugin_subtree_fragments`).
    """
    want = [p for p in frag.split("/") if p]
    parts = [p for p in candidate.split("/") if p and p != "."]
    tail = 1 if frag.endswith("/") else 0  # a directory fragment needs a component below it
    if frag.startswith("/"):
        return len(parts) >= len(want) + tail and parts[: len(want)] == want
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


def _protected_for(role: str | None, repo_root: str | None = None) -> tuple[str, ...]:
    """The protected fragments that apply to the acting role.

    Universal set for everyone, plus the plugin's own trees when they are inside this repo;
    `src/**` is added for the two protected-tree agents so the implementer's lane is closed to
    them (it stays open to the implementer and the default).
    """
    fragments = (*PROTECTED_FRAGMENTS, *_plugin_subtree_fragments(repo_root))
    if role in SRC_CLOSED_TO:
        return (*fragments, SRC_FRAGMENT)
    return fragments


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
    cwd = cwd or os.getcwd()
    for target in _write_targets(command, cwd):
        token = _anchorable(target.token)
        if token is None:
            continue  # an unexpanded expansion anchors the path nowhere (T06i)
        if repo_root is None:
            candidate = token  # fallback: the raw token, root-insensitive
        else:
            rel = _repo_relative(token, target.cwd, repo_root)
            if rel is None:
                continue  # outside the repo tree, or unresolvable — never fires (T06e/T06f)
            candidate = rel
        frag = owned_or_offending(candidate, role, repo_root=repo_root)
        if frag is not None:
            return frag
    return None


def owned_or_offending(candidate: str, role: str | None, *, repo_root: str | None) -> str | None:
    """The protected fragment `candidate` hits that `role` does not own, or None.

    `candidate` is a repo-relative POSIX path (or, in the `repo_root is None` fallback, a raw
    token). This is the ONE implementation of "owned overrides protected" (T06d) — both write
    paths route through it: `offending()` for the shell, `path_offence()` for Edit|Write. Per C7
    the table has one home, and so does the rule that reads it: a lane opened for the shell and
    forgotten for the editor is exactly the drift this function exists to make impossible.
    """
    if any(_matches(frag, candidate) for frag in ROLE_OWNED.get(role or "", ())):
        return None  # the acting role owns this tree — sanctioned write path
    for frag in _protected_for(role, repo_root):
        if _matches(frag, candidate):
            return frag
    return None


def path_offence(file_path: str, role: str | None, *, cwd: str | None = None) -> str | None:
    """The Edit|Write counterpart of `offending()`: the fragment an edited file hits, or None.

    Same table, same owned-overrides-protected rule, and **no tokenising** — an Edit/Write
    payload names its target outright in `file_path`, so the shell grammar that produced seven
    rounds of false positives (A5) has no part in this path at all.

    `file_path` is expected absolute (the Edit/Write tools require it). A relative one cannot be
    anchored without the caller's effective cwd, so it is dropped — the same "do not fire"
    answer T06f gives an unknown cwd, never a guess.
    """
    root = _repo_root(cwd or os.getcwd())
    if root is None:
        candidate = file_path  # fallback: root-insensitive, exactly as `offending()` degrades
    else:
        rel = _repo_relative(file_path, None, root)
        if rel is None:
            return None  # outside the repo tree, or relative-and-unanchorable (T06e/T06f)
        candidate = rel
    return owned_or_offending(candidate, role, repo_root=root)


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
