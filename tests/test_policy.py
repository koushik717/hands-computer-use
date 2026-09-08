from __future__ import annotations

import pytest

from hands.safety.engine import PolicyViolation, assert_url, redact_text, url_allowed
from hands.schema.policy import load_policy


def test_allowlist_blocks_off_host():
    policy = load_policy()
    assert url_allowed("http://127.0.0.1:8765/", policy)
    assert not url_allowed("https://evil.example/", policy)
    with pytest.raises(PolicyViolation):
        assert_url("https://evil.example/login", policy)


def test_redact_ssn_password_and_pan():
    text = "ssn 123-45-6789 password: hunter2 card 4111 1111 1111 1111"
    out = redact_text(text)
    assert "123-45-6789" not in out
    assert "hunter2" not in out
    assert "4111 1111 1111 1111" not in out
    assert "REDACTED" in out


def test_irreversible_step_blocked_on_draft():
    from hands.record.golden import lookup_regular_share
    from hands.safety.engine import PolicyViolation, assert_step
    from hands.schema.artifact import ActionType, ControlTarget, LocatorCandidate, LocatorStrategy, RiskClass, Step

    policy = load_policy()
    cap = lookup_regular_share("http://127.0.0.1:8765", policy)
    cap.approval = "draft"
    step = Step(
        id="commit",
        action=ActionType.CLICK,
        target=ControlTarget(
            description="Confirm Open Share",
            primary=LocatorCandidate(
                by=LocatorStrategy.ROLE, role="button", name="Confirm Open Share", frame="ws"
            ),
        ),
        risk=RiskClass.IRREVERSIBLE,
    )
    with pytest.raises(PolicyViolation):
        assert_step(step, cap, policy)
