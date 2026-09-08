from __future__ import annotations

from hands.agent.loop import infer_params
from hands.record.compiler import compile_capability
from hands.schema.policy import load_policy
from hands.surface.a11y import Control


def test_infer_member_id():
    assert infer_params("look up member 12345 and read the share balance") == {"member_id": "12345"}


def test_compiler_binds_typed_member_id():
    control = Control(
        ref=2,
        role="textbox",
        name="Member Number",
        value="",
        frame="ws",
        html_name="txtMemNo",
        tag="input",
    )
    cap = compile_capability(
        trace=[{"action": "type", "control": control, "text": "12345"}],
        goal="look up member 12345",
        target_url="http://127.0.0.1:8765",
        run_id="t",
        policy=load_policy(),
        parameters={"member_id": "12345"},
        outputs={},
    )
    typed = [s for s in cap.steps if s.action.value == "type"][0]
    assert typed.parameter == "member_id"
    assert typed.value is None
    dumped = cap.model_dump()
    typed_dump = next(s for s in dumped["steps"] if s["action"] == "type")
    assert typed_dump["value"] is None
