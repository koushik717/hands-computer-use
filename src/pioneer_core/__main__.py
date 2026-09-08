from __future__ import annotations

import os

import uvicorn

from pioneer_core.server import create_app


def main() -> None:
    host = os.environ.get("PIONEER_HOST", "127.0.0.1")
    port = int(os.environ.get("PIONEER_PORT", "8765"))
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
