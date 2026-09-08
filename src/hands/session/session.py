from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from hands.schema.artifact import Controller
from hands.schema.policy import RuntimePolicy
from hands.surface.a11y import Observation, snapshot_page
from hands.surface.web import WebDriver


class NotInControl(Exception):
    pass


@dataclass
class Intervention:
    id: str
    run_id: str
    reason: str
    step_id: str | None
    page_excerpt: str
    screenshot_path: str | None
    created_at: float
    resolved: bool = False
    human_actions: list[dict] = field(default_factory=list)


class BrowserSession:
    """One live browser that the agent and a human can take turns driving.

    Control is a lease, not a flag. The agent may not act without the lease.
    Escalation does not open a new browser — that is the whole point.
    """

    def __init__(
        self,
        policy: RuntimePolicy,
        evidence_dir: Path,
        *,
        headed: bool = False,
        run_id: str | None = None,
    ):
        self.policy = policy
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.headed = headed
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.controller = Controller.NONE
        self.intervention: Intervention | None = None
        self.resume_event = asyncio.Event()
        self._pw = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.driver: WebDriver | None = None

    async def start(self, url: str) -> None:
        from hands.safety.engine import assert_url

        assert_url(url, self.policy)
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=not self.headed)
        self.context = await self.browser.new_context(viewport={"width": 1100, "height": 800})
        self.page = await self.context.new_page()
        self.driver = WebDriver(self.page, self.policy)
        self.controller = Controller.AGENT
        await self.driver.goto(url)

    async def close(self) -> None:
        self.controller = Controller.NONE
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    def require(self, who: Controller) -> None:
        if self.controller != who:
            raise NotInControl(
                f"{who.value} is not in control; {self.controller.value} holds the lease"
            )

    async def snapshot(self) -> Observation:
        assert self.page is not None
        return await snapshot_page(self.page)

    async def screenshot_to(self, name: str) -> Path:
        assert self.driver is not None
        path = self.evidence_dir / name
        path.write_bytes(await self.driver.screenshot())
        return path

    async def click_ref(self, ref: int) -> None:
        self.require(Controller.AGENT)
        assert self.page is not None
        loc = None
        for frame in self.page.frames:
            candidate = frame.locator(f"[data-hands-ref='{ref}']")
            if await candidate.count():
                loc = candidate.first
                break
        if loc is None:
            raise RuntimeError(f"ref {ref} is not on the page")
        await loc.click()
        await self.page.wait_for_timeout(200)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

    async def type_ref(self, ref: int, text: str) -> None:
        self.require(Controller.AGENT)
        assert self.page is not None
        loc = None
        for frame in self.page.frames:
            candidate = frame.locator(f"[data-hands-ref='{ref}']")
            if await candidate.count():
                loc = candidate.first
                break
        if loc is None:
            raise RuntimeError(f"ref {ref} is not on the page")
        await loc.fill(text)
        await self.page.wait_for_timeout(100)

    async def escalate(self, *, reason: str, step_id: str | None, excerpt: str) -> Intervention:
        shot = await self.screenshot_to(f"escalation-{self.run_id}.png")
        ticket = Intervention(
            id=uuid.uuid4().hex[:10],
            run_id=self.run_id,
            reason=reason,
            step_id=step_id,
            page_excerpt=excerpt[:1500],
            screenshot_path=str(shot),
            created_at=time.time(),
        )
        self.intervention = ticket
        self.controller = Controller.HUMAN
        self.resume_event.clear()
        await self._arm_human_recorder()
        return ticket

    async def wait_for_resume(self, timeout_s: float | None = None) -> None:
        if timeout_s is None:
            await self.resume_event.wait()
        else:
            await asyncio.wait_for(self.resume_event.wait(), timeout=timeout_s)

    async def resume(self) -> list[dict]:
        actions = await self._collect_human_actions()
        if self.intervention:
            self.intervention.resolved = True
            self.intervention.human_actions = actions
        self.controller = Controller.AGENT
        self.resume_event.set()
        return actions

    async def _arm_human_recorder(self) -> None:
        assert self.page is not None
        script = """
        () => {
          window.__handsHuman = [];
          const rec = (type, el) => {
            const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : {};
            window.__handsHuman.push({
              type,
              tag: el && el.tagName,
              name: el && (el.getAttribute('name') || el.innerText || el.value || ''),
              value: el && el.value,
              t: Date.now(),
              x: r.x, y: r.y,
            });
          };
          document.addEventListener('click', (e) => rec('click', e.target), true);
          document.addEventListener('change', (e) => rec('change', e.target), true);
          for (const f of Array.from(document.querySelectorAll('iframe'))) {
            try {
              const d = f.contentDocument;
              if (!d) continue;
              d.addEventListener('click', (e) => rec('click', e.target), true);
              d.addEventListener('change', (e) => rec('change', e.target), true);
            } catch (err) {}
          }
        }
        """
        await self.page.evaluate(script)
        for frame in self.page.frames:
            try:
                await frame.evaluate(script)
            except Exception:
                pass

    async def _collect_human_actions(self) -> list[dict]:
        assert self.page is not None
        actions: list[dict] = []
        for frame in self.page.frames:
            try:
                chunk = await frame.evaluate("() => window.__handsHuman || []")
                actions.extend(chunk or [])
            except Exception:
                continue
        return actions
