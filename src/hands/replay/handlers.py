from __future__ import annotations

from fnmatch import fnmatch

from hands.schema.artifact import ActionType, Capability, Handler, RunStatus
from hands.session.session import BrowserSession
from hands.surface.a11y import Observation
from hands.surface.locators import TargetNotFound


class HandlerHit:
    def __init__(self, handler: Handler, status: RunStatus | None):
        self.handler = handler
        self.status = status


async def match_handlers(obs: Observation, handlers: list[Handler]) -> list[Handler]:
    hits = []
    for h in handlers:
        ok = True
        if h.when.text_contains and h.when.text_contains not in obs.page_text:
            ok = False
        if h.when.url_glob and not fnmatch(obs.url, h.when.url_glob):
            ok = False
        if ok and (h.when.text_contains or h.when.url_glob):
            hits.append(h)
    return hits


async def apply_handlers(
    session: BrowserSession,
    capability: Capability,
    *,
    log=None,
) -> HandlerHit | None:
    assert session.driver is not None
    obs = await session.snapshot()
    hits = await match_handlers(obs, capability.handlers)
    for h in hits:
        if h.then == "recover":
            if h.recover is None:
                continue
            try:
                await session.driver.act(ActionType.CLICK, h.recover.target, None)
            except TargetNotFound:
                continue
            if log:
                log.event("recovered", handler=h.id)
            return HandlerHit(h, None)
        if h.then == "business_outcome":
            return HandlerHit(h, RunStatus.BUSINESS_OUTCOME)
        if h.then == "escalate":
            return HandlerHit(h, RunStatus.ESCALATED)
        if h.then == "fail":
            return HandlerHit(h, RunStatus.FAILED)
    return None
