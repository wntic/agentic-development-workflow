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
HOOKS_DIR = TOOLS_DIR.parent / "hooks"
HOOKS = ("criteria_guard.py", "bash_guard.py", "subagent_stop.py", "session_stop.py")

CRITERIA_REL = "specs/demo/changes/001-thing/criteria.md"


def run_hook(
    script: str, payload: dict, *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    e["GATE_DOCKER"] = "0"  # any gate the hook re-runs must skip Docker deterministically
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
    proc = run_hook("bash_guard.py", payload, cwd=TOOLS_DIR)
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
    assert decision(run_hook("bash_guard.py", payload, cwd=TOOLS_DIR)) is None, command


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
