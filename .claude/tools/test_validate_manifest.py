"""Tests for the stdlib manifest validator (.claude/tools/validate_manifest.py).

Lives next to the validator. Run it explicitly (it is outside the default `tests/` path):

    uv run pytest .claude/tools/test_validate_manifest.py

Mirrors the key graph/degradation/sources cases of the old codegen graph-validator test
suite, plus the FORM checks the old design delegated to Pydantic (unknown/missing/enum/then).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_manifest as vm

_FIXTURES = Path(__file__).resolve().parent / "fixtures"  # manifests live next to the tool
_FIXTURE = _FIXTURES / "label_manifest.yaml"
_HELPDESK = _FIXTURES / "helpdesk_manifest.yaml"
_VECTOR_RAG = _FIXTURES / "vector_rag_manifest.yaml"
# `sources:` resolution (--uc-dir) is exercised against a tmp_path mock — the tool stores no UCs;
# at pipeline time the runner points --uc-dir at the consuming project's specs/use-cases.


def _data(mutate=None) -> dict:
    data = vm.load_yaml(_FIXTURE)
    if mutate is not None:
        mutate(data)
    return data


def _command(data: dict, name: str) -> dict:
    return next(c for c in data["application"]["commands"] if c["name"] == name)


def _has(report: vm.Report, code: str, needle: str | None = None) -> bool:
    return any(f.code == code and (needle is None or needle in f.message) for f in report.findings)


# ── clean: the real fixtures validate with no errors/questions ──────────────────


def test_helpdesk_is_clean() -> None:
    assert vm.validate_file(_HELPDESK).ok


def test_vector_rag_is_clean() -> None:
    assert vm.validate_file(_VECTOR_RAG).ok


def test_label_fixture_is_clean() -> None:
    report = vm.validate_file(_FIXTURE)
    assert report.ok
    assert report.errors == []
    assert report.warnings == []


# ── graph integrity (rule #2) ──────────────────────────────────────────────────


def test_unresolved_handler_dependency() -> None:
    report = vm.validate(
        _data(lambda d: _command(d, "DeleteLabel")["handler"]["dependencies"].append("IGhostRepository"))
    )
    assert not report.ok
    assert _has(report, "unresolved_ref", "IGhostRepository")


def test_undeclared_exception_in_raises() -> None:
    report = vm.validate(_data(lambda d: _command(d, "DeleteLabel")["raises"].append("BoomError")))
    assert _has(report, "unresolved_ref", "BoomError")


def test_endpoint_unknown_handler() -> None:
    report = vm.validate(_data(lambda d: d["restapi"]["endpoints"][0].update({"handler": "NopeHandler"})))
    assert _has(report, "unresolved_ref", "NopeHandler")


def test_endpoint_unknown_response_schema() -> None:
    report = vm.validate(_data(lambda d: d["restapi"]["endpoints"][0].update({"response": "GhostResponse"})))
    assert _has(report, "unresolved_ref", "GhostResponse")


def test_repository_backs_unknown_entity() -> None:
    report = vm.validate(_data(lambda d: d["infrastructure"]["repositories"][0].update({"backs": "Ghost"})))
    assert _has(report, "unresolved_ref", "Ghost")


def test_repository_store_unresolved_datastore() -> None:
    report = vm.validate(_data(lambda d: d["infrastructure"]["repositories"][0].update({"store": "ghoststore"})))
    assert not report.ok
    assert _has(report, "unresolved_ref", "ghoststore")


def test_datastore_settings_unresolved() -> None:
    def mutate(d: dict) -> None:
        d["infrastructure"]["datastores"] = [
            {"name": "vectors", "kind": "qdrant", "settings": "GhostSettings", "sources": []}
        ]

    report = vm.validate(_data(mutate))
    assert _has(report, "unresolved_ref", "GhostSettings")


def test_cross_epic_edge_is_warning_not_error() -> None:
    report = vm.validate(
        _data(lambda d: _command(d, "DeleteLabel")["handler"]["dependencies"].append("auth:IUserRepository"))
    )
    assert report.ok  # warnings do not block
    assert _has(report, "cross_epic_edge")


def test_reserved_audit_field_on_entity() -> None:
    report = vm.validate(
        _data(lambda d: d["domain"]["entities"][0]["fields"].append({"name": "created_at", "type": "datetime"}))
    )
    assert not report.ok
    assert _has(report, "reserved_field", "created_at")


# ── local behaviour consistency (rule #11) ──────────────────────────────────────


def test_then_raises_not_in_node_raises() -> None:
    report = vm.validate(
        _data(lambda d: _command(d, "CreateLabel")["behaviour"][0].__setitem__("then", {"raises": "Nope"}))
    )
    assert _has(report, "behaviour_contract", "Nope")


# ── form checks (extra=forbid, required, enums, then) ───────────────────────────


def test_unknown_field_rejected() -> None:
    report = vm.validate(_data(lambda d: _command(d, "DeleteLabel").update({"bogus": 1})))
    assert _has(report, "unknown_field", "bogus")


def test_missing_required_field() -> None:
    report = vm.validate(_data(lambda d: _command(d, "DeleteLabel").pop("output")))
    assert _has(report, "missing_field", "output")


def test_bad_enum_value() -> None:
    report = vm.validate(_data(lambda d: d["restapi"]["endpoints"][0].update({"method": "FETCH"})))
    assert _has(report, "bad_enum")


def test_then_with_no_verb() -> None:
    report = vm.validate(_data(lambda d: _command(d, "CreateLabel")["behaviour"][0].__setitem__("then", {})))
    assert _has(report, "empty_then")


def test_with_requires_persists() -> None:
    report = vm.validate(
        _data(
            lambda d: _command(d, "CreateLabel")["behaviour"][0].__setitem__(
                "then", {"returns": "None", "with": {"x": "y"}}
            )
        )
    )
    assert _has(report, "with_without_persists")


def test_protocol_method_extra_key_rejected() -> None:
    def mutate(d: dict) -> None:
        d["domain"]["repository_protocols"][0]["methods"].append({"signature": "async def x(self) -> None", "bogus": 1})

    report = vm.validate(_data(mutate))
    assert _has(report, "unknown_field", "bogus")


# ── loud degradation (warnings, non-blocking) ───────────────────────────────────


def test_body_without_behaviour_or_notes_warns() -> None:
    def mutate(d: dict) -> None:
        c = _command(d, "CreateLabel")
        c.pop("behaviour", None)
        c.pop("notes", None)

    report = vm.validate(_data(mutate))
    assert report.ok  # a warning, not a blocker
    assert _has(report, "unspecified_body", "CreateLabel")


def test_notes_alone_clears_the_guidance_gate() -> None:
    def mutate(d: dict) -> None:
        c = _command(d, "CreateLabel")
        c.pop("behaviour", None)
        c["notes"] = "Mint a new label; reject a duplicate with ConflictError."

    report = vm.validate(_data(mutate))
    assert not _has(report, "unspecified_body")


def test_id_only_persists_without_with_or_notes_warns() -> None:
    def mutate(d: dict) -> None:
        a = _command(d, "ArchiveLabel")  # input is only label_id
        a["behaviour"][0]["then"] = {"persists": "Label"}  # drop the post-state `with`
        a.pop("notes", None)

    report = vm.validate(_data(mutate))
    assert report.ok
    assert _has(report, "unspecified_transition", "ArchiveLabel")


# ── skill-coverage gate (§16) ────────────────────────────────────────────────────


def test_registry_covers_every_schema_artifact_kind() -> None:
    """The "done when" guarantee: every artifact kind the schema can parse maps to a producer
    skill (minus the documented store-profile-driven exemption). A new SCHEMAS list-field with no
    KIND_TO_SKILL entry fails here, before it could ever reach an uncovered scaffolder."""
    universe = set(vm.artifact_kind_tokens())
    expected = universe - vm._PROFILE_DRIVEN_KINDS
    assert set(vm.KIND_TO_SKILL) == expected, set(vm.KIND_TO_SKILL).symmetric_difference(expected)
    assert universe >= vm._PROFILE_DRIVEN_KINDS  # the exemption names a real schema kind


def test_helpdesk_passes_the_coverage_gate() -> None:
    report = vm.validate_file(_HELPDESK)
    assert not _has(report, "skill_gap")


def test_unmapped_artifact_kind_is_a_skill_gap(monkeypatch) -> None:
    """Drop a producer mapping → a manifest that uses that kind trips the presence-gap stop."""
    patched = dict(vm.KIND_TO_SKILL)
    patched.pop("domain.entities")
    monkeypatch.setattr(vm, "KIND_TO_SKILL", patched)
    report = vm.validate_file(_HELPDESK)  # Helpdesk declares entities
    assert not report.ok
    assert _has(report, "skill_gap", "domain.entities")


def test_datastore_kind_is_exempt_from_the_gate() -> None:
    """A free-token datastore never trips the gate — it is store-profile-driven, not skill-mapped."""
    report = vm.validate_file(_VECTOR_RAG)  # declares a qdrant datastore
    assert not _has(report, "skill_gap")


# ── bidirectional coverage: every skill dir is classified (§16, reverse direction) ─────────
#
# The forward gate above guarantees every artifact KIND has a producer skill. This is the REVERSE:
# every skill DIRECTORY is classified into exactly the registry-B taxonomy of the `conventions`
# skill — producer (a value of KIND_TO_SKILL), companion, test, bootstrap, reference, or meta. A
# producing skill that maps to no manifest kind (the orphan `pattern-unit-of-work` was exactly
# this) can no longer hide; adding a skill forces a classification decision here. These four sets
# mirror registry-B prose the way KIND_TO_SKILL mirrors the producer table — keep them in lockstep.

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

_COMPANION_SKILLS = frozenset(
    {
        "infra-di-provider",  # wires each producer's class into containers.py
        "infra-sqlalchemy-table",  # write-once Table scaffold, triggered by a relational repository
        "pattern-compensating-tx",
        "pattern-unit-of-work",
        "restapi-auth-dependency",
        "restapi-error-responses",
        "restapi-file-transfer",
    }
)
_TEST_SKILLS = frozenset(
    {
        "test-application-handler",
        "test-domain-entity",
        "test-domain-enum",
        "test-domain-service",
        "test-domain-value-object",
        "test-fake-repository",
        "test-infra-capability-adapter",
        "test-repository-contract",
        "test-restapi-endpoint",
    }
)
_BOOTSTRAP_SKILLS = frozenset(
    {
        "restapi-app-bootstrap",
        "test-integration-isolation",
        "test-integration-authed-client",
        "test-discovery-invariants",
    }
)
_REFERENCE_SKILLS = frozenset(
    {
        "conventions",
        "general-typing-conventions",
        "general-imports-conventions",
        "general-python-package",
        "general-layered-architecture",
        "general-logging",
        "test-principles",
    }
)
_META_SKILLS = frozenset({"meta-skill-author", "meta-uc-author"})


def test_template_is_in_sync() -> None:
    """Anti-rot (R4): the committed manifest.template.yaml must equal a fresh generation from
    SCHEMAS. The template has no independent source of truth — it is emitted, not hand-edited — so
    it cannot drift (the exact failure the audit found: a hand-maintained template still carrying
    `tables:`/`subpackage:`/`alembic:` fields the validator had long dropped). Regenerate with
    `uv run .claude/tools/gen_template.py` when SCHEMAS changes."""
    import gen_template

    assert gen_template._TEMPLATE.read_text() == gen_template.render(), (
        "manifest.template.yaml is stale — regenerate: uv run .claude/tools/gen_template.py"
    )


def test_every_skill_is_classified() -> None:
    """Reverse §16 gate: the taxonomy union must EXACTLY equal the skill dirs on disk — an
    uncovered dir is an unclassified (orphan) skill; a classified name with no dir is stale.
    `domain-exception` is both a producer (domain.exceptions) and a bootstrap skill; it is listed
    once, under producers — coverage needs each dir in at least one bucket, not exactly one."""
    dirs = {p.name for p in _SKILLS_DIR.iterdir() if p.is_dir()}
    producers = set(vm.KIND_TO_SKILL.values())
    classified = producers | _COMPANION_SKILLS | _TEST_SKILLS | _BOOTSTRAP_SKILLS | _REFERENCE_SKILLS | _META_SKILLS
    orphans = dirs - classified
    stale = classified - dirs
    assert not orphans, f"unclassified skill dirs (classify in conventions registry B): {sorted(orphans)}"
    assert not stale, f"classified skill names with no directory (stale/typo): {sorted(stale)}"


# ── domain.filters (first-class declarative section) ─────────────────────────────


def test_domain_filter_section_validates() -> None:
    def mutate(d: dict) -> None:
        d["domain"]["filters"] = [
            {
                "name": "LabelFilter",
                "subdomain": "labels",
                "fields": [{"name": "name_contains", "type": "str | None", "default": "None"}],
                "pagination": True,
                "sort": {"enum_name": "LabelSortKey", "keys": ["NAME_ASC"], "default": "NAME_ASC"},
                "sources": [],
            }
        ]

    report = vm.validate(_data(mutate))
    assert report.ok, [f.message for f in report.errors + report.questions]
    assert "domain.filters" in vm.KIND_TO_SKILL  # covered by the gate


def test_domain_filter_missing_name_is_flagged() -> None:
    def mutate(d: dict) -> None:
        d["domain"]["filters"] = [{"subdomain": "labels", "fields": [], "sources": []}]  # no name

    report = vm.validate(_data(mutate))
    assert _has(report, "missing_field", "name")


# ── restapi.middlewares (entrypoint cross-cutting section) ───────────────────────


def test_restapi_middleware_section_validates() -> None:
    def mutate(d: dict) -> None:
        d.setdefault("restapi", {})["middlewares"] = [
            {
                "name": "RequestId",
                "config": {"header": "X-Request-ID"},
                "notes": "bind the request id into structlog contextvars",
                "sources": [],
            },
            {
                "name": "MaxRequestSize",
                "config": {"max_bytes": 10485760},
                "introduces_http": [413],
                "notes": "reject bodies over max_bytes with a 413 before the route runs",
                "sources": [],
            },
        ]

    report = vm.validate(_data(mutate))
    assert report.ok, [f.message for f in report.errors + report.questions]
    assert "restapi.middlewares" in vm.KIND_TO_SKILL  # covered by the gate


def test_middleware_introduces_http_must_be_ints() -> None:
    def mutate(d: dict) -> None:
        d.setdefault("restapi", {})["middlewares"] = [
            {"name": "MaxRequestSize", "introduces_http": ["413"], "sources": []}  # strings, not ints
        ]

    report = vm.validate(_data(mutate))
    assert _has(report, "bad_type", "introduces_http")


def test_middleware_missing_name_is_flagged() -> None:
    def mutate(d: dict) -> None:
        d.setdefault("restapi", {})["middlewares"] = [{"config": {}, "sources": []}]  # no name

    report = vm.validate(_data(mutate))
    assert _has(report, "missing_field", "name")


def test_middleware_unknown_field_rejected() -> None:
    def mutate(d: dict) -> None:
        d.setdefault("restapi", {})["middlewares"] = [{"name": "RequestId", "sources": [], "bogus": "nope"}]

    report = vm.validate(_data(mutate))
    assert _has(report, "unknown_field", "bogus")


def test_middleware_without_config_or_notes_warns() -> None:
    """A middleware is body-bearing (the ASGI __call__); with neither config nor notes the
    implementer has no contract — a loud-degradation warning, not a hard error."""

    def mutate(d: dict) -> None:
        d.setdefault("restapi", {})["middlewares"] = [{"name": "BareMiddleware", "sources": []}]

    report = vm.validate(_data(mutate))
    assert report.ok  # warning, not error
    assert _has(report, "unspecified_body", "BareMiddleware")


# ── sources resolution ──────────────────────────────────────────────────────────


def _minimal_manifest(sources: list[str]) -> dict:
    return {"meta": {"epic": "demo", "name": "demo", "sources": sources}}


def test_unresolved_source(tmp_path: Path) -> None:
    report = vm.validate(_minimal_manifest(["UC-999"]), uc_dir=tmp_path)
    assert _has(report, "unresolved_source", "UC-999")


def test_source_resolves_to_mock_uc(tmp_path: Path) -> None:
    (tmp_path / "UC-001-demo.md").write_text("# mock UC")
    report = vm.validate(_minimal_manifest(["UC-001"]), uc_dir=tmp_path)
    assert not _has(report, "unresolved_source")


def test_sources_not_checked_without_uc_dir() -> None:
    report = vm.validate(_minimal_manifest(["UC-999"]), uc_dir=None)
    assert not _has(report, "unresolved_source")
