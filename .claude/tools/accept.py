#!/usr/bin/env python3
"""accept.py — acceptance preconditions as a script (workflow v3, spec §5.4/§5.5).

The single, deterministic path by which a change reaches the S9 base branch and the
canonical capability spec. Acceptance is preconditions-as-code, not command prose (E-09,
principle S4): every gate below either PASSES, FLAGS (surfaced for the human's review,
never blocking silently), or FAILS (denies the merge). `/accept-change` (T10) wraps this
with the human's diff review and the LLM contradiction-hunt pass — the deterministic core
lives here.

Usage:
    accept.py <context>/NNN [--base <branch>] [--execute] [--placement <json>] [--tree <dir>]

  check mode (default): run every gate, print the results AND the prepared merge diff for
                        the human. Touches nothing.
  --execute:            perform the post-approval actions (§5.4) ONLY when no gate FAILs —
                        merge criteria into capability invariants, merge the branch to the
                        base, tag, delete the change dir, then run and print the §5.5 drift
                        check. Requires a clean work tree.
  --placement <json>:   the /accept-change-approved invariant->capability map for a MULTI-target
                        `Affects`; invariant distribution is a semantic act the command owns
                        (§5.4). Single-target is deterministic and ignores it; multi-target with
                        no map is refused (accept.py never dumps every invariant into file[0]).

Gates, in the §5.4 order:
  1. criteria.md: all items [x]|[m] (no open [ ]); every [x] junit-backed and every [m]
     carries a verdict.md entry (reusing gate.py's own criteria checker — one
     implementation); verdict SHA == branch HEAD, else recompute is demanded only when the
     verdict-SHA..HEAD diff intersects the change's files (L-04).
  2. gate.py GREEN on the branch; a DOCKER SKIPPED / docker-exempt integration run is
     surfaced as an EXPLICIT flag (T04b — accepting a skipped Docker tier is a conscious
     human decision, never a silent default); no ESCALATE file; Companion accepted.
  3. Affects-intersection vs in-flight changes → flag list (L-03).
  4. merge-fidelity pre-check: every acceptance criterion of the delta is findable in the
     prepared capability-file merge diff (L-11) — the human's stamp lands on a verified diff.
  5. spec-lint: dangling refs, duplicate capabilities, >300-line files, a capability missing
     from overview.md (L-07/O-13).
  6. orphan sweep (removal flavour): removed behaviour lingers neither in spec text nor as
     dead src symbols (V-02/§5.4) — and a change that DECLARES a removal on its `Class:` line
     without a `## Removed` heading is a FLAG, not silence: the sweep cannot run on free prose,
     so the human sees that V-02 did not run (S4).

Plus one cross-§ gate on the evaluator↔accept seam T09 opened (spec §6 step 4): the
`## Adversarial review` section of verdict.md must be filled when the change class demands the
adversarial pass (M/L depth or the first change of a capability) — a structural hold on the
pass having run, since criteria_guard cannot tell a human evaluator from a self-certifying one.

Stdlib-only. gate.py and criteria_lint.py are imported from this directory — the criteria
grammar and the junit-backing checker have exactly one home (C7).
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True

TOOLS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = TOOLS_DIR.parent / "templates"
GATE_DIR_NAME = ".gate"

# The change dir's verdict.md is the evaluator's artifact, not a change to code/spec
# behaviour: adding or refreshing it must NOT re-trigger the L-04 recompute demand.
VERDICT_BASENAME = "verdict.md"

PASS, FAIL, FLAG, SKIP = "PASS", "FAIL", "FLAG", "SKIP"


@dataclass
class Result:
    id: str
    status: str  # PASS | FAIL | FLAG | SKIP
    detail: str


class AcceptError(Exception):
    """A precondition could not even be evaluated; carries the loud detail."""


_MODULES: dict[str, object] = {}


def _tools() -> tuple[object, object]:
    """Import gate.py + criteria_lint.py from this directory (one home for the grammar)."""
    if not _MODULES:
        sys.path.insert(0, str(TOOLS_DIR))
        import criteria_lint  # noqa: PLC0415 — stdlib-sibling import, path just set
        import gate  # noqa: PLC0415

        _MODULES["gate"] = gate
        _MODULES["criteria_lint"] = criteria_lint
    return _MODULES["gate"], _MODULES["criteria_lint"]


# ---------------------------------------------------------------------------------------
# git + text helpers
# ---------------------------------------------------------------------------------------


def _git(tree: Path, *args: str, check: bool = False) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AcceptError(f"git {' '.join(args)} failed: {(proc.stdout + proc.stderr).strip()}")
    return proc.returncode, proc.stdout


def _section(text: str, heading: str) -> str:
    """Return the body of a `## <heading>` section up to the next `## ` heading."""
    lines = text.splitlines()
    out: list[str] = []
    collecting = False
    for line in lines:
        if line.strip().lower().startswith("## "):
            if collecting:
                break
            collecting = line.strip()[3:].strip().lower() == heading.lower()
            continue
        if collecting:
            out.append(line)
    return "\n".join(out)


def _significant_tokens(text: str) -> set[str]:
    """Content-bearing tokens for token-set matching (numbers kept even when short)."""
    toks = set()
    # strip html comments so a placeholder comment never counts as content
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    for raw in re.findall(r"[A-Za-z0-9_]+", text.lower()):
        if raw.isdigit() or len(raw) >= 3:
            toks.add(raw)
    return toks


# ---------------------------------------------------------------------------------------
# junit correlation: ac-id -> test node-id (for invariant provenance)
# ---------------------------------------------------------------------------------------


def junit_ac_test_ids(gate_dir: Path) -> dict[str, str]:
    """Map each ac-id to a PASSED test node-id, correlating the ac-marked junit testcases
    with the collected node-ids in the gate's inventory. The provenance mark an invariant
    carries (verified by: <node-id>) must be a real node-id gate.py's L-06 check can grep."""
    import json  # noqa: PLC0415

    junit = gate_dir / "last-run.xml"
    inventory = gate_dir / "inventory.json"
    if not junit.exists():
        return {}
    ac_to_name: dict[str, str] = {}
    root = ET.parse(junit).getroot()
    for tc in root.iter("testcase"):
        if any(tc.find(t) is not None for t in ("failure", "error", "skipped")):
            continue
        name = tc.get("name")
        for prop in tc.iter("property"):
            if prop.get("name") == "ac" and prop.get("value") and name:
                ac_to_name.setdefault(str(prop.get("value")), name)
    outcomes: dict[str, str] = {}
    if inventory.exists():
        data = json.loads(inventory.read_text(encoding="utf-8"))
        outcomes = dict(data.get("outcomes", {}))
    result: dict[str, str] = {}
    for ac_id, name in ac_to_name.items():
        for node_id, outcome in outcomes.items():
            if outcome == "passed" and node_id.rsplit("::", 1)[-1] == name:
                result[ac_id] = node_id
                break
    return result


# ---------------------------------------------------------------------------------------
# invariant merge (criteria -> capability-file invariants with provenance)
# ---------------------------------------------------------------------------------------


def build_invariant_lines(criteria: list, ac_ids: dict[str, str]) -> list[tuple[str, str]]:
    """(ac_id, invariant line) per proven criterion — keyed so a placement map can distribute
    each invariant to its human-approved capability file (§5.4)."""
    out: list[tuple[str, str]] = []
    for crit in criteria:
        if crit.state == "x":
            out.append((crit.ac_id, f"- {crit.text} (verified by: {ac_ids.get(crit.ac_id, '?')})"))
        elif crit.state == "m":
            out.append((crit.ac_id, f"- {crit.text} (MANUAL)"))
    return out


def build_invariants(criteria: list, ac_ids: dict[str, str]) -> list[str]:
    """One invariant line per proven criterion, carrying its provenance mark (§5.4)."""
    return [line for _, line in build_invariant_lines(criteria, ac_ids)]


def instantiate_capability(ctx: str, capability: str) -> str:
    """A NEW capability file is born from the template — /spec never creates capability
    files, this script is the template's sole consumer (T03 finding 6)."""
    template = (TEMPLATES_DIR / "capability.md").read_text(encoding="utf-8")
    name = capability[:-3] if capability.endswith(".md") else capability
    return template.replace("<context>", ctx, 1).replace("<capability>", name, 1)


def append_invariants(text: str, invariants: list[str]) -> str:
    if not invariants:
        return text
    if "## Invariants" not in text:
        text = text.rstrip() + "\n\n## Invariants\n"
    return text.rstrip() + "\n" + "\n".join(invariants) + "\n"


def _overview_capabilities(tree: Path, ctx: str) -> list[str]:
    """The `*.md` capability files named in overview.md's `## Capabilities` list — the context
    map the /spec session authors, so it carries the human's chosen capability name."""
    overview = tree / "specs" / ctx / "overview.md"
    if not overview.exists():
        return []
    body = _section(overview.read_text(encoding="utf-8"), "Capabilities")
    files: list[str] = []
    for tok in re.findall(r"`?([A-Za-z0-9_.\-]+\.md)`?", body):
        if tok != "overview.md" and tok not in files:
            files.append(tok)
    return files


def resolve_targets(tree: Path, ctx: str, change_md: str, birth_slug: str | None = None) -> list[str]:
    """Capability files the invariants merge into: the Affects line, else the single existing
    capability of the context, else — for the FIRST change of a context, whose acceptance BIRTHS
    the capability file — the capability the /spec author DECLARED in overview.md's Capabilities
    list (its name is the human's, not a slug artifact), and only if overview.md names none, the
    name derived from the change slug (the `NNN-` prefix stripped). A capability-birthing change
    carries no capability file to fall back to, so without this a first change with no Affects
    line has no determinable target: the change.md template marks Affects optional ("accept.py
    derives it itself"), which only holds once a capability exists. An explicit Affects always
    wins — the derivation is the no-Affects fallback only."""
    m = re.search(r"(?m)^Affects:\s*(.+?)\s*$", change_md)
    files: list[str] = []
    if m:
        line = re.sub(r"<!--.*?-->", "", m.group(1))
        for tok in re.split(r"[,\s]+", line.strip()):
            tok = tok.strip().strip("`")
            if tok.endswith(".md"):
                files.append(tok)
    if not files:
        caps = [p.name for p in sorted((tree / "specs" / ctx).glob("*.md")) if p.name != "overview.md"]
        if len(caps) == 1:
            files = caps
        elif not caps:
            declared = _overview_capabilities(tree, ctx)
            if len(declared) == 1:
                files = declared
            elif not declared and birth_slug:
                derived = re.sub(r"^\d+-", "", birth_slug).strip()
                if derived:
                    files = [f"{derived}.md"]
    return files


@dataclass
class MergePlan:
    infos: list[dict]  # {rel, new, is_new}
    diff_text: str
    invariants: list[str]  # flat, for the merge-fidelity gate (placement-independent)
    error: str  # a target-resolution failure that short-circuits the merge (plan unusable)
    targets: list[str] = field(default_factory=list)
    needs_placement: bool = False  # multi-target with no valid map: distribution not yet decided
    placement_error: str = ""  # a map WAS supplied but is invalid (names a non-Affects file, etc.)


def compute_merge(
    tree: Path,
    ctx: str,
    change_md: str,
    criteria: list,
    ac_ids: dict[str, str],
    placement: dict[str, str] | None = None,
    birth_slug: str | None = None,
) -> MergePlan:
    """Prepare the criteria->invariants merge.

    Single-target: deterministic — every invariant lands in the one capability file.
    Multi-target (`Affects` names >1 file): invariant distribution is a semantic act owned by
    `/accept-change` (spec §5.4). accept.py never dumps all invariants into the first file — it
    consumes an approved placement map {ac-id -> capability file}; with no map it flags that the
    map is needed (`needs_placement`), with an invalid map it refuses (`placement_error`).
    `birth_slug` (the change dir name) lets a capability-birthing first change derive its target
    when it carries no Affects line — see resolve_targets."""
    targets = resolve_targets(tree, ctx, change_md, birth_slug)
    if not targets:
        return MergePlan(
            [],
            "",
            [],
            "cannot determine target capability file — add an 'Affects: <capability>.md' line to change.md",
        )
    inv_pairs = build_invariant_lines(criteria, ac_ids)
    invariants = [line for _, line in inv_pairs]

    # decide per-target distribution of the invariant lines.
    if len(targets) == 1:
        dist: dict[str, list[str]] = {targets[0]: invariants}
    elif not placement:
        return MergePlan([], "", invariants, "", targets=targets, needs_placement=True)
    else:
        bad = sorted({f for f in placement.values() if f not in targets})
        if bad:
            return MergePlan(
                [],
                "",
                invariants,
                "",
                targets=targets,
                placement_error=(
                    f"placement map names capability file(s) not in Affects: {', '.join(bad)} "
                    f"(Affects: {', '.join(targets)}) — a re-cut across separate files is a /spec right, not this map"
                ),
            )
        unmapped = [ac for ac, _ in inv_pairs if ac not in placement]
        if unmapped:
            return MergePlan(
                [],
                "",
                invariants,
                "",
                targets=targets,
                placement_error=(
                    f"placement map has no entry for proven criteria: {', '.join(unmapped)} — "
                    "every invariant needs an approved target file"
                ),
            )
        dist = {t: [] for t in targets}
        for ac, line in inv_pairs:
            dist[placement[ac]].append(line)

    infos: list[dict] = []
    diff_chunks: list[str] = []
    for name in targets:
        path = tree / "specs" / ctx / name
        is_new = not path.exists()
        old = "" if is_new else path.read_text(encoding="utf-8")
        base_text = instantiate_capability(ctx, name) if is_new else old
        target_invs = dist.get(name, [])
        new = append_invariants(base_text, target_invs) if target_invs else base_text
        if new != old:
            label = f"specs/{ctx}/{name}"
            diff = difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=("(new) " + label) if is_new else label,
                tofile=label,
            )
            diff_chunks.append("".join(diff))
            infos.append({"rel": label, "new": new, "is_new": is_new})
    return MergePlan(infos, "\n".join(diff_chunks), invariants, "", targets=targets)


# ---------------------------------------------------------------------------------------
# pure gate helpers (unit-tested directly)
# ---------------------------------------------------------------------------------------


def merge_fidelity_violations(ac_texts: list[tuple[str, str]], merged_text: str) -> list[str]:
    """Every acceptance criterion of the delta must be findable in the prepared merge (L-11).

    Token-set matching (the §5.4 grep-class, deliberately weakened from substring per the
    task's Escalate-if: robust to backtick/punctuation drift between change.md and the merged
    invariant, still catches a criterion that produced no invariant at all)."""
    merged = _significant_tokens(merged_text)
    out: list[str] = []
    for ac_id, text in ac_texts:
        missing = _significant_tokens(text) - merged
        if missing:
            out.append(f"{ac_id}: not found in the prepared merge (missing tokens: {sorted(missing)})")
    return out


def parse_verdict_sha(verdict_text: str) -> str | None:
    """The gate SHA the evaluator pinned in verdict.md (L-04).

    Tolerant to markdown around the hex: the template renders a bare `SHA: <hex>`, but an
    evaluator that wraps it in backticks or emphasis (`` SHA: `246f84…` ``) must not be
    silently denied over cosmetics (T10c). Match the first 7–40 hex run after the `SHA:`
    token, skipping any backticks / emphasis punctuation between them. Freshness still
    requires the hex to resolve to a real commit downstream — this widens the parse, not the
    semantics; a verdict with no hex anywhere still yields None (and FAILs freshness)."""
    m = re.search(r"SHA:[\s`*_]*([0-9a-fA-F]{7,40})", verdict_text)
    return m.group(1) if m else None


def freshness_state(
    verdict_sha: str | None, head: str, changed_since: set[str], change_files: set[str]
) -> tuple[str, str]:
    """(status, detail) for the verdict-freshness gate when the pin is still IN HISTORY (L-04).

    Used when the pinned SHA is HEAD or an ancestor of HEAD (the no-rebase path). A rebase that
    orphans the pin is handled by rebase_freshness_state — see prechecks."""
    if verdict_sha is None:
        return FAIL, "verdict.md carries no 'SHA: <sha>' line — the evaluator must pin the gate SHA"
    if verdict_sha == head:
        return PASS, f"verdict SHA == branch HEAD ({head[:12]})"
    intersect = sorted(changed_since & change_files)
    if intersect:
        return FAIL, (
            f"verdict SHA {verdict_sha[:12]} is behind HEAD {head[:12]} and the diff intersects the "
            f"change's files — recompute the evaluator (L-04): {', '.join(intersect)}"
        )
    if not changed_since:
        return PASS, (
            f"verdict SHA {verdict_sha[:12]} is behind HEAD {head[:12]} but only the verdict metadata "
            "moved since — still fresh (L-04)"
        )
    return FLAG, (
        f"verdict SHA {verdict_sha[:12]} is behind HEAD {head[:12]} but the diff does not intersect the "
        "change's files — verdict still fresh (L-04)"
    )


def rebase_freshness_state(
    verdict_sha: str, head: str, resolvable: bool, changed_since: set[str], change_files: set[str]
) -> tuple[str, str]:
    """(status, detail) for the verdict-freshness gate when the pin is NO LONGER REACHABLE from
    HEAD — a rebase rewrote every SHA on the branch (L-04, T10d).

    The pin is a proxy for a question the spec §5.4 actually asks: does the verdict still attest to
    THIS code + criteria? A rebase (e.g. onto a canon fix landed on main mid-flight) rewrites the
    commit identity of the whole branch, orphaning the pinned SHA, WITHOUT changing what the verdict
    attests to. Anchoring freshness to commit identity then demands a needless evaluator re-pin on
    every rebase (the platform/001 re-pin cascade). Anchor it instead to TREE identity of the
    attested state: the verdict stays fresh iff none of the change's own files differ between the
    (orphaned) pinned commit and HEAD. Base / .claude drift the rebase pulled in is expected and
    irrelevant — it is not part of the change's attested behaviour. A change file that ACTUALLY
    differs still fails: tree-identity is the safe relaxation, commit-identity the accidental
    strictness. If the pinned commit is unresolvable (its object was pruned), the attested tree is
    unknowable — FAIL rather than pass silently (the pre-T10d silent-empty-diff hazard)."""
    if not resolvable:
        return FAIL, (
            f"verdict SHA {verdict_sha[:12]} is not reachable from HEAD {head[:12]} and its commit object "
            "is gone (pruned) — the attested tree cannot be verified; re-run the evaluator and re-pin (L-04)"
        )
    intersect = sorted(changed_since & change_files)
    if intersect:
        return FAIL, (
            f"verdict SHA {verdict_sha[:12]} was rebased away AND the change's attested files differ from "
            f"it — the verdict no longer attests to this code+criteria (L-04): {', '.join(intersect)}"
        )
    return PASS, (
        f"verdict SHA {verdict_sha[:12]} was rebased away but the change's attested tree is byte-identical "
        f"at HEAD {head[:12]} — verdict still fresh (tree-identity survives the rebase, L-04)"
    )


@dataclass(frozen=True)
class RemovalFlavour:
    """Structural classification of a change as removal-flavour, plus the symbols to sweep.

    `by_class`  — the `Class:` line declares the removal flavour (spec §3.1's `REMOVED`).
    `sections`  — the body under every real `#+ Removed…` heading (the ONLY place terms
                  are harvested from).
    `terms`     — node-ids / backticked symbol names found in those sections.
    """

    by_class: bool
    sections: tuple[str, ...]
    terms: tuple[str, ...]

    @property
    def fires(self) -> bool:
        return self.by_class or bool(self.sections)


# The removal flavour is declared structurally, never grepped out of prose (T10e): either the
# `Class:` line carries it (spec §3.1: "Removal-вкус (`REMOVED`)") or the change.md has a REAL
# heading — `#+`, one-or-more, so a wrapped sketch line starting with "removed …" cannot pass
# for one. The pre-T10e classifier used `#*` (zero-or-more) and matched exactly that.
_REMOVAL_ON_CLASS_LINE = re.compile(r"(?im)^Class:[^\n]*\bremov(?:al|als|ed|es|ing)\b")
_REMOVED_HEADING = re.compile(r"(?m)^#+[ \t]*Removed\b[^\n]*$")
_ANY_HEADING = re.compile(r"(?m)^#+[ \t]")


def classify_removal(change_md: str) -> RemovalFlavour:
    """Classify a change's removal flavour from STRUCTURE and harvest the removed symbols
    from the matched heading's own section only.

    Two defects this replaces (both blocked `users/002`, a change that removes nothing):
    a classifier that fired on any line beginning with "removed", and a term capture anchored
    on the FIRST "removed" anywhere in the file — which harvested half the Interface sketch
    (`id`, `save`, `None`, …) and would drown a genuine removal's real signal too.
    """
    text = re.sub(r"<!--.*?-->", "", change_md, flags=re.DOTALL)  # the template's own comment says "removal flavour"
    by_class = bool(_REMOVAL_ON_CLASS_LINE.search(text))
    sections: list[str] = []
    for match in _REMOVED_HEADING.finditer(text):
        rest = text[match.end() :]
        nxt = _ANY_HEADING.search(rest)
        sections.append(rest[: nxt.start()] if nxt else rest)
    terms: list[str] = []
    for body in sections:
        terms += re.findall(r"::(\w+)", body)
        terms += re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", body)
    return RemovalFlavour(by_class=by_class, sections=tuple(sections), terms=tuple(terms))


def orphan_violations(removed_terms: list[str], spec_text: str, src_text: str) -> list[str]:
    """A removal-flavour change's removed behaviour must survive nowhere (V-02)."""
    out: list[str] = []
    for term in removed_terms:
        where = []
        if term in spec_text:
            where.append("spec text")
        if re.search(rf"\b{re.escape(term)}\b", src_text):
            where.append("src symbols")
        if where:
            out.append(f"removed behaviour '{term}' still present in {', '.join(where)}")
    return out


# ---------------------------------------------------------------------------------------
# adversarial-pass presence (spec §6 step 4 — the evaluator↔accept seam T09 opened, T10)
# ---------------------------------------------------------------------------------------


def _has_real_content(section_body: str) -> bool:
    """True when a section carries content beyond template HTML comments / whitespace."""
    return bool(re.sub(r"<!--.*?-->", "", section_body, flags=re.DOTALL).strip())


def adversarial_required(change_md: str, creates_new_capability: bool) -> tuple[bool, str]:
    """Spec §6 step 4: the adversarial pass (recorded as a verdict.md section) is mandatory
    for M/L-depth changes and for the first change of a capability. Depth is read structurally
    — an M/L change carries a filled Context or Interface sketch section, an S change does not
    (the change.md template marks both sections "M/L only"); the first change of a capability is
    the one whose acceptance BIRTHS the capability file (S6), i.e. no file exists for it yet."""
    if creates_new_capability:
        return True, "first change of a capability (its file is born at this acceptance)"
    if _has_real_content(_section(change_md, "Interface sketch")):
        return True, "M/L depth (Interface sketch present)"
    if _has_real_content(_section(change_md, "Context")):
        return True, "M/L depth (Context present)"
    return False, "S depth on an existing capability — the adversarial pass is opt-in"


def _adversarial_body(verdict_text: str) -> str:
    """The adversarial-pass section body, under either canonical heading.

    The template + accept prefer `## Adversarial review`; `/implement` §4 historically said
    "adversarial pass", which misled evaluators into `## Adversarial pass`. Accept either
    heading (case-insensitive, via `_section`) so an author-side wording slip is not a silent
    deny (T10c)."""
    for heading in ("Adversarial review", "Adversarial pass"):
        body = _section(verdict_text, heading)
        if body.strip():
            return body
    return ""


def adversarial_section_filled(verdict_text: str | None) -> bool:
    """True when verdict.md's adversarial section carries a real run — not empty, not the
    template comment, and not a bare N/A marker (which only legitimises the not-required case).
    criteria_guard cannot tell a human evaluator from an agent, so this presence check is the
    only structural hold on the pass having actually run for a change class that demands it.
    Reads either `## Adversarial review` or `## Adversarial pass` (T10c)."""
    if verdict_text is None:
        return False
    stripped = re.sub(r"<!--.*?-->", "", _adversarial_body(verdict_text), flags=re.DOTALL).strip()
    if not stripped:
        return False
    return re.match(r"(?i)n/?a\b", stripped) is None


# ---------------------------------------------------------------------------------------
# context + gate run
# ---------------------------------------------------------------------------------------


@dataclass
class AcceptContext:
    tree: Path
    change_id: str
    ctx: str
    nnn: str
    change_dir: Path
    base: str
    branch: str
    head: str
    change_md: str
    criteria_text: str
    verdict_text: str | None


def resolve(tree: Path, change_id: str, base: str) -> AcceptContext:
    m = re.fullmatch(r"([A-Za-z0-9_-]+)/(\d+)", change_id)
    if not m:
        raise AcceptError(f"change id must look like <context>/NNN, got {change_id!r}")
    ctx, nnn = m.group(1), m.group(2)
    dirs = [d for d in sorted((tree / "specs" / ctx / "changes").glob(f"{nnn}-*")) if d.is_dir()]
    if not dirs:
        raise AcceptError(f"change directory specs/{ctx}/changes/{nnn}-* not found")
    change_dir = dirs[0]
    change_md_path = change_dir / "change.md"
    criteria_path = change_dir / "criteria.md"
    if not change_md_path.exists() or not criteria_path.exists():
        raise AcceptError(f"{change_dir} is missing change.md and/or criteria.md")
    verdict_path = change_dir / VERDICT_BASENAME
    _, head = _git(tree, "rev-parse", "HEAD", check=True)
    _, branch = _git(tree, "rev-parse", "--abbrev-ref", "HEAD", check=True)
    return AcceptContext(
        tree=tree,
        change_id=f"{ctx}/{nnn}",
        ctx=ctx,
        nnn=nnn,
        change_dir=change_dir,
        base=base,
        branch=branch.strip(),
        head=head.strip(),
        change_md=change_md_path.read_text(encoding="utf-8"),
        criteria_text=criteria_path.read_text(encoding="utf-8"),
        verdict_text=verdict_path.read_text(encoding="utf-8") if verdict_path.exists() else None,
    )


def run_gate(actx: AcceptContext) -> dict:
    """Run gate.py --criteria in-process at HEAD; return its verdict.json (the fresh
    GREEN/RED authority + junit backing this run leans on — one implementation, imported)."""
    import json  # noqa: PLC0415

    gate, _ = _tools()
    gate.run_gate(actx.tree, criteria=True, baseline_arg=None, change_arg=actx.change_id)
    verdict_path = actx.tree / GATE_DIR_NAME / "verdict.json"
    return json.loads(verdict_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------
# the gates
# ---------------------------------------------------------------------------------------


def prechecks(actx: AcceptContext) -> list[Result]:
    """Cheap structural gates that need no gate.py run — a FAIL here short-circuits the
    expensive gate run (there is no point gating an already-denied change)."""
    _, criteria_lint = _tools()
    results: list[Result] = []

    # gate 2: ESCALATE file (hook-written at the iteration ceiling; human removes it — E-08).
    escalate = actx.change_dir / "ESCALATE"
    if escalate.exists():
        results.append(
            Result(
                "escalate",
                FAIL,
                f"{escalate.relative_to(actx.tree)} present — the human must resolve and remove it (E-08)",
            )
        )
    else:
        results.append(Result("escalate", PASS, "no ESCALATE file"))

    # gate 1a: no open [ ] criteria.
    lines = criteria_lint._strip_html_comments(actx.criteria_text.splitlines())
    criteria = criteria_lint.iter_criteria(lines)
    open_ids = [c.ac_id for c in criteria if c.state == " "]
    if not criteria:
        results.append(Result("criteria.complete", FAIL, "criteria.md has no acceptance criteria"))
    elif open_ids:
        results.append(Result("criteria.complete", FAIL, f"open [ ] criteria remain: {', '.join(open_ids)}"))
    else:
        results.append(Result("criteria.complete", PASS, f"all {len(criteria)} criteria are [x] or [m]"))

    # gate 1c: verdict present + fresh SHA (L-04).
    if actx.verdict_text is None:
        results.append(Result("verdict.freshness", FAIL, "verdict.md not found — run /implement's evaluator first"))
    else:
        verdict_sha = parse_verdict_sha(actx.verdict_text)
        verdict_rel = str((actx.change_dir / VERDICT_BASENAME).relative_to(actx.tree))
        # the verdict.md commit itself is metadata, never a reason to recompute the verdict
        _, out = _git(actx.tree, "diff", "--name-only", f"{actx.base}...{actx.head}")
        change_files = {line for line in out.splitlines() if line.strip() and line != verdict_rel}
        if verdict_sha is None or verdict_sha == actx.head:
            status, detail = freshness_state(verdict_sha, actx.head, set(), change_files)
        else:
            # Is the pin still IN HISTORY (an ancestor of HEAD), or did a rebase orphan it?
            reachable = _git(actx.tree, "merge-base", "--is-ancestor", verdict_sha, actx.head)[0] == 0
            resolvable = _git(actx.tree, "rev-parse", "--verify", f"{verdict_sha}^{{commit}}")[0] == 0
            changed_since: set[str] = set()
            if resolvable:
                # git diff works against a dangling (rebased-away) commit as long as its object
                # survives, so the tree comparison holds across a rebase (T10d).
                _, out = _git(actx.tree, "diff", "--name-only", f"{verdict_sha}", actx.head)
                changed_since = {line for line in out.splitlines() if line.strip() and line != verdict_rel}
            if reachable:
                status, detail = freshness_state(verdict_sha, actx.head, changed_since, change_files)
            else:
                status, detail = rebase_freshness_state(verdict_sha, actx.head, resolvable, changed_since, change_files)
        results.append(Result("verdict.freshness", status, detail))

    # gate 2: Companion accepted (tag exists AND the companion dir is gone).
    comp_m = re.search(r"(?m)^Companion:\s*([A-Za-z0-9_-]+/\d+)", actx.change_md)
    if not comp_m:
        results.append(Result("companion", PASS, "no companion declared"))
    else:
        comp = comp_m.group(1)
        tag = "change/" + comp.replace("/", "-")
        rc, _ = _git(actx.tree, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        c_ctx, c_nnn = comp.split("/")
        comp_dir = [d for d in (actx.tree / "specs" / c_ctx / "changes").glob(f"{c_nnn}-*") if d.is_dir()]
        if rc == 0 and not comp_dir:
            results.append(Result("companion", PASS, f"companion {comp} already accepted (tag {tag})"))
        else:
            results.append(
                Result(
                    "companion",
                    FAIL,
                    f"companion {comp} not yet accepted — accept both together (T10); tag {tag} missing or its change dir still present",
                )
            )

    # gate (spec §6 step 4): the adversarial-pass section is present when the change class
    # demands it (M/L or first-change-of-a-capability). This is the accept side of the
    # evaluator↔accept seam T09 opened — /implement writes the section, accept checks it.
    targets = resolve_targets(actx.tree, actx.ctx, actx.change_md)
    creates_new = any(not (actx.tree / "specs" / actx.ctx / name).exists() for name in targets) if targets else False
    required, why = adversarial_required(actx.change_md, creates_new)
    if not required:
        results.append(Result("adversarial.presence", PASS, f"adversarial pass not required — {why}"))
    elif adversarial_section_filled(actx.verdict_text):
        results.append(Result("adversarial.presence", PASS, f"adversarial review section present, as required ({why})"))
    else:
        results.append(
            Result(
                "adversarial.presence",
                FAIL,
                f"adversarial pass required ({why}) but verdict.md's '## Adversarial review' section is "
                "empty/absent — run the adversarial pass and record it (spec §6 step 4)",
            )
        )

    return results


def gate_dependent_checks(
    actx: AcceptContext, verdict: dict, placement: dict[str, str] | None = None
) -> tuple[list[Result], MergePlan | None]:
    _, criteria_lint = _tools()
    results: list[Result] = []
    check_by_id = {c["id"]: c for c in verdict.get("checks", [])}

    # gate 2: gate.py GREEN on the branch.
    if verdict.get("result") == "GREEN":
        results.append(Result("gate.green", PASS, f"gate.py GREEN at {verdict.get('sha', '')[:12]}"))
    else:
        failed = ", ".join(verdict.get("failed", [])) or "?"
        results.append(Result("gate.green", FAIL, f"gate.py RED on the branch — failing: {failed}"))

    # gate 2: Docker-exempt integration tests surfaced EXPLICITLY (T04b).
    exempt = verdict.get("docker_exempt") or []
    docker_detail = next((c["detail"] for c in verdict.get("checks", []) if c["id"] == "docker.alembic"), "")
    if exempt:
        results.append(
            Result(
                "docker.tier",
                FLAG,
                f"accepting with a SKIPPED Docker tier — {len(exempt)} integration test(s) not run: {', '.join(exempt)} (conscious human decision, T04b)",
            )
        )
    elif "DOCKER SKIPPED" in docker_detail:
        results.append(
            Result(
                "docker.tier",
                FLAG,
                f"Docker tier SKIPPED ({docker_detail}) — accepting without the migration tier is a conscious human decision (T04b)",
            )
        )
    else:
        results.append(Result("docker.tier", PASS, docker_detail or "Docker tier ran"))

    # gate 1b: junit-backing + [m] verdict entries — reuse gate.py's own checkers.
    for check_id, label in (
        ("criteria.junit-backing", "criteria.junit-backing"),
        ("criteria.manual-verdict", "criteria.manual-verdict"),
    ):
        c = check_by_id.get(check_id)
        if c is None:
            results.append(Result(label, FAIL, "gate.py did not report this criteria check (run with --criteria)"))
        elif c["status"] == "PASS":
            results.append(Result(label, PASS, c["detail"].splitlines()[0]))
        else:
            results.append(Result(label, FAIL, c["detail"].splitlines()[0]))

    # prepare the merge (needs junit-derived provenance).
    lines = criteria_lint._strip_html_comments(actx.criteria_text.splitlines())
    criteria = criteria_lint.iter_criteria(lines)
    ac_ids = junit_ac_test_ids(actx.tree / GATE_DIR_NAME)
    plan = compute_merge(actx.tree, actx.ctx, actx.change_md, criteria, ac_ids, placement, actx.change_dir.name)
    if plan.error:
        results.append(Result("merge.fidelity", FAIL, plan.error))
        return results, None

    # gate 3: Affects-intersection vs in-flight changes → flag list (L-03).
    _, my_affects = _affects_set(actx.tree, actx.ctx, actx.change_md)
    intersections: list[str] = []
    for other in sorted((actx.tree / "specs").glob("*/changes/*")):
        if not other.is_dir() or other == actx.change_dir:
            continue
        other_md = other / "change.md"
        if not other_md.exists():
            continue
        o_ctx = other.parent.parent.name
        _, o_aff = _affects_set(actx.tree, o_ctx, other_md.read_text(encoding="utf-8"))
        shared = my_affects & o_aff
        if shared:
            rel = str(other.relative_to(actx.tree))
            intersections.append(f"{rel} shares {', '.join(sorted(shared))}")
    if intersections:
        results.append(
            Result(
                "affects.intersection",
                FLAG,
                "in-flight changes touch the same capability files — re-review their criteria (L-03): "
                + "; ".join(intersections),
            )
        )
    else:
        results.append(Result("affects.intersection", PASS, "no in-flight change intersects this change's Affects"))

    # gate 4: merge-fidelity.
    ac_texts = _change_ac_texts(actx.change_md)
    if not ac_texts:
        # fall back to criteria.md texts so the gate still asserts every criterion landed
        ac_texts = [(c.ac_id, c.text) for c in criteria]
    violations = merge_fidelity_violations(ac_texts, "\n".join(plan.invariants))
    if violations:
        results.append(
            Result(
                "merge.fidelity",
                FAIL,
                "acceptance criteria absent from the prepared merge (L-11):\n" + "\n".join(violations),
            )
        )
    else:
        results.append(
            Result(
                "merge.fidelity", PASS, f"all {len(ac_texts)} acceptance criteria are present in the merge diff (L-11)"
            )
        )
    if plan.placement_error:
        results.append(Result("merge.placement", FAIL, plan.placement_error))
    elif plan.needs_placement:
        results.append(
            Result(
                "merge.placement",
                FLAG,
                "multi-target Affects ("
                + ", ".join(plan.targets)
                + ") — invariant placement is a semantic act (spec §5.4): /accept-change must propose a "
                'map and pass it to --execute (--placement \'{"AC-1": "<file>.md", ...}\'). accept.py '
                "will not dump every invariant into the first file",
            )
        )
    elif len(plan.targets) > 1:
        results.append(
            Result(
                "merge.placement",
                PASS,
                "invariants distributed across " + ", ".join(plan.targets) + " per the approved placement map",
            )
        )

    # gate 5: spec-lint (surfaced for the human's review diff — L-07/O-13).
    results.append(_spec_lint(actx))

    # gate 6: orphan sweep for removal-flavour changes (V-02).
    results.append(_orphan_sweep(actx))

    return results, plan


def _affects_set(tree: Path, ctx: str, change_md: str) -> tuple[str, set[str]]:
    targets = resolve_targets(tree, ctx, change_md)
    return ctx, {f"specs/{ctx}/{t}" for t in targets}


def _change_ac_texts(change_md: str) -> list[tuple[str, str]]:
    section = _section(change_md, "Acceptance criteria")
    return [(m.group(1), m.group(2).strip()) for m in re.finditer(r"(?m)^-\s*(AC-\d+):\s*(.+?)\s*$", section)]


def _spec_lint(actx: AcceptContext) -> Result:
    ctx_dir = actx.tree / "specs" / actx.ctx
    findings: list[str] = []
    overview = ctx_dir / "overview.md"
    overview_text = overview.read_text(encoding="utf-8") if overview.exists() else ""
    cap_files = [p for p in sorted(ctx_dir.glob("*.md")) if p.name != "overview.md"]
    seen: set[str] = set()
    for path in ctx_dir.rglob("*.md"):
        if "changes" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if len(text.splitlines()) > 300:
            findings.append(f"{path.relative_to(actx.tree)} exceeds 300 lines — cut it (S7)")
        for ref in re.findall(r"`([A-Za-z0-9_./-]+\.md)`", text):
            base = ref.split("/")[-1]
            if not (ctx_dir / base).exists() and not (actx.tree / ref).exists():
                findings.append(f"{path.relative_to(actx.tree)} references missing spec file `{ref}`")
    for cap in cap_files:
        if cap.name in seen:
            findings.append(f"duplicate capability file listing: {cap.name}")
        seen.add(cap.name)
        if overview_text and cap.name not in overview_text:
            findings.append(f"capability {cap.name} is missing from overview.md's map")
    if findings:
        return Result("spec.lint", FLAG, "spec-lint findings for the review diff (L-07/O-13):\n" + "\n".join(findings))
    return Result(
        "spec.lint", PASS, "spec-lint clean (no dangling refs, duplicates, oversize or unlisted capabilities)"
    )


def _orphan_sweep(actx: AcceptContext) -> Result:
    flavour = classify_removal(actx.change_md)
    if not flavour.fires:
        return Result(
            "orphan.sweep",
            SKIP,
            "not a removal-flavour change (no removal flavour on the `Class:` line, no `Removed` heading)",
        )
    if not flavour.sections:
        # FLAG, not SKIP: the change DECLARES a removal, so V-02 is owed — but there is no
        # structural list to sweep (the sweep never harvests free prose), and no command emits
        # a `## Removed` heading yet, so blocking here would deadlock every removal change.
        # Surfaced-but-non-blocking keeps the absent sweep visible in the human's review output
        # instead of silently not running (S4: a gate that can quietly not-run does not exist).
        return Result(
            "orphan.sweep",
            FLAG,
            "the `Class:` line declares the removal flavour but change.md carries no `## Removed` heading — "
            "V-02 did NOT run: there is no structural list of removed behaviour to sweep (the sweep never "
            "harvests free prose). Add a `## Removed` section listing the removed symbols/node-ids, or "
            "confirm in review that nothing is orphaned",
        )
    terms = list(flavour.terms)
    if not terms:
        return Result("orphan.sweep", PASS, "removal-flavour change lists no concrete removed symbols to sweep")
    spec_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (actx.tree / "specs" / actx.ctx).glob("*.md") if p.name != "overview.md"
    )
    src_text = ""
    src = actx.tree / "src"
    if src.is_dir():
        src_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in src.rglob("*.py"))
    violations = orphan_violations(sorted(set(terms)), spec_text, src_text)
    if violations:
        return Result("orphan.sweep", FAIL, "removed behaviour still present (V-02):\n" + "\n".join(violations))
    return Result("orphan.sweep", PASS, f"orphan sweep clean for {len(set(terms))} removed symbol(s)")


# ---------------------------------------------------------------------------------------
# post-approval actions (--execute) + drift check
# ---------------------------------------------------------------------------------------


def execute(actx: AcceptContext, plan: MergePlan) -> str:
    rc, status = _git(actx.tree, "status", "--porcelain")
    if status.strip():
        raise AcceptError("work tree is not clean — commit or stash before --execute")
    # 1. apply invariants on the branch, delete the change dir, commit.
    for info in plan.infos:
        path = actx.tree / info["rel"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(info["new"], encoding="utf-8")
    shutil.rmtree(actx.change_dir)
    _git(actx.tree, "add", "-A", check=True)
    _git(
        actx.tree,
        "commit",
        "-q",
        "-m",
        f"accept {actx.change_id}: merge criteria into capability invariants; remove change dir",
        check=True,
    )
    # 2. merge the branch into the S9 base.
    _git(actx.tree, "checkout", actx.base, check=True)
    _git(actx.tree, "merge", "--no-ff", actx.branch, "-m", f"Merge {actx.branch} (accept {actx.change_id})", check=True)
    # 3. tag.
    tag = "change/" + actx.change_id.replace("/", "-")
    _git(actx.tree, "tag", tag, check=True)
    # 4. drift check on the base.
    return drift_report(actx.tree, actx.base)


def drift_report(tree: Path, base: str) -> str:
    out = [f"drift-check on {base} (spec §5.5):"]
    _, tags = _git(tree, "tag", "--list", "change/*")
    tag_list = [t for t in tags.split() if t]
    _, log = _git(tree, "log", base, "--format=%H", "--", "src")
    commits = [c for c in log.split() if c]
    unlinked = []
    for c in commits:
        if not any(_git(tree, "merge-base", "--is-ancestor", c, t)[0] == 0 for t in tag_list):
            unlinked.append(c)
    if unlinked:
        out.append(
            f"  {len(unlinked)} src commit(s) not reachable from any change/* tag — possible hotfix drift (L-02/O-08):"
        )
        out += [f"    {c[:12]}" for c in unlinked[:20]]
    else:
        out.append("  every src commit is attached to a change/* tag")
    out.append("  OpenAPI route⊆operation drift is surfaced by /orient (needs a constructed app); not re-run here")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------
# orchestration + CLI
# ---------------------------------------------------------------------------------------


def run(tree: Path, change_id: str, base: str, do_execute: bool, placement: dict[str, str] | None = None) -> int:
    actx = resolve(tree, change_id, base)
    results = prechecks(actx)
    plan: MergePlan | None = None
    gate_blocked = any(r.status == FAIL for r in results)

    print(f"accept.py — {actx.change_id} on branch {actx.branch} (base {actx.base}, HEAD {actx.head[:12]})")
    print()

    if gate_blocked:
        for cid in (
            "gate.green",
            "docker.tier",
            "criteria.junit-backing",
            "criteria.manual-verdict",
            "merge.fidelity",
            "spec.lint",
            "orphan.sweep",
        ):
            results.append(Result(cid, SKIP, "gate.py + merge not run — a structural precondition already denied"))
    else:
        verdict = run_gate(actx)
        print()
        gate_results, plan = gate_dependent_checks(actx, verdict, placement)
        results.extend(gate_results)

    for r in results:
        first = r.detail.split("\n", 1)[0]
        print(f"[{r.status}] {r.id} — {first}")
        if r.status in (FAIL, FLAG) and "\n" in r.detail:
            for line in r.detail.split("\n")[1:]:
                print(f"       {line}")

    flags = [r for r in results if r.status == FLAG]
    denied = any(r.status == FAIL for r in results)

    if plan is not None and plan.infos:
        print()
        print("== PREPARED MERGE DIFF (criteria -> capability invariants; not yet applied) ==")
        print(plan.diff_text.rstrip())

    print()
    print("== ACCEPT ==")
    for r in flags:
        print(f"FLAG: {r.id} — {r.detail.splitlines()[0]}")
    print(f"verdict: {'DENIED' if denied else 'ACCEPTABLE'}")

    if do_execute:
        if denied:
            print("refusing to --execute: at least one gate FAILed")
            return 1
        if plan is not None and plan.needs_placement:
            print(
                "refusing to --execute: multi-target Affects ("
                + ", ".join(plan.targets)
                + ") needs a placement map from /accept-change (--placement) — accept.py will not dump "
                "every invariant into the first file (spec §5.4)"
            )
            return 1
        report = execute(actx, plan) if plan is not None else drift_report(tree, base)
        print()
        print("== EXECUTED ==")
        print(
            f"merged {actx.branch} into {actx.base}, tagged change/{actx.change_id.replace('/', '-')}, deleted the change dir"
        )
        print(report)
        return 0

    return 1 if denied else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="accept.py",
        description="workflow v3: deterministic acceptance preconditions for a change, then "
        "(with --execute) merge criteria into capability invariants and the branch into the base.",
    )
    parser.add_argument("change", metavar="CTX/NNN", help="change id, e.g. meetings/003")
    parser.add_argument("--base", default="main", help="the S9 base branch to merge into (default: main)")
    parser.add_argument("--execute", action="store_true", help="perform the post-approval actions when no gate FAILs")
    parser.add_argument("--tree", default=".", help="work-tree root (default: cwd)")
    parser.add_argument(
        "--placement",
        default=None,
        metavar="JSON",
        help="multi-target invariant placement map approved by /accept-change: a JSON object "
        '{"AC-1": "<capability>.md", ...} mapping each proven criterion to its capability file, '
        "or @<path> to read that JSON from a file. Required for a multi-target Affects; single-target "
        "is placed deterministically and ignores this.",
    )
    args = parser.parse_args(argv)

    tree = Path(args.tree).resolve()
    if not tree.is_dir():
        print(f"error: tree {tree} is not a directory", file=sys.stderr)
        return 2
    placement: dict[str, str] | None = None
    if args.placement is not None:
        import json  # noqa: PLC0415

        raw = args.placement
        try:
            if raw.startswith("@"):
                raw = Path(raw[1:]).read_text(encoding="utf-8")
            loaded = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"error: --placement is not readable JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(loaded, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in loaded.items()
        ):
            print('error: --placement must be a JSON object of {"AC-id": "<capability>.md"}', file=sys.stderr)
            return 2
        placement = loaded
    try:
        return run(tree, args.change, args.base, args.execute, placement)
    except AcceptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
