from __future__ import annotations

from typing import Any

from hands.schema.artifact import ControlTarget, LocatorCandidate, Witness


def subst(value: str | None, inputs: dict[str, Any]) -> str | None:
    if value is None:
        return None
    out = value
    for k, v in inputs.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def bind_candidate(c: LocatorCandidate, inputs: dict[str, Any]) -> LocatorCandidate:
    return c.model_copy(
        update={
            "name": subst(c.name, inputs),
            "text": subst(c.text, inputs),
            "near": subst(c.near, inputs),
            "css": subst(c.css, inputs),
        }
    )


def bind_target(target: ControlTarget, inputs: dict[str, Any]) -> ControlTarget:
    witness = None
    if target.witness:
        witness = target.witness.model_copy(
            update={"value": subst(target.witness.value, inputs) or target.witness.value}
        )
    return target.model_copy(
        update={
            "primary": bind_candidate(target.primary, inputs),
            "fallbacks": [bind_candidate(f, inputs) for f in target.fallbacks],
            "witness": witness,
        }
    )
