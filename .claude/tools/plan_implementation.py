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
  * The trigger is TEXTUAL (spec §4): a body scaffold is pending while it still carries
    `raise NotImplementedError`; a relational table is pending while its `Table(...)` has no
    `Column(`. The ground truth is the file tree, not a guess.
  * Node↔file mapping mirrors a thin slice of `conventions` block A — filename derivation only
    (snake / pluralize / per-kind stem), enough to attach a skill + test to each pending file.
    It does not re-implement the full path derivation; the scaffolder owns that.

Output: a human summary, or `--json` for `/verify` to consume. Each work item is one FILE (a router
with several endpoint functions is one unit — one owner, §4/§11), carrying its producer skill, the
canonical test + its kind (flat | manual | none → the §9 acceptance seam), and a DAG level.

Usage:
  uv run .claude/tools/plan_implementation.py <manifest.yaml> <generated-package-root> [--node X] [--json]
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
            f"{s}_repository",
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


def plan(manifest: Path, root: Path, only_node: str | None) -> list[dict]:
    m = load_yaml(manifest)
    if not isinstance(m, dict):
        sys.exit(f"error: {manifest} did not parse to a mapping")
    reg = build_registry(m)
    levels = _dag_level(reg)
    label_to_key = {v["label"]: k for k, v in reg.items()}
    pkg_src = _package_src(root)
    tests_dir = root / "tests"

    items: list[dict] = []
    for f in pending_files(pkg_src):
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
    ap.add_argument("--json", action="store_true", help="emit JSON for /verify to consume")
    args = ap.parse_args(argv)

    if not args.manifest.is_file():
        sys.exit(f"error: manifest not found: {args.manifest}")
    if not args.root.is_dir():
        sys.exit(f"error: package root not found: {args.root}")

    items = plan(args.manifest, args.root, args.node)

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
        print(f"  [{it['test_kind']:^6}] {it['rel']}")
        print(f"           skill={it['skill']}  node={it['label']}{flag}")
        if it["test"]:
            print(f"           test={Path(it['test']).name}")
    print(f"\nExecutable-gated (flat test → green is acceptance): {len(flat)}")
    print(f"Review tail (mypy+ruff only, no executable test): {len(tail)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
