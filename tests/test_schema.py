"""Tests for the Label-slice manifest schema (codegen.manifest.schema)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from codegen.manifest.schema import Manifest

_FIXTURE = Path(__file__).parent / "fixtures" / "label_manifest.yaml"


def _load() -> dict:
    return yaml.safe_load(_FIXTURE.read_text())


def test_label_manifest_parses() -> None:
    m = Manifest.model_validate(_load())

    assert m.meta.epic == "03-labels"
    assert {c.name for c in m.application.commands} == {
        "CreateLabel",
        "UpdateLabel",
        "DeleteLabel",
        "ArchiveLabel",
        "UnarchiveLabel",
    }
    assert {q.name for q in m.application.queries} == {"GetLabel", "ListLabels"}


def test_delete_label_behaviour_is_captured() -> None:
    m = Manifest.model_validate(_load())
    delete = next(c for c in m.application.commands if c.name == "DeleteLabel")

    assert len(delete.behaviour) == 3
    assert {s.then.raises for s in delete.behaviour} == {"ConflictError", None}
    assert any(s.then.deletes == "Label" for s in delete.behaviour)


def test_arrange_and_act_round_trip() -> None:
    m = Manifest.model_validate(_load())
    delete = next(c for c in m.application.commands if c.name == "DeleteLabel")
    in_use = next(s for s in delete.behaviour if s.given == "a label with usage_count > 0")

    assert in_use.act == {"label_id": "33333333-3333-3333-3333-333333333333"}
    assert len(in_use.arrange) == 1
    seed = in_use.arrange[0]
    assert seed.entity == "Label"
    assert seed.fields["usage_count"] == 3

    create = next(c for c in m.application.commands if c.name == "CreateLabel")
    assert create.behaviour[0].act == {"name": "urgent"}
    assert create.behaviour[0].arrange == []


def test_arrange_and_act_default_empty_when_omitted() -> None:
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0].pop("arrange", None)
    create["behaviour"][0].pop("act", None)

    m = Manifest.model_validate(data)
    scenario = next(c for c in m.application.commands if c.name == "CreateLabel").behaviour[0]
    assert scenario.arrange == []
    assert scenario.act == {}


def test_then_raises_must_be_declared() -> None:
    # rule #11: then.raises must appear in the node's `raises:`.
    data = _load()
    delete = next(c for c in data["application"]["commands"] if c["name"] == "DeleteLabel")
    delete["behaviour"][0]["then"] = {"raises": "UndeclaredError"}
    with pytest.raises(ValidationError, match="not in node raises"):
        Manifest.model_validate(data)


def test_then_logs_must_match_log_event() -> None:
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0]["then"] = {"logs": "wrong_event"}
    with pytest.raises(ValidationError, match="log_event"):
        Manifest.model_validate(data)


def test_then_requires_at_least_one_verb() -> None:
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0]["then"] = {}
    with pytest.raises(ValidationError, match="at least one outcome verb"):
        Manifest.model_validate(data)


def test_unknown_then_verb_rejected() -> None:
    # extra="forbid": a typo'd outcome verb is a loud error, not silently ignored.
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0]["then"] = {"raisez": "ConflictError"}
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_then_with_post_state_parses() -> None:
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0]["then"] = {"persists": "Label", "with": {"is_archived": True}}
    m = Manifest.model_validate(data)
    then = next(c for c in m.application.commands if c.name == "CreateLabel").behaviour[0].then
    assert then.with_ == {"is_archived": True}  # the `with` alias maps to with_


def test_then_with_requires_persists() -> None:
    # `with` asserts the PERSISTED entity's post-state, so it is only valid alongside
    # `persists` — pairing it with another verb is rejected.
    data = _load()
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateLabel")
    create["behaviour"][0]["then"] = {"returns": "Label", "with": {"is_archived": True}}  # no persists
    with pytest.raises(ValidationError, match="with requires"):
        Manifest.model_validate(data)


def test_protocol_methods_accept_string_or_object() -> None:
    # bare signature strings stay terse; a method that needs a note grows a {signature, notes}.
    data = _load()
    proto = data["domain"]["repository_protocols"][0]
    proto["methods"] = [
        proto["methods"][0],  # bare string
        {"signature": "async def search(self, q: str) -> tuple[Label, ...]", "notes": "rank by usage_count"},
    ]
    m = Manifest.model_validate(data)
    methods = next(p for p in m.domain.repository_protocols if p.name == proto["name"]).methods
    assert methods[0].notes is None  # coerced from a bare string
    assert methods[1].notes == "rank by usage_count"


def test_malformed_signature_is_rejected() -> None:
    # the signature guard: a verbatim Python signature must be well-formed (shape only),
    # so a typo fails loudly at parse time instead of crashing the generator's regex.
    data = _load()
    proto = data["domain"]["repository_protocols"][0]
    proto["methods"] = ["asyc def add(self, x: int) -> None"]  # typo'd `async`
    with pytest.raises(ValidationError, match="malformed method signature"):
        Manifest.model_validate(data)


def test_signature_missing_self_is_rejected() -> None:
    data = _load()
    proto = data["domain"]["repository_protocols"][0]
    proto["methods"] = ["async def add(x: int) -> None"]  # no self
    with pytest.raises(ValidationError, match="malformed method signature"):
        Manifest.model_validate(data)


def test_invariant_field_is_optional() -> None:
    # a whole-entity / cross-field rule may report no single field.
    data = _load()
    label = next(e for e in data["domain"]["entities"] if e["name"] == "Label")
    label["invariants"] = [{"rule": "name and is_pinned are consistent", "source": "UC-03"}]
    m = Manifest.model_validate(data)
    inv = next(e for e in m.domain.entities if e.name == "Label").invariants[0]
    assert inv.field is None


def test_unmodelled_node_kind_fails_loudly() -> None:
    # `filters` is still unmodelled (extra="forbid") → a manifest using it fails loudly,
    # rather than silently dropping the node. (enums/value_objects/services/capability_
    # protocols/settings/capabilities ARE modelled now — auth no longer needs hardcoding.)
    data = _load()
    data["domain"]["filters"] = [{"name": "SomeFilter"}]
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_entity_carries_domain_state_only() -> None:
    # The entity declares domain state only. Audit timestamps (created_at/updated_at)
    # are a DB-managed table convention, NOT domain fields and NOT a manifest concern,
    # so they never appear in entity.fields. The Field model carries no glue attributes
    # (no server_default / archive_flag / list_order).
    m = Manifest.model_validate(_load())
    label = next(e for e in m.domain.entities if e.name == "Label")
    names = {f.name for f in label.fields}
    assert names == {"id", "name", "is_pinned", "is_archived", "usage_count"}
    assert "created_at" not in names and "updated_at" not in names
