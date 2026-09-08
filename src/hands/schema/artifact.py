"""Typed capability artifact — the product of discovery, the input to replay.

A capability is what an AI agent calls in production. It is not a model
transcript. It is a reviewable contract: parameters in, outputs out,
steps a human can read, handlers for the states the happy path never saw.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SurfaceKind(str, Enum):
    WEB = "web"
    DESKTOP = "desktop"


class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    PRESS = "press"
    DISMISS = "dismiss"
    WAIT = "wait"
    EXTRACT = "extract"


class RiskClass(str, Enum):
    SAFE = "safe"
    SENSITIVE = "sensitive"
    IRREVERSIBLE = "irreversible"
    JUDGMENT = "judgment"


class LocatorStrategy(str, Enum):
    ROLE = "role"
    NEAR_TEXT = "near_text"
    TEXT = "text"
    CSS = "css"
    TABLE = "table"


class RunStatus(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    FAILED = "failed"
    ESCALATED = "escalated"
    BLOCKED_BY_POLICY = "blocked_by_policy"


class Controller(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    NONE = "none"


class LocatorCandidate(StrictModel):
    """One way to find a control. Replay tries primary then fallbacks."""

    by: LocatorStrategy
    role: str | None = None
    name: str | None = None
    name_exact: bool = True
    text: str | None = None
    near: str | None = None
    css: str | None = None
    nth: int | None = None
    frame: str | None = Field(
        default=None,
        description="Named frame/iframe, e.g. 'ws'. Desktop drivers ignore this.",
    )
    html_name: str | None = Field(
        default=None,
        description="Vendor control name (txtMemNo). Often stable across tenants of the same core.",
    )


class Witness(StrictModel):
    """A cheap precondition. Wrong page / drift fails here, not three steps later."""

    kind: Literal["heading", "text", "url_glob", "title"]
    value: str


class ControlTarget(StrictModel):
    description: str
    primary: LocatorCandidate
    fallbacks: list[LocatorCandidate] = Field(default_factory=list)
    witness: Witness | None = None
    rationale: str = Field(
        default="",
        description="Why this targeting should survive tenant branding and modest version drift.",
    )


class WaitPolicy(StrictModel):
    appear_ms: int = 10000
    settle_ms: int = 150
    retry: int = 2


class Parameter(StrictModel):
    name: str
    type: Literal["string", "number", "currency", "enum"]
    description: str
    required: bool = True
    sensitive: bool = False
    enum: list[str] | None = None
    example: str | None = None


class OutputSpec(StrictModel):
    name: str
    type: Literal["string", "number", "currency"]
    description: str
    sensitive: bool = False
    target: ControlTarget
    pattern: str | None = Field(
        default=None,
        description="Optional regex; first group or full match becomes the output value.",
    )


class Step(StrictModel):
    id: str
    action: ActionType
    target: ControlTarget | None = None
    value: str | None = None
    parameter: str | None = Field(
        default=None,
        description="Bind this step's typed value to a parameter name. Mutually exclusive with literal value.",
    )
    extract_as: str | None = None
    risk: RiskClass = RiskClass.SAFE
    wait: WaitPolicy = Field(default_factory=WaitPolicy)
    notes: str | None = None

    @model_validator(mode="after")
    def bind_or_literal(self) -> Step:
        if self.action == ActionType.TYPE and not self.parameter and self.value is None:
            raise ValueError(f"{self.id}: type steps need a parameter binding or a literal value")
        if self.parameter and self.value is not None:
            raise ValueError(f"{self.id}: parameter and literal value cannot both be set")
        return self


class RecoverAction(StrictModel):
    action: Literal["click"] = "click"
    target: ControlTarget


class HandlerMatch(StrictModel):
    text_contains: str | None = None
    url_glob: str | None = None


class Handler(StrictModel):
    """Exceptional states live here, not in the happy-path step list.

    Interstitials that only appear on some visits must not be compiled as
    required steps — replay two would then fail when the notice is gone.
    """

    id: str
    description: str
    when: HandlerMatch
    then: Literal["business_outcome", "recover", "fail", "escalate"]
    outcome_code: str | None = None
    recover: RecoverAction | None = None
    message: str | None = None


class Checkpoint(StrictModel):
    description: str
    all_of: list[Witness]


class EntryPoint(StrictModel):
    kind: SurfaceKind = SurfaceKind.WEB
    app_family: str
    url: str | None = None
    launch: str | None = None


class CapabilityPolicy(StrictModel):
    allowed_hosts: list[str]
    allowed_actions: list[ActionType]
    irreversible_requires: Literal["approval", "hitl", "block"] = "hitl"


class Metadata(StrictModel):
    created_at: str
    discovery_run_id: str
    compiler: str = "hands/0.1"
    source: Literal["discovery", "human_amended", "authored"] = "discovery"


class TenantOverlay(StrictModel):
    """Per-institution specialization of a base capability.

    Same app_family, different branding. Overlays may replace locators;
    they may not add actions or widen policy.
    """

    tenant_id: str
    notes: str = ""
    locator_rewrites: dict[str, ControlTarget] = Field(
        default_factory=dict,
        description="step_id -> replacement target",
    )


class Capability(StrictModel):
    schema_version: str = "1.0"
    id: str
    name: str
    version: int = 1
    description: str
    entry: EntryPoint
    parameters: list[Parameter]
    outputs: list[OutputSpec]
    steps: list[Step]
    checkpoint: Checkpoint
    handlers: list[Handler]
    policy: CapabilityPolicy
    approval: Literal["draft", "approved"] = "draft"
    overlays: list[TenantOverlay] = Field(default_factory=list)
    metadata: Metadata

    def parameter_map(self) -> dict[str, Parameter]:
        return {p.name: p for p in self.parameters}

    def bind(self, inputs: dict[str, Any]) -> dict[str, Any]:
        bound: dict[str, Any] = {}
        for p in self.parameters:
            if p.required and p.name not in inputs:
                raise ValueError(f"missing required parameter {p.name}")
            if p.name in inputs:
                bound[p.name] = inputs[p.name]
        extra = set(inputs) - set(self.parameter_map())
        if extra:
            raise ValueError(f"unknown parameters: {sorted(extra)}")
        return bound
