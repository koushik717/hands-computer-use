from __future__ import annotations

from datetime import datetime, timezone

from hands.record.compiler import _share_balance_target
from hands.record.family import family_handlers
from hands.schema.artifact import (
    ActionType,
    Capability,
    CapabilityPolicy,
    Checkpoint,
    ControlTarget,
    EntryPoint,
    LocatorCandidate,
    LocatorStrategy,
    Metadata,
    OutputSpec,
    Parameter,
    RiskClass,
    Step,
    SurfaceKind,
    WaitPolicy,
    Witness,
)
from hands.schema.policy import RuntimePolicy


def lookup_regular_share(url: str, policy: RuntimePolicy) -> Capability:
    member_field = ControlTarget(
        description="Member number field on inquiry (no label-for; adjacent table text)",
        primary=LocatorCandidate(
            by=LocatorStrategy.NEAR_TEXT,
            near="Member Number",
            role="textbox",
            frame="ws",
            html_name="txtMemNo",
        ),
        fallbacks=[
            LocatorCandidate(
                by=LocatorStrategy.NEAR_TEXT,
                near="Acct Base",
                role="textbox",
                frame="ws",
                html_name="txtMemNo",
            ),
            LocatorCandidate(
                by=LocatorStrategy.CSS,
                css="input[name='txtMemNo']",
                frame="ws",
            ),
        ],
        witness=Witness(kind="text", value="Member Inquiry"),
        rationale=(
            "Primary: visible label used by Pioneer. Fallback near-text is the Lakeside "
            "tenant label. Last fallback is the vendor field name txtMemNo, which both "
            "tenants share."
        ),
    )
    search_btn = ControlTarget(
        description="Inquiry submit",
        primary=LocatorCandidate(
            by=LocatorStrategy.ROLE, role="button", name="Search", frame="ws"
        ),
        fallbacks=[
            LocatorCandidate(
                by=LocatorStrategy.ROLE, role="button", name="Inquire", frame="ws"
            ),
            LocatorCandidate(
                by=LocatorStrategy.CSS, css="input[name='btnInq']", frame="ws"
            ),
        ],
        rationale="Role+name for the Pioneer label; vendor name btnInq is tenant-stable.",
    )
    member_link = ControlTarget(
        description="Result row for this membership",
        primary=LocatorCandidate(
            by=LocatorStrategy.ROLE, role="link", name="{{member_id}}", frame="ws"
        ),
        fallbacks=[
            LocatorCandidate(
                by=LocatorStrategy.CSS,
                css="a[href*='id={{member_id}}']",
                frame="ws",
            )
        ],
        rationale="The result link text is the member number. Interpolated at replay time.",
    )
    return Capability(
        id="lookup_regular_share_balance",
        name="lookup_regular_share_balance",
        version=1,
        description=(
            "Look up a membership by member number and return the regular share (S0000) "
            "available balance. Inquiry only."
        ),
        entry=EntryPoint(kind=SurfaceKind.WEB, app_family="pioneer_core", url=url),
        parameters=[
            Parameter(
                name="member_id",
                type="string",
                description="Membership / account base",
                example="12345",
            )
        ],
        outputs=[
            OutputSpec(
                name="regular_share_balance",
                type="currency",
                description="Available balance of regular share S0000",
                target=_share_balance_target(),
                pattern=r"\$[\d,]+\.\d{2}",
            )
        ],
        steps=[
            Step(
                id="s1",
                action=ActionType.TYPE,
                target=member_field,
                parameter="member_id",
                risk=RiskClass.SAFE,
                wait=WaitPolicy(),
            ),
            Step(
                id="s2",
                action=ActionType.CLICK,
                target=search_btn,
                risk=RiskClass.SAFE,
            ),
            Step(
                id="s3",
                action=ActionType.CLICK,
                target=member_link,
                risk=RiskClass.SAFE,
            ),
            Step(
                id="s4",
                action=ActionType.EXTRACT,
                target=_share_balance_target(),
                extract_as="regular_share_balance",
                risk=RiskClass.SENSITIVE,
            ),
        ],
        checkpoint=Checkpoint(
            description="Share inquiry screen is showing",
            all_of=[Witness(kind="text", value="Share Inquiry")],
        ),
        handlers=family_handlers(),
        policy=CapabilityPolicy(
            allowed_hosts=list(policy.allowed_hosts),
            allowed_actions=list(policy.allowed_actions),
            irreversible_requires="hitl",
        ),
        approval="approved",
        metadata=Metadata(
            created_at=datetime.now(timezone.utc).isoformat(),
            discovery_run_id="authored-golden",
            source="authored",
        ),
    )
