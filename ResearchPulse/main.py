from __future__ import annotations

import importlib
import logging
from typing import Iterable

from fastapi import FastAPI

from common.http import close_client
from common.logger import setup_logging
from settings import settings

setup_logging(settings.log_level, settings.log_file)
logger = logging.getLogger(__name__)

app = FastAPI(title="ResearchPulse")
app.add_event_handler("shutdown", close_client)

APP_MOUNT_PATHS = {
    "arxiv_crawler": "/arxiv/crawler",
    "arxiv_ui": "/arxiv/ui",
    "wechat_crawler": "/wechat/crawler",
    "wechat_ui": "/wechat/ui",
    "rss_crawler": "/rss/crawler",
    "rss_ui": "/rss/ui",
}


def _load_apps(enabled_apps: Iterable[str]) -> None:
    for app_name in enabled_apps:
        module_name = f"apps.{app_name}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            logger.warning("App module not found", extra={"app": app_name})
            continue

        mount_path = APP_MOUNT_PATHS.get(app_name)
        if mount_path and hasattr(module, "router"):
            app.include_router(module.router, prefix=mount_path, tags=[app_name])
        elif mount_path:
            logger.warning("App missing router", extra={"app": app_name})

        if hasattr(module, "init_app"):
            module.init_app(app, mount_path)
            logger.info("App initialized", extra={"app": app_name})
        else:
            logger.warning("App missing init_app", extra={"app": app_name})


_load_apps(settings.enabled_apps_list)
