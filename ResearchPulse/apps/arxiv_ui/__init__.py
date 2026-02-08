from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router
from .tasks import run_scan_on_startup, shutdown_scheduler, start_scheduler


def init_app(app: FastAPI, mount_path: str | None = None) -> None:
    app.add_event_handler("startup", start_scheduler)
    app.add_event_handler("startup", run_scan_on_startup)
    app.add_event_handler("shutdown", shutdown_scheduler)

    if mount_path:
        static_dir = Path(__file__).parent / "static"
        app.mount(f"{mount_path}/static", StaticFiles(directory=static_dir), name="arxiv_ui_static")
