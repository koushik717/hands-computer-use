from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from pioneer_core.server import create_app


@pytest.fixture(scope="session")
def core_url() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            r = httpx.get(url + "/healthz", timeout=0.2)
            if r.status_code == 200:
                return url
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("Pioneer Core failed to start")
