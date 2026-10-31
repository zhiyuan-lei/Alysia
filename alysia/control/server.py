from __future__ import annotations

from pathlib import Path

import uvicorn

from alysia.core.config import load_config

from .api import create_control_app


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def start_control_center(*, port: int = DEFAULT_PORT, open_browser: bool = False) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("port 必须在 1024-65535 之间")
    app = create_control_app(load_config(), static_dir=Path("control-center/dist"))
    if open_browser:
        import webbrowser

        webbrowser.open(f"http://{DEFAULT_HOST}:{port}")
    uvicorn.run(app, host=DEFAULT_HOST, port=port, log_level="info")
