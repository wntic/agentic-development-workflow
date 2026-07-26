"""Bypass suite for the enforcement wiring (workflow v3, T06 / spec §5.2, §5.3).

Two tiers, matching the design's S8 inversion:
  1. hook ergonomics — drive each hook as a script with a synthetic Claude Code payload and
     assert the fast, explained decision (allow / deny / block);
  2. bypass proof — for every hook bypass (Write that rewords under the same checkboxes, a
     shell edit the hook may miss, conftest test-suppression, editing gate.py itself), drive
     the REAL gate.py on a fixture tree and assert it goes RED. The hook is porous by
     construction; the trust anchor is the post-hoc baseline check (S8).

The fixture-tree machinery is reused from test_gate.py (same directory) — a git repo with
gate.py + criteria_lint.py committed and a `baseline/demo-001` tag."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_gate import CRITERIA_MD, SRC_MAIN_BROKEN, TESTS_CORE, FixtureRepo, make_repo

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent.parent  # <repo>/.claude/tools -> <repo>
HOOKS_DIR = TOOLS_DIR.parent / "hooks"
HOOKS = ("criteria_guard.py", "bash_guard.py", "subagent_stop.py", "session_stop.py")

CRITERIA_REL = "specs/demo/changes/001-thing/criteria.md"


def run_hook(
    script: str, payload: dict, *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    e["GATE_DOCKER"] = "0"  # any gate the hook re-runs must skip Docker deterministically
    # The gate a hook re-runs must be the FIXTURE's, never one an ambient CLAUDE_PLUGIN_ROOT
    # points at (T15/D4): this repo's settings.json sets it, and a plugin install would set it
    # to an absolute path, which would silently bypass every stubbed gate below.
    e.pop("CLAUDE_PLUGIN_ROOT", None)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=e,
    )


def _load_hook(name: str):  # noqa: ANN202 — the hook module, imported for its pure helpers
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"{name}_mod", HOOKS_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec: a module with `from __future__ import annotations` AND a
    # @dataclass (bash_guard) resolves its field annotations through sys.modules at class
    # creation, and blows up with AttributeError if it is not there.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def decision(proc: subprocess.CompletedProcess[str]) -> str | None:
    """The PreToolUse permissionDecision (or None on allow / empty output)."""
    out = proc.stdout.strip()
    if not out:
        return None
    obj = json.loads(out)
    if "hookSpecificOutput" in obj:
        return obj["hookSpecificOutput"].get("permissionDecision")
    return obj.get("decision")


@pytest.fixture()
def repo(tmp_path: Path) -> FixtureRepo:
    return make_repo(tmp_path / "app")


# =======================================================================================
# --describe + shape (verification: each hook prints a one-line self-description; stdlib-only)
# =======================================================================================


@pytest.mark.parametrize("script", HOOKS)
def test_describe_is_one_line(script: str) -> None:
    proc = subprocess.run([sys.executable, str(HOOKS_DIR / script), "--describe"], capture_output=True, text=True)
    assert proc.returncode == 0
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, proc.stdout
    assert script in lines[0]


@pytest.mark.parametrize("script", HOOKS)
def test_hook_is_executable(script: str) -> None:
    assert os.access(HOOKS_DIR / script, os.X_OK), script


@pytest.mark.parametrize("script", HOOKS)
def test_hook_is_stdlib_only(script: str) -> None:
    # `-S` disables site so third-party imports (site-packages) would fail; stdlib survives.
    proc = subprocess.run([sys.executable, "-S", str(HOOKS_DIR / script), "--describe"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# =======================================================================================
# criteria_guard — ergonomics
# =======================================================================================


def _write_payload(repo: FixtureRepo, content: str, *, rel: str = CRITERIA_REL) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": str(repo.root / rel), "content": content}}


def test_criteria_guard_allows_state_flip_write(repo: FixtureRepo) -> None:
    flipped = CRITERIA_MD.replace("- [ ] AC-1:", "- [x] AC-1:", 1)
    proc = run_hook("criteria_guard.py", _write_payload(repo, flipped), cwd=repo.root)
    assert proc.returncode == 0
    assert decision(proc) is None, proc.stdout  # allowed


def test_criteria_guard_denies_reword_write(repo: FixtureRepo) -> None:
    reworded = CRITERIA_MD.replace("returns the sum `3`", "returns any value")
    proc = run_hook("criteria_guard.py", _write_payload(repo, reworded), cwd=repo.root)
    assert decision(proc) == "deny", proc.stdout
    assert "/spec" in proc.stdout  # points at the legal path


def test_criteria_guard_denies_added_line_write(repo: FixtureRepo) -> None:
    grown = CRITERIA_MD + "- [ ] AC-3: silently widened scope\n"
    proc = run_hook("criteria_guard.py", _write_payload(repo, grown), cwd=repo.root)
    assert decision(proc) == "deny", proc.stdout


def test_criteria_guard_edit_flip_allowed_reword_denied(repo: FixtureRepo) -> None:
    flip = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(repo.root / CRITERIA_REL),
            "old_string": "- [ ] AC-1: `app.core.add` returns the sum `3` for input `1, 2`",
            "new_string": "- [x] AC-1: `app.core.add` returns the sum `3` for input `1, 2`",
        },
    }
    assert decision(run_hook("criteria_guard.py", flip, cwd=repo.root)) is None

    reword = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(repo.root / CRITERIA_REL),
            "old_string": "- [ ] AC-1: `app.core.add` returns the sum `3` for input `1, 2`",
            "new_string": "- [x] AC-1: `app.core.add` returns something",
        },
    }
    assert decision(run_hook("criteria_guard.py", reword, cwd=repo.root)) == "deny"


def test_criteria_guard_ignores_non_criteria_file(repo: FixtureRepo) -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(repo.root / "src/app/core.py"), "content": "x"}}
    assert decision(run_hook("criteria_guard.py", payload, cwd=repo.root)) is None


def test_criteria_guard_creation_denied_when_baseline_exists(repo: FixtureRepo) -> None:
    # a second change dir whose baseline tag already exists -> criteria list is frozen
    repo.git("tag", "baseline/demo-002")
    rel = "specs/demo/changes/002-new/criteria.md"
    (repo.root / rel).parent.mkdir(parents=True, exist_ok=True)
    proc = run_hook("criteria_guard.py", _write_payload(repo, CRITERIA_MD, rel=rel), cwd=repo.root)
    assert decision(proc) == "deny", proc.stdout
    assert "baseline/demo-002" in proc.stdout


def test_criteria_guard_creation_allowed_before_baseline(repo: FixtureRepo) -> None:
    rel = "specs/demo/changes/003-fresh/criteria.md"  # no baseline/demo-003 tag
    (repo.root / rel).parent.mkdir(parents=True, exist_ok=True)
    proc = run_hook("criteria_guard.py", _write_payload(repo, CRITERIA_MD, rel=rel), cwd=repo.root)
    assert decision(proc) is None, proc.stdout


# =======================================================================================
# criteria_guard — path canonicalisation (E-10): case-variant and `..`-variant paths
# =======================================================================================


def test_criteria_guard_dotdot_path_reword_denied(repo: FixtureRepo) -> None:
    sneaky = str(repo.root / "specs/demo/changes/001-thing/../001-thing/criteria.md")
    reworded = CRITERIA_MD.replace("returns the sum `3`", "returns any value")
    payload = {"tool_name": "Write", "tool_input": {"file_path": sneaky, "content": reworded}}
    assert decision(run_hook("criteria_guard.py", payload, cwd=repo.root)) == "deny"


def test_criteria_guard_case_variant_path_reword_denied(repo: FixtureRepo) -> None:
    # APFS is case-insensitive (E-10): CRITERIA.MD resolves to the same file; casefold catches it.
    variant = str(repo.root / "specs/demo/changes/001-thing/CRITERIA.MD")
    if not os.path.exists(variant):
        pytest.skip("case-sensitive filesystem — case-variant evasion is not reachable here")
    reworded = CRITERIA_MD.replace("returns the sum `3`", "returns any value")
    payload = {"tool_name": "Write", "tool_input": {"file_path": variant, "content": reworded}}
    assert decision(run_hook("criteria_guard.py", payload, cwd=repo.root)) == "deny"


# =======================================================================================
# bash_guard — ergonomics
# =======================================================================================
#
# bash_guard anchors its protected-path match to the repo root (T06e): a relative target is
# resolved against the cwd and only fires when its repo-relative form matches a fragment, so
# the tests run from a realistic cwd (the repo root) with CLAUDE_PROJECT_DIR set to it.


def run_bash_guard(payload: dict, *, root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """Drive bash_guard anchored to `root`; protected fragments match repo-relative paths (T06e)."""
    return run_hook("bash_guard.py", payload, cwd=root, env={"CLAUDE_PROJECT_DIR": str(root)})


@pytest.mark.parametrize(
    "command",
    [
        "sed -i '' 's/x/y/' tests/test_core.py",
        "echo pwned >> specs/demo/changes/001-thing/criteria.md",
        "rm .claude/tools/gate.py",
        "git checkout -- specs/demo/core.md",
        "mv pyproject.toml pyproject.bak",
        "printf x | tee tests/test_core.py",
        # T06b — a real write to a protected path is still caught by the retargeted matcher:
        "echo x > tests/test_foo.py",
        "sed -i 's/x/y/' specs/demo/foo.md",
    ],
)
def test_bash_guard_denies_writes_to_protected_paths(command: str) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = run_bash_guard(payload)
    assert decision(proc) == "deny", (command, proc.stdout)


@pytest.mark.parametrize(
    "command",
    [
        "grep -rn foo src/",
        "ls -la",
        "cat specs/demo/core.md",  # read, not write
        "python3 -m pytest tests/",  # runs tests, no write token
        # T06b — false positives that trained the operator toward --no-verify (finding 3):
        # a `>` and a protected fragment inside the quoted commit message are not a write.
        'git commit -m "msg with <brackets> and .claude/hooks"',
        # `2>&1` is fd duplication (target `&1`), and the tee target is unprotected.
        "pytest 2>&1 | tee /tmp/log",
        # the protected path is a *read* argument to pytest, not a write target.
        "uv run pytest .claude/tools/test_enforcement.py 2>&1 | tee /tmp/log",
    ],
)
def test_bash_guard_allows_benign(command: str) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    assert decision(run_bash_guard(payload)) is None, command


# =======================================================================================
# bash_guard — role-aware owned-tree write path (T06d)
# =======================================================================================
#
# The cycle subagents have no Write/Edit tool (a path-scoped disallowedTools drops the tool
# wholesale), so the shell is their only write path to their OWNED tree. The guard reads the
# acting role from the payload's `agent_type` and does not fire on that role's owned tree,
# while a write to a NON-owned protected tree still fires (precision, S8 backstop unchanged).


def _bash(command: str, agent_type: str | None = None) -> dict:
    p = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent_type is not None:
        p["agent_type"] = agent_type
    return p


@pytest.mark.parametrize(
    ("role", "command", "expected"),
    [
        # --- test-author owns tests/** + the deps files: sanctioned, no denial ---
        ("test-author", "echo x > tests/test_foo.py", None),
        ("test-author", "printf x | tee tests/integration/test_foo.py", None),
        ("test-author", "sed -i '' 's/a/b/' pyproject.toml", None),
        ("test-author", "echo locked > uv.lock", None),
        # ... but the implementer's lane and the other cycle files stay closed to it
        ("test-author", "echo x > src/app/core.py", "deny"),
        ("test-author", "echo x > specs/demo/changes/001-thing/verdict.md", "deny"),
        ("test-author", "echo x > specs/demo/changes/001-thing/criteria.md", "deny"),
        ("test-author", "echo x >> .claude/settings.json", "deny"),
        # --- evaluator owns criteria.md + verdict.md ---
        ("evaluator", "echo x > specs/demo/changes/001-thing/verdict.md", None),
        ("evaluator", "printf y >> specs/demo/changes/001-thing/criteria.md", None),
        # ... but tests/, src/, and capability prose stay closed to it
        ("evaluator", "echo x > tests/test_foo.py", "deny"),
        ("evaluator", "echo x > src/app/core.py", "deny"),
        ("evaluator", "echo x > specs/demo/core.md", "deny"),  # capability prose is /spec's
        ("evaluator", "rm .claude/tools/gate.py", "deny"),
        # --- implementer owns src/** (unchanged); tests/ and pyproject stay closed ---
        ("implementer", "echo x > src/app/core.py", None),
        ("implementer", "mkdir -p src/app/domain && echo x > src/app/domain/entities.py", None),
        ("implementer", "echo x > tests/test_foo.py", "deny"),
        ("implementer", "sed -i '' 's/a/b/' pyproject.toml", "deny"),  # deps are the test-author's
        # --- an unidentified/default session: pre-T06d behavior, everyone-denied ---
        ("default", "echo x > tests/test_foo.py", "deny"),
        ("default", "echo x > src/app/core.py", None),  # src stays open to the default session
    ],
)
def test_bash_guard_role_aware_owned_tree(role: str, command: str, expected: str | None) -> None:
    agent_type = None if role == "default" else role
    proc = run_bash_guard(_bash(command, agent_type))
    assert decision(proc) == expected, (role, command, proc.stdout)


def test_bash_guard_owner_denial_names_the_role() -> None:
    # the deny message reports the acting role so the trace explains *why* a non-owned write fired
    proc = run_bash_guard(_bash("echo x > src/app/core.py", "evaluator"))
    assert decision(proc) == "deny"
    assert "'evaluator'" in proc.stdout, proc.stdout


# --- T15/D1: the same role, namespaced by the plugin loader -----------------------------
#
# Installed as a plugin, `agent_type` arrives as `adw:<role>`; loaded from project config
# (as in this repo) it arrives bare. ROLE_OWNED is keyed on bare names, so without stripping
# the namespace every cycle role loses its owned-tree write path — silently, and invisibly to
# every other test here. BOTH forms are pinned: the bare one must keep working.


@pytest.mark.parametrize(
    ("agent_type", "command", "expected"),
    [
        ("adw:test-author", "echo x > tests/test_foo.py", None),
        ("adw:test-author", "echo x > src/app/core.py", "deny"),
        ("adw:evaluator", "echo x > specs/demo/changes/001-thing/verdict.md", None),
        ("adw:evaluator", "echo x > tests/test_foo.py", "deny"),
        ("adw:implementer", "echo x > src/app/core.py", None),
        ("adw:implementer", "echo x > tests/test_foo.py", "deny"),
        # The namespace is STRIPPED, not validated (D1's rule is the last segment): a foreign
        # plugin's identically-named role is read as this workflow's. Pinned as the shipped
        # behaviour — the widening only ever grants a role its OWN tree, so the blast radius is
        # an unrelated `*:test-author` writing tests/**, and the gate backstops it (S8).
        ("other:test-author", "echo x > tests/test_foo.py", None),
        # a name that is no role of this workflow's still fires on every protected tree
        ("stranger", "echo x > tests/test_foo.py", "deny"),
        ("adw:stranger", "echo x > tests/test_foo.py", "deny"),
    ],
)
def test_bash_guard_role_survives_the_plugin_namespace(agent_type: str, command: str, expected: str | None) -> None:
    proc = run_bash_guard(_bash(command, agent_type))
    assert decision(proc) == expected, (agent_type, command, proc.stdout)


def test_bash_guard_acting_role_strips_only_the_namespace() -> None:
    mod = _load_hook("bash_guard")
    assert mod.acting_role("adw:implementer") == "implementer"
    assert mod.acting_role("implementer") == "implementer"
    assert mod.acting_role(None) is None
    assert mod.acting_role("") is None
    assert mod.acting_role("adw:") is None  # a trailing colon names no role


# =======================================================================================
# bash_guard — repo-root anchoring (T06e)
# =======================================================================================
#
# A protected fragment (tests/, specs/, criteria.md, …) is a path RELATIVE TO THE REPO ROOT,
# so the match must be too. A target that merely CONTAINS a fragment but resolves OUTSIDE the
# repo tree (a /tmp scratch dir, a sibling of the repo) never fires — this is what blocked a
# legitimate `/tmp` fixture setup. The in-repo protection is untouched: a non-owner write to a
# protected tree inside the repo still fires (relative or absolute). The gate backstops (S8).


def _run_anchored(command: str, *, agent_type: str | None, root: Path) -> subprocess.CompletedProcess[str]:
    return run_hook("bash_guard.py", _bash(command, agent_type), cwd=root, env={"CLAUDE_PROJECT_DIR": str(root)})


def test_bash_guard_absolute_in_repo_protected_denied(repo: FixtureRepo) -> None:
    # <repo>/tests/x.py written by a non-owner (evaluator) — inside the repo, still denied.
    cmd = f"echo x > {repo.root}/tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_absolute_outside_repo_allowed(repo: FixtureRepo, tmp_path: Path) -> None:
    # A scratch tree that merely CONTAINS `tests/` but lives OUTSIDE the repo never fires.
    # (`repo` is tmp_path/"app"; this scratch is a sibling, not under the repo root.)
    scratch = tmp_path / "scratch" / "tests" / "x.py"
    cmd = f"echo x > {scratch}"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) is None


def test_bash_guard_tmp_scratch_write_allowed(repo: FixtureRepo) -> None:
    # The exact friction from T09f: a /tmp fixture setup under a non-owner role must be allowed.
    cmd = "cat > /tmp/x/tests/conftest.py"
    assert decision(_run_anchored(cmd, agent_type="test-author", root=repo.root)) is None


def test_bash_guard_specs_in_repo_denied(repo: FixtureRepo) -> None:
    cmd = f"echo x > {repo.root}/specs/demo/core.md"
    assert decision(_run_anchored(cmd, agent_type="test-author", root=repo.root)) == "deny"


def test_bash_guard_relative_under_repo_still_denied(repo: FixtureRepo) -> None:
    # A relative target resolving under the repo (cwd = repo root) is still protected.
    assert decision(_run_anchored("echo x > tests/x.py", agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_owned_tree_under_repo_still_allowed(repo: FixtureRepo) -> None:
    # T06d owned-tree allowance survives the anchoring: the test-author writes tests/ freely.
    assert decision(_run_anchored("echo x > tests/x.py", agent_type="test-author", root=repo.root)) is None


# =======================================================================================
# bash_guard — cd-aware resolution of relative targets (T06f)
# =======================================================================================
#
# T06e anchored the ABSOLUTE variant; the relative one stayed broken because the payload's
# `cwd` is the SESSION cwd and the tokeniser had no `cd` awareness — so a write into a scratch
# copy of the tree (`cd /tmp/mut && cat > tests/...`) resolved under the repo root and fired.
# It denied the users/002 adversarial mutation pass twice; the evaluator rerouted and finished
# anyway, i.e. the guard trained the bypass reflex it exists to prevent. A relative target is
# now resolved against the command's EFFECTIVE cwd; when that cannot be determined with
# confidence the target is dropped, never guessed (T06b precision bias, S8 backstop).


def test_bash_guard_cd_into_scratch_then_relative_write_allowed(repo: FixtureRepo, tmp_path: Path) -> None:
    # users/002 denial #1, replayed: a probe test written into a throwaway mutation copy.
    cmd = f"cd {tmp_path / 'mut'} && cat > tests/integration/x_test.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) is None


def test_bash_guard_cd_into_scratch_dissolves_the_compound_veto(repo: FixtureRepo, tmp_path: Path) -> None:
    # users/002 denial #2, replayed: the real mutations are in src/, and the command died only
    # because a leading `rm -f tests/...` shared the line. A PreToolUse hook can only allow or
    # deny the whole call, so the fix is that BOTH targets now resolve into the /tmp copy.
    cmd = f"cd {tmp_path / 'mut'} && rm -f tests/x.py && cat > src/y.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) is None


def test_bash_guard_relative_write_without_cd_still_denied(repo: FixtureRepo) -> None:
    # No cd: the session cwd IS the repo, so the protection is exactly as before.
    assert decision(_run_anchored("cat > tests/x.py", agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_cd_does_not_excuse_an_absolute_in_repo_target(repo: FixtureRepo, tmp_path: Path) -> None:
    # T06e's anchoring is untouched: an absolute target ignores the effective cwd.
    cmd = f"cd {tmp_path / 'mut'} && cat > {repo.root}/tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_cd_out_and_back_in_still_denied(repo: FixtureRepo) -> None:
    # The escalate-if case of T06f: cd-tracking must NOT open `cd .. && > <repo>/tests/x`.
    # Resolution narrows, ownership does not: the target lands back inside the repo and fires.
    cmd = f"cd .. && cat > {repo.root.name}/tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_cd_from_scratch_into_the_repo_is_denied(repo: FixtureRepo, tmp_path: Path) -> None:
    # The mirror image: a relative target resolves INTO the repo through the cd, and fires.
    # The session cwd is the scratch tree, so only the cd tells the guard where the write lands.
    scratch = tmp_path / "mut"
    scratch.mkdir()
    cmd = f"cd {repo.root}/tests && cat > x.py"
    proc = run_hook("bash_guard.py", _bash(cmd, "evaluator"), cwd=scratch, env={"CLAUDE_PROJECT_DIR": str(repo.root)})
    assert decision(proc) == "deny"


@pytest.mark.parametrize(
    "prefix",
    [
        "cd &&",  # bare cd -> the home directory
        "cd - &&",  # the previous directory
        "cd $SCRATCH &&",  # an expansion this guard cannot evaluate
        "cd ~/mut &&",  # an unexpanded ~
        "pushd /x >/dev/null && popd >/dev/null &&",  # a stack this guard does not model
    ],
)
def test_bash_guard_indeterminate_cwd_does_not_fire(repo: FixtureRepo, prefix: str) -> None:
    # Precision bias: an effective cwd that cannot be determined drops the relative target
    # rather than guessing the session cwd. The gate's baseline diff backstops the miss (S8).
    assert decision(_run_anchored(f"{prefix} cat > tests/x.py", agent_type="evaluator", root=repo.root)) is None


def test_bash_guard_cd_in_a_subshell_does_not_fire(repo: FixtureRepo, tmp_path: Path) -> None:
    # `(cd x && …)` scopes the cd to a subshell — beyond a one-line model, so indeterminate.
    cmd = f"(cd {tmp_path / 'mut'} && cat > tests/x.py)"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) is None


def test_bash_guard_cd_preserves_the_owned_tree_allowance(repo: FixtureRepo) -> None:
    # T06d survives: the test-author still writes its own tree through a cd-prefixed command.
    cmd = f"cd {repo.root} && cat > tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="test-author", root=repo.root)) is None


# =======================================================================================
# bash_guard — fragments match path COMPONENTS, not bare substrings (T06f)
# =======================================================================================
#
# `change.md` is a filename relative to the repo root, so a file whose name merely CONTAINS
# it is not it. Found building T10e: `git show … > .claude/tools/fixtures/users-002-change.md`
# was reported as a write to `change.md`, which sent the builder renaming the fixture. That
# path is in fact protected — it lives under `.claude/tools` — and the denial now says so.


@pytest.mark.parametrize(
    "command",
    [
        "echo x > notes/users-002-change.md",  # not a change.md
        "echo x > notes/verdict.md.draft",  # not a verdict.md
        "sed -i '' 's/a/b/' pyproject.toml.bak",  # not pyproject.toml
        "echo x > notes/mycriteria.md",  # not a criteria.md
    ],
)
def test_bash_guard_filename_fragment_needs_a_whole_component(repo: FixtureRepo, command: str) -> None:
    assert decision(_run_anchored(command, agent_type="test-author", root=repo.root)) is None, command


def test_bash_guard_real_change_md_still_denied(repo: FixtureRepo) -> None:
    cmd = "echo x > specs/demo/changes/001-thing/change.md"
    assert decision(_run_anchored(cmd, agent_type="test-author", root=repo.root)) == "deny"


def test_bash_guard_protected_dir_denial_names_the_directory(repo: FixtureRepo) -> None:
    # The T10e write: still denied — `.claude/tools` is a protected tree whoever the fixture
    # is named for — but the reported fragment is now the real reason, not the filename.
    cmd = "git show HEAD:x > .claude/tools/fixtures/users-002-change.md"
    proc = _run_anchored(cmd, agent_type="test-author", root=repo.root)
    assert decision(proc) == "deny"
    assert ".claude/tools" in proc.stdout and "(change.md)" not in proc.stdout, proc.stdout


# =======================================================================================
# bash_guard — a heredoc BODY is data, not command (T06g)
# =======================================================================================
#
# `git commit -F - <<'EOF' … EOF` is how every agent in this repo writes a multi-line message,
# and the tokeniser read the body as part of the command — so prose that happened to contain
# `>` followed by a protected path was denied as a redirect, while the identical idiom with a
# clean message passed. It fired on message CONTENT, not command shape (hence "unreproducible").
# Bodies are now stripped before tokenising; the opener's own line stays, so a real redirect
# there still fires — that boundary is the whole correctness question of the fix.

COMMIT_HEREDOC = "git commit -F - <<'EOF'\nfix: something\n\nthe prose mentions > tests/x.py as an example\nEOF"


@pytest.mark.parametrize(
    "command",
    [
        # the verbatim reproduction: a redirect-looking token inside the message body
        COMMIT_HEREDOC,
        # unterminated: the remainder is body, and an unresolvable command never fires (S8)
        "git commit -F - <<'EOF'\nthe prose mentions > tests/x.py\n",
        # two heredocs in one command — the SECOND body carries the protected token
        "cmd <<A <<B\nbodyA\nA\nthe prose mentions > tests/x.py\nB",
        # `<<-` strips tabs, so its terminator may be indented
        "git commit -F - <<-EOF\n\tthe prose mentions > tests/x.py\n\tEOF",
        # the body's own quoting must not matter either (an apostrophe used to break shlex)
        "git commit -F - <<'EOF'\ndon't hand-edit > tests/x.py\nEOF",
    ],
)
def test_bash_guard_heredoc_body_is_not_a_write(repo: FixtureRepo, command: str) -> None:
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) is None, command


@pytest.mark.parametrize(
    "command",
    [
        "cat > tests/x.py <<'EOF'\nbody\nEOF",  # the `>` precedes the heredoc tag
        "cat <<'EOF' > tests/x.py\nbody\nEOF",  # ... and after it: still the command line
        "cat <<EOF >> tests/x.py\nbody\nEOF",  # append form, bare tag
        "git commit -F - <<'EOF'\nmsg\nEOF\nrm tests/y.py",  # a real write AFTER the terminator
    ],
)
def test_bash_guard_redirect_on_the_heredoc_command_line_still_fires(repo: FixtureRepo, command: str) -> None:
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) == "deny", command


def test_bash_guard_herestring_is_not_a_heredoc(repo: FixtureRepo) -> None:
    # `<<<` is a different construct (one shlex word, no body): the redirect after it still fires.
    cmd = "grep foo <<< 'a b' > tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_heredoc_preserves_cd_awareness(repo: FixtureRepo, tmp_path: Path) -> None:
    # T06f regression: cd-tracking and heredoc-stripping compose — the body is dropped and the
    # opener line's relative target still resolves against the EFFECTIVE cwd, not the session one.
    scratch = f"cd {tmp_path / 'mut'} && cat > tests/x.py <<'EOF'\nbody\nEOF"
    assert decision(_run_anchored(scratch, agent_type="evaluator", root=repo.root)) is None
    in_repo = "cat > tests/x.py <<'EOF'\nbody\nEOF"
    assert decision(_run_anchored(in_repo, agent_type="evaluator", root=repo.root)) == "deny"


def test_bash_guard_heredoc_preserves_the_owned_tree_allowance(repo: FixtureRepo) -> None:
    # T06d regression: the owner still writes its own tree through a heredoc.
    cmd = "cat > tests/x.py <<'EOF'\nbody\nEOF"
    assert decision(_run_anchored(cmd, agent_type="test-author", root=repo.root)) is None


# =======================================================================================
# bash_guard — the real tokeniser (T06i)
# =======================================================================================
#
# The six point fixes above each closed one variant and left the next to be discovered by the
# agent it blocked. The seventh arrived while the decision task was open, so the shape changed
# instead of growing a seventh patch: quoted spans are masked (a quoted operator is data),
# `shlex(punctuation_chars=…)` yields the shell operators as their own tokens, the stream is split
# into simple commands, and a mutator counts only in COMMAND POSITION. Every case above passed the
# rewrite unchanged — that suite is the specification of what the guard means. What follows pins
# the two variants that motivated it plus the classes the new shape closes as a side effect.


def test_bash_guard_control_operator_glued_to_a_quoted_word(repo: FixtureRepo) -> None:
    # Variant 6, verbatim (cost a builder two denied commands): the `;` glued to `"$S"` was no
    # CONTROL token, so `rm`'s target slice ran to the end of the line and swallowed the later
    # `cp`'s SOURCE — a path the command only READS — which is then what the denial blamed.
    swallow = 'rm -rf "$S"; cp .claude/tools/x.py "$S/x.py"'
    assert decision(_run_anchored(swallow, agent_type="v3-builder", root=repo.root)) is None
    # ... and a single space before the `;` used to flip the verdict. Now both read the same.
    spaced = 'rm -rf "$S" ; cp .claude/tools/x.py "$S/x.py"'
    assert decision(_run_anchored(spaced, agent_type="v3-builder", root=repo.root)) is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf tests/x.py; cp /tmp/a /tmp/b",  # the rm's OWN target is protected
        "mkdir -p /tmp/x; echo x > tests/y.py",  # ... and so is the second command's redirect
    ],
)
def test_bash_guard_segmenting_does_not_open_the_protected_tree(repo: FixtureRepo, command: str) -> None:
    # Bounding the argument slice at `;` must not lose the write that really is in the tree.
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) == "deny", command


@pytest.mark.parametrize(
    ("command", "role"),
    [
        # Variant 7, verbatim: `$CD` is a scratchpad OUTSIDE the repo, but the guard cannot expand
        # it, so the token was not absolute, got joined onto the repo root, and `specs/` matched.
        ('rm -f "$CD/specs/demo/changes/001-x/ESCALATE"', "v3-builder"),
        ("echo x > ${SCRATCH}/tests/x.py", "evaluator"),
        ("cat > `pwd`/tests/x.py", "evaluator"),
        # the same hole through a `~` the guard would have to expand itself
        ("cat > ~/scratch/tests/x.py", "evaluator"),
    ],
)
def test_bash_guard_unresolvable_target_location_does_not_fire(repo: FixtureRepo, command: str, role: str) -> None:
    # An expansion in the target's FIRST component anchors the path nowhere: indeterminate, so
    # dropped rather than resolved against the repo root (T06b/T06f precision bias, S8 backstop).
    assert decision(_run_anchored(command, agent_type=role, root=repo.root)) is None, command


@pytest.mark.parametrize(
    ("command", "role"),
    [
        # the literal spelling of the same path is still protected for a non-owner
        ("rm -f specs/demo/changes/001-x/ESCALATE", "test-author"),
        # an expansion BELOW the anchoring components leaves the location known
        ("rm -f tests/$name.py", "evaluator"),
        ('rm -f "tests/$name.py"', "evaluator"),
        # `$'…'` is quoting, not an expansion — the target is fully determined
        ("echo x > $'tests/x.py'", "evaluator"),
    ],
)
def test_bash_guard_determinable_target_still_fires(repo: FixtureRepo, command: str, role: str) -> None:
    assert decision(_run_anchored(command, agent_type=role, root=repo.root)) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "grep '>' tests/x.py",  # the redirect character is the search PATTERN
        "git commit -m 'body: ; rm tests/x.py'",  # ... and a whole command inside a message
        'git commit -m "see > tests/x.py"',
    ],
)
def test_bash_guard_quoted_operator_is_data(repo: FixtureRepo, command: str) -> None:
    # Masking quoted spans before lexing is what makes this structural rather than one more
    # special case: after it, every punctuation character left is unquoted, hence a real operator.
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) is None, command


def test_bash_guard_bare_operator_beside_a_quoted_one_still_fires(repo: FixtureRepo) -> None:
    # The discriminating pair: the quoted `>` is data, the bare one is the redirect.
    cmd = "echo '>' > tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("grep -rn rm tests/", None),  # `rm` as a search pattern removes nothing
        ("echo done # rm tests/x.py", None),  # ... nor inside a trailing comment
        ("tee -a /tmp/log < tests/x.py", None),  # an INPUT redirect is a read
        ("sudo rm tests/x.py", "deny"),  # ... but a wrapped mutator is still the mutator
        ("VAR=1 rm tests/x.py", "deny"),
        ("if true; then rm tests/x.py; fi", "deny"),
        ("tee -a tests/x.py < /tmp/log", "deny"),
    ],
)
def test_bash_guard_mutator_counts_in_command_position(repo: FixtureRepo, command: str, expected: str | None) -> None:
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) == expected, command


@pytest.mark.parametrize(
    "command",
    [
        "echo a\nrm tests/x.py",  # a newline ends a command: `rm` is in command position
        "rm \\\n tests/x.py",  # ... but a line continuation does not: one command, one target
        "echo x >| tests/x.py",  # noclobber-override redirect
        "echo x &> tests/x.py",  # stdout+stderr redirect
        "echo x &>> tests/x.py",
    ],
)
def test_bash_guard_operator_inventory(repo: FixtureRepo, command: str) -> None:
    assert decision(_run_anchored(command, agent_type="evaluator", root=repo.root)) == "deny", command


# --- the family, replayed ----------------------------------------------------------------
#
# One list of every false positive the tokeniser family was paid for, so a future rewrite is
# measured against all seven variants at once rather than against the one being fixed.

RECORDED_FALSE_POSITIVES = [
    # T06b — a protected fragment and a `>` inside a quoted commit message
    ('git commit -m "msg with <brackets> and .claude/hooks"', "test-author"),
    # T06e — an absolute path outside the repo that merely contains `tests/`
    ("cat > /tmp/x/tests/conftest.py", "test-author"),
    # T06f A — a relative target inside a scratch tree reached by `cd`
    ("cd /tmp/mut && cat > tests/integration/x_test.py", "evaluator"),
    # T06f A — a filename that merely CONTAINS a protected filename
    ("echo x > notes/users-002-change.md", "test-author"),
    # T06g — a heredoc BODY read as command
    (COMMIT_HEREDOC, "evaluator"),
    # T06i variant 6 — `;` glued to a quoted word; the reason blamed the `cp`'s source
    ('rm -rf "$S"; cp .claude/tools/x.py "$S/x.py"', "v3-builder"),
    # T06i variant 7 — an unexpanded variable resolved against the repo root
    ('rm -f "$CD/specs/demo/changes/001-x/ESCALATE"', "v3-builder"),
]


@pytest.mark.parametrize(("command", "role"), RECORDED_FALSE_POSITIVES)
def test_bash_guard_no_recorded_false_positive_fires(repo: FixtureRepo, command: str, role: str) -> None:
    assert decision(_run_anchored(command, agent_type=role, root=repo.root)) is None, command


@pytest.mark.parametrize(
    ("command", "role"),
    [
        ("cat > tests/x.py", "evaluator"),  # a non-owner writing tests/ in the repo
        ("echo x > specs/demo/changes/001-thing/change.md", "test-author"),  # spec prose is /spec's
        ("rm -rf .claude/tools/gate.py", "implementer"),  # the enforcement tree
    ],
)
def test_bash_guard_in_repo_denials_survive_the_rewrite(repo: FixtureRepo, command: str, role: str) -> None:
    assert decision(_run_anchored(command, agent_type=role, root=repo.root)) == "deny", command


def test_bash_guard_cd_out_and_back_in_survives_the_rewrite(repo: FixtureRepo) -> None:
    # The escalate-if case of the whole family: narrowing resolution must never open the tree.
    cmd = f"cd .. && cat > {repo.root.name}/tests/x.py"
    assert decision(_run_anchored(cmd, agent_type="evaluator", root=repo.root)) == "deny"


# =======================================================================================
# session_stop — ergonomics
# =======================================================================================


def _finish_change(repo: FixtureRepo) -> None:
    """Bring the change dir to a resolved state: all criteria checked + verdict.md present."""
    checked = CRITERIA_MD.replace("- [ ] AC-1:", "- [x] AC-1:").replace("- [ ] AC-2:", "- [x] AC-2:")
    repo.write(CRITERIA_REL, checked)
    repo.write("specs/demo/changes/001-thing/verdict.md", "# Verdict\nGate: GREEN\n")


def _on_change_branch(repo: FixtureRepo) -> FixtureRepo:
    """Put the fixture on a `change/<ctx>-NNN` branch — the only branch session_stop fires on."""
    repo.git("checkout", "-q", "-b", "change/demo-001")
    return repo


def test_session_stop_blocks_on_unchecked_criteria(repo: FixtureRepo) -> None:
    _on_change_branch(repo)
    proc = run_hook("session_stop.py", {"cwd": str(repo.root)}, cwd=repo.root)
    assert decision(proc) == "block", proc.stdout
    assert "unchecked" in proc.stdout


def test_session_stop_blocks_on_missing_verdict(repo: FixtureRepo) -> None:
    _on_change_branch(repo)
    repo.write(CRITERIA_REL, CRITERIA_MD.replace("- [ ] AC-1:", "- [x] AC-1:").replace("- [ ] AC-2:", "- [x] AC-2:"))
    proc = run_hook("session_stop.py", {"cwd": str(repo.root)}, cwd=repo.root)
    assert decision(proc) == "block", proc.stdout
    assert "verdict.md" in proc.stdout


def test_session_stop_allows_when_resolved(repo: FixtureRepo) -> None:
    _on_change_branch(repo)
    _finish_change(repo)
    proc = run_hook("session_stop.py", {"cwd": str(repo.root)}, cwd=repo.root)
    assert decision(proc) is None, proc.stdout


def test_session_stop_escalate_blocks_then_allows_after_human_turn(repo: FixtureRepo) -> None:
    _on_change_branch(repo)
    _finish_change(repo)  # otherwise the criteria/verdict reasons would fire first
    repo.write("specs/demo/changes/001-thing/ESCALATE", "ceiling reached\n")
    first = run_hook("session_stop.py", {"cwd": str(repo.root), "stop_hook_active": False}, cwd=repo.root)
    assert decision(first) == "block", first.stdout
    assert "ESCALATE" in first.stdout
    # already surfaced (stop_hook_active) -> let the human take over; only a human removes ESCALATE
    again = run_hook("session_stop.py", {"cwd": str(repo.root), "stop_hook_active": True}, cwd=repo.root)
    assert decision(again) is None, again.stdout


# T06c (F1b) — the hook is scoped to an active cycle: only a change/<ctx>-NNN branch fires it.


def test_session_stop_passes_through_on_base_branch_with_floating_escalate(repo: FixtureRepo) -> None:
    # make_repo leaves the fixture on the default (base/build) branch — not a change branch.
    _finish_change(repo)  # unresolved reasons must NOT matter off-cycle
    repo.write("specs/demo/changes/001-thing/ESCALATE", "stale, floating on the build branch\n")
    proc = run_hook("session_stop.py", {"cwd": str(repo.root), "stop_hook_active": False}, cwd=repo.root)
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout  # a stale ESCALATE off-cycle never deadlocks


def test_session_stop_passes_through_on_base_branch_with_unchecked_criteria(repo: FixtureRepo) -> None:
    # Unchecked criteria on the base branch (design turn) must not block an ordinary Stop.
    proc = run_hook("session_stop.py", {"cwd": str(repo.root)}, cwd=repo.root)
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout


def test_session_stop_passes_through_on_change_branch_before_baseline(repo: FixtureRepo) -> None:
    # F6: /spec authors the change and creates the change branch, but the red baseline tag does
    # not exist until the test-author runs in /implement. The spec-author session legitimately
    # ends with criteria still `[ ]` and no verdict.md, so the hook must pass through until the
    # baseline exists — the branch alone is not enough to declare the cycle live.
    _on_change_branch(repo)
    repo.git("tag", "-d", "baseline/demo-001")
    proc = run_hook("session_stop.py", {"cwd": str(repo.root)}, cwd=repo.root)
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout


def test_session_stop_escalate_blocks_on_change_branch(repo: FixtureRepo) -> None:
    _on_change_branch(repo)
    _finish_change(repo)
    repo.write("specs/demo/changes/001-thing/ESCALATE", "ceiling reached\n")
    proc = run_hook("session_stop.py", {"cwd": str(repo.root), "stop_hook_active": False}, cwd=repo.root)
    assert decision(proc) == "block", proc.stdout
    assert "ESCALATE" in proc.stdout


# =======================================================================================
# subagent_stop — re-runs the real gate.py
# =======================================================================================


def _implementer(payload: dict) -> dict:
    """Tag a SubagentStop payload as the implementer stopping (F-2: payload carries agent_type)."""
    return {**payload, "agent_type": "implementer"}


def test_subagent_stop_allows_when_gate_green(repo: FixtureRepo) -> None:
    proc = run_hook("subagent_stop.py", _implementer({"cwd": str(repo.root), "stop_hook_active": False}), cwd=repo.root)
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout  # not blocked
    assert repo.verdict()["result"] == "GREEN"


def test_subagent_stop_blocks_while_gate_red(repo: FixtureRepo) -> None:
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)  # A4 construct-smoke failure -> gate RED
    proc = run_hook("subagent_stop.py", _implementer({"cwd": str(repo.root), "stop_hook_active": False}), cwd=repo.root)
    assert decision(proc) == "block", proc.stdout
    assert "smoke.construct" in proc.stdout  # names the failed check


def test_subagent_stop_writes_escalate_at_ceiling(repo: FixtureRepo) -> None:
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)
    proc = run_hook(
        "subagent_stop.py",
        _implementer({"cwd": str(repo.root), "stop_hook_active": True}),
        cwd=repo.root,
        env={"WORKFLOW_STOP_CEILING": "0"},  # escalate immediately
    )
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) != "block", proc.stdout  # stop is allowed once escalated
    escalate = repo.root / "specs/demo/changes/001-thing/ESCALATE"
    assert escalate.exists(), "hook must author the ESCALATE file (E-08)"
    assert "gate.py stayed RED" in escalate.read_text(encoding="utf-8")


def test_subagent_stop_gate_path_prefers_the_plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # T15/D4: installed as a plugin the gate is NOT under the project, so CLAUDE_PLUGIN_ROOT wins
    # — but only when it really holds one, otherwise the checked-out location is the answer.
    mod = _load_hook("subagent_stop")
    root = tmp_path / "project"
    root.mkdir()

    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert mod.gate_path(root) == root / ".claude" / "tools" / "gate.py"

    plugin = tmp_path / "plugins" / "adw"
    (plugin / "tools").mkdir(parents=True)
    (plugin / "tools" / "gate.py").write_text("")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    assert mod.gate_path(root) == plugin / "tools" / "gate.py"

    # a relative value (the workflow's own repo sets `.claude`) resolves against the acting root
    checked_out = root / ".claude" / "tools"
    checked_out.mkdir(parents=True)
    (checked_out / "gate.py").write_text("")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", ".claude")
    assert mod.gate_path(root) == checked_out / "gate.py"

    # a value that names no tools directory must not defeat the fallback
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "nowhere"))
    assert mod.gate_path(root) == root / ".claude" / "tools" / "gate.py"


def test_subagent_stop_gate_python_prefers_venv(tmp_path: Path) -> None:
    # F7: the hook re-runs gate.py, whose toolchain/smoke need the app's deps. Claude Code
    # launches the hook with the ambient system python (no fastapi), so it must prefer the
    # project's .venv interpreter, falling back to the launching interpreter only when no
    # venv exists (test fixtures have a pyproject but no venv — the fallback keeps them as-is).
    mod = _load_hook("subagent_stop")

    # no venv in the tree -> fall back to the launching interpreter
    assert mod.gate_python(tmp_path) == sys.executable

    # a .venv/bin/python present -> that interpreter is chosen over sys.executable
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("")
    assert mod.gate_python(tmp_path) == str(venv_py)


# T06c (F1) — only the implementer is held-and-counted; other agents pass straight through.


def test_subagent_stop_passes_through_non_implementer_while_red(repo: FixtureRepo) -> None:
    # The test-author's deliverable IS a red gate — its stop must NOT block or bump the counter.
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)  # gate is RED
    proc = run_hook(
        "subagent_stop.py",
        {"cwd": str(repo.root), "stop_hook_active": False, "agent_type": "test-author"},
        cwd=repo.root,
    )
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout  # not blocked
    assert not proc.stdout.strip(), "no gate run, no output for a non-implementer stop"
    # counter untouched: the hook never wrote it, and no ESCALATE was authored
    assert not (repo.root / ".gate/subagent-stop-count").exists()
    assert not (repo.root / "specs/demo/changes/001-thing/ESCALATE").exists()


def test_subagent_stop_passes_through_when_agent_type_absent(repo: FixtureRepo) -> None:
    # Defensive: a payload with no agent_type is treated as not-the-implementer.
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)  # gate is RED
    proc = run_hook("subagent_stop.py", {"cwd": str(repo.root), "stop_hook_active": False}, cwd=repo.root)
    assert proc.returncode == 0, proc.stderr
    assert decision(proc) is None, proc.stdout


# T15/D1 — installed as a plugin the payload says `adw:implementer`. Comparing the whole string
# would release the implementer on every RED gate, i.e. silently undo T06c in every consumer.


def test_subagent_stop_holds_a_namespaced_implementer(repo: FixtureRepo) -> None:
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)  # gate is RED
    proc = run_hook(
        "subagent_stop.py",
        {"cwd": str(repo.root), "stop_hook_active": False, "agent_type": "adw:implementer"},
        cwd=repo.root,
    )
    assert decision(proc) == "block", proc.stdout
    assert "smoke.construct" in proc.stdout


def test_subagent_stop_passes_through_a_namespaced_non_implementer(repo: FixtureRepo) -> None:
    repo.write("src/app/main.py", SRC_MAIN_BROKEN)  # gate is RED
    proc = run_hook(
        "subagent_stop.py",
        {"cwd": str(repo.root), "stop_hook_active": False, "agent_type": "adw:test-author"},
        cwd=repo.root,
    )
    assert decision(proc) is None, proc.stdout
    assert not proc.stdout.strip(), "no gate run, no output for a non-implementer stop"


def test_subagent_stop_is_implementer_reads_both_forms() -> None:
    mod = _load_hook("subagent_stop")
    assert mod.is_implementer("implementer")
    assert mod.is_implementer("adw:implementer")
    assert not mod.is_implementer("adw:test-author")
    assert not mod.is_implementer("implementer-helper")
    assert not mod.is_implementer(None)
    assert not mod.is_implementer("")


# T06j — a gate that CANNOT RUN is not a RED: its sentence must reach the human, and it must
# not cost the implementer an iteration of a ceiling it can never work its way out of.


def _bare_venv(root: Path) -> None:
    """A real interpreter with no mypy/ruff/pytest — the consumer's first-run environment.

    Placed at <root>/.venv so gate_python() picks it exactly as it would in a real project (F7):
    the gate then genuinely aborts on its own toolchain preflight (T12b), no stubbing involved.
    """
    proc = subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root / ".venv")], capture_output=True)
    if proc.returncode != 0:  # pragma: no cover — environment without ensurepip/venv
        pytest.skip("python -m venv unavailable")


def test_subagent_stop_surfaces_unrunnable_gate_without_spending_a_block(repo: FixtureRepo) -> None:
    # The gate aborts (exit 2, no verdict.json) because the project's environment lacks the
    # toolchain. Before T06j the hook read only verdict.json, reported `gate produced no
    # verdict.json`, blocked — and did so three times before writing an ESCALATE for a defect
    # no src/** edit can clear. Now the gate's own sentence comes out, once, and costs nothing.
    _bare_venv(repo.root)
    (repo.root / ".gate").mkdir(exist_ok=True)
    (repo.root / ".gate/subagent-stop-count").write_text("2\n", encoding="utf-8")  # 2 blocks already spent

    proc = run_hook("subagent_stop.py", _implementer({"cwd": str(repo.root), "stop_hook_active": False}), cwd=repo.root)

    assert proc.returncode == 0, proc.stderr
    assert decision(proc) != "block", proc.stdout  # released, not held
    message = json.loads(proc.stdout)["systemMessage"]
    assert "toolchain missing from this project's environment" in message
    for tool in ("mypy", "ruff", "pytest"):
        assert tool in message
    assert "uv sync" in message  # the fix, not just the symptom
    assert "gate produced no verdict.json" not in message  # the swallowed-diagnostic wording is gone
    # the ceiling is untouched: not spent (this was no iteration), not reset (no free unblock)
    assert (repo.root / ".gate/subagent-stop-count").read_text(encoding="utf-8").strip() == "2"
    assert not (repo.root / "specs/demo/changes/001-thing/ESCALATE").exists()


def test_subagent_stop_surfaces_a_crashed_gate_too(repo: FixtureRepo) -> None:
    # Exit 2 is the deliberate abort; any other exit with no verdict is a crash. Both are
    # "the gate could not answer" — the implementer is released either way, with the tail.
    repo.write(
        ".claude/tools/gate.py",
        "import sys\nprint('boom: gate exploded', file=sys.stderr)\nsys.exit(1)\n",
    )
    proc = run_hook("subagent_stop.py", _implementer({"cwd": str(repo.root), "stop_hook_active": False}), cwd=repo.root)

    assert proc.returncode == 0, proc.stderr
    assert decision(proc) != "block", proc.stdout
    message = json.loads(proc.stdout)["systemMessage"]
    assert "boom: gate exploded" in message
    assert "exit 1" in message
    assert not (repo.root / ".gate/subagent-stop-count").exists()  # never counted


def test_unrunnable_message_names_the_abort_and_keeps_the_gate_wording() -> None:
    mod = _load_hook("subagent_stop")
    aborted = mod.unrunnable_message(2, "", "error: toolchain missing from this project's environment (...): ruff")
    assert "aborted (exit 2)" in aborted
    assert "toolchain missing from this project's environment" in aborted

    crashed = mod.unrunnable_message(1, "stdout tail", "")
    assert "exit 1" in crashed
    assert "stdout tail" in crashed  # falls back to stdout when stderr is empty

    silent = mod.unrunnable_message(9, "", "")
    assert "no output" in silent  # a silent failure still says something


# =======================================================================================
# Bypass proof — the hook is porous; gate.py catches it post-hoc (S8)
# =======================================================================================


def test_criteria_reword_denied_by_hook_and_red_at_gate(repo: FixtureRepo) -> None:
    reworded = CRITERIA_MD.replace("returns the sum `3`", "returns any value")
    # 1) the hook denies the Write ...
    assert decision(run_hook("criteria_guard.py", _write_payload(repo, reworded), cwd=repo.root)) == "deny"
    # 2) ... and if the agent bypasses the hook and writes it anyway, the gate goes RED
    repo.write(CRITERIA_REL, reworded)
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.criteria-flips"] == "FAIL"


def test_shell_edit_missed_by_hook_is_red_at_gate(repo: FixtureRepo) -> None:
    # A shell edit the bash_guard's best-effort matcher might miss still hits the gate.
    reworded = CRITERIA_MD.replace("returns the sum `3`", "returns any value")
    repo.write(CRITERIA_REL, reworded)  # stands in for `sed -i` slipping through
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.criteria-flips"] == "FAIL"


def test_conftest_suppression_bypass_is_red_at_gate(repo: FixtureRepo) -> None:
    repo.write(
        "conftest.py",
        "def pytest_collection_modifyitems(config, items):\n"
        '    items[:] = [i for i in items if "test_add_zero" not in i.nodeid]\n',
    )
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.test-inventory"] == "FAIL"


def test_baseline_test_deleted_is_red_at_gate(repo: FixtureRepo) -> None:
    repo.write("tests/test_core.py", TESTS_CORE.replace('@pytest.mark.ac("AC-1")\ndef test_add', "def _gone", 1))
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.test-inventory"] == "FAIL"


def test_gate_self_edit_bypass_is_red_at_gate(repo: FixtureRepo) -> None:
    repo.append(".claude/tools/gate.py", "\n# softened after baseline\n")
    proc = repo.gate()
    assert proc.returncode == 1
    assert repo.statuses()["integrity.self-hash"] == "FAIL"
