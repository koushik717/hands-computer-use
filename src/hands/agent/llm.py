from __future__ import annotations

import json
import os
from typing import Any, Protocol

from hands.schema.result import AgentDecision
from hands.surface.a11y import Observation

SYSTEM = """You are driving a credit-union teller inquiry console (Pioneer Core).
There is no API. You only act through the listed controls.

Rules:
- Use only refs that appear in the current observation.
- Prefer type/click. Do not invent URLs.
- After you can see the regular share (S0000) available balance, call done.
  Prefer setting outputs.regular_share_balance if you can read it; otherwise done alone is fine.
- "No member record matches..." is a legitimate business outcome, not a failure. Call done with outcome_code=member_not_found.
- "sufficient privileges" is permission_denied.
- A fraud hold must be escalated. Do not click continue on a fraud hold.
- Never type passwords or secrets.
- Stop when the goal is met.

Return a single JSON object with these fields:
  thought: string (short)
  action: one of click | type | extract | wait | done | escalate
  ref: integer control ref when acting on a control, else null
  text: string to type when action=type (NOT "value")
  extract_as: optional string
  outcome_code: optional string
  outputs: optional object
  reason: string (short)

No markdown. JSON only.
"""


def _coerce_decision(raw: dict[str, Any]) -> AgentDecision:
    data = dict(raw)
    if "text" not in data and "value" in data:
        data["text"] = data.pop("value")
    data.setdefault("thought", data.get("reason") or data.get("action") or "proceed")
    data.setdefault("reason", data.get("thought") or data.get("action") or "proceed")
    data.setdefault("action", "escalate")
    return AgentDecision.model_validate(data)


class LLM(Protocol):
    async def decide(self, *, goal: str, observation: Observation, history: list[dict[str, Any]]) -> AgentDecision: ...


class OpenAILLM:
    def __init__(self, model: str | None = None):
        from openai import AsyncOpenAI

        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        kwargs: dict[str, Any] = {}
        if os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        if os.environ.get("OPENAI_API_KEY"):
            kwargs["api_key"] = os.environ["OPENAI_API_KEY"]
        self.client = AsyncOpenAI(**kwargs)
        self.calls = 0

    async def decide(self, *, goal: str, observation: Observation, history: list[dict[str, Any]]) -> AgentDecision:
        self.calls += 1
        user = (
            f"GOAL: {goal}\n\n"
            f"OBSERVATION:\n{observation.compact()}\n\n"
            f"HISTORY: {json.dumps(history[-6:], ensure_ascii=False)}\n\n"
            "Reply with a single JSON object only."
        )
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ]
        try:
            resp = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=AgentDecision,
            )
            parsed = resp.choices[0].message.parsed
            if parsed is None:
                raise RuntimeError("empty structured response")
            return parsed
        except Exception:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
            )
            content = resp.choices[0].message.content or "{}"
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                content = content.replace("json", "", 1).strip()
            return _coerce_decision(json.loads(content))


class AnthropicLLM:
    def __init__(self, model: str | None = None):
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        self.client = anthropic.AsyncAnthropic()
        self.calls = 0

    async def decide(self, *, goal: str, observation: Observation, history: list[dict[str, Any]]) -> AgentDecision:
        self.calls += 1
        user = (
            f"GOAL: {goal}\n\n"
            f"OBSERVATION:\n{observation.compact()}\n\n"
            f"HISTORY: {json.dumps(history[-6:], ensure_ascii=False)}\n\n"
            "Reply with JSON only."
        )
        msg = await self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        return _coerce_decision(json.loads(text))


class ScriptedLLM:
    def __init__(self, decisions: list[AgentDecision]):
        self.decisions = list(decisions)
        self.calls = 0

    async def decide(self, *, goal: str, observation: Observation, history: list[dict[str, Any]]) -> AgentDecision:
        del goal, observation, history
        if self.calls >= len(self.decisions):
            return AgentDecision(
                thought="script exhausted",
                action="escalate",
                reason="no more scripted decisions",
            )
        d = self.decisions[self.calls]
        self.calls += 1
        return d


def make_llm() -> LLM:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLM()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAILLM()
    raise RuntimeError(
        "No model key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY. Replay does not need a model."
    )
