#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Deterministic manifest validator — the verifier core of the agentic pipeline (spec §6).

This REPLACES the old Pydantic `schema.py` + `validator.py` pair. It is **stdlib-only**
validation logic (no pydantic, no codegen package) so it ships bare in a plugin; the only
third-party dependency is PyYAML for *parsing*, isolated in `load_yaml` and declared via
PEP 723 so `uv run .claude/tools/validate_manifest.py <manifest.yaml>` is self-contained.
Swap `load_yaml` for a handrolled subset parser if true zero-dep is ever wanted — nothing
else imports yaml.

What it checks (and ONLY this — see spec §6 / MANIFEST_SCHEMA.md):
  1. FORM     — required fields, closed enums, unknown-key rejection (extra=forbid),
                Then has ≥1 outcome verb, `then.with` requires `then.persists`.
  2. GRAPH    — every DECLARED edge resolves to a declared node (handler deps → protocols,
                endpoint.handler → command/query, raises → exceptions, repo.backs → entity,
                repo.store → datastore, settings refs, …). Local behaviour-consistency
                (rule #11): then.raises ∈ node.raises, then.logs == log_event, then.calls
                dep ∈ dependencies. Reserved audit fields (created_at/updated_at) rejected
                on entities. Cross-epic refs (`epic:Name`) are warnings, not errors.
  3. SKILL COVERAGE (§16) — every artifact KIND present in the manifest has a producer skill
                in the `kind→skill` registry (KIND_TO_SKILL, mirroring the `conventions` skill).
                An unmapped kind is a presence-gap → pre-flight stop (error), before the runner
                spawns scaffolders. Free-token `infrastructure.datastores` is exempt: it is
                store-profile-driven (degrades gracefully), not skill-dispatched.
  4. LOUD DEGRADATION (warnings, non-blocking) — a body-bearing node with no behaviour AND
                no notes (unspecified_body); an id-only command that persists with no
                `then.with` and no notes (unspecified_transition).

What it does NOT check — by design (spec §6, §0 principle 3): it never parses a TYPE or
SIGNATURE string. Type/signature correctness is the toolchain's job (mypy/compile). So
`output: "AsyncIterator[str]"` and any free type expression pass untouched; the validator
follows only explicit named-reference fields. This is what keeps it thin and language-agnostic.

Exit 0 when clean (no errors, no open questions); exit 1 otherwise. Warnings never block.
"""

import argparse
import copy
from dataclasses import dataclass, field
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Findings
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "question" | "warning"
    code: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(Finding(severity, code, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def questions(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "question"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        """The pipeline may proceed only with no errors and no open questions."""
        return not self.errors and not self.questions


# ─────────────────────────────────────────────────────────────────────────────
# Schema as data — one entry per node kind. THIS dict is the CANONICAL manifest shape:
# manifest.template.yaml is generated from it (gen_template.py), and the prose in
# MANIFEST_SCHEMA.md is a stale restatement scheduled for a thin rewrite (validator wins).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class F:
    """A field spec. `kind` is one of:
    "str" | "int" | "bool" | "strlist" | "intlist" | "map" | "any" | "enum"
    | ("obj", <SchemaName>) | ("list", <SchemaName>) | "protocol_methods".
    `any` = a free literal/expression the validator never inspects (types, defaults)."""

    kind: object
    required: bool = True
    default: object = None
    choices: tuple[str, ...] = ()


# Leaf + node schemas. `sources` is a required str-list on most nodes; closed enums use
# choices. Notably ABSENT vs the old pydantic schema: the signature regex guard (toolchain's
# job) and Repository.constraint_map (the constraint name is the implementer's, authored in
# the write-once Table scaffold — intent moves to repository `notes` + protocol `raises`).
SCHEMAS: dict[str, dict[str, F]] = {
    "Field": {
        "name": F("str"),
        "type": F("str"),
        "optional": F("bool", required=False, default=False),
        "default": F("any", required=False, default=None),
    },
    "Invariant": {
        "rule": F("str"),
        "field": F("str", required=False, default=None),
        "source": F("str"),
    },
    "Then": {
        "raises": F("str", required=False, default=None),
        "returns": F("str", required=False, default=None),
        "persists": F("str", required=False, default=None),
        "deletes": F("str", required=False, default=None),
        "logs": F("str", required=False, default=None),
        "calls": F("str", required=False, default=None),
        "with": F("map", required=False, default={}),
    },
    "Seed": {
        "entity": F("str"),
        "fields": F("map", required=False, default={}),
    },
    "Behaviour": {
        "given": F("str"),
        "arrange": F(("list", "Seed"), required=False, default=[]),
        "when": F("str"),
        "act": F("map", required=False, default={}),
        "then": F(("obj", "Then")),
        "source": F("str"),
    },
    "EnumMember": {"name": F("str"), "value": F("str")},
    "EnumMethod": {"signature": F("str"), "rule": F("str")},
    "Enum": {
        "name": F("str"),
        "subdomain": F("str"),
        "base": F("enum", required=False, default="StrEnum", choices=("StrEnum", "Enum")),
        "members": F(("list", "EnumMember")),
        "methods": F(("list", "EnumMethod"), required=False, default=[]),
        "sources": F("strlist"),
    },
    "ValueObject": {
        "name": F("str"),
        "subdomain": F("str"),
        "frozen": F("bool", required=False, default=True),
        "fields": F(("list", "Field")),
        "invariants": F(("list", "Invariant"), required=False, default=[]),
        "sources": F("strlist"),
    },
    "ServiceMethod": {
        "signature": F("str"),
        "raises": F("strlist", required=False, default=[]),
        "behaviour": F(("list", "Behaviour"), required=False, default=[]),
        "notes": F("str", required=False, default=None),
    },
    "Service": {
        "name": F("str"),
        "subdomain": F("str"),
        # No `kind:` field. The orchestrator-vs-pure structural axis is DERIVED, not declared:
        # a service is an orchestrator iff it has `dependencies`, pure otherwise (a derivable
        # decision fails earn-its-place — spec §5). The domain-service skill reads `dependencies`
        # to pick the template; the validator carries nothing.
        "dependencies": F("strlist", required=False, default=[]),
        "methods": F(("list", "ServiceMethod")),
        "notes": F("str", required=False, default=None),
        "sources": F("strlist"),
    },
    "CapabilityProtocol": {
        "name": F("str"),
        "subdomain": F("str"),
        "methods": F("protocol_methods"),
        "sources": F("strlist"),
        "notes": F("str", required=False, default=None),
    },
    "Entity": {
        "name": F("str"),
        "subdomain": F("str"),
        "identity_field": F("str", required=False, default="id"),
        "fields": F(("list", "Field")),
        "invariants": F(("list", "Invariant"), required=False, default=[]),
        "sources": F("strlist"),
    },
    "RepositoryProtocol": {
        "name": F("str"),
        "subdomain": F("str"),
        "aggregate": F("str"),
        "methods": F("protocol_methods"),
        "raises": F("strlist", required=False, default=[]),
        "sources": F("strlist"),
    },
    "DomainException": {
        "name": F("str"),
        "code": F("str"),
        "http_status": F("int"),
        "sources": F("strlist"),
    },
    "FilterSort": {
        "enum_name": F("str"),
        "keys": F("strlist"),
        "default": F("str"),
    },
    "Filter": {
        "name": F("str"),
        "subdomain": F("str"),
        "fields": F(("list", "Field")),
        "pagination": F("bool", required=False, default=False),
        "sort": F(("obj", "FilterSort"), required=False, default=None),
        "sources": F("strlist"),
    },
    "Domain": {
        "enums": F(("list", "Enum"), required=False, default=[]),
        "value_objects": F(("list", "ValueObject"), required=False, default=[]),
        "entities": F(("list", "Entity"), required=False, default=[]),
        "services": F(("list", "Service"), required=False, default=[]),
        "filters": F(("list", "Filter"), required=False, default=[]),
        "repository_protocols": F(("list", "RepositoryProtocol"), required=False, default=[]),
        "capability_protocols": F(("list", "CapabilityProtocol"), required=False, default=[]),
        "exceptions": F(("list", "DomainException"), required=False, default=[]),
    },
    "Handler": {"dependencies": F("strlist", required=False, default=[])},
    "Command": {
        "name": F("str"),
        "input": F(("list", "Field"), required=False, default=[]),
        "output": F("str"),
        "handler": F(("obj", "Handler")),
        "log_event": F("str", required=False, default=None),
        "raises": F("strlist", required=False, default=[]),
        "behaviour": F(("list", "Behaviour"), required=False, default=[]),
        "sources": F("strlist"),
        "notes": F("str", required=False, default=None),
    },
    "ResultDto": {"name": F("str"), "fields": F(("list", "Field"))},
    "Query": {
        "name": F("str"),
        "input": F(("list", "Field"), required=False, default=[]),
        "output": F("str"),
        "result_fields": F(("list", "Field"), required=False, default=[]),
        "result_dtos": F(("list", "ResultDto"), required=False, default=[]),
        "handler": F(("obj", "Handler")),
        "raises": F("strlist", required=False, default=[]),
        "behaviour": F(("list", "Behaviour"), required=False, default=[]),
        "sources": F("strlist"),
        "notes": F("str", required=False, default=None),
    },
    "Application": {
        "commands": F(("list", "Command"), required=False, default=[]),
        "queries": F(("list", "Query"), required=False, default=[]),
    },
    "Datastore": {
        "name": F("str"),
        "kind": F("str"),
        "settings": F("str", required=False, default=None),
        "requires_packages": F("strlist", required=False, default=[]),
        "sources": F("strlist"),
    },
    "Repository": {
        "implements": F("str"),
        "backs": F("str"),
        "store": F("str", required=False, default=None),
        "notes": F("str", required=False, default=None),
        "sources": F("strlist"),
    },
    "SettingsField": {
        "name": F("str"),
        "type": F("str"),
        "default": F("any", required=False, default=None),
        "secret": F("bool", required=False, default=False),
    },
    "SettingsMethod": {
        "signature": F("str"),
        "decorators": F("strlist", required=False, default=[]),
        "notes": F("str", required=False, default=None),
    },
    "Settings": {
        "name": F("str"),
        "env_prefix": F("str"),
        "fields": F(("list", "SettingsField")),
        "methods": F(("list", "SettingsMethod"), required=False, default=[]),
        "sources": F("strlist"),
    },
    "Capability": {
        "implements": F("str"),
        "adapter": F("str"),
        "role": F("str", required=False, default=None),
        "settings": F("str", required=False, default=None),
        "requires_packages": F("strlist", required=False, default=[]),
        "notes": F("str", required=False, default=None),
        "sources": F("strlist"),
    },
    "Infrastructure": {
        "settings": F(("list", "Settings"), required=False, default=[]),
        "datastores": F(("list", "Datastore"), required=False, default=[]),
        "repositories": F(("list", "Repository"), required=False, default=[]),
        "capabilities": F(("list", "Capability"), required=False, default=[]),
    },
    "RestSchema": {
        "name": F("str"),
        "resource": F("str"),
        "kind": F("enum", choices=("request", "response")),
        "fields": F(("list", "Field")),
        "sources": F("strlist"),
    },
    "Endpoint": {
        "method": F("enum", choices=("GET", "POST", "PATCH", "PUT", "DELETE")),
        "path": F("str"),
        "resource": F("str"),
        "auth": F("str"),
        "request": F("str", required=False, default=None),
        "response": F("str", required=False, default=None),
        "request_kind": F("enum", required=False, default="json", choices=("json", "multipart")),
        "status_code": F("int", required=False, default=None),
        "handler": F("str"),
        "notes": F("str", required=False, default=None),
        "sources": F("strlist"),
    },
    "Middleware": {
        "name": F("str"),
        # `config` is the ONE sanctioned open key→value map in the schema. A middleware's __init__
        # kwargs are an irreducibly open passthrough (header name, max_bytes, …) validated at runtime
        # by the constructor — not architect-reviewable structure, so it is not the arbitrary
        # per-artifact escape-hatch map the earn-its-place rule forbids. Same family as behaviour
        # `act`/`then.with`: flat literals the validator deliberately never inspects.
        "config": F("map", required=False, default={}),
        "introduces_http": F("intlist", required=False, default=[]),
        "notes": F("str", required=False, default=None),
        "sources": F("strlist"),
    },
    "RestApi": {
        "schemas": F(("list", "RestSchema"), required=False, default=[]),
        "endpoints": F(("list", "Endpoint"), required=False, default=[]),
        "middlewares": F(("list", "Middleware"), required=False, default=[]),
    },
    "ArchitectureRule": {
        "name": F("str"),
        "pattern": F("str"),
        "paths": F("strlist"),
        "allow_list": F("strlist", required=False, default=[]),
        "sources": F("strlist", required=False, default=[]),
    },
    "Tests": {
        "architecture_rules": F(("list", "ArchitectureRule"), required=False, default=[]),
    },
    "Meta": {
        "epic": F("str"),
        "name": F("str"),
        "sources": F("strlist"),
        "supersedes": F("strlist", required=False, default=[]),
        "replaces": F("strlist", required=False, default=[]),
        "notes": F("str", required=False, default=None),
    },
    "Manifest": {
        "meta": F(("obj", "Meta")),
        "domain": F(("obj", "Domain"), required=False, default={}),
        "application": F(("obj", "Application"), required=False, default={}),
        "infrastructure": F(("obj", "Infrastructure"), required=False, default={}),
        "restapi": F(("obj", "RestApi"), required=False, default={}),
        "tests": F(("obj", "Tests"), required=False, default={}),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Skill-coverage registry — mirrors the `conventions` skill's kind→skill map (§16)
# ─────────────────────────────────────────────────────────────────────────────

# The DETERMINISTIC dispatch: one PRODUCER skill per manifest artifact kind. This is a small
# data mirror of registry B in `.claude/skills/conventions/SKILL.md` (the way SCHEMAS mirrors
# MANIFEST_SCHEMA.md) — the source of truth is the conventions skill; this dict is what the
# pre-flight coverage gate reads so it stays stdlib-only. Companion/test/bootstrap/reference
# skills are NOT here — they are not per-artifact-kind dispatch (see the conventions skill).
KIND_TO_SKILL: dict[str, str] = {
    "domain.enums": "domain-enum",
    "domain.value_objects": "domain-value-object",
    "domain.entities": "domain-entity",
    "domain.services": "domain-service",
    "domain.filters": "domain-filter",
    "domain.repository_protocols": "domain-repository-protocol",
    "domain.capability_protocols": "domain-capability-protocol",
    "domain.exceptions": "domain-exception",
    "application.commands": "application-command",
    "application.queries": "application-query",
    "infrastructure.repositories": "infra-sqlalchemy-repository",  # relational default — see repository_skill()
    "infrastructure.settings": "infra-settings",
    "infrastructure.capabilities": "infra-capability-adapter",
    "restapi.schemas": "restapi-schema",
    "restapi.endpoints": "restapi-endpoint",
    "restapi.middlewares": "restapi-middleware",
    "tests.architecture_rules": "test-architecture-rule",
}

# Artifact kinds handled by a store PROFILE (conventions), not a producer skill: a free-token
# `kind` degrades gracefully to a generic client (§3), so an unmapped datastore is never a
# presence-gap. Excluded from the gate AND from the meta-coverage assertion.
_PROFILE_DRIVEN_KINDS: frozenset[str] = frozenset({"infrastructure.datastores"})

# Repositories are the one kind whose producer skill depends on a graph EDGE
# (`repository.store → datastore.kind`), not the kind alone: a relational (bootstrap) store maps to
# the SQLAlchemy skill, any client-style store (vector/cache/document) to the vendor-agnostic store
# skill. KIND_TO_SKILL carries only the relational default — all the §16 presence gate needs ("does
# this kind have *a* producer"); `repository_skill()` makes the finer store-aware choice the runner
# and scaffolder dispatch on (conventions block B/C). A new client-style backend (chroma, pinecone,
# mongo) is a block-C profile row + the node's `requires_packages` — never a new skill, the same
# way one `infra-capability-adapter` serves boto3/httpx/PyJWT/openai.
STORE_REPOSITORY_SKILL = "infra-store-repository"  # client-style stores (vector / cache / document)
BOOTSTRAP_STORE_KINDS: frozenset[str] = frozenset({"postgres"})  # relational; mirrors block C `uses_bootstrap`


def repository_skill(store_kind: str | None) -> str:
    """The producer skill for a repository node, chosen by its backing store's profile (block B/C).
    Bootstrap (relational) store → the SQLAlchemy skill; any client-style store → the store skill.
    `store_kind is None` ⇒ the implicit single postgres store (relational)."""
    if store_kind is None or store_kind in BOOTSTRAP_STORE_KINDS:
        return KIND_TO_SKILL["infrastructure.repositories"]
    return STORE_REPOSITORY_SKILL


# The manifest sections whose list-fields ARE artifact kinds (meta is not a producer container).
_CONTAINER_SCHEMAS: dict[str, str] = {
    "domain": "Domain",
    "application": "Application",
    "infrastructure": "Infrastructure",
    "restapi": "RestApi",
    "tests": "Tests",
}


def artifact_kind_tokens() -> list[str]:
    """Every artifact-kind path token (`<section>.<field>`) the schema knows — derived from the
    container schemas so it stays in lockstep with SCHEMAS (a new list-field is picked up for
    free). This is the universe the coverage gate and the meta-coverage test range over."""
    tokens: list[str] = []
    for section, schema_name in _CONTAINER_SCHEMAS.items():
        for fname, fspec in SCHEMAS[schema_name].items():
            if isinstance(fspec.kind, tuple) and fspec.kind[0] == "list":
                tokens.append(f"{section}.{fname}")
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — form check + normalization (fills defaults, coerces, rejects unknowns)
# ─────────────────────────────────────────────────────────────────────────────


def _empty_for(kind: object) -> object:
    if isinstance(kind, tuple):
        return [] if kind[0] == "list" else {}
    return {"strlist": [], "intlist": [], "map": {}, "protocol_methods": [], "int": 0, "bool": False}.get(kind)  # type: ignore[arg-type]


def _check_value(value: object, fspec: F, path: str, report: Report) -> object:
    kind = fspec.kind
    if isinstance(kind, tuple):
        tag, sub = kind
        if tag == "obj":
            if not isinstance(value, dict):
                report.add("error", "bad_type", f"{path}: expected a mapping, got {type(value).__name__}")
                return _check_mapping({}, sub, path, report)
            return _check_mapping(value, sub, path, report)
        if tag == "list":
            if not isinstance(value, list):
                report.add("error", "bad_type", f"{path}: expected a list, got {type(value).__name__}")
                return []
            return [_check_mapping(it, sub, f"{path}[{i}]", report) for i, it in enumerate(value)]
        report.add("error", "bad_schema", f"{path}: unknown composite kind {kind!r}")
        return value

    if kind == "any":
        return value
    if kind == "str":
        if not isinstance(value, str):
            report.add("error", "bad_type", f"{path}: expected a string, got {type(value).__name__}")
        return value
    if kind == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            report.add("error", "bad_type", f"{path}: expected an int, got {type(value).__name__}")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            report.add("error", "bad_type", f"{path}: expected a bool, got {type(value).__name__}")
        return value
    if kind == "strlist":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            report.add("error", "bad_type", f"{path}: expected a list of strings")
            return value if isinstance(value, list) else []
        return value
    if kind == "intlist":
        if not isinstance(value, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in value):
            report.add("error", "bad_type", f"{path}: expected a list of ints")
            return value if isinstance(value, list) else []
        return value
    if kind == "map":
        if not isinstance(value, dict):
            report.add("error", "bad_type", f"{path}: expected a mapping, got {type(value).__name__}")
            return {}
        return value
    if kind == "enum":
        if value not in fspec.choices:
            report.add("error", "bad_enum", f"{path}: {value!r} not in {list(fspec.choices)}")
        return value
    if kind == "protocol_methods":
        return _check_protocol_methods(value, path, report)
    report.add("error", "bad_schema", f"{path}: unknown kind {kind!r}")
    return value


def _check_protocol_methods(value: object, path: str, report: Report) -> list[dict]:
    """A `methods:` list whose entries are a bare signature string OR a {signature, notes}
    mapping. Coerce both to {signature, notes} dicts (matches the old `_coerce_protocol_methods`)."""
    if not isinstance(value, list):
        report.add("error", "bad_type", f"{path}: expected a list of methods")
        return []
    out: list[dict] = []
    for i, item in enumerate(value):
        if isinstance(item, str):
            out.append({"signature": item, "notes": None})
        elif isinstance(item, dict):
            out.append(_check_mapping(item, "ProtocolMethod", f"{path}[{i}]", report))
        else:
            report.add("error", "bad_type", f"{path}[{i}]: a method must be a string or a {{signature, notes}} mapping")
    return out


# ProtocolMethod is referenced by _check_protocol_methods; register its shape.
SCHEMAS["ProtocolMethod"] = {
    "signature": F("str"),
    "notes": F("str", required=False, default=None),
}


def _check_mapping(data: object, schema_name: str, path: str, report: Report) -> dict:
    schema = SCHEMAS[schema_name]
    if not isinstance(data, dict):
        report.add("error", "bad_type", f"{path}: expected a {schema_name} mapping, got {type(data).__name__}")
        return {}

    for key in data:
        if key not in schema:
            report.add("error", "unknown_field", f"{path}: unknown field {key!r} (not in {schema_name})")

    out: dict = {}
    for fname, fspec in schema.items():
        _p = f"{path}.{fname}" if path else fname
        if fname in data and data[fname] is not None:
            out[fname] = _check_value(data[fname], fspec, _p, report)
        elif fname in data:  # present but explicitly null
            if fspec.required:
                report.add("error", "missing_field", f"{path or '<root>'}: required field {fname!r} is null")
                out[fname] = _required_empty(fspec, _p, report)
            else:
                out[fname] = None  # null == unset for an optional field
        elif fspec.required:
            report.add("error", "missing_field", f"{path or '<root>'}: required field {fname!r} is missing")
            out[fname] = _required_empty(fspec, _p, report)
        else:
            out[fname] = _optional_default(fspec, _p, report)

    if schema_name == "Then":
        _check_then(out, path, report)
    return out


def _required_empty(fspec: F, path: str, report: Report) -> object:
    """A structurally-complete placeholder for a missing/null required field, so downstream
    graph checks never KeyError. A nested object is normalized from an empty mapping (which
    also surfaces its own missing-required fields)."""
    if isinstance(fspec.kind, tuple) and fspec.kind[0] == "obj":
        return _check_mapping({}, fspec.kind[1], path, report)
    return _empty_for(fspec.kind)


def _optional_default(fspec: F, path: str, report: Report) -> object:
    """The default for an absent optional field. A nested-object default ({}) is normalized
    through its sub-schema so its own optional lists fill in (the Manifest's domain/
    application/... containers, whose fields are all optional → no spurious errors)."""
    if isinstance(fspec.kind, tuple) and fspec.kind[0] == "obj":
        base = fspec.default if isinstance(fspec.default, dict) else {}
        return _check_mapping(copy.deepcopy(base), fspec.kind[1], path, report)
    return copy.deepcopy(fspec.default)


def _check_then(then: dict, path: str, report: Report) -> None:
    verbs = ("raises", "returns", "persists", "deletes", "logs", "calls")
    if not any(then.get(v) for v in verbs):
        report.add("error", "empty_then", f"{path}: at least one outcome verb is required")
    if then.get("with") and not then.get("persists"):
        report.add("error", "with_without_persists", f"{path}: then.with requires then.persists")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — graph integrity + local behaviour consistency (rule #11)
# ─────────────────────────────────────────────────────────────────────────────

_RESERVED_AUDIT_FIELDS = frozenset({"created_at", "updated_at"})


def _is_cross_epic(ref: str) -> bool:
    return ":" in ref


def build_cross_index(siblings: list[dict]) -> dict[tuple[str, str], set[str]]:
    """Index sibling manifests so a cross-epic ref `subdomain:Name` can be resolved (spec §7/§8,
    the cross-epic-resolution frontier). Maps (subdomain, category) -> node names for DOMAIN nodes
    (which carry a `subdomain`), and ("*", category) -> names for the subdomain-less categories
    (exceptions / settings / datastores / handlers / schemas, resolved by name alone). The `category`
    keys mirror the local valid-sets `check_ref` consults. Reads raw (un-normalized) sibling dicts
    defensively — a malformed sibling contributes nothing rather than raising."""
    idx: dict[tuple[str, str], set[str]] = {}

    def add(sub: object, category: str, name: object) -> None:
        if isinstance(sub, str) and isinstance(name, str) and name:
            idx.setdefault((sub, category), set()).add(name)

    for sm in siblings:
        if not isinstance(sm, dict):
            continue
        d = sm.get("domain") or {}
        a = sm.get("application") or {}
        infra = sm.get("infrastructure") or {}
        rest = sm.get("restapi") or {}
        for e in d.get("entities") or []:
            add(e.get("subdomain"), "entity", e.get("name"))
        for p in d.get("repository_protocols") or []:
            add(p.get("subdomain"), "repo_protocol", p.get("name"))
            add(p.get("subdomain"), "dependency", p.get("name"))
        for c in d.get("capability_protocols") or []:
            add(c.get("subdomain"), "capability", c.get("name"))
            add(c.get("subdomain"), "dependency", c.get("name"))
        for s in d.get("services") or []:
            add(s.get("subdomain"), "dependency", s.get("name"))
        for v in d.get("value_objects") or []:
            add(v.get("subdomain"), "dependency", v.get("name"))
        for en in d.get("enums") or []:
            add(en.get("subdomain"), "enum", en.get("name"))
        for x in d.get("exceptions") or []:
            add("*", "exception", x.get("name"))
        for st in infra.get("settings") or []:
            add("*", "settings", st.get("name"))
        for ds in infra.get("datastores") or []:
            add("*", "datastore", ds.get("name"))
        for h in (a.get("commands") or []) + (a.get("queries") or []):
            add("*", "handler", h.get("name"))
        for sc in rest.get("schemas") or []:
            add("*", "schema", sc.get("name"))
    return idx


def _is_uuid_type(type_str: str) -> bool:
    return type_str.split("|")[0].strip() == "UUID"


def _check_graph(m: dict, report: Report, cross_index: dict[tuple[str, str], set[str]] | None = None) -> None:
    cross = cross_index or {}
    d, a, infra, rest = m["domain"], m["application"], m["infrastructure"], m["restapi"]

    entity_names = {e["name"] for e in d["entities"]}
    repo_protocol_names = {p["name"] for p in d["repository_protocols"]}
    capability_names = {c["name"] for c in d["capability_protocols"]}
    service_names = {s["name"] for s in d["services"]}
    value_object_names = {v["name"] for v in d["value_objects"]}
    # A value object resolves as a dependency only in its tunable role — a config knob DI-wired as a
    # Singleton from settings (the domain-value-object tunable variant), injected into services /
    # handlers. Ordinary VOs (Email, a principal) are built inline and never injected. The validator
    # stays graph-only: the tunable-vs-ordinary judgment is the architect's, and the
    # <Stem>Tunable <- <Stem>Settings wiring is the conventions skill's derivation, not a naming rule
    # encoded here.
    dependency_names = repo_protocol_names | capability_names | service_names | value_object_names
    settings_names = {s["name"] for s in infra["settings"]}
    datastore_names = {ds["name"] for ds in infra["datastores"]}
    exception_names = {x["name"] for x in d["exceptions"]}
    handler_names = {c["name"] for c in a["commands"]} | {q["name"] for q in a["queries"]}
    schema_names = {s["name"] for s in rest["schemas"]}

    def check_ref(ref: str, valid: set[str], *, where: str, kind: str, category: str) -> None:
        if _is_cross_epic(ref):
            prefix, _, name = ref.partition(":")
            if name in cross.get((prefix, category), set()) or name in cross.get(("*", category), set()):
                return  # resolved against a sibling manifest
            if cross:
                # siblings were provided → a cross-epic ref that resolves to nothing is a real error
                report.add(
                    "error",
                    "unresolved_cross_epic_ref",
                    f"{where}: cross-epic {kind} {ref!r} matches no node in the sibling manifests",
                )
            else:
                # single-manifest mode (no siblings) → keep the non-blocking warning (back-compat)
                report.add(
                    "warning",
                    "cross_epic_edge",
                    f"{where}: cross-epic ref {ref!r} left unresolved (no sibling manifests provided)",
                )
            return
        if ref not in valid:
            report.add("error", "unresolved_ref", f"{where}: {kind} {ref!r} is not declared in this manifest")

    for p in d["repository_protocols"]:
        check_ref(
            p["aggregate"], entity_names, where=f"repository_protocol {p['name']}", kind="aggregate", category="entity"
        )

    for svc in d["services"]:
        for dep in svc["dependencies"]:
            check_ref(dep, dependency_names, where=f"service {svc['name']}", kind="dependency", category="dependency")
        for meth in svc["methods"]:
            for exc in meth["raises"]:
                check_ref(exc, exception_names, where=f"service {svc['name']}", kind="exception", category="exception")

    for node in (*a["commands"], *a["queries"]):
        for dep in node["handler"]["dependencies"]:
            check_ref(dep, dependency_names, where=f"handler {node['name']}", kind="dependency", category="dependency")
        for exc in node["raises"]:
            check_ref(exc, exception_names, where=f"handler {node['name']}", kind="exception", category="exception")

    for ds in infra["datastores"]:
        if ds["settings"] is not None:
            check_ref(
                ds["settings"], settings_names, where=f"datastore {ds['name']}", kind="settings", category="settings"
            )

    for r in infra["repositories"]:
        check_ref(
            r["implements"],
            repo_protocol_names,
            where=f"repository {r['implements']}",
            kind="protocol",
            category="repo_protocol",
        )
        check_ref(r["backs"], entity_names, where=f"repository {r['implements']}", kind="aggregate", category="entity")
        if r["store"] is not None:
            check_ref(
                r["store"],
                datastore_names,
                where=f"repository {r['implements']}",
                kind="datastore",
                category="datastore",
            )

    for cap in infra["capabilities"]:
        check_ref(
            cap["implements"],
            capability_names,
            where=f"capability {cap['implements']}",
            kind="capability protocol",
            category="capability",
        )
        if cap["settings"] is not None:
            check_ref(
                cap["settings"],
                settings_names,
                where=f"capability {cap['implements']}",
                kind="settings",
                category="settings",
            )

    for e in d["entities"]:
        for fld in e["fields"]:
            if fld["name"] in _RESERVED_AUDIT_FIELDS:
                report.add(
                    "error",
                    "reserved_field",
                    f"entity {e['name']}: field {fld['name']!r} is reserved for the DB-managed audit-timestamp "
                    f"convention — do not declare it on the entity (surface it read-side via a read-model if needed)",
                )

    for ep in rest["endpoints"]:
        loc = f"endpoint {ep['method']} {ep['path']}"
        check_ref(ep["handler"], handler_names, where=loc, kind="handler", category="handler")
        if ep["request"] is not None:
            check_ref(ep["request"], schema_names, where=loc, kind="request schema", category="schema")
        if ep["response"] is not None:
            check_ref(ep["response"], schema_names, where=loc, kind="response schema", category="schema")

    _check_behaviour_consistency(m, report)


def _check_behaviour_consistency(m: dict, report: Report) -> None:
    """Rule #11 (local): every `then` clause type-checks against its own node — then.raises
    ∈ node.raises, then.logs == log_event, then.calls dep ∈ dependencies."""
    for node in (*m["application"]["commands"], *m["application"]["queries"]):
        raises = set(node["raises"])
        deps = set(node["handler"]["dependencies"])
        log_event = node.get("log_event")
        for sc in node["behaviour"]:
            _check_then_against(sc, raises, deps, log_event, f"handler {node['name']}", report)

    for svc in m["domain"]["services"]:
        deps = set(svc["dependencies"])
        for meth in svc["methods"]:
            raises = set(meth["raises"])
            for sc in meth["behaviour"]:
                _check_then_against(sc, raises, deps, None, f"service {svc['name']} {meth['signature']!r}", report)


def _check_then_against(
    sc: dict, raises: set[str], deps: set[str], log_event: object, where: str, report: Report
) -> None:
    then = sc["then"]
    given = sc["given"]
    if then.get("raises") and then["raises"] not in raises:
        report.add(
            "error",
            "behaviour_contract",
            f"{where} behaviour[{given!r}]: then.raises={then['raises']!r} not in node raises {sorted(raises)}",
        )
    if then.get("logs") and log_event is not None and then["logs"] != log_event:
        report.add(
            "error",
            "behaviour_contract",
            f"{where} behaviour[{given!r}]: then.logs={then['logs']!r} != log_event {log_event!r}",
        )
    if then.get("calls"):
        dep = then["calls"].split(".", 1)[0]
        if dep not in deps:
            report.add(
                "error",
                "behaviour_contract",
                f"{where} behaviour[{given!r}]: then.calls dependency {dep!r} not in dependencies {sorted(deps)}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — loud degradation (warnings) + sources
# ─────────────────────────────────────────────────────────────────────────────


def _check_degradation(m: dict, report: Report) -> None:
    for kind, node in (
        *(("command", c) for c in m["application"]["commands"]),
        *(("query", q) for q in m["application"]["queries"]),
    ):
        if not node["behaviour"] and not node["notes"]:
            report.add(
                "warning",
                "unspecified_body",
                f"{kind} {node['name']}: no behaviour and no notes — the implementer "
                f"has no contract to fill the body from",
            )
    for svc in m["domain"]["services"]:
        if svc["notes"]:
            continue
        for meth in svc["methods"]:
            if not meth["behaviour"]:
                report.add(
                    "warning",
                    "unspecified_body",
                    f"service {svc['name']} method {meth['signature']!r}: no behaviour "
                    f"and no service notes — no contract to fill the body from",
                )

    for mw in m["restapi"]["middlewares"]:
        if not mw["config"] and not mw["notes"]:
            report.add(
                "warning",
                "unspecified_body",
                f"middleware {mw['name']}: no config and no notes — the implementer has no "
                f"contract to fill the ASGI body from",
            )

    for c in m["application"]["commands"]:
        if c["notes"] or any(not _is_uuid_type(f["type"]) for f in c["input"]):
            continue
        if any(sc["then"].get("persists") and not sc["then"].get("with") for sc in c["behaviour"]):
            report.add(
                "warning",
                "unspecified_transition",
                f"command {c['name']}: persists with no `then.with` post-state, no `notes`, and no payload input — "
                f"the state change is unspecified (the implementer would infer it from the class name). "
                f"Declare the post-state via `then.with` or describe it in `notes`.",
            )


def _all_sources(m: dict) -> set[str]:
    s: set[str] = set(m["meta"]["sources"])
    d = m["domain"]
    groups = [
        d["enums"],
        d["value_objects"],
        d["entities"],
        d["services"],
        d["filters"],
        d["repository_protocols"],
        d["capability_protocols"],
        d["exceptions"],
        m["application"]["commands"],
        m["application"]["queries"],
        m["infrastructure"]["settings"],
        m["infrastructure"]["datastores"],
        m["infrastructure"]["repositories"],
        m["infrastructure"]["capabilities"],
        m["restapi"]["schemas"],
        m["restapi"]["endpoints"],
    ]
    for group in groups:
        for artifact in group:
            s.update(artifact.get("sources", []))
    return s


def _check_sources(m: dict, uc_dir: Path, report: Report) -> None:
    for uc in sorted(_all_sources(m)):
        if not (list(uc_dir.glob(f"{uc}-*.md")) + list(uc_dir.glob(f"{uc}.md"))):
            report.add("error", "unresolved_source", f"source {uc!r} resolves to no file in {uc_dir}")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — skill-coverage gate (§16): every present artifact kind has a producer skill
# ─────────────────────────────────────────────────────────────────────────────


def _section_list(m: dict, token: str) -> list:
    """The artifact list for a `<section>.<field>` token in the normalized manifest (defaults
    fill every container, so this never KeyErrors on a covered manifest)."""
    section, field = token.split(".", 1)
    return m.get(section, {}).get(field, [])


def _check_skill_coverage(m: dict, report: Report) -> None:
    """Presence-gap gate (spec §16): a non-empty artifact kind with no `KIND_TO_SKILL` entry is a
    pre-flight stop. For a manifest that only uses today's schema this never fires (the meta-test
    pins full coverage) — it trips the day the schema grows a new artifact kind whose skill nobody
    registered, the deterministic detector that keeps the scaffolder off an uncovered manifest."""
    for token in artifact_kind_tokens():
        if token in _PROFILE_DRIVEN_KINDS:
            continue
        if _section_list(m, token) and token not in KIND_TO_SKILL:
            report.add(
                "error",
                "skill_gap",
                f"artifact kind {token!r} has no skill in the kind→skill registry (presence-gap, §16): "
                f"author the producing skill (via meta-skill-author, human-reviewed) before scaffolding",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────


def load_yaml(path: Path) -> object:
    """The ONLY third-party touch point — swap for a stdlib subset parser for true zero-dep."""
    import yaml

    return yaml.safe_load(path.read_text())


def _check_field_order(m: dict, report: Report) -> None:
    """A dataclass field without a default may not follow one WITH a default (Python raises
    `TypeError: non-default argument follows default argument` at class definition). The form check
    validates field SHAPE but not this ordering, so a structurally un-generatable entity / VO / DTO
    would pass and the scaffolder would silently reorder it — the generated order then differs from
    the manifest invisibly (F-024). Pydantic models (REST schemas, pydantic-settings) are exempt —
    field order is irrelevant there. A field 'has a default' iff its `default` is not None (the
    Python `None` literal is written `"None"`); `optional: true` alone does not grant one."""

    def check(fields: object, where: str) -> None:
        seen_default = False
        for f in fields if isinstance(fields, list) else []:
            if not isinstance(f, dict):
                continue
            has_default = f.get("default") is not None
            if seen_default and not has_default:
                report.add(
                    "error",
                    "field_order",
                    f"{where}: field {f.get('name', '?')!r} has no default but follows a defaulted "
                    f"field — an invalid @dataclass order (move every defaulted field last)",
                )
            seen_default = seen_default or has_default

    for e in _section_list(m, "domain.entities"):
        check(e.get("fields"), f"entity {e.get('name', '?')}")
    for vo in _section_list(m, "domain.value_objects"):
        check(vo.get("fields"), f"value_object {vo.get('name', '?')}")
    for fl in _section_list(m, "domain.filters"):
        check(fl.get("fields"), f"filter {fl.get('name', '?')}")
    for c in _section_list(m, "application.commands"):
        check(c.get("input"), f"command {c.get('name', '?')} input")
    for q in _section_list(m, "application.queries"):
        check(q.get("input"), f"query {q.get('name', '?')} input")
        check(q.get("result_fields"), f"query {q.get('name', '?')} result")
        for dto in q.get("result_dtos") if isinstance(q.get("result_dtos"), list) else []:
            if isinstance(dto, dict):
                check(dto.get("fields"), f"result_dto {dto.get('name', '?')}")


def validate(data: object, uc_dir: Path | None = None, siblings: list[dict] | None = None) -> Report:
    """Validate an already-parsed manifest (a plain dict). Pure stdlib — no YAML, no I/O
    except optional `sources` resolution against `uc_dir`. When `siblings` (other parsed manifests
    of the same app) are given, cross-epic refs (`subdomain:Name`) are RESOLVED against them — an
    unresolved cross-epic ref becomes an error; with no siblings it stays a non-blocking warning."""
    report = Report()
    m = _check_mapping(data, "Manifest", "", report)
    _check_graph(m, report, build_cross_index(siblings) if siblings else None)
    _check_field_order(m, report)
    _check_skill_coverage(m, report)
    _check_degradation(m, report)
    if uc_dir is not None:
        _check_sources(m, uc_dir, report)
    return report


def validate_file(path: str | Path, uc_dir: Path | None = None, sibling_paths: list[Path] | None = None) -> Report:
    siblings = [s for s in (load_yaml(p) for p in (sibling_paths or [])) if isinstance(s, dict)]
    return validate(load_yaml(Path(path)), uc_dir, siblings or None)


def _print_report(report: Report, manifest: str) -> None:
    order = {"error": 0, "question": 1, "warning": 2}
    for f in sorted(report.findings, key=lambda x: order.get(x.severity, 9)):
        print(f"  [{f.severity}] {f.code}: {f.message}")
    n_e, n_q, n_w = len(report.errors), len(report.questions), len(report.warnings)
    status = "OK" if report.ok else "FAILED"
    print(f"{manifest}: {status} — {n_e} error(s), {n_q} question(s), {n_w} warning(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an epic manifest (form + graph + loud degradation).")
    parser.add_argument("manifest", help="path to the manifest YAML")
    parser.add_argument("--uc-dir", type=Path, default=None, help="resolve `sources:` against this use-case dir")
    parser.add_argument(
        "--app",
        type=Path,
        default=None,
        help="resolve cross-epic refs against the sibling manifests under this dir (e.g. specs/epics): "
        "globs <dir>/*/manifest.yaml, excluding the target itself",
    )
    args = parser.parse_args(argv)

    sibling_paths: list[Path] | None = None
    if args.app is not None:
        target = Path(args.manifest).resolve()
        sibling_paths = [p for p in sorted(args.app.glob("*/manifest.yaml")) if p.resolve() != target]

    report = validate_file(args.manifest, args.uc_dir, sibling_paths)
    _print_report(report, args.manifest)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
