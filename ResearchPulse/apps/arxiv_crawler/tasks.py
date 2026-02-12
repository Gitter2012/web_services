from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from common.email import send_email
from common.storage import (
    build_output_path,
    migrate_legacy_arxiv_outputs,
    render_aggregated_html,
    render_aggregated_markdown,
    render_html,
    render_markdown,
    write_markdown,
)
from common.utils import today_str
from settings import settings

from .config import settings as arxiv_settings
from .parser import fetch_papers_multi, select_backfill_by_date, serialize_papers

# Lazy import to avoid circular dependency – populated after the app is mounted.
_arxiv_ui_scan_fn = None


def _get_ui_scan_fn():
    global _arxiv_ui_scan_fn
    if _arxiv_ui_scan_fn is None:
        try:
            from apps.arxiv_ui.tasks import scan_entries
            _arxiv_ui_scan_fn = scan_entries
        except ImportError:
            _arxiv_ui_scan_fn = lambda: None  # noqa: E731
    return _arxiv_ui_scan_fn

logger = logging.getLogger(__name__)

_last_run_at: Optional[str] = None
_last_error: Optional[str] = None
_last_files: List[str] = []

_scheduler: Optional[BackgroundScheduler] = None


def get_status() -> dict:
    return {
        "last_run_at": _last_run_at,
        "last_error": _last_error,
        "last_files": _last_files,
    }


def run_crawl() -> dict:
    global _last_run_at, _last_error, _last_files

    run_date = today_str(arxiv_settings.date_window_timezone)
    results: List[str] = []
    sections: dict[str, List[dict[str, str]]] = {}
    global_seen: set[str] = set()
    selected_per_category: dict[str, dict[str, List[Paper]]] = {}

    try:
        migrate_legacy_arxiv_outputs(settings.data_dir)
        categories = arxiv_settings.categories_list
        for idx, category in enumerate(categories):
            # Batch delay between categories to avoid rate-limiting
            if idx > 0:
                batch_delay = arxiv_settings.arxiv_batch_delay
                batch_jitter = batch_delay * 0.3  # ±30% jitter
                actual_batch_delay = batch_delay + random.uniform(-batch_jitter, batch_jitter)
                actual_batch_delay = max(1.0, actual_batch_delay)
                logger.info(
                    "Waiting %.1fs before crawling next category",
                    actual_batch_delay,
                    extra={"category": category, "delay": actual_batch_delay},
                )
                time.sleep(actual_batch_delay)

            papers = fetch_papers_multi(
                category=category,
                max_results=arxiv_settings.arxiv_max_results,
                min_results=arxiv_settings.arxiv_min_results,
                fallback_days=arxiv_settings.arxiv_fallback_days,
                base_url=arxiv_settings.arxiv_base_url,
                rss_url=arxiv_settings.arxiv_rss_url,
                list_new_url=arxiv_settings.arxiv_html_list_new_url,
                list_recent_url=arxiv_settings.arxiv_html_list_recent_url,
                search_url=arxiv_settings.arxiv_html_search_url,
                run_date=run_date,
                http_delay=arxiv_settings.http_delay_base,
                http_jitter=arxiv_settings.http_delay_jitter,
                http_cache_ttl=arxiv_settings.http_cache_ttl,
            )
            selected_by_date = select_backfill_by_date(
                papers,
                run_date=run_date,
                min_results=arxiv_settings.arxiv_min_results,
                fallback_days=arxiv_settings.arxiv_fallback_days,
            )
            selected_per_category[category] = selected_by_date

        id_best_date: dict[str, str] = {}
        for date_map in selected_per_category.values():
            for date_key, day_papers in date_map.items():
                for paper in day_papers:
                    if not paper.arxiv_id:
                        continue
                    current = id_best_date.get(paper.arxiv_id)
                    if not current or date_key > current:
                        id_best_date[paper.arxiv_id] = date_key

        for category, date_map in selected_per_category.items():
            category_entries: List[dict[str, str]] = []
            for date_key in sorted(date_map.keys(), reverse=True):
                day_papers = []
                for paper in date_map.get(date_key, []):
                    if id_best_date.get(paper.arxiv_id) != date_key:
                        continue
                    if paper.arxiv_id in global_seen:
                        continue
                    global_seen.add(paper.arxiv_id)
                    day_papers.append(paper)
                if not day_papers:
                    continue

                serialized = serialize_papers(day_papers)
                category_entries.extend(serialized)

                metadata = {
                    "date": date_key,
                    "category": category,
                    "count": str(len(serialized)),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                content = render_markdown(
                    metadata,
                    serialized,
                    abstract_max_len=arxiv_settings.abstract_max_len,
                )

                output_path = build_output_path(settings.data_dir, category, run_date)
                write_markdown(output_path, content)
                results.append(str(output_path))

            if category_entries:
                sections[category] = category_entries

        if arxiv_settings.email_enabled and sections:
            if arxiv_settings.email_to_list and (settings.email_from or arxiv_settings.email_from):
                report_date = run_date
                total_papers = sum(len(items) for items in sections.values())
                subject = (
                    f"[ResearchPulse] {report_date} 多分类论文汇总（共{total_papers}篇 | {len(sections)}类）"
                )
                body = render_aggregated_markdown(
                    report_date,
                    sections,
                    abstract_max_len=arxiv_settings.abstract_max_len,
                    today_window_days=arxiv_settings.date_window_days,
                )
                html_body = None
                if arxiv_settings.email_html_enabled:
                    html_body = render_aggregated_html(
                        report_date,
                        sections,
                        abstract_max_len=arxiv_settings.abstract_max_len,
                        today_window_days=arxiv_settings.date_window_days,
                    )
                sender = settings.email_from or arxiv_settings.email_from
                backends = settings.email_backends_list or ["smtp"]
                sent = False
                last_traceback = ""
                for backend in backends:
                    if backend == "smtp":
                        profiles = arxiv_settings.smtp_profiles_list
                        tried_profiles: List[str] = []
                        for profile in profiles:
                            profile_id = str(profile.get("id", ""))
                            smtp_host = str(profile.get("host", ""))
                            if not smtp_host:
                                logger.warning(
                                    "SMTP profile missing host",
                                    extra={"smtp_profile": profile_id},
                                )
                                continue
                            tried_profiles.append(profile_id)
                            ok, tb = send_email(
                                subject=subject,
                                body=body,
                                html_body=html_body,
                                from_addr=sender,
                                to_addrs=arxiv_settings.email_to_list,
                                smtp_host=smtp_host,
                                smtp_port=int(profile.get("port", arxiv_settings.smtp_port)),
                                smtp_user=str(profile.get("user", arxiv_settings.smtp_user)),
                                smtp_password=str(profile.get("password", arxiv_settings.smtp_password)),
                                use_tls=bool(profile.get("tls", arxiv_settings.smtp_tls)),
                                use_ssl=bool(profile.get("ssl", arxiv_settings.smtp_ssl)),
                                smtp_ports=profile.get("ports") or [],
                                smtp_ssl_ports=profile.get("ssl_ports") or [],
                                timeout=float(profile.get("timeout", arxiv_settings.smtp_timeout)),
                                retries=int(profile.get("retries", arxiv_settings.smtp_retries)),
                                retry_backoff=float(
                                    profile.get("retry_backoff", arxiv_settings.smtp_retry_backoff)
                                ),
                            )
                            if ok:
                                sent = True
                                break
                            last_traceback = tb
                            logger.error(
                                "Email send failed",
                                extra={
                                    "categories": list(sections.keys()),
                                    "recipients": arxiv_settings.email_to_list,
                                    "smtp_profile": profile_id,
                                    "smtp_host": smtp_host,
                                    "smtp_port": profile.get("port"),
                                    "smtp_ports": profile.get("ports"),
                                    "smtp_ssl_ports": profile.get("ssl_ports"),
                                    "smtp_tls": profile.get("tls"),
                                    "smtp_ssl": profile.get("ssl"),
                                    "traceback": tb,
                                },
                            )
                        if sent:
                            break
                        logger.error(
                            "All SMTP profiles failed",
                            extra={"smtp_profiles": tried_profiles},
                        )
                        continue

                    if backend == "sendgrid":
                        ok, tb = send_email(
                            subject=subject,
                            body=body,
                            html_body=html_body,
                            from_addr=sender,
                            to_addrs=arxiv_settings.email_to_list,
                            backend="sendgrid",
                            api_key=settings.sendgrid_api_key,
                            retries=settings.sendgrid_retries,
                            retry_backoff=settings.sendgrid_retry_backoff,
                        )
                    elif backend == "mailgun":
                        ok, tb = send_email(
                            subject=subject,
                            body=body,
                            html_body=html_body,
                            from_addr=sender,
                            to_addrs=arxiv_settings.email_to_list,
                            backend="mailgun",
                            api_key=settings.mailgun_api_key,
                            domain=settings.mailgun_domain,
                            retries=settings.mailgun_retries,
                            retry_backoff=settings.mailgun_retry_backoff,
                        )
                    elif backend == "brevo":
                        ok, tb = send_email(
                            subject=subject,
                            body=body,
                            html_body=html_body,
                            from_addr=sender,
                            to_addrs=arxiv_settings.email_to_list,
                            backend="brevo",
                            api_key=settings.brevo_api_key,
                            from_name=settings.brevo_from_name,
                            retries=settings.brevo_retries,
                            retry_backoff=settings.brevo_retry_backoff,
                        )
                    else:
                        logger.error("Unsupported email backend", extra={"backend": backend})
                        continue

                    if ok:
                        sent = True
                        break
                    last_traceback = tb
                    logger.error(
                        "Email send failed",
                        extra={
                            "categories": list(sections.keys()),
                            "recipients": arxiv_settings.email_to_list,
                            "backend": backend,
                            "traceback": tb,
                        },
                    )

                if not sent:
                    logger.error(
                        "All email backends failed",
                        extra={"backends": backends, "traceback": last_traceback},
                    )
            else:
                logger.warning("Email enabled but SMTP config incomplete")

        _last_run_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        _last_files = results
        logger.info("arXiv crawl finished", extra={"files": results})

        # Trigger arXiv UI re-scan so new entries show immediately
        try:
            _get_ui_scan_fn()()
            logger.info("arXiv UI re-scan triggered after crawl")
        except Exception:
            logger.debug("arXiv UI re-scan after crawl failed (non-fatal)")
    except Exception as exc:  # pragma: no cover - runtime safety
        _last_error = str(exc)
        logger.exception("arXiv crawl failed")

    return get_status()


def _build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=arxiv_settings.schedule_timezone)
    trigger = CronTrigger(
        hour=arxiv_settings.schedule_hour,
        minute=arxiv_settings.schedule_minute,
        timezone=arxiv_settings.schedule_timezone,
    )
    scheduler.add_job(run_crawl, trigger, id="arxiv_daily", replace_existing=True)
    return scheduler


def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = _build_scheduler()
    _scheduler.start()
    logger.info(
        "arXiv scheduler started",
        extra={"hour": arxiv_settings.schedule_hour, "minute": arxiv_settings.schedule_minute},
    )


def run_crawl_on_startup() -> None:
    logger.info("arXiv startup crawl triggered")
    thread = threading.Thread(target=run_crawl, name="arxiv-startup-crawl", daemon=True)
    thread.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("arXiv scheduler stopped")
