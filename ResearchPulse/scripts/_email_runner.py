#!/usr/bin/env python3
"""Manual email trigger runner for ResearchPulse v2.

手动触发邮件发送的 CLI 工具，支持以下操作:
  - test:      发送测试邮件，验证邮件配置是否正常
  - notify:    触发用户订阅通知（等同于定时任务 run_notification_job）
  - send:      向指定地址发送一封自定义邮件

Usage:
    python scripts/_email_runner.py test --to admin@example.com
    python scripts/_email_runner.py notify [--since 2025-01-01] [--max-users 50]
    python scripts/_email_runner.py send --to user@example.com --subject "Hi" --body "Hello"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from settings import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def _print(msg: str, level: str = "info") -> None:
    """Print a color-coded message."""
    colors = {"info": BLUE, "ok": GREEN, "warn": YELLOW, "error": RED}
    c = colors.get(level, NC)
    print(f"{c}{msg}{NC}")


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

async def cmd_test(args: argparse.Namespace) -> int:
    """Send a test email to verify configuration.

    发送测试邮件验证邮件配置。
    """
    from common.email import send_email, send_email_with_fallback

    to_addr = args.to
    backend = args.backend
    subject = "ResearchPulse 测试邮件"
    body = (
        "这是一封来自 ResearchPulse 的测试邮件。\n\n"
        "如果您收到此邮件，说明邮件配置正确。\n"
        f"发送时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"后端: {backend or 'fallback (all)'}\n"
    )
    html_body = (
        "<h2>ResearchPulse 测试邮件</h2>"
        "<p>如果您收到此邮件，说明邮件配置正确。</p>"
        f"<p><b>发送时间:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>"
        f"<p><b>后端:</b> {backend or 'fallback (all)'}</p>"
    )

    _print(f"发送测试邮件到: {to_addr}")
    _print(f"后端: {backend or 'fallback (all)'}")

    if backend:
        ok, err = send_email(
            subject=subject,
            body=body,
            to_addrs=[to_addr],
            html_body=html_body,
            backend=backend,
        )
    else:
        ok, err = send_email_with_fallback(
            subject=subject,
            body=body,
            to_addrs=[to_addr],
            html_body=html_body,
        )

    if ok:
        _print("测试邮件发送成功", "ok")
        return 0
    else:
        _print(f"测试邮件发送失败: {err}", "error")
        return 1


async def cmd_notify(args: argparse.Namespace) -> int:
    """Trigger the user notification job.

    手动触发用户订阅通知任务，等同于定时任务 run_notification_job。
    """
    from core.database import close_db

    # 预加载所有 ORM 模型，确保 SQLAlchemy mapper 能解析 relationship 中的
    # 字符串引用（如 User.roles -> "Role"）。正常运行时 main.py 的 lifespan
    # 会完成这些导入，但 CLI 脚本跳过了 FastAPI 启动流程，需要手动触发。
    import core.models.user  # noqa: F401
    import core.models.permission  # noqa: F401
    import apps.crawler.models  # noqa: F401

    since: Optional[datetime] = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                since = datetime.strptime(args.since, "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                _print(f"无法解析日期: {args.since}  (格式: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)", "error")
                return 1

    max_users = args.max_users

    try:
        # 预热 feature_config 缓存:
        # feature_config._maybe_refresh_cache() 的同步版本会在检测到
        # 运行中的事件循环时，通过 ThreadPoolExecutor 在新线程中调用
        # asyncio.run()，导致在不同事件循环中创建数据库连接，
        # 从而触发 "Future attached to a different loop" 错误。
        # 通过提前异步加载缓存来避免此问题。
        from common.feature_config import feature_config

        await feature_config.async_reload()

        from apps.scheduler.jobs.notification_job import (
            run_notification_job,
            send_all_user_notifications,
        )

        if since or max_users != 100:
            # 自定义参数: 直接调用 send_all_user_notifications
            _print(f"触发用户通知 (since={since}, max_users={max_users})")
            results = await send_all_user_notifications(since=since, max_users=max_users)
        else:
            # 默认: 调用完整的 run_notification_job (过去 24 小时)
            _print("触发通知任务 (过去 24 小时)")
            results = await run_notification_job()
    finally:
        # 确保在同一事件循环中关闭数据库连接，
        # 避免事件循环关闭后连接清理报错
        await close_db()

    # 打印结果
    print()
    _print("=" * 50)
    _print("通知任务结果:")
    _print("-" * 50)
    for key, value in results.items():
        print(f"  {key}: {value}")
    _print("=" * 50)

    sent = results.get("sent", 0)
    failed = results.get("failed", 0)
    status = results.get("status", "")

    if status == "failed":
        _print(f"通知任务失败: {results.get('error', '未知错误')}", "error")
        return 1
    elif failed > 0:
        _print(f"通知任务完成，但有 {failed} 封失败 (成功 {sent} 封)", "warn")
        return 1
    else:
        _print(f"通知任务完成: 成功发送 {sent} 封邮件", "ok")
        return 0


async def cmd_send(args: argparse.Namespace) -> int:
    """Send a custom email to specified recipients.

    向指定地址发送自定义邮件。
    """
    from common.email import send_email, send_email_with_fallback

    to_addrs = [addr.strip() for addr in args.to.split(",")]
    subject = args.subject
    body = args.body
    backend = args.backend

    # 读取 --body-file 内容
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            _print(f"文件不存在: {args.body_file}", "error")
            return 1
        body = body_path.read_text(encoding="utf-8")

    if not body:
        _print("邮件正文不能为空 (使用 --body 或 --body-file)", "error")
        return 1

    html_body = None
    if args.html:
        html_body = body  # 如果 --html 标志，将 body 视为 HTML

    _print(f"发送邮件到: {', '.join(to_addrs)}")
    _print(f"主题: {subject}")
    _print(f"后端: {backend or 'fallback (all)'}")
    if args.html:
        _print("格式: HTML")

    if backend:
        ok, err = send_email(
            subject=subject,
            body=body,
            to_addrs=to_addrs,
            html_body=html_body,
            backend=backend,
        )
    else:
        ok, err = send_email_with_fallback(
            subject=subject,
            body=body,
            to_addrs=to_addrs,
            html_body=html_body,
        )

    if ok:
        _print("邮件发送成功", "ok")
        return 0
    else:
        _print(f"邮件发送失败: {err}", "error")
        return 1


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="ResearchPulse v2 手动邮件发送工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/_email_runner.py test --to admin@example.com\n"
            "  python scripts/_email_runner.py test --to admin@example.com --backend smtp\n"
            "  python scripts/_email_runner.py notify\n"
            "  python scripts/_email_runner.py notify --since 2025-01-01 --max-users 10\n"
            "  python scripts/_email_runner.py send --to user@example.com --subject '标题' --body '内容'\n"
            "  python scripts/_email_runner.py send --to a@x.com,b@x.com --subject '标题' --body-file msg.txt\n"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="操作类型")
    subparsers.required = True

    # --- test ---
    p_test = subparsers.add_parser("test", help="发送测试邮件")
    p_test.add_argument(
        "--to",
        required=True,
        help="收件人邮箱地址",
    )
    p_test.add_argument(
        "--backend",
        choices=["smtp", "sendgrid", "mailgun", "brevo"],
        default=None,
        help="指定邮件后端 (默认: 按优先级 fallback)",
    )

    # --- notify ---
    p_notify = subparsers.add_parser("notify", help="触发用户订阅通知")
    p_notify.add_argument(
        "--since",
        default=None,
        help="文章时间下限 (格式: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS, 默认: 过去24小时)",
    )
    p_notify.add_argument(
        "--max-users",
        type=int,
        default=100,
        help="最大处理用户数 (默认: 100)",
    )

    # --- send ---
    p_send = subparsers.add_parser("send", help="发送自定义邮件")
    p_send.add_argument(
        "--to",
        required=True,
        help="收件人邮箱地址 (多个以逗号分隔)",
    )
    p_send.add_argument(
        "--subject",
        required=True,
        help="邮件主题",
    )
    body_group = p_send.add_mutually_exclusive_group(required=True)
    body_group.add_argument(
        "--body",
        default=None,
        help="邮件正文",
    )
    body_group.add_argument(
        "--body-file",
        default=None,
        help="从文件读取邮件正文",
    )
    p_send.add_argument(
        "--html",
        action="store_true",
        help="将正文视为 HTML 格式",
    )
    p_send.add_argument(
        "--backend",
        choices=["smtp", "sendgrid", "mailgun", "brevo"],
        default=None,
        help="指定邮件后端 (默认: 按优先级 fallback)",
    )

    return parser


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    _print("=" * 50)
    _print("ResearchPulse v2 邮件工具")
    _print("=" * 50)

    dispatch = {
        "test": cmd_test,
        "notify": cmd_notify,
        "send": cmd_send,
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    try:
        exit_code = asyncio.run(handler(args))
    except KeyboardInterrupt:
        _print("\n操作已取消", "warn")
        sys.exit(130)
    except Exception as e:
        _print(f"执行失败: {e}", "error")
        logger.exception("Unhandled error")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
