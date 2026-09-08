from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from hands.session.session import BrowserSession

SESSIONS: dict[str, BrowserSession] = {}


def register(session: BrowserSession) -> None:
    SESSIONS[session.run_id] = session


def get(run_id: str) -> BrowserSession | None:
    return SESSIONS.get(run_id)


def create_operator_app() -> FastAPI:
    app = FastAPI(title="Hands operator", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        rows = []
        for s in SESSIONS.values():
            t = s.intervention
            if not t or t.resolved:
                continue
            rows.append(
                f"<li><a href='/i/{s.run_id}'>{s.run_id}</a> — {t.reason}</li>"
            )
        body = "".join(rows) or "<li>No open interventions.</li>"
        return _shell("<h1>Open interventions</h1><ul>" + body + "</ul>")

    @app.get("/i/{run_id}", response_class=HTMLResponse)
    def ticket(run_id: str) -> str:
        s = SESSIONS.get(run_id)
        if not s or not s.intervention:
            return _shell("<p>No intervention for this run.</p>")
        t = s.intervention
        img = ""
        if t.screenshot_path and Path(t.screenshot_path).exists():
            img = f"<p><img src='/shot/{run_id}' style='max-width:720px;border:1px solid #333'></p>"
        return _shell(
            f"<h1>Intervention {t.id}</h1>"
            f"<p><b>Run</b> {run_id} &nbsp; <b>step</b> {t.step_id or '—'}</p>"
            f"<p><b>Why it stopped.</b> {t.reason}</p>"
            f"<pre>{t.page_excerpt[:1200]}</pre>"
            f"{img}"
            f"<p>The live browser session is the same one automation was using. "
            f"Take control, do the judgment step there, then resume.</p>"
            f"<form method='post' action='/i/{run_id}/resume'><button>Resume automation</button></form>"
        )

    @app.get("/shot/{run_id}")
    def shot(run_id: str):
        s = SESSIONS.get(run_id)
        if not s or not s.intervention or not s.intervention.screenshot_path:
            raise HTTPException(404)
        return HTMLResponse(
            Path(s.intervention.screenshot_path).read_bytes(),
            media_type="image/png",
        )

    @app.post("/i/{run_id}/resume")
    async def resume(run_id: str):
        s = SESSIONS.get(run_id)
        if not s:
            raise HTTPException(404)
        await s.resume()
        return JSONResponse({"ok": True, "controller": s.controller.value})

    return app


def _shell(body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Hands operator</title>
<style>
 body {{ font: 14px/1.4 ui-sans-serif, system-ui; background:#111; color:#eee; margin:32px; }}
 a {{ color:#8cb4ff; }}
 pre {{ background:#1c1c1c; padding:12px; white-space:pre-wrap; }}
 button {{ font:inherit; padding:8px 14px; }}
</style></head><body>{body}</body></html>"""
