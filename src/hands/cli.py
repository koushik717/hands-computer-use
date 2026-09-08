from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from hands.schema.artifact import Capability
from hands.schema.policy import load_policy

app = typer.Typer(help="Hands — discover a UI flow once, replay it as a capability.")
console = Console()
ROOT = Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    return ROOT


def _headed() -> bool:
    return os.environ.get("HANDS_HEADLESS", "1") not in {"1", "true", "True"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_core(port: int | None = None) -> tuple[str, uvicorn.Server]:
    from pioneer_core.server import create_app

    port = port or int(os.environ.get("PIONEER_PORT", "8765"))
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            import httpx

            r = httpx.get(url + "/healthz", timeout=0.2)
            if r.status_code == 200:
                return url, server
        except Exception:
            time.sleep(0.1)
    return url, server


@app.command()
def core(
    port: int = typer.Option(8765, help="Port for Pioneer Core"),
) -> None:
    """Run the local teller console (the stand-in core with no API)."""
    url, _ = start_core(port)
    console.print(f"Pioneer Core at {url}")
    console.print("Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        raise typer.Exit()


@app.command()
def discover(
    goal: str = typer.Option(..., "--goal", help="Natural-language goal"),
    target: str = typer.Option("http://127.0.0.1:8765", "--target"),
    out: Path = typer.Option(Path("evidence/capabilities/lookup_regular_share_balance.json"), "--out"),
    teacher: bool = typer.Option(False, "--teacher", help="Use the deterministic teacher (not a live model)"),
) -> None:
    """LLM-driven run against a live surface. Compiles a capability on success."""
    import asyncio

    from dotenv import load_dotenv

    from hands.agent.loop import discover as run_discover
    from hands.agent.teacher import TeacherLLM

    load_dotenv(_repo_root() / ".env", override=True)
    llm = TeacherLLM() if teacher else None
    cap, result = asyncio.run(
        run_discover(
            goal,
            target,
            headed=_headed(),
            evidence_dir=Path("evidence/discovery"),
            llm=llm,
        )
    )
    _print_result(result)
    if cap is None:
        raise typer.Exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cap.model_dump_json(indent=2))
    console.print(f"wrote {out}")


@app.command()
def replay(
    artifact: Path = typer.Option(
        Path("evidence/capabilities/lookup_regular_share_balance.json"),
        "--artifact",
    ),
    input: list[str] = typer.Option([], "--input", help="name=value"),
    target: Optional[str] = typer.Option(None, "--target"),
    evidence: Path = typer.Option(Path(".hands-runs/replay"), "--evidence"),
) -> None:
    """Replay a saved capability. No model in the loop."""
    import asyncio

    from hands.replay.engine import replay as run_replay

    inputs = _parse_inputs(input) or {"member_id": "12345"}
    cap = _load_cap(artifact, target)
    result = asyncio.run(
        run_replay(cap, inputs, start_url=target or cap.entry.url, evidence_dir=evidence, headed=_headed())
    )
    _print_result(result)
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "result.json").write_text(result.model_dump_json(indent=2))
    if result.status.value not in {"success", "business_outcome"}:
        raise typer.Exit(1)


@app.command()
def demo(
    skip_discovery: bool = typer.Option(True, "--skip-discovery/--discovery"),
) -> None:
    """The path reviewers should run: core up, replay success, not-found, second tenant."""
    import asyncio

    from dotenv import load_dotenv

    from hands.record.golden import lookup_regular_share
    from hands.replay.engine import replay as run_replay

    load_dotenv()
    url, _ = start_core(int(os.environ.get("PIONEER_PORT", "8765")))
    console.print(f"[bold]Pioneer Core[/bold] {url}")
    policy = load_policy()
    cap = lookup_regular_share(url, policy)
    out = ROOT / "evidence" / "capabilities" / "lookup_regular_share_balance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cap.model_dump_json(indent=2))

    async def run_all() -> None:
        ok = await run_replay(
            cap,
            {"member_id": "12345"},
            start_url=url,
            evidence_dir=ROOT / "evidence" / "replay" / "success",
        )
        _print_result(ok)
        missing = await run_replay(
            cap,
            {"member_id": "99999"},
            start_url=url,
            evidence_dir=ROOT / "evidence" / "replay" / "member_not_found",
        )
        _print_result(missing)
        lakeside = await run_replay(
            cap,
            {"member_id": "12345"},
            start_url=url + "/?inst=lakeside",
            evidence_dir=ROOT / "evidence" / "replay" / "lakeside_tenant",
        )
        _print_result(lakeside)

        async def human(session):
            ws = session.page.frame_locator("iframe[name='ws']")
            await ws.locator("input[value='continue']").click()
            await ws.get_by_text("Share Inquiry").wait_for(timeout=8000)

        hold = await run_replay(
            cap,
            {"member_id": "77777"},
            start_url=url,
            evidence_dir=ROOT / "evidence" / "replay" / "fraud_hold",
            on_escalate=human,
        )
        _print_result(hold)

    asyncio.run(run_all())

    if not skip_discovery and (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        from hands.agent.loop import discover as run_discover
        import asyncio as aio

        console.print("[bold]Discovery (live model)[/bold]")
        cap2, result = asyncio.run(
            run_discover(
                "Look up member 12345 and read their current regular share balance",
                url,
                headed=_headed(),
                evidence_dir=ROOT / "evidence" / "discovery",
            )
        )
        _print_result(result)
        if cap2:
            (ROOT / "evidence" / "capabilities" / "lookup_regular_share_balance.discovered.json").write_text(
                cap2.model_dump_json(indent=2)
            )


@app.command()
def catalog(
    port: int = 8767,
    target: str = "http://127.0.0.1:8765",
) -> None:
    """Agent-facing capability catalog (stretch)."""
    from hands.catalog.api import create_catalog_app

    uvicorn.run(create_catalog_app(target), host="127.0.0.1", port=port, log_level="warning")


def _parse_inputs(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter("expected name=value")
        k, v = item.split("=", 1)
        out[k] = v
    return out


def _load_cap(path: Path, target: str | None) -> Capability:
    if path.exists():
        cap = Capability.model_validate_json(path.read_text())
        if target:
            cap.entry.url = target
        return cap
    from hands.record.golden import lookup_regular_share

    return lookup_regular_share(target or "http://127.0.0.1:8765", load_policy())


def _print_result(result) -> None:
    table = Table(title=f"{result.mode} · {result.status.value}")
    table.add_column("field")
    table.add_column("value")
    table.add_row("run_id", result.run_id)
    table.add_row("outcome", result.outcome_code or "—")
    table.add_row("outputs", json.dumps(result.outputs))
    table.add_row("recovered", ",".join(result.recovered) or "—")
    if result.failure:
        table.add_row("expected", result.failure.expected)
        table.add_row("observed", result.failure.observed[:200])
    table.add_row("ms", str(result.duration_ms))
    console.print(table)
