from __future__ import annotations

from typing import Protocol

from hands.schema.artifact import ActionType, ControlTarget
from hands.surface.a11y import Observation


class SurfaceDriver(Protocol):
    """Perception + action seam. Web is implemented; desktop would be another driver.

    Artifacts target ControlTarget, never Playwright locators. That is the
    boundary that lets replay move from a browser to an AX tree later.
    """

    async def snapshot(self) -> Observation: ...
    async def act(self, action: ActionType, target: ControlTarget, value: str | None) -> None: ...
    async def read(self, target: ControlTarget) -> str: ...
    async def screenshot(self) -> bytes: ...
    async def goto(self, url: str) -> None: ...
    async def current_url(self) -> str: ...
