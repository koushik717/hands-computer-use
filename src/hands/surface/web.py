from __future__ import annotations

from playwright.async_api import Page

from hands.schema.artifact import ActionType, ControlTarget, Witness
from hands.safety.engine import PolicyViolation, assert_url
from hands.schema.policy import RuntimePolicy
from hands.surface.a11y import Observation, snapshot_page
from hands.surface.locators import TargetNotFound, parse_currency, resolve_all


class WebDriver:
    def __init__(self, page: Page, policy: RuntimePolicy):
        self.page = page
        self.policy = policy

    async def snapshot(self) -> Observation:
        return await snapshot_page(self.page)

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(full_page=True)

    async def current_url(self) -> str:
        return self.page.url

    async def goto(self, url: str) -> None:
        assert_url(url, self.policy)
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(150)

    async def _wait_witness(self, witness: Witness | None, timeout_ms: int) -> None:
        if witness is None:
            return
        if witness.kind == "url_glob":
            await self.page.wait_for_url(witness.value, timeout=timeout_ms)
            return
        if witness.kind == "title":
            await self.page.wait_for_function(
                "t => document.title.includes(t)",
                arg=witness.value,
                timeout=timeout_ms,
            )
            return
        loc = self.page.get_by_text(witness.value, exact=False)
        try:
            await loc.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            # Witness may live in the workspace iframe.
            n = await self.page.locator("iframe").count()
            last_err: Exception | None = None
            for i in range(n):
                inner = self.page.frame_locator("iframe").nth(i).get_by_text(witness.value, exact=False)
                try:
                    await inner.first.wait_for(state="visible", timeout=timeout_ms)
                    return
                except Exception as exc:
                    last_err = exc
            raise TargetNotFound(
                "witness not found",
                expected=f"{witness.kind}:{witness.value}",
                observed=self.page.url,
            ) from last_err

    async def act(self, action: ActionType, target: ControlTarget, value: str | None) -> None:
        if target.witness:
            await self._wait_witness(target.witness, 8000)
        loc = await resolve_all(self.page, target.primary, target.fallbacks)
        if action in {ActionType.CLICK, ActionType.DISMISS}:
            await loc.click()
        elif action == ActionType.TYPE:
            await loc.fill(value or "")
        elif action == ActionType.SELECT:
            await loc.select_option(label=value)
        elif action == ActionType.PRESS:
            await loc.press(value or "Enter")
        elif action == ActionType.WAIT:
            await self.page.wait_for_timeout(int(value or 300))
        elif action == ActionType.EXTRACT:
            return
        else:
            raise PolicyViolation(f"unsupported action {action}")
        await self.page.wait_for_timeout(200)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

    async def read(self, target: ControlTarget) -> str:
        if target.witness:
            await self._wait_witness(target.witness, 8000)
        loc = await resolve_all(self.page, target.primary, target.fallbacks)
        text = (await loc.inner_text()).strip()
        if not text:
            text = (await loc.text_content() or "").strip()
        money = parse_currency(text)
        return money or text
