from __future__ import annotations

import pytest

from hands.record.golden import lookup_regular_share
from hands.replay.engine import replay
from hands.schema.artifact import RunStatus
from hands.schema.policy import load_policy


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_success_extracts_share_balance(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap,
        {"member_id": "12345"},
        start_url=core_url,
        evidence_dir=tmp_path / "ok",
    )
    assert result.status == RunStatus.SUCCESS
    assert result.outputs["regular_share_balance"] == "$4,250.17"
    assert "notice" in result.recovered


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_does_not_use_a_model(core_url: str, tmp_path, monkeypatch):
    from hands.agent import llm as llm_mod

    def boom():
        raise AssertionError("replay must not construct an LLM")

    monkeypatch.setattr(llm_mod, "make_llm", boom)
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap, {"member_id": "12345"}, start_url=core_url, evidence_dir=tmp_path / "nollm"
    )
    assert result.status == RunStatus.SUCCESS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lakeside_tenant_reuses_artifact(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap,
        {"member_id": "12345"},
        start_url=core_url + "/?inst=lakeside",
        evidence_dir=tmp_path / "lakeside",
    )
    assert result.status == RunStatus.SUCCESS
    assert result.outputs["regular_share_balance"] == "$4,250.17"
