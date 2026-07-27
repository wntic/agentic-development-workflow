# T16 — Stand up a packaging-faithful consumer project as the trial venue

## Goal
Every trial so far (`platform/001`, `health/001`, `users/001`, `users/002`) ran **inside this
repository**, whose layout is not what a consumer gets. That is not a cosmetic difference — it is
how T12b's A4 hole survived a full clean end-to-end run: the gate went GREEN on an app that cannot
be started, and nothing in the trial could have noticed, because the trial and the shipped setup
diverge exactly at packaging.

It now blocks work. **T12b would add two checks whose live branches cannot be exercised here:**

- the toolchain preflight — this repo always has the toolchain, so its failure branch never runs;
- the import-without-injection check — this repo is deliberately, permanently non-installable
  (T12b's Out of scope), so only the SKIP branch ever runs; the FAIL branch never does.

Shipping gates whose failure paths were never exercised is the precise defect class the whole
`notes/19` register is about. So the venue has to exist before T12b, not after.

**This is the setup half, deliberately not the plugin.** A sibling directory that is a real
`uv init --package` project with `.claude/` reachable from it. No manifest, no
`${CLAUDE_PLUGIN_ROOT}`, no marketplace — those are **T15**, and they answer a different question
("does it work when *installed*"). Keeping them apart matters: jump straight to a marketplace install
and the first failure could be a plugin-loading bug rather than a workflow bug, with no way to tell
which. This isolates the variable that blocks work today.

## Depends on
Nothing hard. Best done immediately; T12b depends on it.

## Read first
- `tasks/T15-plugin-split.md` — the boundary between this task and that one; T16 answers T15's open
  "where does a trialled change live" question **with evidence** instead of a guess.
- `tasks/T11-*` / the T11 INDEX entry — T11 is the full e2e probe *runbook*; T16 is the venue it
  runs in. Do not duplicate the probe here; one small change is enough to prove the venue works.
- `.claude/tools/gate.py` — `check_self_hash` (`Path(__file__).resolve().parent` → git toplevel of
  the directory `gate.py` lives in). **Verified 2026-07-26: this resolves through a symlink back to
  the workflow repo, so the self-hash works unchanged under the symlink approach.** Do not "fix" it.
- `.claude/hooks/bash_guard.py` — `_repo_root()` (`CLAUDE_PROJECT_DIR` or git toplevel): under this
  setup, plugin root and project root genuinely differ for the first time. That is the point.
- `.claude/settings.json` — the hook paths, and how they resolve from the consumer's cwd.
- `PRINCIPLES.md` F1 (brownfield-first; greenfield is the degenerate case).

## Deliverables
- **A consumer project outside this repository**: its own git repo, created with
  `uv init --package` (**not** plain `uv init` — it creates neither `src/<pkg>/` nor
  `[build-system]`; `workflow_v3_spec.md` §9 now says `--package` for exactly this reason).
  **Location: `~/Projects/adw-consumer-probe`** — a sibling of this repo, named so it is obviously
  disposable. Do not create it anywhere else, do not nest it inside this repository (a nested repo
  would confuse `bash_guard`'s `_repo_root()` and `gate.py`'s self-hash, which are precisely what
  this venue exists to exercise honestly), and do not touch any other directory under `~/Projects`.
  If the path already exists, **stop and report** rather than reusing or overwriting it.
- **`.claude/` reachable from it** — symlink preferred (the self-hash is verified to survive it, and
  edits to the workflow take effect with no sync step). If a symlink proves unworkable, record why
  before falling back to a copy; a copy needs an explicit sync story or the two drift.
- **One small change driven end to end there** — `/spec` → `/implement` → `accept.py` reaching
  ACCEPTABLE. Small on purpose: this proves the venue, it does not exercise the workflow's breadth.
- **A short runbook** in `notes/` — how the venue is created, how `.claude/` is attached, which
  environment variables (if any) the hooks need, and every friction encountered. That note is
  direct input to T15 and T11.

## Verification
- In the consumer project: `uv run <plugin path>/.claude/tools/gate.py` runs at all — this is the
  first time the tools execute against a tree that is not their own repository.
- `integrity.self-hash` PASSes there (it should resolve back to the workflow repo).
- The hooks fire against the **consumer's** tree: at minimum `bash_guard` denies a non-owner write
  to the consumer's `tests/`, and does **not** deny writes to the workflow repo's own files.
- The one small change reaches `verdict: ACCEPTABLE`.
- This repository is untouched by the trial: `git status` clean here throughout.

## Out of scope / Escalate if
- **Do NOT build the plugin** — manifest, `${CLAUDE_PLUGIN_ROOT}`, marketplace publishing are T15.
  If something here *cannot* work without them, that is a finding for T15, not a reason to start it.
- Do NOT change what any gate checks. If a gate misbehaves in the new venue, **record it** — that is
  the whole yield of this task. Fixing it in the same breath hides which layout exposed it.
- Do NOT migrate `change/users-002` into the new project. Keep the branch and its tags here as prior
  art (handing `abandoned/users-001` to the agents as a reference is what let a 14-AC change land in
  one pass); the venue is for *new* trials.
- **Escalate if** the hooks cannot distinguish plugin root from project root without a settings
  change — that is a real T15 finding surfacing early, and it changes T15's shape.
