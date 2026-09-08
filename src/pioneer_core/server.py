"""HTTP app: a hostile, iframe'd teller inquiry console.

This is a stand-in for the long-tail core screens the assignment is about —
no API, no test IDs, nested tables, a rotating viewstate, and runtime
exceptions that actually happen on a teller line.

Two institution skins share field names and error copy (same vendor product)
and differ in chrome/labels (tenant configuration). That is the smallest
honest model of 'hundreds of tenants, ~20 apps'.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pioneer_core.data import MEMBERS, Member, format_usd

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"

# Vendor-stable error copy. Tenants restyle the chrome; they do not rewrite this.
ERR_REQUIRED = "Member Number is required."
ERR_NOT_FOUND = "No member record matches the number entered."
ERR_DENIED = "You do not have sufficient privileges to view this member."
FRAUD_HOLD = "This member has a fraud hold. Continue?"
SESSION_EXPIRED = "Your teller session has expired."
NOTICE_TEXT = "Scheduled maintenance window Saturday 22:00–02:00 ET."

INSTITUTIONS: dict[str, dict[str, str]] = {
    "pioneer": {
        "inst_name": "Pioneer Credit Union",
        "chrome_color": "#003366",
        "member_label": "Member Number",
        "search_label": "Search",
        "share_label": "Regular Share (S0000) Available",
        "draft_label": "Share Draft (S0001) Available",
    },
    # Same core, different branding — a second tenant of the same vendor product.
    "lakeside": {
        "inst_name": "Lakeside Community CU",
        "chrome_color": "#1a4a3a",
        "member_label": "Acct Base",
        "search_label": "Inquire",
        "share_label": "Primary Share (S0000) Avail",
        "draft_label": "Draft (S0001) Avail",
    },
}


def _viewstate() -> str:
    raw = f"{time.time_ns()}:{os.urandom(8).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _inst(request: Request) -> str:
    q = request.query_params.get("inst") or request.cookies.get("inst") or "pioneer"
    return q if q in INSTITUTIONS else "pioneer"


def create_app() -> FastAPI:
    app = FastAPI(title="Pioneer Core", docs_url=None, redoc_url=None)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    def render(name: str, request: Request, **ctx: Any) -> HTMLResponse:
        inst = _inst(request)
        skin = INSTITUTIONS[inst]
        html = env.get_template(name).render(
            inst=inst,
            screen_id=ctx.pop("screen_id", "INQ-MEM-01"),
            today=date.today().isoformat(),
            viewstate=_viewstate(),
            **skin,
            **ctx,
        )
        resp = HTMLResponse(html)
        resp.set_cookie("inst", inst, httponly=False, samesite="lax")
        return resp

    @app.get("/", response_class=HTMLResponse)
    def shell(request: Request) -> HTMLResponse:
        inst = _inst(request)
        iframe_src = f"/cgi/ws.asp?view=lookup&inst={inst}"
        return render(
            "shell.html",
            request,
            iframe_src=iframe_src,
            screen_id="CINQ-HOST",
        )

    @app.get("/cgi/ws.asp", response_class=HTMLResponse)
    def workspace(request: Request) -> HTMLResponse:
        if request.cookies.get("notice_ack") != "1":
            return render("notice.html", request, screen_id="INQ-NOTICE")
        if request.cookies.get("teller_session") == "expired":
            return render("timeout.html", request, screen_id="INQ-SESS")
        view = request.query_params.get("view", "lookup")
        if view == "lookup":
            return render("lookup.html", request, q="", error=None, results=None)
        return render("lookup.html", request, q="", error=None, results=None)

    @app.post("/cgi/notice.asp")
    def ack_notice(request: Request) -> RedirectResponse:
        inst = _inst(request)
        resp = RedirectResponse(url=f"/cgi/ws.asp?view=lookup&inst={inst}", status_code=303)
        resp.set_cookie("notice_ack", "1", httponly=False, samesite="lax")
        resp.set_cookie("inst", inst, httponly=False, samesite="lax")
        return resp

    @app.post("/cgi/search.asp", response_class=HTMLResponse)
    def search(
        request: Request,
        txtMemNo: str = Form(""),
        btnInq: str | None = Form(None),
        inst: str = Form("pioneer"),
    ) -> HTMLResponse:
        del btnInq
        member_id = (txtMemNo or "").strip()
        if not member_id:
            return render(
                "lookup.html",
                request,
                q="",
                error=ERR_REQUIRED,
                results=None,
                screen_id="INQ-MEM-01",
            )
        member = MEMBERS.get(member_id)
        if member is None:
            return render(
                "lookup.html",
                request,
                q=member_id,
                error=ERR_NOT_FOUND,
                results=None,
                screen_id="INQ-MEM-01",
            )
        if member.slow:
            time.sleep(3.5)
        if member.fraud_hold and request.cookies.get(f"fraud_ok_{member_id}") != "1":
            return render(
                "fraud.html",
                request,
                member_id=member_id,
                screen_id="INQ-HOLD",
            )
        if member.restricted:
            return render("denied.html", request, screen_id="INQ-ACL")
        return render(
            "lookup.html",
            request,
            q=member_id,
            error=None,
            results=[member],
            screen_id="INQ-MEM-01",
        )

    @app.post("/cgi/fraud.asp")
    def fraud_continue(
        request: Request,
        member_id: str = Form(...),
        decision: str = Form(...),
    ) -> RedirectResponse:
        inst = _inst(request)
        if decision != "continue":
            return RedirectResponse(url=f"/cgi/ws.asp?view=lookup&inst={inst}", status_code=303)
        resp = RedirectResponse(
            url=f"/cgi/member.asp?id={member_id}&inst={inst}",
            status_code=303,
        )
        resp.set_cookie(f"fraud_ok_{member_id}", "1", httponly=False, samesite="lax")
        return resp

    @app.get("/cgi/member.asp", response_class=HTMLResponse)
    def member_detail(request: Request) -> HTMLResponse:
        member_id = (request.query_params.get("id") or "").strip()
        member = MEMBERS.get(member_id)
        if member is None:
            return render(
                "lookup.html",
                request,
                q=member_id,
                error=ERR_NOT_FOUND,
                results=None,
            )
        if member.restricted:
            return render("denied.html", request, screen_id="INQ-ACL")
        if member.fraud_hold and request.cookies.get(f"fraud_ok_{member_id}") != "1":
            return render("fraud.html", request, member_id=member_id, screen_id="INQ-HOLD")
        return render(
            "detail.html",
            request,
            member=member,
            savings_display=format_usd(member.savings),
            checking_display=format_usd(member.checking),
            screen_id="INQ-SHR-02",
        )

    @app.get("/cgi/open.asp", response_class=HTMLResponse)
    def open_share_form(request: Request) -> HTMLResponse:
        member_id = (request.query_params.get("id") or "").strip()
        member = MEMBERS.get(member_id)
        if member is None:
            return render(
                "lookup.html",
                request,
                q=member_id,
                error=ERR_NOT_FOUND,
                results=None,
            )
        return render(
            "open_share.html",
            request,
            member=member,
            error=None,
            screen_id="FMS-SHR-09",
        )

    @app.post("/cgi/open.asp", response_class=HTMLResponse)
    def open_share_confirm(
        request: Request,
        member_id: str = Form(...),
        product: str = Form(...),
        nickname: str = Form(""),
        deposit: str = Form(""),
    ) -> HTMLResponse:
        member = MEMBERS.get(member_id)
        if member is None:
            return render(
                "lookup.html",
                request,
                q=member_id,
                error=ERR_NOT_FOUND,
                results=None,
            )
        if not product:
            return render(
                "open_share.html",
                request,
                member=member,
                error="Product type is required.",
                screen_id="FMS-SHR-09",
            )
        return render(
            "confirm_open.html",
            request,
            member=member,
            product=product,
            nickname=nickname,
            deposit=deposit or "0.00",
            screen_id="FMS-SHR-09C",
        )

    @app.post("/cgi/open_commit.asp", response_class=HTMLResponse)
    def open_share_commit(
        request: Request,
        member_id: str = Form(...),
        product: str = Form(...),
        nickname: str = Form(""),
        deposit: str = Form(""),
    ) -> HTMLResponse:
        ref = hashlib.sha1(f"{member_id}:{product}:{time.time_ns()}".encode()).hexdigest()[:10].upper()
        return render(
            "opened.html",
            request,
            member_id=member_id,
            product=product,
            nickname=nickname,
            deposit=deposit or "0.00",
            reference=f"SHR-{ref}",
            screen_id="FMS-SHR-09R",
        )

    @app.post("/cgi/session.asp")
    def session_action(request: Request, action: str = Form("continue")) -> RedirectResponse:
        inst = _inst(request)
        if action == "expire":
            resp = RedirectResponse(url=f"/cgi/ws.asp?inst={inst}", status_code=303)
            resp.set_cookie("teller_session", "expired", httponly=False, samesite="lax")
            return resp
        resp = RedirectResponse(url=f"/cgi/ws.asp?view=lookup&inst={inst}", status_code=303)
        resp.set_cookie("teller_session", "ok", httponly=False, samesite="lax")
        return resp

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
