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
   strip HTML comments (unlike `criteria_lint._strip_html_comments`) — so the template's own
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
- `gate.py` on `main` is **RED on F-01 only** — deliberately left as found (T16 forbids fixing a
  gate in the same breath as exposing it). Clear it by deciding F-01, not by hand-editing the
  capability file.
- This repository was untouched throughout: `git status` clean on `markdown-specs` before, during
  and after.
