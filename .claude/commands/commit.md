---
description: Lint, stage, and commit specified files or previously introduced changes
---

> Invoked as `/adw:commit` when the workflow is installed as a plugin, `/commit` when it is
> loaded from a project's own `.claude/` — as in the workflow's own repo. The two forms name
> this same file; other commands are referred to below in the `/adw:` form.

## Argument interpretation

`$ARGUMENTS` can be:
- File paths / directories (e.g. `module1.py package1/`) — commit exactly those
- A description like `changes that you introduced` — resolve to the files you edited in this session

If `$ARGUMENTS` is empty, fall back to whatever is already staged.

## Steps

### 1. Resolve target files

If arguments are file paths: use them directly.
If arguments describe prior changes: recall which files you created or modified in this conversation and use those.

### 2. Run ruff

Detect the package manager:
- If `uv.lock` exists → `uv run ruff check --fix <files> && uv run ruff format <files>`
- If `poetry.lock` exists → `poetry run ruff check --fix <files> && poetry run ruff format <files>`
- Fallback → `ruff check --fix <files> && ruff format <files>`

If ruff reports unfixable errors, stop and report them to the user before proceeding.

### 3. Stage files

```
git add <resolved files>
```

### 4. Write the commit message

Inspect the staged diff with `git diff --staged`, then compose a message following these rules:

**Subject line**
- Imperative mood ("This commit will…" completes the sentence)
- ≤50 chars ideally, hard limit 72
- Capitalize first word, no trailing period
- Specific enough to understand without reading the diff

**Verb choices** — prefer specific over vague:

| Vague | Better |
|---|---|
| `Update X` | `Refactor X`, `Simplify X`, `Optimize X` |
| `Fix X` | `Handle X`, `Prevent X`, `Resolve X` |
| `Change X` | `Replace X`, `Rename X`, `Move X` |
| `Add X` | `Introduce X`, `Expose X`, `Implement X` |

**Body** (include when the cause/decision is non-obvious):
- Blank line after subject
- 72-char wrap
- Explain *why*, not what — context, problem before, trade-offs
- Plain prose, not bullet lists

**Footers** (blank line before):
- `Closes #N`, `Fixes #N`, `Refs #N`
- `BREAKING CHANGE: <description>`

**Atomic commits**: one logical change per commit — if the subject needs "and", split it.

### 5. Commit

```
git commit -m "<message>"
```

Output the commit hash to the user after committing:

```
Commited as <hash> - <N> files, <M> insertions.
```
