#!/usr/bin/env python3
"""drift.py — the §5.5 drift check as a script (workflow v3, T17).

Spec §5.5 gives the drift check two halves, both reported by `accept.py` AND `/orient`:

  * the HOTFIX lane — src commits on the base branch reachable from no `change/*` tag (L-02/O-08).
    Owned by `accept.py`, which prints it after every `--execute`. Invoked here, never restated
    (C7: `accept.hotfix_drift_lines`).
  * the OBSERVABLE SURFACE — the app's OpenAPI routes against the capability files, in BOTH
    directions ("роуты ⊆ описанные операции и наоборот"). This one needs a CONSTRUCTED app, which
    is why `accept.py` hands it over: `gate.py`'s construct-smoke builds the app, `accept.py` never
    does.

Until T17 each side pointed at the other — `accept.py` deferred the surface half to `/orient` and
`/orient` deferred the whole check to `accept.py`'s arrival — so nobody ran it. This script is that
half plus a call into `accept.py`'s half, so `/adw:orient` has exactly one thing to run.

WHAT THIS IS NOT: a gate. §5.5 SURFACES drift; it never denies. A hotfix past the workflow is
legal, it is only not silent — `/adw:spec --retro` legalises it, and the delta then reaches the
capability file through an ordinary acceptance. Nothing here blocks a merge, no gate reads its exit
status, and the status is a convenience for a reader: 0 = nothing to read, 1 = something to read.

WHY A SCRIPT AND NOT COMMAND PROSE (the T17 decision)

    The comparison has a deterministic core and a semantic residue, and prose could only do the
    residue. The core — which paths+methods the running app actually serves, and which of them
    appear in the living spec at all — is a machine question: an app is constructed, `app.openapi()`
    is authoritative about the surface, and a path template matches or it does not. Left to the
    reader, that core is re-derived by hand every session against a growing corpus (the 2026-07-26
    manual check that found this gap was one route wide; it does not scale, and S4 says a rule
    nobody enforces does not exist).

    The residue is real and stays with the reader: a route may be described in prose that names
    neither its path nor its method, and no matcher can settle that. So this script narrows the
    reader's job instead of pretending to finish it — every route it cannot match is REPORTED as
    "not matched by path", with the file list, for the human to judge. It never concludes that the
    spec is wrong; §5.5 asks it to «репортят рассинхрон», and that is all it does.

THE UNDETERMINED-INPUT RULE (T10f, notes/19_accept_gate_audit.md)

    A half whose input could not be DETERMINED reports UNDETERMINED. Never "clean", never absent.

    Concretely: an app that will not construct, a spec that describes operations while no app
    surface can be built, routes with no living spec beside them, and an unanswerable git question
    each produce a loud UNDETERMINED line and exit 1. The defect class this exists to avoid is the
    one that made the whole family: an empty result read as "nothing wrong" instead of
    "nothing known".

    Distinguished from it, and equally loud: NOT APPLICABLE — a tree with no HTTP surface AND no
    capability line describing one (the workflow's own repo, permanently). There the comparison has
    nothing to compare rather than something it failed to read, which is `gate.py`'s loud-SKIP case,
    not its FAIL case. Collapsing the two would make every run in such a tree report drift, which
    is how a report earns the ignore-reflex the check exists to defeat.

Stdlib-only. `gate.py` and `accept.py` are imported from this directory: the ROUTE INVENTORY
itself (`gate.route_inventory` — the gate needs the same one for the `invisible` class's
before/after diff, T20), the capability corpus rule, the HTML-comment strip and the hotfix
comparison each have exactly one home (C7). The imports run reporter → decider only; nothing that
can deny is allowed to reach this script, which is pinned by a test.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the surface types live in gate.py (C7) — imported for annotations only
    from gate import Route, Surface

sys.dont_write_bytecode = True

TOOLS_DIR = Path(__file__).resolve().parent

_MODULES: dict[str, object] = {}


def _gate_module():  # stdlib-only sibling import
    """`gate.py` from this directory: app construction, the route inventory, the corpus rule (C7).

    Split from the accept import on purpose: the surface half needs only the gate, and a caller
    that wants a route inventory must not drag the acceptance script in with it.
    """
    if "gate" not in _MODULES:
        sys.path.insert(0, str(TOOLS_DIR))
        import gate  # stdlib-sibling import, path just set

        _MODULES["gate"] = gate
    return _MODULES["gate"]


def _accept_module():  # stdlib-only sibling import
    """`accept.py` from this directory: the hotfix half of §5.5 is ITS implementation (C7)."""
    if "accept" not in _MODULES:
        sys.path.insert(0, str(TOOLS_DIR))
        import accept  # stdlib-sibling import, path just set

        _MODULES["accept"] = accept
    return _MODULES["accept"]


CLEAN, DRIFT, UNDETERMINED = "CLEAN", "DRIFT", "UNDETERMINED"

# An operation as a spec author writes it: a method token then a path, `GET /users/{id}` — the one
# form that is unambiguous enough to check in the spec→app direction. A path mentioned with no
# method is not read as an operation (it is a reference), and prose with neither is the semantic
# residue the reader keeps. The method vocabulary is the gate's (C7), so the app side and the spec
# side can never recognise different sets of methods.
SPEC_OPERATION = re.compile(r"\b(" + "|".join(_gate_module().HTTP_METHODS) + r")\b[ \t`]*(/[^\s`,;)\]]*)")

# `{id}` in a route template. FastAPI's schema uses this form; a spec may write `:id` or `<id>`.
PARAM_SEGMENT = re.compile(r"\{[^/}]*\}")
PARAM_ANY = r"(?:\{[^/}]*\}|:[A-Za-z_][A-Za-z0-9_]*|<[^/>]*>)"


# ---------------------------------------------------------------------------------------
# the observable surface: what the constructed app serves
# ---------------------------------------------------------------------------------------
#
# NOT implemented here. Constructing the app and reading `app.openapi()` lives in `gate.py`
# (`route_inventory`, section 3a) — the gate already builds the app on every run, owns the import
# environment, and needs the very same inventory for the `invisible` class's before/after diff
# (§3.1, T20). One implementation, two readers (C7); and the dependency runs reporter → decider,
# never the reverse, because nothing that can DENY may reach this script (§5.5 surfaces only).


def route_inventory(tree: Path) -> Surface:
    """The tree's OpenAPI operation surface — `gate.route_inventory`, cited not restated (C7)."""
    return _gate_module().route_inventory(tree)


# ---------------------------------------------------------------------------------------
# the living spec: what the capability files describe
# ---------------------------------------------------------------------------------------


@dataclass
class Corpus:
    lines: list[tuple[Path, str]] = field(default_factory=list)  # (file, one comment-stripped line)
    files: list[Path] = field(default_factory=list)
    absent: str = ""  # no living spec in this tree at all


def capability_corpus(tree: Path) -> Corpus:
    """Every canonical spec line, HTML comments blanked out. Paths are tree-relative (a reader's
    report names `specs/<context>/<capability>.md`, not an absolute path nobody can compare).

    A comment is not content (T10j): the capability template's own comment documents the invariant
    form with a `<test-id>` placeholder, and a route named inside a comment describes nothing. Both
    the corpus rule and the strip come from the tools that already own them.
    """
    gate = _gate_module()
    lint = gate._criteria_lint()
    files = gate.capability_files(tree)
    if not files:
        return Corpus(absent=f"no capability files under {tree / 'specs'} — this tree carries no living spec")
    corpus = Corpus(files=[p.relative_to(tree) for p in files])
    for path in files:
        stripped = lint.strip_html_comments(path.read_text(encoding="utf-8", errors="replace").splitlines())
        corpus.lines += [(path.relative_to(tree), line) for line in stripped if line.strip()]
    return corpus


def spec_operations(corpus: Corpus) -> list[tuple[Path, str, str]]:
    """Every `METHOD /path` operation a capability line spells out: (file, method, path)."""
    found: list[tuple[Path, str, str]] = []
    for path, line in corpus.lines:
        found += [(path, method, spec_path) for method, spec_path in SPEC_OPERATION.findall(line)]
    return found


def _shape(route_path: str) -> str:
    """A route template as a regex body: literal segments escaped, `{param}` matching any spelling."""
    parts = [PARAM_ANY if PARAM_SEGMENT.fullmatch(segment) else re.escape(segment) for segment in route_path.split("/")]
    return "/".join(parts)


def path_mention(route_path: str) -> re.Pattern[str]:
    """Matches this route's path where a spec line mentions it, and nothing longer.

    The tail guard is what keeps `/health` out of `/healthz` and the collection route `/users` out
    of `/users/{id}` — a substring match would report a described route as described by accident.
    """
    return re.compile(r"(?<![\w\-/])" + _shape(route_path) + r"/?(?![\w\-/{<:])")


def serves(route: Route, method: str, path: str) -> bool:
    """Does `route` serve the operation a spec line spells as `method path`?"""
    return route.method == method and re.fullmatch(_shape(route.path) + "/?", path) is not None


# ---------------------------------------------------------------------------------------
# the comparison, both directions
# ---------------------------------------------------------------------------------------


@dataclass
class Finding:
    status: str  # DRIFT | UNDETERMINED
    text: str


def compare(surface: Surface, corpus: Corpus) -> tuple[list[Finding], list[str]]:
    """Return (findings, ok-lines). Findings are surfaced for the reader, never a verdict."""
    findings: list[Finding] = []
    ok: list[str] = []

    # route ⊆ described operations
    for route in surface.routes:
        pattern = path_mention(route.path)
        hits = [(path, line) for path, line in corpus.lines if pattern.search(line)]
        if not hits:
            findings.append(
                Finding(
                    DRIFT,
                    f"{route.method} {route.path} — served by {route.module}, described in no capability file "
                    "(an unlegalised change, or prose that names neither the path nor the method: read it)",
                )
            )
            continue
        named = [path for path, line in hits if re.search(rf"\b{route.method}\b", line)]
        if named:
            ok.append(f"{route.method} {route.path} — described in {_files(named)}")
        else:
            findings.append(
                Finding(
                    DRIFT,
                    f"{route.method} {route.path} — the path appears in {_files([p for p, _ in hits])} but no line "
                    f"there names the {route.method} method: the operation may be undescribed",
                )
            )

    # ... and back: described operations ⊆ routes
    for path, method, spec_path in spec_operations(corpus):
        if not any(serves(route, method, spec_path) for route in surface.routes):
            findings.append(
                Finding(
                    DRIFT,
                    f"{method} {spec_path} — described in {path}, served by no route of the constructed app "
                    "(behaviour removed without the spec following, or a spec that ran ahead)",
                )
            )
    return findings, ok


def _files(paths: list[Path]) -> str:
    seen = sorted({str(p) for p in paths})
    return ", ".join(seen[:5]) + (f" (+{len(seen) - 5} more)" if len(seen) > 5 else "")


# ---------------------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------------------


def resolve_base(tree: Path, base: str | None) -> tuple[str, str]:
    """The branch whose src commits the hotfix half examines: `(base, error)`.

    NOT `accept.derive_base` unconditionally: that function answers "which branch does the change
    at HEAD merge into", and it EXCLUDES the current branch by construction. `/orient` normally runs
    while standing ON the base — the question there is about the branch you are on. So: an ordinary
    branch at HEAD is the base; a `change/*` branch or a detached HEAD delegates to `accept.py`'s
    derivation, whose ambiguity is reported and never guessed (T10g), and no name is ever defaulted
    (`main` is right for most projects and wrong for this one, C6).
    """
    accept = _accept_module()
    if base:
        return base, ""
    rc, out = accept._git(tree, "symbolic-ref", "--quiet", "--short", "HEAD")
    current = out.strip() if rc == 0 else ""
    if current and not current.startswith(accept.CHANGE_BRANCH_PREFIX):
        return current, ""
    try:
        return accept.derive_base(tree), ""
    except accept.AcceptError as exc:
        return "", str(exc)


def _undetermined(out: list[str], reason: str) -> str:
    head, *rest = reason.splitlines()
    out.append(f"  [{UNDETERMINED}] {head}")
    out += [f"      {line}" for line in rest]
    out.append("      undetermined is NOT clean — the comparison did not run (T10f)")
    return UNDETERMINED


def _surface_section(tree: Path, out: list[str]) -> str:
    """The surface half, appending its lines to `out` and returning its status.

    The four input states are kept apart because collapsing them is how this whole family of
    defects reads "nothing known" as "nothing wrong":

      1. a factory that will not construct       -> UNDETERMINED (the T10f case)
      2. no HTTP surface, but the spec describes
         operations                              -> UNDETERMINED (half the input is missing)
      3. no HTTP surface and no described
         operation                               -> not applicable, said out loud (this repo's
                                                    permanent case: a meta layer with no app)
      4. routes but no living spec               -> UNDETERMINED (a tree outside the spec store)
    """
    surface = route_inventory(tree)
    corpus = capability_corpus(tree)
    if surface.undetermined:
        return _undetermined(out, surface.undetermined)
    described = spec_operations(corpus)
    if surface.absent:
        if described:
            return _undetermined(
                out,
                f"{surface.absent}, yet {len(described)} operation(s) are described in the living spec:\n"
                + "\n".join(f"{method} {path} ({file})" for file, method, path in described[:20]),
            )
        out.append(f"  [n/a] {surface.absent}; no capability line describes an HTTP operation either")
        out.append("        nothing to compare — this is applicability, not cleanliness")
        return CLEAN
    if corpus.absent:
        return _undetermined(out, f"{corpus.absent}, yet {len(surface.routes)} route(s) are served")
    out.append(f"  surface: {len(surface.routes)} route(s) from {', '.join(surface.modules)}")
    out.append(f"  corpus:  {len(corpus.files)} capability file(s), {len(corpus.lines)} non-empty line(s)")
    findings, ok = compare(surface, corpus)
    out += [f"  [ok] {line}" for line in ok]
    out += [f"  [{finding.status}] {finding.text}" for finding in findings]
    return DRIFT if findings else CLEAN


def report(tree: Path, base: str | None) -> tuple[str, list[str]]:
    """Run both halves of §5.5 over `tree`. Returns (verdict, report lines)."""
    accept = _accept_module()
    out = [f"drift-check (spec §5.5) on {tree}", ""]
    statuses: list[str] = []

    resolved, base_error = resolve_base(tree, base)
    out.append("hotfix lane — src commits on the base not tied to a change/* tag (L-02/O-08):")
    if base_error:
        statuses.append(UNDETERMINED)
        out += [
            f"  [{UNDETERMINED}] the base branch could not be resolved, so the comparison did not run:",
            f"    {base_error}",
        ]
    else:
        half = accept.hotfix_drift_lines(tree, resolved)
        statuses.append(UNDETERMINED if not half.determined else (CLEAN if half.status == "PASS" else DRIFT))
        out.append(f"  base: {resolved}")
        out += half.lines
    out.append("")

    out.append("observable surface — OpenAPI routes vs capability files, both directions:")
    statuses.append(_surface_section(tree, out))

    verdict = UNDETERMINED if UNDETERMINED in statuses else (DRIFT if DRIFT in statuses else CLEAN)
    out += [
        "",
        f"verdict: {verdict}",
        "§5.5 surfaces drift; it never denies. A hotfix is legal — `/adw:spec --retro` legalises it "
        "and the delta reaches the capability file through an ordinary acceptance.",
    ]
    return verdict, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drift.py",
        description="workflow v3: the §5.5 drift check — the base's unattached src commits "
        "(accept.py's half) plus the constructed app's OpenAPI routes against the capability files, "
        "in both directions. Reports; never denies.",
    )
    parser.add_argument("--tree", default=".", help="work-tree root (default: cwd)")
    parser.add_argument(
        "--base",
        default=None,
        help="the branch whose src commits are checked against change/* tags; omitted, it is the "
        "branch at HEAD, or (on a change/* branch or a detached HEAD) derived as accept.py derives it",
    )
    args = parser.parse_args(argv)

    tree = Path(args.tree).resolve()
    if not tree.is_dir():
        print(f"error: tree {tree} is not a directory", file=sys.stderr)
        return 2
    verdict, lines = report(tree, args.base)
    print("\n".join(lines))
    return 0 if verdict == CLEAN else 1


if __name__ == "__main__":
    sys.exit(main())
