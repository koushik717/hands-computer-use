from __future__ import annotations

import pytest

from hands.record.golden import lookup_regular_share
from hands.replay.engine import replay
from hands.schema.artifact import Controller, RunStatus
from hands.schema.policy import load_policy
from hands.session.session import NotInControl


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fraud_hold_escalates_then_human_resumes(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    seen = {"lease": None}

    async def human(session):
        seen["lease"] = session.controller
        with pytest.raises(NotInControl):
            session.require(Controller.AGENT)
        ws = session.page.frame_locator("iframe[name='ws']")
        await ws.locator("input[value='continue']").click()
        await ws.get_by_text("Share Inquiry").wait_for(timeout=8000)

    result = await replay(
        cap,
        {"member_id": "77777"},
        start_url=core_url,
        evidence_dir=tmp_path / "hold",
        on_escalate=human,
    )
    assert seen["lease"] == Controller.HUMAN
    assert result.status == RunStatus.SUCCESS
    assert result.outputs["regular_share_balance"] == "$640.02"
