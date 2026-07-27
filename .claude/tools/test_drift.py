"""Tests for drift.py — the §5.5 drift check (workflow v3, T17).

One fixture git repo per case, built from a stdlib-only fake app: `create_app()` returns an object
whose `openapi()` yields a `paths` mapping, which is the entire contract drift.py needs. No web
framework is involved on purpose — the meta layer's test environment ships none (T15), and the
route inventory is a property of the OpenAPI schema, not of FastAPI.

The load-bearing cases, in the order they matter:
  * a manufactured route that the spec does not describe is REPORTED (a check that runs but cannot
    fail is the defect class notes/19 is about);
  * every degenerate input reports UNDETERMINED and never CLEAN (T10f's rule, walked as a list so
    a new degenerate path is covered by construction);
  * the hotfix half is accept.py's one implementation, not a copy (C7).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
DRIFT = TOOLS_DIR / "drift.py"

# --- fixture tree content --------------------------------------------------------------

APP_INIT = '"""Fixture app package."""\n'

APP_MAIN = '''\
"""Fixture app factory: the openapi() surface drift.py reads, with no framework involved."""

PATHS = %s


class App:
    """Stand-in for the constructed application."""

    def openapi(self) -> dict:
        return {"openapi": "3.1.0", "paths": PATHS}


def create_app() -> App:
    return App()
'''

APP_MAIN_BROKEN = '''\
"""Fixture app factory that raises at construction time (the A4/T10f failure mode)."""


def create_app() -> object:
    raise RuntimeError("missing framework dependency at construct time")
'''

OVERVIEW = """\
# health — overview

## Capabilities

- `service-health.md` — the liveness probe an operator polls over HTTP.
"""

CAPABILITY = """\
# health / service-health

<!-- The LIVING spec of one capability. Canonical-file writes happen only via accept.py. -->

## Behaviour

The probe is unauthenticated and side-effect free.

## Invariants
- `GET /health` returns 200 with the JSON body `{"status": "ok"}`. (verified by: tests/test_health.py::test_health)
"""


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, rel: str, content: str) -> "Fixture":
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=drift", "-c", "user.email=drift@test", *args],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"git {args} failed: {proc.stdout}{proc.stderr}"
        return proc.stdout

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DRIFT), "--tree", str(self.root), *args],
            capture_output=True,
            text=True,
            cwd=self.root,
        )

    def verdict(self, *args: str) -> str:
        proc = self.run(*args)
        match = re.search(r"^verdict: (\w+)$", proc.stdout, re.MULTILINE)
        assert match, f"no verdict line in:\n{proc.stdout}{proc.stderr}"
        return match.group(1)


def make_tree(
    root: Path,
    *,
    paths: str | None = '{"/health": {"get": {}}}',
    capability: str | None = CAPABILITY,
    broken_app: bool = False,
) -> Fixture:
    """A git repo whose one commit carries the app + spec, tagged as an accepted change.

    Tagging is what makes the hotfix half CLEAN, so a case about the surface half is not muddied
    by unattached src commits (and one case deliberately un-tags itself).
    """
    fx = Fixture(root)
    root.mkdir(parents=True, exist_ok=True)
    fx.git("init", "-q")
    fx.git("config", "user.name", "drift")
    fx.git("config", "user.email", "drift@test")
    if broken_app:
        fx.write("src/app/__init__.py", APP_INIT).write("src/app/main.py", APP_MAIN_BROKEN)
    elif paths is not None:
        fx.write("src/app/__init__.py", APP_INIT).write("src/app/main.py", APP_MAIN % paths)
    if capability is not None:
        fx.write("specs/health/overview.md", OVERVIEW).write("specs/health/service-health.md", capability)
    fx.write("README.md", "fixture\n")
    fx.commit("the change that shipped the app and its spec")
    fx.git("tag", "change/health-001")
    return fx


@pytest.fixture()
def clean(tmp_path: Path) -> Fixture:
    return make_tree(tmp_path / "app")


# --- the clean case ---------------------------------------------------------------------


def test_a_described_route_reports_clean(clean: Fixture) -> None:
    proc = clean.run()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verdict: CLEAN" in proc.stdout
    assert "[ok] GET /health — described in" in proc.stdout
    assert "every src commit is attached to a change/* tag" in proc.stdout


def test_the_report_states_that_it_never_denies(clean: Fixture) -> None:
    # The canon boundary: §5.5 SURFACES drift, it does not gate. A reader who takes the exit
    # status for a merge condition has been misled by this script.
    assert "never denies" in clean.run().stdout


@pytest.mark.parametrize(
    "decider",
    ["gate.py", "accept.py", "red_check.py"]
    + [f"../hooks/{h}" for h in ("bash_guard.py", "criteria_guard.py")]
    + [f"../hooks/{h}" for h in ("subagent_stop.py", "session_stop.py")],
)
def test_no_decider_runs_this_script(decider: str) -> None:
    """Nothing that can DENY may invoke drift.py, or §5.5 would have become a gate by the back door.

    Making it deny would change canon (a hotfix is legal, only not silent). A MENTION is not the
    risk and must stay legal — `accept.py`'s report points the reader at the tool, and both scripts
    document the reuse seam in prose. An invocation is the risk: a spawned path or an import.
    """
    source = (TOOLS_DIR / decider).read_text(encoding="utf-8")
    invocations = ('"drift.py"', "'drift.py'", "import drift", "drift.report(", "drift.main(")
    hits = [line.strip() for line in source.splitlines() if any(form in line for form in invocations)]
    assert not hits, f"{decider} invokes drift.py: {hits}"


# --- route ⊆ described operations --------------------------------------------------------


def test_a_route_the_spec_does_not_describe_is_reported(tmp_path: Path) -> None:
    # THE case that matters: a route added to the app with no spec change. Manufactured here
    # exactly as the T17 verification manufactures it in the consumer venue.
    fx = make_tree(tmp_path / "app", paths='{"/health": {"get": {}}, "/metrics": {"get": {}}}')
    proc = fx.run()
    assert proc.returncode == 1
    assert "verdict: DRIFT" in proc.stdout
    assert "[DRIFT] GET /metrics — served by app.main, described in no capability file" in proc.stdout
    assert "[ok] GET /health" in proc.stdout  # the described one is still reported as fine


def test_a_route_named_only_inside_an_html_comment_is_undescribed(tmp_path: Path) -> None:
    # T10j's lesson, in the other direction: a comment is not content, so a route "described"
    # only in a commented-out line is not described.
    commented = CAPABILITY.replace("- `GET /health` returns 200", "<!-- - `GET /health` returns 200 -->\n- nothing")
    fx = make_tree(tmp_path / "app", capability=commented)
    assert "[DRIFT] GET /health" in fx.run().stdout


def test_a_path_described_without_its_method_is_reported(tmp_path: Path) -> None:
    without_method = CAPABILITY.replace("`GET /health` returns 200", "the probe at `/health` returns 200")
    fx = make_tree(tmp_path / "app", capability=without_method)
    out = fx.run().stdout
    assert "the path appears in" in out
    assert "no line" in out and "names the GET method" in out


def test_a_parameter_named_differently_in_the_spec_still_matches(tmp_path: Path) -> None:
    fx = make_tree(
        tmp_path / "app",
        paths='{"/users/{user_id}": {"get": {}}}',
        capability=CAPABILITY.replace("`GET /health` returns 200", "`GET /users/{id}` returns 200"),
    )
    proc = fx.run()
    assert proc.returncode == 0, proc.stdout
    assert "[ok] GET /users/{user_id}" in proc.stdout


@pytest.mark.parametrize(
    ("route_path", "spec_path"),
    [
        ("/health", "/healthz"),  # a longer path must not match a shorter route
        ("/users", "/users/{id}"),  # the collection route is not described by the item route
    ],
)
def test_a_similar_path_is_not_taken_for_a_match(tmp_path: Path, route_path: str, spec_path: str) -> None:
    fx = make_tree(
        tmp_path / "app",
        paths='{"' + route_path + '": {"get": {}}}',
        capability=CAPABILITY.replace("`GET /health` returns 200", f"`GET {spec_path}` returns 200"),
    )
    assert f"[DRIFT] GET {route_path} — served by app.main, described in no capability file" in fx.run().stdout


# --- ... and back: described operations ⊆ routes -----------------------------------------


def test_an_operation_the_app_does_not_serve_is_reported(tmp_path: Path) -> None:
    fx = make_tree(
        tmp_path / "app",
        capability=CAPABILITY + "\n- `DELETE /health` clears the cached probe. (MANUAL)\n",
    )
    proc = fx.run()
    assert proc.returncode == 1
    assert "[DRIFT] DELETE /health — described in specs/health/service-health.md, served by no route" in proc.stdout


# --- the hotfix half is accept.py's, invoked not copied (C7) ------------------------------


def test_an_unattached_src_commit_is_surfaced(clean: Fixture) -> None:
    clean.write("src/app/extra.py", '"""A src change nobody legalised."""\n')
    sha = clean.commit("hotfix straight onto the base")
    proc = clean.run()
    assert proc.returncode == 1
    assert "1 src commit(s) not reachable from any change/* tag" in proc.stdout
    assert sha[:12] in proc.stdout


def test_the_hotfix_half_is_not_reimplemented_here() -> None:
    source = DRIFT.read_text(encoding="utf-8")
    assert "hotfix_drift_lines" in source, "drift.py must invoke accept.py's implementation"
    assert "is-ancestor" not in source, "the src-commit/change-tag comparison has one home (C7)"
    assert "merge-base" not in source


def test_the_route_inventory_is_the_gates_one_implementation() -> None:
    """The surface half is not reimplemented either — `gate.route_inventory` is called (C7, T20).

    The gate needs the very same inventory for the `invisible` class's before/after diff, and two
    copies would let the reporter and the decider disagree about what the app serves. The direction
    is fixed by `test_no_decider_runs_this_script`: the gate cannot import this script, so the
    extraction lives in the gate and this script borrows it.
    """
    source = DRIFT.read_text(encoding="utf-8")
    assert "_gate_module().route_inventory" in source, "drift.py must invoke gate.py's implementation"
    assert "importlib.import_module" not in source, "app construction has one home: gate.py (C7)"
    assert "app.openapi()" not in source.replace("`app.openapi()`", ""), "the schema read has one home"
    gate_source = (TOOLS_DIR / "gate.py").read_text(encoding="utf-8")
    assert "def route_inventory(" in gate_source
    assert "def check_invisible_surface(" in gate_source  # the second reader of the same inventory


# --- the undetermined-input rule (T10f) --------------------------------------------------


def _no_app(root: Path) -> Fixture:
    """A living spec describing an operation, with no constructible app surface."""
    return make_tree(root, paths=None)


def _no_spec(root: Path) -> Fixture:
    """Routes served, with no living spec beside them."""
    return make_tree(root, capability=None)


def _broken_app(root: Path) -> Fixture:
    """A factory that exists and will not construct — the A4 failure mode."""
    return make_tree(root, broken_app=True)


def _broken_app_without_a_spec(root: Path) -> Fixture:
    """A factory that will not construct in a tree with no living spec.

    The case that separates "could not read the surface" from "there is no surface": with no spec
    line to describe an operation, a broken factory misclassified as ABSENT would report `[n/a]` and
    exit 0 — the fail-open. Found by mutating route_inventory, not by reasoning.
    """
    return make_tree(root, broken_app=True, capability=None)


def _unresolvable_base(root: Path) -> Fixture:
    return make_tree(root)


UNDETERMINED_INPUTS = {
    "no constructible app but described operations": (_no_app, ()),
    "routes but no living spec": (_no_spec, ()),
    "a factory that will not construct": (_broken_app, ()),
    "a factory that will not construct, with no spec": (_broken_app_without_a_spec, ()),
    "a base branch that does not resolve": (_unresolvable_base, ("--base", "no-such-branch")),
}


@pytest.mark.parametrize("case", sorted(UNDETERMINED_INPUTS))
def test_no_half_reports_clean_on_undetermined_input(tmp_path: Path, case: str) -> None:
    build, args = UNDETERMINED_INPUTS[case]
    fx = build(tmp_path / "app")
    proc = fx.run(*args)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "verdict: UNDETERMINED" in proc.stdout, f"{case}: {proc.stdout}"
    assert "verdict: CLEAN" not in proc.stdout


def test_a_broken_factory_names_the_construction_failure(tmp_path: Path) -> None:
    out = _broken_app(tmp_path / "app").run().stdout
    assert "app.main.create_app()/openapi() did not yield a route list" in out
    assert "missing framework dependency at construct time" in out
    assert "undetermined is NOT clean" in out


def test_an_unresolvable_base_names_the_git_call(tmp_path: Path) -> None:
    out = _unresolvable_base(tmp_path / "app").run("--base", "no-such-branch").stdout
    assert "git log no-such-branch -- src failed" in out


# --- applicability is not cleanliness ----------------------------------------------------


def test_a_tree_with_neither_app_nor_described_operation_is_not_applicable(tmp_path: Path) -> None:
    # The workflow's own repo, permanently. Reporting DRIFT here would train the ignore reflex
    # this check exists to defeat; reporting nothing at all would hide that it did not run.
    fx = make_tree(tmp_path / "meta", paths=None, capability=None)
    proc = fx.run()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verdict: CLEAN" in proc.stdout
    assert "[n/a]" in proc.stdout
    assert "applicability, not cleanliness" in proc.stdout


# --- the base is derived, never defaulted to a name (T10g/C6) ----------------------------


def test_on_a_change_branch_the_base_is_derived(clean: Fixture) -> None:
    base = clean.git("symbolic-ref", "--short", "HEAD").strip()
    clean.git("checkout", "-q", "-b", "change/health-002")
    clean.write("src/app/extra.py", '"""work in progress on the change branch."""\n')
    clean.commit("wip on the change branch")
    out = clean.run().stdout
    assert f"base: {base}" in out, out
    assert "main" not in out.split("hotfix lane")[1].split("observable surface")[0] or base == "main"
