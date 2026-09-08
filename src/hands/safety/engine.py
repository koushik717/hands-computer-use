from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from hands.schema.artifact import ActionType, Capability, RiskClass, Step
from hands.schema.policy import RuntimePolicy
from hands.schema.result import FailureDetail, RunResult
from hands.schema.artifact import RunStatus


class PolicyViolation(Exception):
    def __init__(self, message: str, *, expected: str = "allowed action", observed: str = ""):
        super().__init__(message)
        self.message = message
        self.expected = expected
        self.observed = observed or message


_HOST_RE = re.compile(r"^\[.*\]$")


def host_of(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host


def url_allowed(url: str, policy: RuntimePolicy) -> bool:
    host = host_of(url)
    if host not in policy.allowed_hosts:
        return False
    return any(url.startswith(p) for p in policy.allowed_url_prefixes)


def classify_risk(name: str | None, policy: RuntimePolicy) -> RiskClass:
    text = (name or "").lower()
    for pat in policy.judgment_name_patterns:
        if pat.lower() in text:
            return RiskClass.JUDGMENT
    for pat in policy.irreversible_name_patterns:
        if pat.lower() in text:
            return RiskClass.IRREVERSIBLE
    return RiskClass.SAFE


def assert_url(url: str, policy: RuntimePolicy) -> None:
    if not url_allowed(url, policy):
        raise PolicyViolation(
            f"url not on allowlist: {url}",
            expected=f"host in {policy.allowed_hosts}",
            observed=url,
        )


def assert_action(action: ActionType, policy: RuntimePolicy) -> None:
    if action not in policy.allowed_actions:
        raise PolicyViolation(
            f"action {action.value} is not allowed",
            expected=str([a.value for a in policy.allowed_actions]),
            observed=action.value,
        )


def assert_step(step: Step, capability: Capability, policy: RuntimePolicy) -> None:
    assert_action(step.action, policy)
    if step.risk == RiskClass.IRREVERSIBLE:
        req = capability.policy.irreversible_requires
        if req == "block":
            raise PolicyViolation(
                f"irreversible step {step.id} is blocked by capability policy",
                expected="no irreversible action",
                observed=step.id,
            )
        if req == "hitl":
            raise PolicyViolation(
                f"irreversible step {step.id} requires a human",
                expected="human control for irreversible action",
                observed=step.id,
            )
        if req == "approval" and capability.approval != "approved":
            raise PolicyViolation(
                f"irreversible step {step.id} needs an approved capability (currently {capability.approval})",
                expected="approval=approved",
                observed=capability.approval,
            )


def policy_failure(run_id: str, mode: str, exc: PolicyViolation) -> RunResult:
    return RunResult(
        status=RunStatus.BLOCKED_BY_POLICY,
        run_id=run_id,
        mode=mode,  # type: ignore[arg-type]
        failure=FailureDetail(
            expected=exc.expected,
            observed=exc.observed,
        ),
    )


def redact_value(name: str, value: Any, policy: RuntimePolicy) -> Any:
    if name.lower() in {n.lower() for n in policy.redact_parameter_names}:
        return f"[REDACTED:{name}]"
    if isinstance(value, str):
        return redact_text(value)
    return value


_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PAN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_PASSWORD = re.compile(r"(?i)(password|token|secret|ssn)\s*[:=]\s*\S+")


def redact_text(text: str) -> str:
    text = _SSN.sub("[REDACTED:ssn]", text)
    text = _PAN.sub("[REDACTED:pan]", text)
    text = _PASSWORD.sub(r"\1=[REDACTED]", text)
    return text


def redact_mapping(data: dict[str, Any], policy: RuntimePolicy) -> dict[str, Any]:
    return {k: redact_value(k, v, policy) for k, v in data.items()}
