from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hands.schema.artifact import ActionType


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePolicy(StrictModel):
    allowed_hosts: list[str]
    allowed_url_prefixes: list[str]
    allowed_actions: list[ActionType]
    denied_actions: list[str] = Field(default_factory=list)
    irreversible_name_patterns: list[str] = Field(default_factory=list)
    judgment_name_patterns: list[str] = Field(default_factory=list)
    max_steps: int = 25
    step_timeout_ms: int = 12000
    run_timeout_s: int = 120
    redact_parameter_names: list[str] = Field(default_factory=list)


def load_policy(path: Path | None = None) -> RuntimePolicy:
    if path is None:
        candidates = [
            Path.cwd() / "config" / "policy.yaml",
            Path(__file__).resolve().parents[3] / "config" / "policy.yaml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        if path is None:
            raise FileNotFoundError("config/policy.yaml not found")
    data = yaml.safe_load(path.read_text())
    data["allowed_actions"] = [ActionType(a) for a in data["allowed_actions"]]
    return RuntimePolicy.model_validate(data)
