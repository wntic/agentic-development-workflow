"""Graph validation for an epic manifest (work order §5).

Runs AFTER the Pydantic form check (`schema.py`). Where the schema checks that
each artifact is well-formed in isolation, this checks the cross-artifact graph
(MANIFEST_SCHEMA.md validation rules #2, #3, #10):

  - every reference resolves to a declared node (handler deps → protocols,
    endpoint.handler → command/query, endpoint.request/response → schema,
    node.raises → exceptions, repository/table.backs → entity);
  - reserved audit-timestamp names (created_at/updated_at) are not declared as
    domain entity fields (they belong to the DB-managed table convention);
  - every `sources:` entry resolves to a real UC file under specs/use-cases/.

Single-manifest scope (Tag): there is no prior-approved-manifest registry yet,
so every reference must resolve within this manifest. Cross-epic edges use the
`epic:Name` notation (e.g. `auth:IUserRepository`); they are recognized and
reported as warnings (they resolve against other manifests, which don't exist
yet) rather than failing as broken edges.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schema import Manifest

# Column names owned by the DB-managed audit-timestamp convention; an entity may not
# declare them as domain fields (they are not domain state).
_RESERVED_AUDIT_FIELDS = frozenset({"created_at", "updated_at"})


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "question" | "warning"
    code: str
    message: str


@dataclass
class ValidationReport:
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
        """Generation may proceed only with no errors and no open questions."""
        return not self.errors and not self.questions


def _is_cross_epic(ref: str) -> bool:
    return ":" in ref


def _is_uuid_type(type_str: str) -> bool:
    """A bare identifier field (the base of `UUID` / `UUID | None`) — i.e. carries no
    persistable payload, only a reference."""
    return type_str.split("|")[0].strip() == "UUID"


def validate_graph(manifest: Manifest, uc_dir: Path | None = None) -> ValidationReport:
    """Check the manifest graph. `uc_dir` enables `sources:` resolution when given."""
    report = ValidationReport()
    d = manifest.domain
    a = manifest.application

    entity_names = {e.name for e in d.entities}
    repo_protocol_names = {p.name for p in d.repository_protocols}
    capability_names = {c.name for c in d.capability_protocols}
    service_names = {s.name for s in d.services}
    # A handler/service dependency is satisfied by a repository protocol, a capability
    # protocol, or another domain service (all are injected ports).
    dependency_names = repo_protocol_names | capability_names | service_names
    settings_names = {s.name for s in manifest.infrastructure.settings}
    datastore_names = {ds.name for ds in manifest.infrastructure.datastores}
    # references resolve ONLY to exceptions the manifest declares — there is no hardcoded
    # standard catalog. A `raises: NotFoundError` is a broken edge unless this manifest
    # declares NotFoundError in `domain.exceptions` (the manifest is the single source of
    # truth for the error catalog, like the free-token store `kind`).
    exception_names = {x.name for x in d.exceptions}
    handler_names = {c.name for c in a.commands} | {q.name for q in a.queries}
    schema_names = {s.name for s in manifest.restapi.schemas}

    def check_ref(ref: str, valid: set[str], *, where: str, kind: str) -> None:
        if _is_cross_epic(ref):
            report.add(
                "warning",
                "cross_epic_edge",
                f"{where}: cross-epic ref {ref!r} left unresolved (no other manifests yet)",
            )
            return
        if ref not in valid:
            report.add(
                "error",
                "unresolved_ref",
                f"{where}: {kind} {ref!r} is not declared in this manifest",
            )

    for p in d.repository_protocols:
        check_ref(p.aggregate, entity_names, where=f"repository_protocol {p.name}", kind="aggregate")

    for svc in d.services:
        for dep in svc.dependencies:
            check_ref(dep, dependency_names, where=f"service {svc.name}", kind="dependency")
        for m in svc.methods:
            for exc in m.raises:
                check_ref(exc, exception_names, where=f"service {svc.name}", kind="exception")

    for node in (*a.commands, *a.queries):
        for dep in node.handler.dependencies:
            check_ref(dep, dependency_names, where=f"handler {node.name}", kind="dependency")
        for exc in node.raises:
            check_ref(exc, exception_names, where=f"handler {node.name}", kind="exception")

    # Note: there is no generate-vs-scaffold classification to police here. Every
    # handler body is a scaffold the implementer fills (spec §3); the manifest carries
    # no body/operation axis, so there is nothing for the validator to gate.

    for ds in manifest.infrastructure.datastores:
        if ds.settings is not None:
            check_ref(ds.settings, settings_names, where=f"datastore {ds.name}", kind="settings")

    for r in manifest.infrastructure.repositories:
        check_ref(r.implements, repo_protocol_names, where=f"repository {r.implements}", kind="protocol")
        check_ref(r.backs, entity_names, where=f"repository {r.implements}", kind="aggregate")
        if r.store is not None:
            check_ref(r.store, datastore_names, where=f"repository {r.implements}", kind="datastore")

    for cap in manifest.infrastructure.capabilities:
        check_ref(cap.implements, capability_names, where=f"capability {cap.implements}", kind="capability protocol")
        if cap.settings is not None:
            check_ref(cap.settings, settings_names, where=f"capability {cap.implements}", kind="settings")

    # created_at/updated_at are RESERVED for the DB-managed audit-timestamp convention
    # (the generator adds them to every aggregate table). They are never domain state, so
    # an entity may not declare them — a read that must surface/filter them does so via a
    # read-model DTO projected from the row (read-side), not a domain field.
    for e in d.entities:
        for f in e.fields:
            if f.name in _RESERVED_AUDIT_FIELDS:
                report.add(
                    "error",
                    "reserved_field",
                    f"entity {e.name}: field {f.name!r} is reserved for the DB-managed audit-timestamp "
                    f"convention — do not declare it on the entity (surface it read-side via a read-model "
                    f"if the API needs it)",
                )

    # No field-level glue cross-ref check needed: there is no `server_default`/`list_order`/
    # `archive_flag` to resolve — audit timestamps are a table convention and list
    # ordering/filtering is a body contract (behaviour + signature), not a schema field.

    for e in manifest.restapi.endpoints:
        loc = f"endpoint {e.method} {e.path}"
        check_ref(e.handler, handler_names, where=loc, kind="handler")
        if e.request is not None:
            check_ref(e.request, schema_names, where=loc, kind="request schema")
        if e.response is not None:
            check_ref(e.response, schema_names, where=loc, kind="response schema")
        # No endpoint.errors to resolve: advertised codes are derived from the handler's
        # raises (already validated above) + the auth dependency.

    _check_body_guidance(manifest, report)

    if uc_dir is not None:
        _check_sources(manifest, uc_dir, report)

    return report


def _check_body_guidance(manifest: Manifest, report: ValidationReport) -> None:
    """Loud-degradation gate: a body-bearing node the implementer must fill needs SOME
    contract to fill it from — at least one `behaviour` scenario OR prose `notes`. A node
    with neither is silently under-specified (the implementer would reconstruct the logic
    from the class name alone — the CloseTicket footgun). Surfaced as a warning so it is
    visible in review; it does not block generation (escalate locally if you prefer).

    Note: `behaviour` VERIFIES (it pins outcomes via generated tests) and `notes` GUIDES
    (prose intent); either alone clears the gate, but having only an existence-level
    `then` (e.g. bare `persists`) without `notes` still leaves a transition unspecified —
    that finer check arrives with `then.persists.with` (the VERIFY half), not here."""
    for kind, node in (
        *(("command", c) for c in manifest.application.commands),
        *(("query", q) for q in manifest.application.queries),
    ):
        if not node.behaviour and not node.notes:
            report.add(
                "warning",
                "unspecified_body",
                f"{kind} {node.name}: no behaviour and no notes — the implementer has no "
                f"contract to fill the body from (add a behaviour scenario or notes)",
            )
    for svc in manifest.domain.services:
        if svc.notes:  # service-level notes covers all its methods
            continue
        for m in svc.methods:
            if not m.behaviour:
                report.add(
                    "warning",
                    "unspecified_body",
                    f"service {svc.name} method {m.signature!r}: no behaviour and no service "
                    f"notes — the implementer has no contract to fill the body from",
                )

    # Finer degradation: a command that PERSISTS but leaves the state change unspecified.
    # The signal is "nothing explains what it writes" — no payload input (every input is a
    # UUID, i.e. only identifiers), no `then.with` post-state, and no `notes`. That is the
    # hidden-transition footgun (the original CloseTicket: input is only ticket_id, persists
    # with no with/notes → status→CLOSED lives only in the class name). A command that
    # carries payload inputs (title, …) is writing from its inputs and is NOT flagged.
    for c in manifest.application.commands:
        if c.notes or any(not _is_uuid_type(f.type) for f in c.input):
            continue
        if any(sc.then.persists and not sc.then.with_ for sc in c.behaviour):
            report.add(
                "warning",
                "unspecified_transition",
                f"command {c.name}: persists with no `then.with` post-state, no `notes`, and no payload "
                f"input — the state change is unspecified (the implementer would infer it from the class "
                f"name). Declare the post-state via `then.with` or describe it in `notes`.",
            )


def _all_sources(manifest: Manifest) -> set[str]:
    s: set[str] = set(manifest.meta.sources)
    d = manifest.domain
    groups: list[Iterable] = [
        d.enums,
        d.value_objects,
        d.entities,
        d.services,
        d.repository_protocols,
        d.capability_protocols,
        d.exceptions,
        manifest.application.commands,
        manifest.application.queries,
        manifest.infrastructure.settings,
        manifest.infrastructure.datastores,
        manifest.infrastructure.repositories,
        manifest.infrastructure.capabilities,
        manifest.restapi.schemas,
        manifest.restapi.endpoints,
    ]
    for group in groups:
        for artifact in group:
            s.update(artifact.sources)
    return s


def _check_sources(manifest: Manifest, uc_dir: Path, report: ValidationReport) -> None:
    for uc in sorted(_all_sources(manifest)):
        matches = list(uc_dir.glob(f"{uc}-*.md")) + list(uc_dir.glob(f"{uc}.md"))
        if not matches:
            report.add(
                "error",
                "unresolved_source",
                f"source {uc!r} resolves to no file in {uc_dir}",
            )


def load_and_validate(path: str | Path, uc_dir: Path | None = None) -> tuple[Manifest, ValidationReport]:
    """Parse YAML, run the Pydantic form check, then the graph check.

    Raises pydantic.ValidationError on a malformed manifest (the form gate);
    returns (manifest, report) once the form is valid.
    """
    data = yaml.safe_load(Path(path).read_text())
    manifest = Manifest.model_validate(data)
    return manifest, validate_graph(manifest, uc_dir)
