from __future__ import annotations

import pytest

from hands.record.golden import lookup_regular_share
from hands.replay.engine import replay
from hands.schema.artifact import RunStatus
from hands.schema.policy import load_policy


@pytest.mark.integration
@pytest.mark.asyncio
async def test_member_not_found_is_business_outcome(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap, {"member_id": "99999"}, start_url=core_url, evidence_dir=tmp_path / "nf"
    )
    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.outcome_code == "member_not_found"
    assert result.failure is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_permission_denied_is_business_outcome(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap, {"member_id": "00001"}, start_url=core_url, evidence_dir=tmp_path / "acl"
    )
    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.outcome_code == "permission_denied"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_member_validation(core_url: str, tmp_path):
    cap = lookup_regular_share(core_url, load_policy())
    result = await replay(
        cap, {"member_id": ""}, start_url=core_url, evidence_dir=tmp_path / "val"
    )
    # empty is still a supplied param; the field is filled with "" then Search.
    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.outcome_code == "validation_error"
