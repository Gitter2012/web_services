from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router


def init_app(app: FastAPI, mount_path: str | None = None) -> None:
    if mount_path:
        static_dir = Path(__file__).parent / "static"
        app.mount(
            f"{mount_path}/static",
            StaticFiles(directory=static_dir),
            name="rss_ui_static",
        )
