from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hands.schema.artifact import RunStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FailureDetail(StrictModel):
    step_id: str | None = None
    expected: str
    observed: str
    screenshot: str | None = None
    page_excerpt: str | None = None


class RunResult(StrictModel):
    status: RunStatus
    run_id: str
    mode: Literal["discovery", "replay"]
    capability_id: str | None = None
    outcome_code: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    recovered: list[str] = Field(default_factory=list)
    failure: FailureDetail | None = None
    escalation_id: str | None = None
    duration_ms: int = 0
    steps_executed: int = 0
    controller_at_end: str = "agent"


class AgentDecision(StrictModel):
    thought: str
    action: Literal["click", "type", "extract", "wait", "done", "escalate"]
    ref: int | None = None
    text: str | None = None
    extract_as: str | None = None
    outcome_code: str | None = None
    outputs: dict[str, str] | None = None
    reason: str
