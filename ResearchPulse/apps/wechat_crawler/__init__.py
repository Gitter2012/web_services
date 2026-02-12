from __future__ import annotations

from fastapi import FastAPI

from .api import router
from .tasks import run_crawl_on_startup, shutdown_scheduler, start_scheduler


def init_app(app: FastAPI, mount_path: str | None = None) -> None:
    app.add_event_handler("startup", start_scheduler)
    app.add_event_handler("startup", run_crawl_on_startup)
    app.add_event_handler("shutdown", shutdown_scheduler)
