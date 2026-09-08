from __future__ import annotations

import pytest

from hands.agent.loop import discover
from hands.agent.teacher import TeacherLLM
from hands.replay.engine import replay
from hands.schema.artifact import RunStatus
from hands.schema.policy import load_policy


@pytest.mark.integration
@pytest.mark.asyncio
async def test_teacher_discover_compiles_and_replays(core_url: str, tmp_path):
    cap, result = await discover(
        "Look up member 12345 and read their current regular share balance",
        core_url,
        evidence_dir=tmp_path / "disc",
        llm=TeacherLLM(member_id="12345"),
    )
    assert result.status == RunStatus.SUCCESS
    assert cap is not None
    assert cap.steps[0].parameter == "member_id"
    replayed = await replay(
        cap,
        {"member_id": "12345"},
        start_url=core_url,
        evidence_dir=tmp_path / "from_discovery",
    )
    assert replayed.status == RunStatus.SUCCESS
    assert replayed.outputs["regular_share_balance"] == "$4,250.17"
