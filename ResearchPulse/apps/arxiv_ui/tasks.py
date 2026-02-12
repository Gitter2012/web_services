from __future__ import annotations

import logging
import threading
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from settings import settings as global_settings

from .config import settings as ui_settings

logger = logging.getLogger(__name__)

_entries: List[Dict[str, str]] = []
_categories: List[str] = []
_latest_date: str = ""
_latest_source_date: str = ""
_last_scan_at: Optional[str] = None
_lock = threading.Lock()
_scheduler: Optional[BackgroundScheduler] = None


def _parse_entry_block(block: List[str], category: str) -> Optional[Dict[str, str]]:
    if not block:
        return None
    header = block[0].strip()
    if not header.startswith("### ["):
        return None
    try:
        prefix, title = header.split("] ", 1)
        arxiv_id = prefix.replace("### [", "").strip()
    except ValueError:
        return None

    entry: Dict[str, str] = {
        "arxiv_id": arxiv_id,
        "title": title.strip(),
        "authors": "",
        "primary_category": "",
        "categories": "",
        "published": "",
        "updated": "",
        "source_date": "",
        "abstract": "",
        "pdf_url": "",
        "translate_url": "",
        "category": category,
    }

    for line in block[1:]:
        stripped = line.strip()
        if stripped.startswith("**arXiv ID**:"):
            entry["arxiv_id"] = stripped.replace("**arXiv ID**:", "").strip()
        elif stripped.startswith("**Authors**:"):
            entry["authors"] = stripped.replace("**Authors**:", "").strip()
        elif stripped.startswith("**Primary Category**:"):
            entry["primary_category"] = stripped.replace("**Primary Category**:", "").strip()
        elif stripped.startswith("**Categories**:"):
            entry["categories"] = stripped.replace("**Categories**:", "").strip()
        elif stripped.startswith("**Published**:"):
            entry["published"] = stripped.replace("**Published**:", "").strip()
        elif stripped.startswith("**Updated**:"):
            entry["updated"] = stripped.replace("**Updated**:", "").strip()
        elif stripped.startswith("**Date**:"):
            entry["source_date"] = stripped.replace("**Date**:", "").strip()
        elif stripped.startswith("**Abstract**:"):
            entry["abstract"] = stripped.replace("**Abstract**:", "").strip()

        if "[PDF]" in stripped:
            match = re.search(r"\[PDF\]\(([^)]+)\)", stripped)
            if match:
                entry["pdf_url"] = match.group(1)
        if "[翻译]" in stripped:
            match = re.search(r"\[翻译\]\(([^)]+)\)", stripped)
            if match:
                entry["translate_url"] = match.group(1)

    return entry if entry.get("arxiv_id") else None


def _parse_markdown(file_path: Path, category: str, fallback_date: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    block: List[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### ["):
            entry = _parse_entry_block(block, category)
            if entry:
                if not entry.get("source_date"):
                    entry["source_date"] = fallback_date
                entries.append(entry)
            block = [line]
        else:
            if block:
                block.append(line)
    entry = _parse_entry_block(block, category)
    if entry:
        if not entry.get("source_date"):
            entry["source_date"] = fallback_date
        entries.append(entry)
    return entries


def scan_entries() -> None:
    global _latest_date, _latest_source_date, _last_scan_at
    if not ui_settings.enabled:
        return
    data_dir = Path(global_settings.data_dir) / "arxiv"
    if not data_dir.exists():
        return

    entries: List[Dict[str, str]] = []
    latest_run_date = ""
    for file_path in data_dir.rglob("*.md"):
        stem = file_path.stem
        if "_" not in stem:
            continue
        date_part, category = stem.split("_", 1)
        try:
            datetime.fromisoformat(date_part)
        except ValueError:
            continue
        if date_part > latest_run_date:
            latest_run_date = date_part
        entries.extend(_parse_markdown(file_path, category, date_part))

    latest_source_date = ""
    for entry in entries:
        date_val = entry.get("source_date", "")
        if date_val and date_val > latest_source_date:
            latest_source_date = date_val

    if latest_source_date and ui_settings.max_content_age_days > 0:
        cutoff = datetime.fromisoformat(latest_source_date).date() - timedelta(
            days=ui_settings.max_content_age_days
        )
        entries = [
            entry
            for entry in entries
            if entry.get("source_date") and datetime.fromisoformat(entry["source_date"]).date() >= cutoff
        ]

    categories = sorted({entry.get("category", "") for entry in entries if entry.get("category")})

    with _lock:
        _entries.clear()
        _entries.extend(entries)
        _categories.clear()
        _categories.extend(categories)
        _latest_date = latest_run_date
        _latest_source_date = latest_source_date
        _last_scan_at = datetime.now().isoformat()

    logger.info(
        "arXiv UI scan complete",
        extra={
            "entries": len(entries),
            "latest_run_date": latest_run_date,
            "latest_source_date": latest_source_date,
        },
    )


def get_entries() -> List[Dict[str, str]]:
    with _lock:
        return list(_entries)


def get_categories() -> List[str]:
    with _lock:
        return list(_categories)


def get_latest_date() -> str:
    with _lock:
        return _latest_date


def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    if not ui_settings.enabled:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(scan_entries, "interval", seconds=ui_settings.scan_interval, id="arxiv_ui_scan")
    _scheduler.start()
    logger.info("arXiv UI scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("arXiv UI scheduler stopped")


def run_scan_on_startup() -> None:
    if not ui_settings.enabled:
        return
    thread = threading.Thread(target=scan_entries, daemon=True)
    thread.start()
