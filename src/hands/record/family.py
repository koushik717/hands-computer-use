from __future__ import annotations

from hands.schema.artifact import (
    ActionType,
    ControlTarget,
    Handler,
    HandlerMatch,
    LocatorCandidate,
    LocatorStrategy,
    RecoverAction,
    RiskClass,
)

# Vendor-stable copy from Pioneer Core. Same strings on Pioneer and Lakeside.
# Tenant chrome changes; these sentences do not.


def family_handlers() -> list[Handler]:
    continue_btn = ControlTarget(
        description="Dismiss the scheduled-maintenance notice",
        primary=LocatorCandidate(
            by=LocatorStrategy.ROLE,
            role="button",
            name="Continue to Console",
            frame="ws",
        ),
        fallbacks=[
            LocatorCandidate(
                by=LocatorStrategy.CSS,
                css="input[name='btnContinue']",
                frame="ws",
            )
        ],
        rationale="Notice is optional. It is a handler, not a required first step.",
    )
    return [
        Handler(
            id="notice",
            description="First-visit maintenance interstitial",
            when=HandlerMatch(text_contains="Scheduled maintenance window"),
            then="recover",
            recover=RecoverAction(action="click", target=continue_btn),
            message="Dismissed scheduled-maintenance notice",
        ),
        Handler(
            id="not_found",
            description="Inquiry returned no membership",
            when=HandlerMatch(text_contains="No member record matches the number entered."),
            then="business_outcome",
            outcome_code="member_not_found",
            message="No member record matches the number entered.",
        ),
        Handler(
            id="validation",
            description="Empty member number",
            when=HandlerMatch(text_contains="Member Number is required."),
            then="business_outcome",
            outcome_code="validation_error",
            message="Member Number is required.",
        ),
        Handler(
            id="denied",
            description="Teller lacks privilege to view the membership",
            when=HandlerMatch(text_contains="You do not have sufficient privileges to view this member."),
            then="business_outcome",
            outcome_code="permission_denied",
            message="You do not have sufficient privileges to view this member.",
        ),
        Handler(
            id="fraud_hold",
            description="Fraud hold is a judgment call, not a click to skip",
            when=HandlerMatch(text_contains="This member has a fraud hold."),
            then="escalate",
            outcome_code="fraud_hold",
            message="Fraud hold requires a human with hold-release authority.",
        ),
        Handler(
            id="session_expired",
            description="Do not type credentials to recover a session",
            when=HandlerMatch(text_contains="Your teller session has expired."),
            then="escalate",
            outcome_code="session_expired",
            message="Teller session expired; credentials are out of policy.",
        ),
    ]
