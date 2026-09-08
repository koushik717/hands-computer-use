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


def test_redact_ssn_and_password():
    text = "ssn 123-45-6789 password: hunter2"
    out = redact_text(text)
    assert "123-45-6789" not in out
    assert "hunter2" not in out
    assert "REDACTED" in out
