from __future__ import annotations

from hands.record.golden import lookup_regular_share
from hands.schema.artifact import Capability
from hands.schema.policy import load_policy


def test_golden_roundtrip():
    cap = lookup_regular_share("http://127.0.0.1:8765", load_policy())
    raw = cap.model_dump_json()
    again = Capability.model_validate_json(raw)
    assert again.name == "lookup_regular_share_balance"
    assert again.parameters[0].name == "member_id"
    assert again.outputs[0].name == "regular_share_balance"
    assert any(h.outcome_code == "member_not_found" for h in again.handlers)
    assert again.steps[0].parameter == "member_id"
    assert again.steps[0].value is None


def test_missing_param_rejected():
    cap = lookup_regular_share("http://127.0.0.1:8765", load_policy())
    try:
        cap.bind({})
        assert False, "expected missing param"
    except ValueError as exc:
        assert "member_id" in str(exc)


def test_json_schema_has_contract_fields():
    schema = Capability.model_json_schema()
    required = schema["required"]
    for field in ["steps", "parameters", "outputs", "checkpoint", "handlers", "policy"]:
        assert field in required
