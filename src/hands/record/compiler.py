from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from hands.surface.a11y import Control


def locators_for(control: Control, *, param_values: dict[str, str]) -> ControlTarget:
    frame = control.frame or "ws"
    name = control.name
    for pname, pval in param_values.items():
        if name == pval:
            name = "{{" + pname + "}}"
            break

    fallbacks: list[LocatorCandidate] = []
    if control.html_name:
        fallbacks.append(
            LocatorCandidate(
                by=LocatorStrategy.CSS,
                css=f"[name='{control.html_name}']",
                frame=frame,
            )
        )

    if control.role == "textbox":
        primary = LocatorCandidate(
            by=LocatorStrategy.NEAR_TEXT,
            near=control.name,
            role="textbox",
            frame=frame,
            html_name=control.html_name,
        )
        rationale = (
            "Primary: visible label in the adjacent table cell (this screen has no label-for). "
            "Fallback: vendor control name, which is stable across tenants of the same core."
        )
    elif control.role in {"button", "link", "combobox"}:
        primary = LocatorCandidate(
            by=LocatorStrategy.ROLE,
            role=control.role,
            name=name,
            frame=frame,
        )
        rationale = (
            "Primary: accessible role + name. Fallback: vendor name attribute when present."
        )
    else:
        primary = LocatorCandidate(
            by=LocatorStrategy.TEXT,
            text=name or control.text,
            frame=frame,
        )
        rationale = "Visible text; last-resort targeting."

    return ControlTarget(
        description=f"{control.role} {control.name!r}",
        primary=primary,
        fallbacks=fallbacks,
        rationale=rationale,
    )


def compile_capability(
    *,
    trace: list[dict[str, Any]],
    goal: str,
    target_url: str,
    run_id: str,
    policy: RuntimePolicy,
    parameters: dict[str, str],
    outputs: dict[str, str],
) -> Capability:
    steps: list[Step] = []
    n = 0
    compiled_outputs: list[OutputSpec] = []

    for event in trace:
        action = event.get("action")
        control: Control | None = event.get("control")
        if action in {"done", "escalate", "wait"}:
            continue
        if control is None and action != "extract":
            continue
        n += 1
        sid = f"s{n}"
        if action == "type":
            text = event.get("text") or ""
            param = None
            literal = text
            for pname, pval in parameters.items():
                if text == pval:
                    param = pname
                    literal = None
                    break
            steps.append(
                Step(
                    id=sid,
                    action=ActionType.TYPE,
                    target=locators_for(control, param_values=parameters),
                    parameter=param,
                    value=literal,
                    risk=RiskClass.SAFE,
                    wait=WaitPolicy(),
                    notes="Typed value bound to a parameter when it appeared in the goal.",
                )
            )
        elif action == "click":
            steps.append(
                Step(
                    id=sid,
                    action=ActionType.CLICK,
                    target=locators_for(control, param_values=parameters),
                    risk=RiskClass.SAFE,
                    wait=WaitPolicy(),
                )
            )
        elif action == "extract":
            target = locators_for(control, param_values=parameters) if control else _share_balance_target()
            name = event.get("extract_as") or "value"
            compiled_outputs.append(
                OutputSpec(
                    name=name,
                    type="currency",
                    description=name,
                    target=target,
                    pattern=r"\$[\d,]+\.\d{2}",
                )
            )
            steps.append(
                Step(
                    id=sid,
                    action=ActionType.EXTRACT,
                    target=target,
                    extract_as=name,
                    risk=RiskClass.SENSITIVE,
                )
            )

    if not compiled_outputs:
        compiled_outputs.append(
            OutputSpec(
                name="regular_share_balance",
                type="currency",
                description="Available balance of regular share S0000",
                target=_share_balance_target(),
                pattern=r"\$[\d,]+\.\d{2}",
            )
        )

    params = [
        Parameter(
            name=k,
            type="string",
            description=f"Value supplied per invocation ({k})",
            example="12345" if k == "member_id" else None,
            sensitive=False,
        )
        for k in parameters
    ]
    if not params:
        params = [
            Parameter(
                name="member_id",
                type="string",
                description="Membership / account base",
                example="12345",
            )
        ]

    return Capability(
        id="lookup_regular_share_balance",
        name="lookup_regular_share_balance",
        version=1,
        description=(
            "Look up a membership by member number and return the regular share (S0000) "
            "available balance. Inquiry only — no file maintenance."
        ),
        entry=EntryPoint(
            kind=SurfaceKind.WEB,
            app_family="pioneer_core",
            url=target_url,
        ),
        parameters=params,
        outputs=compiled_outputs,
        steps=steps,
        checkpoint=Checkpoint(
            description="Share inquiry screen showing the membership's share balances",
            all_of=[Witness(kind="text", value="Share Inquiry")],
        ),
        handlers=family_handlers(),
        policy=CapabilityPolicy(
            allowed_hosts=list(policy.allowed_hosts),
            allowed_actions=list(policy.allowed_actions),
            irreversible_requires="hitl",
        ),
        approval="draft",
        metadata=Metadata(
            created_at=datetime.now(timezone.utc).isoformat(),
            discovery_run_id=run_id,
            source="discovery",
        ),
    )


def _share_balance_target() -> ControlTarget:
    return ControlTarget(
        description="Regular share available balance (S0000)",
        primary=LocatorCandidate(
            by=LocatorStrategy.TABLE,
            near="S0000",
            nth=1,
            frame="ws",
        ),
        fallbacks=[
            LocatorCandidate(
                by=LocatorStrategy.NEAR_TEXT,
                near="S0000",
                role="generic",
                frame="ws",
            )
        ],
        witness=Witness(kind="text", value="Share Inquiry"),
        rationale=(
            "Target the share ID S0000, not the tenant's marketing label "
            "('Regular Share' vs 'Primary Share')."
        ),
    )
