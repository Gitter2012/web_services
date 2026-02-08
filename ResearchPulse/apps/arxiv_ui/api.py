from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from common.utils import window_dates

from .config import settings as ui_settings
from .tasks import get_categories, get_entries, get_latest_date

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _sorted_entries(entries: List[dict]) -> List[dict]:
    def sort_key(item: dict) -> tuple[str, str]:
        return (item.get("source_date", ""), item.get("arxiv_id", ""))

    return sorted(entries, key=sort_key, reverse=True)


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        "index.html.j2",
        {
            "request": request,
            "categories": get_categories(),
            "latest_date": get_latest_date(),
            "default_show_all": ui_settings.show_all_content,
            "default_page_size": ui_settings.default_page_size,
        },
    )


@router.get("/api/entries")
def api_entries(
    category: Optional[str] = None,
    show_all: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=200),
) -> dict:
    latest_date = get_latest_date()
    entries = get_entries()
    today_dates = window_dates(latest_date, ui_settings.date_window_days) if latest_date else set()

    if category:
        entries = [entry for entry in entries if entry.get("category") == category]

    effective_show_all = ui_settings.show_all_content if show_all is None else show_all
    if not effective_show_all and today_dates:
        entries = [entry for entry in entries if entry.get("source_date") in today_dates]

    entries = _sorted_entries(entries)
    for entry in entries:
        entry["backfill"] = bool(today_dates and entry.get("source_date") not in today_dates)

    total = len(entries)
    size = page_size or ui_settings.default_page_size
    start = (page - 1) * size
    entries = entries[start : start + size]
    return {
        "entries": entries,
        "total": total,
        "page": page,
        "page_size": size,
        "latest_date": latest_date,
    }


@router.get("/api/categories")
def api_categories() -> dict:
    return {"categories": get_categories()}


@router.get("/api/latest-date")
def api_latest_date() -> dict:
    return {"latest_date": get_latest_date()}
