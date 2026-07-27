# T06g — bash_guard must not tokenise heredoc bodies

## Goal
`bash_guard` parses a heredoc's *body* as part of the command, so ordinary prose inside a commit
message is read as a shell redirect and the commit is denied. Found building T06f (its finding 3),
which hit it on its own commit message.

Confirmed reproduction (`offending()` with `repo_root=cwd=<repo>`, role `v3-builder`):

```
git commit -F - <<'EOF'
fix: something

the prose mentions > tests/x.py as an example
EOF
                                        →  DENIED (tests/)

same heredoc with no `>` token in the body →  ALLOWED
```

Two things make this worse than a normal false positive:

- **It fires on message *content*, not command shape.** The identical `git commit -F - <<'EOF'`
  idiom works until the day the message happens to contain `>` followed by a protected path — so it
  is unreproducible-looking and burns an agent's turns before anyone diagnoses it.
- **It hits the repo's own commit convention.** Multi-line commit messages are how every agent and
  command in this repo commits. T06b fixed the quoted `-m "…"` case; the heredoc case survived it.

Same family as T06b/T06e/T06f: the tokeniser treating something that is not a write target as one.
This is the last known member of that family; the fix is one function.

## Depends on
T06, T06b (the precision-first tokeniser), T06f (current `_write_targets` + effective-cwd shape —
build on it, do not revert it).

## Read first
- `.claude/hooks/bash_guard.py` — `_write_targets()`: the `shlex.split` call and the `REDIRECT`
  match that consumes the next token as a target.
- `tasks/T06f-bash-guard-cd-awareness.md` finding 3 (the reproduction) and Part A's precision bias.
- `PRINCIPLES.md` S8 — the guard is ergonomics; a false positive costs more than a miss because it
  trains the bypass reflex.

## Deliverables
- `.claude/hooks/bash_guard.py` — strip heredoc **bodies** before tokenising: `<<TAG`, `<<'TAG'`,
  `<<"TAG"`, and the tab-stripping `<<-TAG`, up to the terminating `TAG` line (for `<<-` the
  terminator may be indented). Handle more than one heredoc in a single command. Keep T06f's
  effective-cwd tracking and T06b's precision bias intact.

  **The redirect on the heredoc's own command line is OUTSIDE the body and must still fire** — this
  is the whole correctness boundary of the task:
  - `cat > tests/x.py <<'EOF' … EOF` → **denied** (the `>` precedes the heredoc tag)
  - `cat <<'EOF' > tests/x.py … EOF` → **denied** (the `>` follows the tag, still on the command line)
  - `git commit -F - <<'EOF' … > tests/x.py … EOF` → **allowed** (inside the body)
- `.claude/tools/test_enforcement.py` — cases for each of the three above, plus: an unterminated
  heredoc (no closing tag → treat the remainder as body, do not fire — precision bias); two heredocs
  in one command where the *second* body contains a protected token; `<<-EOF` with an indented
  terminator; and a regression that the T06f cd-awareness cases still behave identically.

## Verification
- `uv run pytest .claude/tools/test_enforcement.py` green (101 cases today, plus the new ones).
- The exact reproduction above replayed through the real hook (simulated PreToolUse payload) → exit
  0, empty stdout.
- `cat > tests/x.py <<'EOF'…` through the real hook, non-owner role → still denied. If this one
  regresses the task has failed, however green the suite looks.
- `uv run pytest .claude/tools` — whole meta suite still green (247 today).

## Out of scope / Escalate if
- Do NOT implement a shell parser. Handle the heredoc forms bash actually accepts; anything
  ambiguous (unterminated, nested quoting you cannot resolve) degrades to **not firing**, and the
  gate's protected-tree diff backstops (S8).
- Do NOT touch the `cd`/effective-cwd logic, the fragment-component matching, or the role-owned
  allowance — all three just landed in T06f and are separately tested.
- Note `<<<` (herestring) is a *different* construct and is already one shlex word; if you find it
  mis-tokenising, record it as a finding rather than widening this task.
- Bear in mind the guard covers **Bash only** — the `Write` tool has its own path (T06f finding 1).
  If the fix tempts you toward "agents can just use Write", that is not a fix; the shell path must
  work for the roles that own their trees (T06d).
