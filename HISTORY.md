# History — three attempts, and where each one lives now

Nothing was thrown away. This file is the only pointer you need: every attempt is a git tag, and
every path below is one `git checkout` away. The working tree is deliberately clean of all of it,
because a repository that carries three dead generations of its own tooling cannot be read.

| Attempt | Tag | What it was | Why it stopped |
|---|---|---|---|
| **1** | (in the history of `v2-archive`) | a code generator over a hand-written schema | every new app needed the schema widened; endless hardcoding |
| **2** | `v2-archive` (`6824289`) | YAML manifest + stdlib validator + scaffolder/implementer over a DAG | proven end-to-end, then abandoned: the manifest schema overfitted the one reference app it was born from |
| **3** | `v3-archive` (`1f90295`) | living Markdown specs + a change cycle + deterministic gates (`gate.py` / `accept.py`) and PreToolUse hooks | the enforcement layer became the product — see the measurements below |

## What attempt 3 measured about itself

Taken at `v3-archive`:

| | |
|---|---|
| tasks planned in the design doc | 11 |
| task files actually written | **64** (20 root + 44 discovered while building) |
| lines of enforcement (`tools/` + `hooks/` + `bin/`) | **~17 200** |
| lines of orchestration (`commands/` + `agents/`) | ~1 190 |
| lines of application code produced | **0** |
| features shipped through the cycle | **0** |
| agent-hours spent building the workflow | ~12 |

The ratio is the finding: 14 lines of checking per line of orchestrating, and nothing built with
it. The diagnosis — why this was structural rather than bad luck, and what the rest of the industry
does instead — is in [`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md).

## How to recover any of it

```bash
# read without touching the tree
git show v3-archive:workflow_v3_spec.md          # the v3 design canon (Russian)
git show v3-archive:PRINCIPLES.md                # the A/S/C/D/E/F decision register
git show v2-archive:codegen_workflow_spec.md     # the v2 design canon
git ls-tree -r --name-only v3-archive tasks/     # the 64-file build-out register

# bring something back
git checkout v3-archive -- plugins/adw/tools/gate.py
git checkout v3-archive -- plugins/adw/templates/
git checkout v2-archive -- specs/use-cases/      # the Meeting Assistant BA corpus, UC-10..17
```

### What is where

| Path (at `v3-archive`) | Contents |
|---|---|
| `plugins/adw/tools/` | `gate.py` (2075), `accept.py` (1730), `red_check.py` (1785), `drift.py`, `anchors.py`, `criteria_lint.py`, plus ~9 400 lines of tests over them |
| `plugins/adw/hooks/` | `bash_guard.py`, `criteria_guard.py`, `subagent_stop.py`, `session_stop.py`, `hooks.json` |
| `plugins/adw/agents/` | `v3-builder`, `test-author`, `implementer`, `evaluator` |
| `plugins/adw/commands/` | `spec`, `implement`, `accept-change`, `abandon`, `orient`, `build-task` |
| `plugins/adw/templates/` | `change.md`, `criteria.md`, `verdict.md`, `overview.md`, `capability.md` |
| `plugins/adw/skills/test-principles/` | the catalog's paid-fixes guard (died with the script it guarded) |
| `tasks/` | `INDEX.md` + 64 task files |
| `workflow_v3_spec.md`, `PRINCIPLES.md` | the design canon and the decision register |
| `codegen_workflow_spec.md` | v2's rationale, kept through v3 for the "why" of what survived |
| `specs/use-cases/` (at `v2-archive`) | the Meeting Assistant BA corpus, UC-10..17 |

## What survived into the working tree, and why

- **`plugins/adw/skills/`** — the house-style knowledge catalog (~8 100 lines, three rounds of
  altitude audit). It never depended on the gates: it is knowledge about writing Python, not about
  running a workflow. Carried over verbatim, minus the references to deleted tooling.
- **`plugins/adw/commands/commit.md`** — generic, no workflow coupling.
- **`notes/`** — the decision history. What was paid for and what it cost. Read `15` (the v3
  adversarial design review), `19` (the accept-gate audit) and `pipeline_dryrun_feedback.md` (the
  honesty benchmark for defect logs) before proposing any mechanism a fourth time.
- **`research/`** — the survey the fourth attempt starts from.

## The one rule this file exists to enforce

Do not rebuild a deleted mechanism from memory. If a mechanism is worth having again, recover the
real file from its tag and read what it actually cost — the tasks named `T04b…T04i`,
`T06b…T06m`, `T09b…T09j`, `T10b…T10k` are the price list.
