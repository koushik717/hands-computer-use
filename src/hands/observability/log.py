from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hands.safety.engine import redact_text
from hands.schema.policy import RuntimePolicy


class RunLog:
    def __init__(self, path: Path, policy: RuntimePolicy):
        self.path = path
        self.policy = policy
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()

    def event(self, kind: str, **payload: Any) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **_redact(payload, self.policy),
        }
        with self.path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _redact(payload: dict[str, Any], policy: RuntimePolicy) -> dict[str, Any]:
    out: dict[str, Any] = {}
    sensitive = {n.lower() for n in policy.redact_parameter_names}
    for k, v in payload.items():
        if k.lower() in sensitive:
            out[k] = f"[REDACTED:{k}]"
        elif isinstance(v, str):
            out[k] = redact_text(v)
        elif isinstance(v, dict):
            out[k] = _redact(v, policy)
        else:
            out[k] = v
    return out
