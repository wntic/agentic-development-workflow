"""Tests for the manifest graph validator (codegen.manifest.validator)."""

from pathlib import Path

import yaml

from codegen.manifest.schema import Manifest
from codegen.manifest.validator import load_and_validate, validate_graph

_FIXTURE = Path(__file__).parent / "fixtures" / "label_manifest.yaml"
_UC_DIR = Path(__file__).parents[1] / "specs" / "use-cases"


def _manifest_from(mutate=None) -> Manifest:
    data = yaml.safe_load(_FIXTURE.read_text())
    if mutate is not None:
        mutate(data)
    return Manifest.model_validate(data)


def _command(data: dict, name: str) -> dict:
    return next(c for c in data["application"]["commands"] if c["name"] == name)


def test_label_manifest_graph_is_clean() -> None:
    _, report = load_and_validate(_FIXTURE, uc_dir=_UC_DIR)
    assert report.ok
    assert report.errors == []
    assert report.questions == []
    assert report.warnings == []


def test_unresolved_handler_dependency() -> None:
    def mutate(d: dict) -> None:
        _command(d, "DeleteLabel")["handler"]["dependencies"].append("IGhostRepository")

    report = validate_graph(_manifest_from(mutate))
    assert not report.ok
    assert any(f.code == "unresolved_ref" and "IGhostRepository" in f.message for f in report.errors)


def test_undeclared_exception_in_raises() -> None:
    # adding BoomError to a node's `raises` (it is not a declared exception)
    m = _manifest_from(lambda d: _command(d, "DeleteLabel")["raises"].append("BoomError"))
    report = validate_graph(m)
    assert any(f.code == "unresolved_ref" and "BoomError" in f.message for f in report.errors)


def test_endpoint_unknown_handler() -> None:
    def mutate(d: dict) -> None:
        d["restapi"]["endpoints"][0]["handler"] = "NopeHandler"

    report = validate_graph(_manifest_from(mutate))
    assert any(f.code == "unresolved_ref" and "NopeHandler" in f.message for f in report.errors)


def test_endpoint_unknown_response_schema() -> None:
    def mutate(d: dict) -> None:
        d["restapi"]["endpoints"][0]["response"] = "GhostResponse"

    report = validate_graph(_manifest_from(mutate))
    assert any(f.code == "unresolved_ref" and "GhostResponse" in f.message for f in report.errors)


def test_repository_backs_unknown_entity() -> None:
    # the `tables:` block is gone; a repository's `backs` is the surviving aggregate edge.
    def mutate(d: dict) -> None:
        d["infrastructure"]["repositories"][0]["backs"] = "Ghost"

    report = validate_graph(_manifest_from(mutate))
    assert any(f.code == "unresolved_ref" and "Ghost" in f.message for f in report.errors)


def test_cross_epic_edge_is_warning_not_error() -> None:
    m = _manifest_from(lambda d: _command(d, "DeleteLabel")["handler"]["dependencies"].append("auth:IUserRepository"))
    report = validate_graph(m)
    assert report.errors == []
    assert report.ok  # warnings do not block
    assert any(f.code == "cross_epic_edge" for f in report.warnings)


def test_unresolved_source() -> None:
    def mutate(d: dict) -> None:
        d["meta"]["sources"].append("UC-999")

    report = validate_graph(_manifest_from(mutate), uc_dir=_UC_DIR)
    assert any(f.code == "unresolved_source" and "UC-999" in f.message for f in report.errors)


def test_sources_not_checked_without_uc_dir() -> None:
    # graph check runs; source resolution is skipped when uc_dir is None
    m = _manifest_from(lambda d: d["meta"]["sources"].append("UC-999"))
    report = validate_graph(m, uc_dir=None)
    assert all(f.code != "unresolved_source" for f in report.findings)


def test_body_without_behaviour_or_notes_warns() -> None:
    # loud-degradation gate: a body the implementer must fill needs SOME contract.
    def mutate(d: dict) -> None:
        c = _command(d, "CreateLabel")
        c.pop("behaviour", None)
        c.pop("notes", None)

    report = validate_graph(_manifest_from(mutate))
    assert any(f.code == "unspecified_body" and "CreateLabel" in f.message for f in report.warnings)
    assert report.ok  # a warning, not a blocker


def test_notes_alone_clears_the_guidance_gate() -> None:
    # notes (the GUIDE channel) is sufficient even with no behaviour scenarios.
    def mutate(d: dict) -> None:
        c = _command(d, "CreateLabel")
        c.pop("behaviour", None)
        c["notes"] = "Mint a new label from the given name; reject a duplicate with ConflictError."

    report = validate_graph(_manifest_from(mutate))
    assert all(f.code != "unspecified_body" for f in report.findings)


def test_id_only_persists_without_with_or_notes_warns() -> None:
    # finer degradation: an id-only command that persists, with no `then.with` post-state
    # and no `notes`, hides its transition (the implementer would infer it from the name).
    def mutate(d: dict) -> None:
        a = _command(d, "ArchiveLabel")  # input is only label_id
        a["behaviour"][0]["then"] = {"persists": "Label"}  # drop the post-state `with`
        a.pop("notes", None)

    report = validate_graph(_manifest_from(mutate))
    assert any(f.code == "unspecified_transition" and "ArchiveLabel" in f.message for f in report.warnings)
    assert report.ok  # a warning, not a blocker


def test_persists_with_payload_input_is_not_flagged() -> None:
    # CreateLabel carries `name` (a payload input) → its persisted state is explained by its
    # inputs, so it is NOT a hidden-transition case.
    report = validate_graph(_manifest_from())
    assert all(not (f.code == "unspecified_transition" and "CreateLabel" in f.message) for f in report.findings)


def test_repository_store_resolves_to_declared_datastore() -> None:
    # a repository naming a declared datastore via `store` is a clean edge.
    def mutate(d: dict) -> None:
        d["infrastructure"]["datastores"] = [{"name": "main", "kind": "postgres", "sources": []}]
        d["infrastructure"]["repositories"][0]["store"] = "main"

    report = validate_graph(_manifest_from(mutate))
    assert report.ok
    assert all(f.code != "unresolved_ref" for f in report.findings)


def test_repository_store_unresolved_datastore_errors() -> None:
    # `store` pointing at no declared datastore is a broken edge.
    def mutate(d: dict) -> None:
        d["infrastructure"]["repositories"][0]["store"] = "ghoststore"

    report = validate_graph(_manifest_from(mutate))
    assert not report.ok
    assert any(f.code == "unresolved_ref" and "ghoststore" in f.message for f in report.errors)


def test_datastore_settings_unresolved_errors() -> None:
    # a datastore's `settings` must reference a declared settings class.
    def mutate(d: dict) -> None:
        d["infrastructure"]["datastores"] = [
            {"name": "vectors", "kind": "qdrant", "settings": "GhostSettings", "sources": []}
        ]

    report = validate_graph(_manifest_from(mutate))
    assert not report.ok
    assert any(f.code == "unresolved_ref" and "GhostSettings" in f.message for f in report.errors)


def test_audit_timestamp_names_are_reserved_on_entities() -> None:
    # created_at/updated_at belong to the DB-managed table audit convention; an entity
    # may not declare them as domain fields (surface them read-side via a read-model).
    def mutate(d: dict) -> None:
        d["domain"]["entities"][0]["fields"].append({"name": "created_at", "type": "datetime"})

    report = validate_graph(_manifest_from(mutate))
    assert not report.ok
    assert any(f.code == "reserved_field" and "created_at" in f.message for f in report.errors)
