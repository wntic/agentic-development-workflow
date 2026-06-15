#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Thin implementation planner — the runner's deterministic trigger + DAG ordering (spec §4, §11).

This is the *orchestration* half of the scaffold tail. The scaffolder (spec §3) lays every file;
the implementer (spec §4) fills one file's bodies. Between them sits the runner: it detects WHICH
files are still pending and in WHAT order to dispatch implementers. Both are deterministic — this
script computes them and emits a worklist; `/verify` drives the dispatch from it.

It deliberately stays THIN and reuses the validator (spec §0 principle 1 — knowledge lives in one
place):
  * `KIND_TO_SKILL` (the kind→skill registry), `load_yaml`, `_section_list` are imported from
    `validate_manifest.py`, never re-stated here.
  * The trigger has two halves (spec §4 — "наличие NotImplementedError + краснота тулчейна"):
      1. a body scaffold is pending while it still carries `raise NotImplementedError`; a relational
         table is pending while its `Table(...)` has no `Column(`.
      2. **contract drift** — a protocol-implementing body (repository / capability adapter) is
         MISSING a method its protocol declares. An additive delta regenerates the protocol
         (declarative) with the new method but leaves the body (written once) untouched, so it no
         longer satisfies the protocol → mypy red, yet there is NO `NotImplementedError`, so the
         textual scan alone would miss it. Detected STRUCTURALLY — the manifest declares the methods,
         the file is the ground truth — so the runner stays thin and never invokes mypy itself.
    Both halves read the file tree, not a guess.
  * Node↔file mapping mirrors a thin slice of `conventions` block A — filename derivation only
    (snake / pluralize / per-kind stem), enough to attach a skill + test to each pending file.
    It does not re-implement the full path derivation; the scaffolder owns that.

Output: a human summary, or `--json` for `/verify` to consume. Each work item is one FILE (a router
with several endpoint functions is one unit — one owner, §4/§11), carrying its producer skill, the
canonical test + its kind (flat | manual | none → the §9 acceptance seam), and a DAG level.

Usage:
  uv run .claude/tools/plan_implementation.py <manifest.yaml> <generated-package-root> [--node X] [--json]
  # multi-context (block F) — union the worklist over every sibling context so none is UNMAPPED:
  uv run .claude/tools/plan_implementation.py <one-manifest.yaml> <tree> --app <epics-dir> [--json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_manifest import BOOTSTRAP_STORE_KINDS, KIND_TO_SKILL, _section_list, load_yaml, repository_skill

# ─────────────────────────────────────────────────────────────────────────────
# Name derivation — the thin slice of `conventions` block A the runner needs to
# turn a manifest identifier into the file stem the scaffolder wrote.
# ─────────────────────────────────────────────────────────────────────────────


def snake(name: str) -> str:
    """PascalCase → snake_case (conventions block A): `ITicketRepository` → `i_ticket_repository`,
    `MaxRequestSize` → `max_request_size`. Acronym runs are not special-cased (matches block A)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def pluralize(name: str) -> str:
    """Table-name pluralization (conventions block A)."""
    if re.search(r"[^aeiou]y$", name):
        return name[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", name):
        return name + "es"
    return name + "s"


def repo_file_stem(repo: dict, store_kind: str | None) -> str:
    """The filename stem the scaffolder wrote for a repository node (conventions block A).

    A relational (bootstrap) store repo → `<snake(backs)>_repository`; a client-style store repo →
    the PROTOCOL-derived stem (strip the leading `I` from `implements`, then snake). The protocol
    form is what keeps POLYGLOT persistence unambiguous: two repositories backing ONE aggregate (a
    Postgres `IMeetingRepository` + a Qdrant `IMeetingSearchIndex`, both `backs: Meeting`) collide
    on the backs-derived name, so the client side keys off its own protocol instead
    (`IMeetingSearchIndex` → `meeting_search_index`). One rule, read by both scaffolder and runner."""
    if store_kind is None or store_kind in BOOTSTRAP_STORE_KINDS:
        return f"{snake(repo.get('backs', ''))}_repository"
    return snake(re.sub(r"^I", "", str(repo.get("implements", ""))))


# ─────────────────────────────────────────────────────────────────────────────
# Work item
# ─────────────────────────────────────────────────────────────────────────────


def _layer_of(rel_path: str) -> str:
    for layer in ("domain", "application", "infrastructure", "restapi"):
        if f"/{layer}/" in rel_path or rel_path.startswith(f"{layer}/"):
            return layer
    return "other"


_LAYER_ORDER = {"domain": 0, "application": 1, "infrastructure": 1, "restapi": 2, "other": 3}


def build_registry(m: dict) -> dict[str, dict]:
    """Map a body-bearing node's file *stem* (+ a directory hint) → its metadata. Keyed by the
    filename stem the scaffolder emitted; the directory hint disambiguates the few collisions
    (a repository vs a same-named anything). Only kinds that scaffold to a BODY appear here —
    declarative nodes (protocols, DTOs, plain VOs/entities, schemas, settings) are already complete."""
    reg: dict[str, dict] = {}

    def put(stem: str, *, kind: str, skill: str, label: str, test_base: str | None, dir_hint: str = "") -> None:
        reg[stem + "|" + dir_hint] = {
            "stem": stem,
            "kind": kind,
            "skill": skill,
            "label": label,
            "test_base": test_base,  # None ⇒ no executable unit test (review tail)
            "dir_hint": dir_hint,
            "deps": [],  # body-node labels this one depends on (filled later)
        }

    # domain — only the body-bearing variants
    for e in _section_list(m, "domain.enums"):
        if e.get("methods"):
            s = snake(e["name"])
            put(
                s, kind="domain.enums", skill=KIND_TO_SKILL["domain.enums"], label=e["name"], test_base=f"test_{s}_enum"
            )
    for vo in _section_list(m, "domain.value_objects"):
        if vo.get("invariants"):
            s = snake(vo["name"])
            put(
                s,
                kind="domain.value_objects",
                skill=KIND_TO_SKILL["domain.value_objects"],
                label=vo["name"],
                test_base=f"test_{s}",
            )
    for en in _section_list(m, "domain.entities"):
        if en.get("invariants"):
            s = snake(en["name"])
            put(
                s,
                kind="domain.entities",
                skill=KIND_TO_SKILL["domain.entities"],
                label=en["name"],
                test_base=f"test_{s}_entity",
            )
    for sv in _section_list(m, "domain.services"):
        s = snake(sv["name"])
        # the test-domain-service file is test_<snake>_service.py — but the `_service` suffix is
        # not doubled when the service name already ends in "Service" (→ test_<snake>.py).
        tb = f"test_{s}" if s.endswith("_service") else f"test_{s}_service"
        put(s, kind="domain.services", skill=KIND_TO_SKILL["domain.services"], label=sv["name"], test_base=tb)

    # application — one handler body per command/query
    for c in _section_list(m, "application.commands"):
        s = snake(c["name"])
        put(
            f"{s}_handler",
            kind="application.commands",
            skill=KIND_TO_SKILL["application.commands"],
            label=c["name"],
            test_base=f"test_{s}_handler",
        )
    for q in _section_list(m, "application.queries"):
        s = snake(q["name"])
        put(
            f"{s}_handler",
            kind="application.queries",
            skill=KIND_TO_SKILL["application.queries"],
            label=q["name"],
            test_base=f"test_{s}_handler",
        )

    # infrastructure — repository body + (relational only) its write-once table; capability adapter body
    store_kind_by_name = {d["name"]: d.get("kind") for d in _section_list(m, "infrastructure.datastores")}
    for r in _section_list(m, "infrastructure.repositories"):
        agg = r.get("backs", "")
        s = snake(agg)
        store_name = r.get("store")
        store_kind = store_kind_by_name.get(store_name) if store_name else None  # None ⇒ implicit postgres
        put(
            repo_file_stem(r, store_kind),  # polyglot-safe: backs-derived (relational) or protocol-derived (client)
            kind="infrastructure.repositories",
            skill=repository_skill(store_kind),  # store-aware: SQLAlchemy vs store skill (block B/C)
            label=f"{r.get('implements', s)} impl",
            test_base=None,
            dir_hint="repositories",
        )
        # the relational table is body-bearing too (write-once skeleton) — only for a bootstrap
        # (relational) store; a client-style store (qdrant/redis/…) persists with no SQLAlchemy table.
        if store_kind is None or store_kind in BOOTSTRAP_STORE_KINDS:
            put(
                pluralize(s),
                kind="infrastructure.tables",
                skill="infra-sqlalchemy-table",
                label=f"{agg} table",
                test_base=None,
                dir_hint="tables",
            )
    for cap in _section_list(m, "infrastructure.capabilities"):
        adapter = str(cap.get("adapter", ""))
        role = cap.get("role")
        if role:
            cls = adapter.capitalize() + role
        else:
            impl = str(cap.get("implements", ""))
            cls = adapter.capitalize() + re.sub(r"^ICan", "", impl)
        s = snake(cls)
        put(
            s,
            kind="infrastructure.capabilities",
            skill=KIND_TO_SKILL["infrastructure.capabilities"],
            label=cls,
            test_base=None,
        )

    # restapi — one router file per resource (groups several endpoint bodies); one file per middleware
    seen_resources: set[str] = set()
    for ep in _section_list(m, "restapi.endpoints"):
        res = str(ep.get("resource", ""))
        if res in seen_resources:
            continue
        seen_resources.add(res)
        put(
            res,
            kind="restapi.endpoints",
            skill=KIND_TO_SKILL["restapi.endpoints"],
            label=f"{res} router",
            test_base=None,
            dir_hint="routers",
        )
    for mw in _section_list(m, "restapi.middlewares"):
        s = snake(mw["name"])
        put(
            s,
            kind="restapi.middlewares",
            skill=KIND_TO_SKILL["restapi.middlewares"],
            label=mw["name"],
            test_base=None,
            dir_hint="middleware",
        )

    _wire_deps(m, reg)
    return reg


def _wire_deps(m: dict, reg: dict[str, dict]) -> None:
    """Body→body edges for DAG ordering (§11). Most edges point at DECLARATIVE nodes (protocols,
    entities) which are already complete (level 0); the only body→body edges in practice are a
    handler that depends on a domain SERVICE, and a router that groups its handlers."""
    service_names = {s["name"] for s in _section_list(m, "domain.services")}

    def handler_dep_labels(node: dict) -> list[str]:
        deps = (node.get("handler") or {}).get("dependencies", []) or []
        return [d for d in deps if d in service_names]  # only the body-bearing ones

    for c in _section_list(m, "application.commands"):
        key = f"{snake(c['name'])}_handler|"
        if key in reg:
            reg[key]["deps"] = handler_dep_labels(c)
    for q in _section_list(m, "application.queries"):
        key = f"{snake(q['name'])}_handler|"
        if key in reg:
            reg[key]["deps"] = handler_dep_labels(q)
    # routers depend on their handler bodies (integration ordering — handlers first)
    for ep in _section_list(m, "restapi.endpoints"):
        res = str(ep.get("resource", ""))
        key = f"{res}|routers"
        if key in reg:
            h = ep.get("handler")
            hkey = f"{snake(h)}_handler|" if h else None
            if hkey and hkey in reg and reg[hkey]["label"] not in reg[key]["deps"]:
                reg[key]["deps"].append(reg[hkey]["label"])
    # a relational repository's body SELECTs its aggregate's table columns, so the write-once table
    # must be filled FIRST — no manifest edge spans the two infra sections, so synthesize a
    # repo→table edge (F-025) and the DAG places the table one level below its repo (spec §11).
    store_kind_by_name = {d["name"]: d.get("kind") for d in _section_list(m, "infrastructure.datastores")}
    labels = {v["label"] for v in reg.values()}
    for r in _section_list(m, "infrastructure.repositories"):
        store_kind = store_kind_by_name.get(r.get("store")) if r.get("store") else None
        if store_kind is not None and store_kind not in BOOTSTRAP_STORE_KINDS:
            continue  # client-style store has no SQLAlchemy table
        repo_key = repo_file_stem(r, store_kind) + "|repositories"
        table_label = f"{r.get('backs', '')} table"
        if repo_key in reg and table_label in labels and table_label not in reg[repo_key]["deps"]:
            reg[repo_key]["deps"].append(table_label)


def _dag_level(reg: dict[str, dict]) -> dict[str, int]:
    """Longest-path level over body→body deps. Independent nodes are level 0."""
    label_to_key = {v["label"]: k for k, v in reg.items()}
    memo: dict[str, int] = {}

    def lvl(key: str, stack: tuple[str, ...] = ()) -> int:
        if key in memo:
            return memo[key]
        if key in stack:  # cycle guard — should not happen on a valid manifest
            return 0
        deps = reg[key]["deps"]
        out = (
            0
            if not deps
            else 1 + max((lvl(label_to_key[d], (*stack, key)) for d in deps if d in label_to_key), default=-1)
        )
        memo[key] = out
        return out

    return {k: lvl(k) for k in reg}


# ─────────────────────────────────────────────────────────────────────────────
# Trigger detection — the file tree is ground truth (spec §4)
# ─────────────────────────────────────────────────────────────────────────────


def _package_src(root: Path) -> Path:
    src = root / "src"
    pkgs = [p for p in src.iterdir() if p.is_dir() and not p.name.startswith(".")] if src.is_dir() else []
    if len(pkgs) != 1:
        sys.exit(f"error: expected exactly one package under {src}/, found {[p.name for p in pkgs]}")
    return pkgs[0]


def pending_files(pkg_src: Path) -> list[Path]:
    """Files still carrying a pending scaffold: a `raise NotImplementedError` body, or a
    column-less relational table (`Table(` present, no `Column(`)."""
    out: list[Path] = []
    for p in sorted(pkg_src.rglob("*.py")):
        text = p.read_text()
        # strip line comments so a CONTRACT note that says "fills each Column(...)" does not read
        # as a filled table (the table scaffold lists its columns in a comment).
        code = "".join(line.split("#", 1)[0] for line in text.splitlines(keepends=True))
        is_column_less_table = "/tables/" in p.as_posix() and "Table(" in code and "Column(" not in code
        if "raise NotImplementedError" in code or is_column_less_table:
            out.append(p)
    return out


def _decl_method_names(entries: list | None) -> set[str]:
    """Method names a protocol declares in the manifest. Each entry is a bare signature string or a
    `{signature, notes}` mapping; pull the name out of `(async )?def <name>(`."""
    out: set[str] = set()
    for me in entries or []:
        sig = me if isinstance(me, str) else (me.get("signature") or "")
        mo = re.search(r"\bdef\s+(\w+)", sig)
        if mo:
            out.add(mo.group(1))
    return out


def _defined_method_names(path: Path) -> set[str]:
    """Method names a concrete body file defines (comments stripped, so a contract-comment that
    mentions a method name does not count as a definition)."""
    code = "".join(line.split("#", 1)[0] for line in path.read_text().splitlines(keepends=True))
    return set(re.findall(r"\bdef\s+(\w+)", code))


def drifted_files(m: dict, pkg_src: Path, already: set[Path]) -> dict[Path, list[str]]:
    """The second trigger half (spec §4): protocol-implementing bodies (repositories, capability
    adapters) whose concrete class is MISSING a method its protocol declares — additive-delta
    contract drift. The protocol regenerated with the new method; the written-once body did not, so
    it no longer satisfies the protocol (mypy red) but carries no `NotImplementedError`. Detected
    structurally against the manifest; files already pending (NIE / column-less) are skipped."""
    repo_protocols = {p["name"]: p for p in _section_list(m, "domain.repository_protocols")}
    cap_protocols = {c["name"]: c for c in _section_list(m, "domain.capability_protocols")}
    store_kind_by_name = {d["name"]: d.get("kind") for d in _section_list(m, "infrastructure.datastores")}
    out: dict[Path, list[str]] = {}

    def check(stem: str, declared: set[str]) -> None:
        f = next((p for p in pkg_src.rglob(f"{stem}.py")), None)
        if f is None or f in already:
            return
        missing = sorted(declared - _defined_method_names(f))
        if missing:
            out[f] = missing

    for r in _section_list(m, "infrastructure.repositories"):
        proto = repo_protocols.get(r.get("implements", ""))
        if proto:
            store_kind = store_kind_by_name.get(r.get("store")) if r.get("store") else None
            check(repo_file_stem(r, store_kind), _decl_method_names(proto.get("methods")))

    for cap in _section_list(m, "infrastructure.capabilities"):
        proto = cap_protocols.get(cap.get("implements", ""))
        if not proto:
            continue
        adapter = str(cap.get("adapter", ""))
        role = cap.get("role")
        cls = (
            adapter.capitalize() + role
            if role
            else adapter.capitalize() + re.sub(r"^ICan", "", str(cap.get("implements", "")))
        )
        check(snake(cls), _decl_method_names(proto.get("methods")))

    return out


def _match(pkg_src: Path, f: Path, reg: dict[str, dict]) -> dict | None:
    stem = f.stem
    rel = f.relative_to(pkg_src).as_posix()
    # prefer a dir-hinted entry (repositories / tables / routers / middleware) when the path says so
    for hint in ("repositories", "tables", "routers", "middleware"):
        if f"/{hint}/" in f"/{rel}" and (stem + "|" + hint) in reg:
            return reg[stem + "|" + hint]
    return reg.get(stem + "|")


def _find_test(tests_dir: Path, test_base: str | None) -> tuple[str | None, str]:
    """Return (test path relative-ish, kind) where kind ∈ {flat, manual, none}."""
    if not test_base or not tests_dir.is_dir():
        return None, "none"
    flat = next(tests_dir.rglob(f"{test_base}.py"), None)
    if flat:
        return str(flat), "flat"
    manual = next(tests_dir.rglob(f"{test_base}_manual.py"), None)
    if manual:
        return str(manual), "manual"
    return None, "none"


# ─────────────────────────────────────────────────────────────────────────────
# Plan
# ─────────────────────────────────────────────────────────────────────────────


def plan(manifests: list[Path], root: Path, only_node: str | None) -> list[dict]:
    """Build the implementer worklist for a scaffolded tree. In single-context mode `manifests` is
    one path; in app-mode (block F) it is the target plus its sibling context manifests, so the
    registry is the UNION over every context — no other context's body is left UNMAPPED (F-010)."""
    loaded: list[dict] = []
    for mp in manifests:
        m = load_yaml(mp)
        if not isinstance(m, dict):
            sys.exit(f"error: {mp} did not parse to a mapping")
        loaded.append(m)
    reg: dict[str, dict] = {}
    for m in loaded:
        for k, v in build_registry(m).items():
            reg.setdefault(k, v)  # first context wins on a shared-substrate node (deduped, block F)
    levels = _dag_level(reg)
    label_to_key = {v["label"]: k for k, v in reg.items()}
    pkg_src = _package_src(root)
    tests_dir = root / "tests"

    items: list[dict] = []
    pending = pending_files(pkg_src)
    for f in pending:
        meta = _match(pkg_src, f, reg)
        rel = f.relative_to(root).as_posix()
        if meta is None:
            # a pending file the manifest does not map — a bootstrap body scaffold or a gap
            layer = _layer_of(f.relative_to(pkg_src).as_posix())
            items.append(
                {
                    "file": str(f),
                    "rel": rel,
                    "label": f.stem,
                    "kind": "(unmapped)",
                    "skill": "restapi-app-bootstrap" if layer == "restapi" else "(?)",
                    "test": None,
                    "test_kind": "none",
                    "dag_level": _LAYER_ORDER.get(layer, 3),
                    "unmapped": True,
                    "trigger": "scaffold",
                    "missing_methods": [],
                }
            )
            continue
        key = label_to_key[meta["label"]]
        test, tkind = _find_test(tests_dir, meta["test_base"])
        items.append(
            {
                "file": str(f),
                "rel": rel,
                "label": meta["label"],
                "kind": meta["kind"],
                "skill": meta["skill"],
                "test": test,
                "test_kind": tkind,
                "dag_level": levels[key],
                "unmapped": False,
                "trigger": "scaffold",
                "missing_methods": [],
            }
        )

    # second trigger half — contract drift (a protocol-implementer missing a declared method),
    # merged across every in-scope context (app-mode unions the drift the same way as the registry)
    drift: dict[Path, list[str]] = {}
    for m in loaded:
        for f, missing in drifted_files(m, pkg_src, set(pending)).items():
            drift.setdefault(f, missing)
    for f, missing in drift.items():
        meta = _match(pkg_src, f, reg)
        if meta is None:
            continue
        key = label_to_key[meta["label"]]
        test, tkind = _find_test(tests_dir, meta["test_base"])
        items.append(
            {
                "file": str(f),
                "rel": f.relative_to(root).as_posix(),
                "label": meta["label"],
                "kind": meta["kind"],
                "skill": meta["skill"],
                "test": test,
                "test_kind": tkind,
                "dag_level": levels[key],
                "unmapped": False,
                "trigger": "drift",
                "missing_methods": missing,
            }
        )

    if only_node:
        nl = only_node.lower()
        items = [it for it in items if nl in it["label"].lower() or nl in it["rel"].lower()]

    items.sort(key=lambda it: (it["dag_level"], _LAYER_ORDER.get(_layer_of(it["rel"]), 3), it["rel"]))
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the implementer worklist for a scaffolded package.")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("root", type=Path, help="the generated package root (e.g. examples/generated/helpdesk5)")
    ap.add_argument("--node", default=None, help="filter to one node/file (substring of label or path)")
    ap.add_argument(
        "--app",
        type=Path,
        default=None,
        help="multi-context (block F): also union the registry over the sibling manifests under this "
        "dir (globs <dir>/*/manifest.yaml, excluding the target) so no other context's body is UNMAPPED",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON for /verify to consume")
    args = ap.parse_args(argv)

    if not args.manifest.is_file():
        sys.exit(f"error: manifest not found: {args.manifest}")
    if not args.root.is_dir():
        sys.exit(f"error: package root not found: {args.root}")

    manifests = [args.manifest]
    if args.app is not None:
        target = args.manifest.resolve()
        manifests += [p for p in sorted(args.app.glob("*/manifest.yaml")) if p.resolve() != target]

    items = plan(manifests, args.root, args.node)

    if args.json:
        print(json.dumps({"root": str(args.root), "count": len(items), "items": items}, indent=2))
        return 0

    if not items:
        print("No pending scaffolds — every body is filled. ✓")
        return 0

    flat = [i for i in items if i["test_kind"] == "flat"]
    tail = [i for i in items if i["test_kind"] != "flat"]
    print(f"{len(items)} pending file(s) under {args.root}\n")
    last = None
    for it in items:
        if it["dag_level"] != last:
            print(f"── DAG level {it['dag_level']} " + "─" * 40)
            last = it["dag_level"]
        flag = "  ⚠ UNMAPPED" if it["unmapped"] else ""
        drift = f"  ⟲ DRIFT: missing {', '.join(it['missing_methods'])}" if it.get("trigger") == "drift" else ""
        print(f"  [{it['test_kind']:^6}] {it['rel']}{drift}")
        print(f"           skill={it['skill']}  node={it['label']}{flag}")
        if it["test"]:
            print(f"           test={Path(it['test']).name}")
    print(f"\nExecutable-gated (flat test → green is acceptance): {len(flat)}")
    print(f"Review tail (mypy+ruff only, no executable test): {len(tail)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
