from __future__ import annotations

import re

from playwright.async_api import FrameLocator, Locator, Page

from hands.schema.artifact import LocatorCandidate, LocatorStrategy
from hands.surface.a11y import frame_scope


class TargetNotFound(Exception):
    def __init__(self, message: str, *, expected: str, observed: str):
        super().__init__(message)
        self.expected = expected
        self.observed = observed


def _candidate_label(c: LocatorCandidate) -> str:
    if c.by == LocatorStrategy.ROLE:
        return f"role={c.role} name={c.name!r}"
    if c.by == LocatorStrategy.NEAR_TEXT:
        return f"near={c.near!r} role={c.role}"
    if c.by == LocatorStrategy.TEXT:
        return f"text={c.text!r}"
    if c.by == LocatorStrategy.CSS:
        return f"css={c.css}"
    if c.by == LocatorStrategy.TABLE:
        return f"table near={c.near!r}"
    return c.by.value


def _build(scope: Page | FrameLocator, c: LocatorCandidate) -> Locator:
    if c.by == LocatorStrategy.ROLE:
        kwargs: dict = {"name": c.name} if c.name else {}
        if c.name is not None:
            kwargs["exact"] = c.name_exact
        loc = scope.get_by_role(c.role or "generic", **kwargs)
    elif c.by == LocatorStrategy.NEAR_TEXT:
        row = scope.locator("tr, fieldset, form, table, div, p").filter(has_text=c.near or "")
        if c.role == "textbox":
            loc = row.locator("input[type='text'], input:not([type]), textarea").first
        elif c.role == "button":
            loc = row.get_by_role("button")
        elif c.role == "combobox":
            loc = row.get_by_role("combobox")
        else:
            loc = row.locator("input, button, select, a").first
    elif c.by == LocatorStrategy.TEXT:
        loc = scope.get_by_text(c.text or "", exact=True)
    elif c.by == LocatorStrategy.CSS:
        loc = scope.locator(c.css or "body")
    elif c.by == LocatorStrategy.TABLE:
        loc = scope.locator("tr").filter(has_text=c.near or "").locator("td").nth(c.nth or 1)
    else:
        raise TargetNotFound(
            "unknown locator strategy",
            expected=_candidate_label(c),
            observed=c.by.value,
        )
    if c.html_name and c.by == LocatorStrategy.CSS and not c.css:
        loc = scope.locator(f"[name='{c.html_name}']")
    if c.nth is not None and c.by not in {LocatorStrategy.TABLE}:
        loc = loc.nth(c.nth)
    return loc


async def _visible_count(loc: Locator) -> int:
    try:
        return await loc.count()
    except Exception:
        return 0


async def resolve_candidate(page: Page, c: LocatorCandidate) -> Locator | None:
    """Resolve exactly as declared. Vendor html_name is a fallback candidate, not a short-circuit."""
    scopes: list[Page | FrameLocator] = []
    if c.frame:
        scopes.append(frame_scope(page, c.frame))
    else:
        scopes.append(page)
        n = await page.locator("iframe").count()
        for i in range(n):
            scopes.append(page.frame_locator("iframe").nth(i))

    for scope in scopes:
        loc = _build(scope, c)
        count = await _visible_count(loc)
        if count == 1:
            return loc
        if count > 1:
            first = loc.first
            try:
                if await first.is_visible():
                    return first
            except Exception:
                continue
    return None


async def resolve_all(page: Page, primary: LocatorCandidate, fallbacks: list[LocatorCandidate]) -> Locator:
    tried: list[LocatorCandidate] = [primary, *fallbacks]
    # Vendor control name is an intentional last-resort when the primary strategy did not declare CSS.
    if primary.html_name and not any(
        (c.by == LocatorStrategy.CSS and c.css and primary.html_name in (c.css or "")) for c in tried
    ):
        tried.append(
            LocatorCandidate(
                by=LocatorStrategy.CSS,
                css=f"[name='{primary.html_name}']",
                frame=primary.frame,
            )
        )
    labels = []
    for c in tried:
        labels.append(_candidate_label(c))
        found = await resolve_candidate(page, c)
        if found is None:
            continue
        try:
            if await found.is_visible():
                return found
        except Exception:
            continue
    excerpt = ""
    try:
        excerpt = (await page.inner_text("body"))[:400]
    except Exception:
        excerpt = page.url
    raise TargetNotFound(
        "control not found",
        expected=" | ".join(labels),
        observed=excerpt or page.url,
    )


CURRENCY_RE = re.compile(r"\$[\d,]+\.\d{2}")


def parse_currency(text: str) -> str | None:
    m = CURRENCY_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    return m.group(0)
