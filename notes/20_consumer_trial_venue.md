# 20 — The consumer trial venue (T16)

Runbook + findings for `~/Projects/adw-consumer-probe`: a packaging-faithful consumer project that
the workflow's tools are pointed at from outside their own repository. Built 2026-07-26 under T16.

Every trial before this one (`platform/001`, `health/001`, `users/001`, `users/002`) ran **inside**
this repository, where plugin root == project root and the app's `pyproject.toml` is the meta
layer's `pyproject.toml`. The venue exists so those two roots differ, which is the only way the
consumer-facing branches of `gate.py` / `accept.py` / the hooks ever execute.

This is deliberately **not** the plugin (T15): no `.claude-plugin/plugin.json`, no
`${CLAUDE_PLUGIN_ROOT}`, no marketplace. One variable at a time.

---

## 1. How the venue is created

```bash
cd ~/Projects
uv init --package adw-consumer-probe        # NOT plain `uv init` — see the §9 canon note
cd adw-consumer-probe
```

`uv init --package` (uv 0.11.6) produces exactly what the workflow assumes and plain `uv init` does
not: `src/adw_consumer_probe/__init__.py`, a `[build-system]` (`uv_build`), and a git repo on
`main` with no commits. It **also** produces two things the hexagonal shell has to undo — a
`[project.scripts]` entry point and a hello-world `main()` in the package `__init__.py`.

Then, before anything else:

```bash
cat >> .gitignore <<'EOF'
/.claude          # the plugin, attached by symlink — tooling reachable from the project,
                  # never content OF the project
.gate/            # gate.py run artifacts
.mypy_cache/
.ruff_cache/
.pytest_cache/
EOF
git add -A && git commit -m "chore: uv init --package baseline"
```

## 2. How `.claude/` is attached

```bash
ln -s ~/Projects/agentic-development-workflow/.claude ~/Projects/adw-consumer-probe/.claude
```

A **symlink**, not a copy — verified working end to end, no sync step, and edits to the workflow
take effect immediately. Specifically:

- `gate.py`'s `check_self_hash` (E-02) resolves `Path(__file__).resolve().parent` **through** the
  symlink to the workflow repo and compares against *that* repo's git HEAD → `[PASS]`.
- `accept.py`'s `TOOLS_DIR` / `TEMPLATES_DIR` resolve the same way, so the templates are found.
- `subagent_stop.py` locates the gate as `<payload cwd>/.claude/tools/gate.py` — through the
  symlink, works. (Under a real plugin install it would not; that is T15's `${CLAUDE_PLUGIN_ROOT}`
  reparenting.)
- **The documented invocation form works verbatim**: `uv run .claude/tools/gate.py` from the
  consumer root behaves exactly like the absolute path. Every command file's copy-pasteable command
  is usable in a consumer with no edit.

## 3. Environment variables the hooks need

**None.** `.claude/settings.json` (reached through the symlink) invokes each hook as
`python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/<hook>.py"`, and Claude Code sets `CLAUDE_PROJECT_DIR`
to the session's project root — the consumer — which is exactly the root `bash_guard._repo_root()`
must anchor to. Outside a session (i.e. when probing a hook by hand) set it explicitly:

```bash
CLAUDE_PROJECT_DIR=~/Projects/adw-consumer-probe python3 ~/Projects/agentic-development-workflow/.claude/hooks/bash_guard.py <<< '<payload>'
```

## 4. The change that was driven through it

`health/001 — service health endpoint`: one AC (`GET /health` → 200 `{"status": "ok"}`), M depth,
first change of the `health` context, so a genuine greenfield vertical slice — deps commit, red
baseline, app shell + behaviour, verdict, adversarial pass, acceptance.

| Step | Result |
|---|---|
| `criteria_lint.py` | OK, 1 criterion |
| `red_check.py --change health/001` | `RED-CONFIRMED`, baseline lint clean, tagged `baseline/health-001` |
| `gate.py --change health/001` | GREEN on the first run (0 implementer retries) |
| live run (`uvicorn … --factory`) | `HTTP/1.1 200 OK`, `{"status":"ok"}` — **no gate-provided import path** |
| `gate.py --criteria` | GREEN, `criteria.junit-backing` PASS |
| `accept.py health/001` | `verdict: ACCEPTABLE`, base `main` **(derived)** |
| `accept.py --execute` | merged, tagged `change/health-001`, change dir deleted |

The whole cycle was executed by **one** agent playing all four roles by hand (a builder subagent
cannot dispatch subagents). The *scripts* were exercised for real; the *anti-collusion* properties
of the cycle (fresh-context evaluator, `disallowedTools`) were not — that half needs a live
`/spec` → `/implement` → `/accept-change` session in the venue and is still owed.

---

## 5. Findings

### F-01 — A capability birth leaves the base branch RED (S9 violation). Venue-independent bug.

After a *successful* `accept.py --execute`, `gate.py` on the consumer's `main` is **RED**:

```
[FAIL] spec.invariant-tests — invariant references rotted (L-06):
       specs/health/service-health.md: (verified by: <test-id>) — test not found
```

Cause, two halves that only meet on the birth path:

1. `accept.py:instantiate_capability` copies `.claude/templates/capability.md` **verbatim**,
   including its HTML comment block, which contains the literal example
   `- <invariant> (verified by: <test-id>)`;
2. `gate.py:check_invariant_tests` runs `CAPABILITY_REF` over the file's **raw** text — it does not
   strip HTML comments (unlike `criteria_lint.strip_html_comments`) — so the template's own
   placeholder is read as a rotted invariant reference.

So every context's first acceptance hands the base branch a RED gate, and it stays RED until a human
deletes the comment out of the canonical file (which no sanctioned writer does: the spec-write owners
are `accept.py` and `/spec`). Blast radius beyond the gate line: `subagent_stop.py` then holds the
*next* change's implementer on a RED that an `src/**` edit can never clear — the T09f deadlock shape.

Why it never showed up here: **no acceptance has ever been `--execute`d in this repository** (no
`change/*` tag exists; `platform/001` stopped at ACCEPTABLE, `users/002` is still in flight), so the
birth path's *output* had never been gate-checked. Not fixed here — T16 forbids changing what a gate
checks, and the fix is a one-line decision between the two halves (strip comments in the gate, or
ship a comment-free template).

**FIXED 2026-07-26 by T10j**, both halves, plus a decision the finding did not raise:

1. *(load-bearing)* `gate.py:check_invariant_tests` now runs `CAPABILITY_REF` over
   `criteria_lint.strip_html_comments(...)` output, exactly as the criteria check already did — a
   comment is not content, and **any** capability file may legitimately carry one. Rot beside a
   comment still FAILs (`test_a_rotted_reference_still_fails_beside_a_comment`).
2. The birth path keeps copying the template's comments **verbatim** and the *template* was
   reworded. Weighed against stripping at instantiation: `accept.py` is the template's only
   consumer, so a comment stripped there serves nobody, while those comments are the entire
   orientation whoever opens a freshly born file gets. What the template owed was to *describe* the
   provenance form instead of *showing* a specimen of it.
3. **What an empty `## Behaviour` means on the birth path** (asked by the human's `/orient` in the
   venue): it is the intended placeholder, and the template now says so, with its owner. The
   criteria `accept.py` merges are already observable-behaviour statements (S3), so the Invariants
   *are* the behaviour record until a human-led `/spec` — the only other sanctioned writer of
   canonical spec files (D4) — writes the narrative around them. Birth must not populate it: a
   script inventing prose no gate can check is A3, and lifting the change's Task up into the
   capability file would be the second copy of history S6 forbids.

End-to-end proof, in a throwaway **clone of this venue** (packaging-faithful: consumer root ≠ plugin
root, `.claude` symlinked): `change/health-001` re-accepted with `--execute` onto a fresh base →
`gate.py` on that base → **GATE: GREEN**, `spec.invariant-tests — 1 invariant reference(s) resolve
to living tests`. One reference, not two. The same sequence is pinned as a test
(`test_executed_capability_birth_leaves_the_base_branch_green`), which reports `GATE: RED` against
the pre-fix scripts.

### F-02 — In a consumer, the enforcement infra is protected by self-hash alone.

`PROTECTED_FRAGMENTS` in `bash_guard` and `PROTECTED_PATHS` in `gate.py` both name
`.claude/tools`, `.claude/hooks`, `.claude/settings.json` — and in a consumer layout neither
reaches them:

- `bash_guard` anchors to the *consumer* root and `Path.resolve()`s targets, so both
  `echo x > /…/agentic-development-workflow/.claude/tools/gate.py` and the symlinked
  `echo x > .claude/tools/gate.py` land **outside** the repo root and are **allowed**. (This is the
  same mechanism as T16's required "does not deny writes to the workflow repo's own files", so it is
  correct *and* it is a hole: the two are one behaviour seen from two sides.)
- `gate.py`'s `integrity.protected-trees` diffs those paths **in the consumer tree**, where they do
  not exist → the check PASSes vacuously; only `pyproject.toml` is really covered there.

What still bites is `check_self_hash`: it resolves back to the workflow repo and compares gate.py +
criteria_lint.py against *its* git HEAD, so a tampered gate is caught. That is the whole E-01/E-02
story in a consumer — worth stating explicitly in T15, which will make plugin root a first-class
concept.

**ANSWERED 2026-07-26 by T18** — `check_self_hash` now anchors the whole enforcement layer, and the
answer to "what backstops each hook in a consumer" is written down below. Both halves of the finding
stand as measured: `bash_guard` still allows a write to the plugin's own files (T06e, on purpose) and
`integrity.protected-trees` is still vacuous in a consumer. What changed is that the vacuum is no
longer unattended.

**The anchor set (plugin-root-relative globs, `SELF_INTEGRITY_GLOBS` in `gate.py`):** `tools/*.py`
(gate, criteria_lint, accept, red_check) · `hooks/*.py` (all four) · `hooks/*.json` (the installed
hook wiring) · `bin/*.py` (the invocation shim) · `.claude-plugin/*.json` (the manifest, which names
the components) · `settings.json` (the checked-out/symlinked hook wiring — i.e. this venue's).
Twelve files today. Globs, not a list, so a new tool or hook is anchored by construction. Not
anchored, deliberately: `tools/test_*.py` (they ship, but no decision reads them) and
skills/agents/commands/templates (knowledge and prompts — drift there is a review question, and
freezing them would mean committing before every gate run while editing a skill).

**Why anchoring is enough, and where the chain actually closes:** a tampered anchor is not
*prevented* — it is made unable to produce a verdict. Any `gate.py` run FAILs with the file named,
and `accept.py` imports `gate` and re-runs it in-process (`accept.run_gate`), so **nothing merges
while an anchor differs from HEAD**. That is S8 in its own terms: the hook is porous, the post-hoc
check is not.

### What backstops each hook in a consumer (T18 deliverable 3)

| Hook | If it is tampered with / never fires | Backstop |
|---|---|---|
| `criteria_guard` | a reworded criterion under the same checkbox | `integrity.criteria-flips` — full baseline diff of every `criteria.md`, plus `accept.py`'s junit cross-check. **Real.** |
| `bash_guard` | a non-owner writes another role's tree | `integrity.protected-trees` for `.claude/**` + `pyproject.toml` — **vacuous in a consumer** for the `.claude` paths (they live outside the project), real for `pyproject.toml`. For the cycle's own lanes (`src/**` vs `tests/**`) the backstop is `integrity.test-inventory` (a silenced/deleted baseline test is RED) and the red baseline's tests-only commit (T09b) — so *anti-collusion* survives, while "which role wrote this line" does not. **Partial, by design (S8).** |
| `subagent_stop` | the implementer is never held on a RED gate, and the iteration ceiling never writes `ESCALATE` | **Nothing at the gate.** The gate is a verdict, not a scheduler: it cannot know that an agent stopped early or that a ceiling was reached. The evaluator's own `gate.py --criteria` run catches the *state* (a RED tree, an unbacked flip), so a bad result cannot pass — but the *ceiling* is unenforced without the hook, and a lock that was never written cannot be missed by `integrity.escalate-intact`. |
| `session_stop` | the end-of-session reminder is silent | Nothing, and nothing is owed: it is advisory ergonomics with no invariant behind it. |

Both "nothing" rows are the honest answer, and they are the interesting output of T18: the two hooks
whose job is *process* (hold the implementer, cap the iterations, remind at the end) have no post-hoc
equivalent, because a post-hoc check judges a tree and those hooks judge a moment. Anchoring them
means a tamper is *detected at the next gate run* — it does not mean the held moment is recovered.
A ceiling that never fires costs iterations, not correctness; that is the trade S8 already accepts.

**Two limits worth stating (neither closed, both known):**

1. **Self-hash compares against the plugin's LOCAL `HEAD`.** An agent that can write the plugin
   directory can also `git -C <plugin> commit -a`, after which work tree == HEAD and the check
   passes. Closing it needs a remote/published-commit comparison (network, or a signed manifest) —
   out of T18's scope. What it costs today: the tamper stops being invisible only if nobody commits
   it inside the plugin.
2. **In this venue, the plugin's `settings.json` is also the project's** (`.claude` is a symlink), so
   a consumer who customises hooks *there* turns the gate RED until the edit is committed in the
   workflow repo. Under a real plugin install the two files are distinct and the question does not
   arise.

### F-03 — Missing toolchain in a consumer is a raw traceback, not a sentence (T12b input, live).

The very first gate run in a fresh `uv init --package` project (deps not yet declared):

```
[FAIL] toolchain.mypy — …/.venv/bin/python: No module named mypy
[FAIL] toolchain.ruff-check — …/.venv/bin/python: No module named ruff
[FAIL] toolchain.ruff-format — …/.venv/bin/python: No module named ruff
```

Three FAILs and no statement that the *project* must declare the toolchain (`conventions` block D).
This is T12b's preflight branch, and this venue is the only place it can be exercised — here it is,
reproduced. Note the flip side, also T12b's: because `uv init --package` ships `[build-system]`, the
package is installed editable by `uv run` and the **operator's own command works** —
`uv run uvicorn adw_consumer_probe.restapi.main:create_app --factory` served `/health` with no
`PYTHONPATH=src` from the gate. The A4 hole T12b describes is a property of *this* repo's
non-installable layout, not of the workflow.

### F-04 — `uv init --package` scaffolding straddles the file-ownership line.

The generated `[project.scripts] adw-consumer-probe = "adw_consumer_probe:main"` points at the
hello-world `main()` in the package `__init__.py`. The shell has to remove the function
(`src/**` → implementer) and the entry point (`pyproject.toml` → test-author), so a first change
must split a single piece of scaffolding removal across two roles' commits. Small, but it is
exactly the kind of friction a "just `uv init --package`" precondition hides; T11's runbook should
say it out loud.

### F-05 — `/implement` §0.5 still says plain `uv init`.

`.claude/commands/implement.md` ("A brand-new project needs nothing but a plain `uv init` project…
the package root `src/<pkg>/` is derived from it") is the drift the 2026-07-26 canon edit fixed in
`workflow_v3_spec.md` §9 and in T11's INDEX entry. The command file was missed. Not fixed here (out
of T16's deliverables); one-line wording fix for whoever touches T11/T12b.

### F-06 — Docker is available on this machine.

`docker.alembic` reports "docker available, but no alembic.ini in tree" rather than
`DOCKER SKIPPED`. The health slice carries no relational store, so the tier is genuinely n/a — but
the venue does **not** exercise the Docker-absence carve-out (T04b) either. A future trial that
wants that branch must force it with `GATE_DOCKER=0`.

---

## 6. State the venue is in

- `~/Projects/adw-consumer-probe`, branch `main`, tags `baseline/health-001`, `change/health-001`.
- Working tree clean; `specs/health/{overview.md,service-health.md}` are the living spec.
- `gate.py` on `main` is **GREEN** since T10j (2026-07-26). Repaired *by the fix*, with **zero edits
  to the venue** — the gate stopped reading comments as data, so the born file needs no touch-up.
  It still carries the pre-T10j template's comment (with the `<test-id>` specimen in it): harmless
  now, and left alone on purpose — hand-editing a canonical spec file is exactly what F-01 said not
  to do, and only `accept.py` and `/spec` write those files (D4).
- This repository was untouched throughout: `git status` clean on `markdown-specs` before, during
  and after.
