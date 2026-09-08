from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import FrameLocator, Page


@dataclass
class Control:
    ref: int
    role: str
    name: str
    value: str
    frame: str | None
    html_name: str | None
    tag: str
    text: str = ""


@dataclass
class Observation:
    url: str
    title: str
    page_text: str
    controls: list[Control] = field(default_factory=list)
    screenshot_png: bytes | None = None

    def by_ref(self, ref: int) -> Control:
        for c in self.controls:
            if c.ref == ref:
                return c
        raise KeyError(f"no control with ref {ref}")

    def compact(self, limit: int = 6000) -> str:
        lines = [f"url: {self.url}", f"title: {self.title}", "controls:"]
        for c in self.controls:
            val = f' value={c.value!r}' if c.value else ""
            frame = f" frame={c.frame}" if c.frame else ""
            lines.append(f"  [{c.ref}] {c.role} {c.name!r}{val}{frame}")
        body = "\n".join(lines)
        excerpt = self.page_text.strip().replace("\n", " | ")
        if excerpt:
            body += f"\nvisible_text: {excerpt[:1500]}"
        return body[:limit]


SNAPSHOT_JS = r"""
(start) => {
  const interesting = (el) => {
    const tag = el.tagName;
    if (!tag) return false;
    const t = tag.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['SCRIPT','STYLE','NOSCRIPT'].includes(tag)) return false;
    if (t === 'input' && type === 'hidden') return false;
    if (t === 'input' || t === 'button' || t === 'select' || t === 'textarea') return true;
    if (t === 'a' && el.hasAttribute('href')) return true;
    if (el.getAttribute('role')) return true;
    return false;
  };

  const visible = (el) => {
    const s = window.getComputedStyle(el);
    if (!s || s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  const accName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return lab.innerText.trim();
    }
    const wrap = el.closest('label');
    if (wrap) return wrap.innerText.trim();
    const ph = el.getAttribute('placeholder');
    if (ph) return ph.trim();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (el.tagName === 'INPUT' && ['submit','button','image'].includes(type)) {
      return (el.value || '').trim();
    }
    if (el.tagName === 'BUTTON') return (el.innerText || el.value || '').trim();
    if (el.tagName === 'A') return (el.innerText || '').trim();
    const td = el.closest('td');
    if (td && td.previousElementSibling) {
      return td.previousElementSibling.innerText.trim().replace(/:\s*$/, '');
    }
    return '';
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const t = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (t === 'a') return 'link';
    if (t === 'button') return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      if (['submit','button','image'].includes(type)) return 'button';
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      return 'textbox';
    }
    return t;
  };

  const nodes = Array.from(document.querySelectorAll('input, button, select, textarea, a[href], [role]'))
    .filter(interesting)
    .filter(visible);

  document.querySelectorAll('[data-hands-ref]').forEach((el) => el.removeAttribute('data-hands-ref'));

  const out = [];
  let n = Number(start) || 1;
  for (const el of nodes) {
    el.setAttribute('data-hands-ref', String(n));
    out.push({
      ref: n,
      role: roleOf(el),
      name: accName(el),
      value: (el.value || '').toString().slice(0, 80),
      html_name: el.getAttribute('name'),
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || '').trim().slice(0, 80),
      frame: window.name || null,
    });
    n += 1;
  }
  return {
    title: document.title,
    text: (document.body && document.body.innerText || '').slice(0, 4000),
    controls: out,
  };
}
"""


async def snapshot_page(page: Page) -> Observation:
    controls: list[Control] = []
    texts: list[str] = []
    title = page.url
    try:
        title = await page.title()
    except Exception:
        title = ""

    payloads = []
    next_ref = 1
    try:
        payload = await page.evaluate(SNAPSHOT_JS, next_ref)
        payloads.append(payload)
        next_ref = next_ref + len(payload.get("controls") or [])
    except Exception:
        payloads.append({"title": title, "text": "", "controls": []})

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            payload = await frame.evaluate(SNAPSHOT_JS, next_ref)
            payloads.append(payload)
            next_ref = next_ref + len(payload.get("controls") or [])
        except Exception:
            continue

    seen: set[int] = set()
    for payload in payloads:
        texts.append(payload.get("text") or "")
        for raw in payload.get("controls") or []:
            ref = int(raw["ref"])
            if ref in seen:
                continue
            seen.add(ref)
            controls.append(
                Control(
                    ref=ref,
                    role=raw.get("role") or "unknown",
                    name=raw.get("name") or "",
                    value=raw.get("value") or "",
                    frame=raw.get("frame") or None,
                    html_name=raw.get("html_name"),
                    tag=raw.get("tag") or "",
                    text=raw.get("text") or "",
                )
            )

    page_text = "\n".join(t for t in texts if t)
    return Observation(url=page.url, title=title, page_text=page_text, controls=controls)


def frame_scope(page: Page, frame: str | None) -> Page | FrameLocator:
    if not frame:
        return page
    return page.frame_locator(f"iframe[name='{frame}']")
