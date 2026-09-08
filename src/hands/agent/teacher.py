from __future__ import annotations

from typing import Any

from hands.schema.result import AgentDecision
from hands.surface.a11y import Observation


class TeacherLLM:
    """A deterministic teacher for evals and key-less demos.

    Not a substitute for the required live-model discovery run. It exists so
    the observe→act→compile path can be exercised without a vendor key, and so
    replay tests do not depend on an LLM.
    """

    def __init__(self, member_id: str = "12345"):
        self.member_id = member_id
        self.calls = 0

    async def decide(self, *, goal: str, observation: Observation, history: list[dict[str, Any]]) -> AgentDecision:
        del goal
        self.calls += 1

        def find(*preds):
            for c in observation.controls:
                if all(p(c) for p in preds):
                    return c
            return None

        notice = find(lambda c: c.name == "Continue to Console")
        if notice:
            return AgentDecision(
                thought="Maintenance notice is in the way.",
                action="click",
                ref=notice.ref,
                reason="dismiss interstitial",
            )

        typed = any(h.get("action") == "type" for h in history)
        box = find(lambda c: c.role == "textbox" and c.html_name == "txtMemNo")
        if box and not typed:
            return AgentDecision(
                thought="Member number field is empty.",
                action="type",
                ref=box.ref,
                text=self.member_id,
                reason="type member_id",
            )

        link = find(lambda c: c.role == "link" and c.name == self.member_id)
        if link:
            return AgentDecision(
                thought="Open the membership.",
                action="click",
                ref=link.ref,
                reason="open detail",
            )

        search = find(lambda c: c.role == "button" and c.name in {"Search", "Inquire"})
        if search and typed:
            return AgentDecision(
                thought="Submit inquiry.",
                action="click",
                ref=search.ref,
                reason="search",
            )

        if "Share Inquiry" in observation.page_text:
            return AgentDecision(
                thought="Share inquiry is on screen.",
                action="done",
                outputs={},
                reason="checkpoint met; extract happens from the artifact outputs",
            )

        return AgentDecision(
            thought="Cannot proceed safely.",
            action="escalate",
            reason="teacher has no next move",
        )
