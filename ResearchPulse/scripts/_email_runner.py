#!/usr/bin/env python3
"""手动邮件发送工具。

本脚本提供命令行接口，用于手动触发邮件发送操作。
支持发送测试邮件、触发用户订阅通知、发送自定义邮件等功能。

子命令：
    test: 发送测试邮件，验证邮件配置是否正常
    notify: 触发用户订阅通知（等同于定时任务 run_notification_job）
    send: 向指定地址发送自定义邮件

支持的邮件后端：
    - smtp: 标准 SMTP 发送
    - sendgrid: SendGrid API
    - mailgun: Mailgun API
    - brevo: Brevo (Sendinblue) API

用法示例：
    # 发送测试邮件
    python scripts/_email_runner.py test --to admin@example.com

    # 指定邮件后端测试
    python scripts/_email_runner.py test --to admin@example.com --backend smtp

    # 触发用户通知（默认过去 24 小时）
    python scripts/_email_runner.py notify

    # 指定时间范围和用户数量
    python scripts/_email_runner.py notify --since 2025-01-01 --max-users 10

    # 发送自定义邮件
    python scripts/_email_runner.py send --to user@example.com --subject "标题" --body "内容"

    # 从文件读取邮件正文
    python scripts/_email_runner.py send --to a@x.com,b@x.com --subject "标题" --body-file msg.txt

    # 发送 HTML 格式邮件
    python scripts/_email_runner.py send --to user@example.com --subject "标题" --body "<p>HTML内容</p>" --html
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

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from settings import settings

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI 颜色常量
# ---------------------------------------------------------------------------
# 用于终端输出着色，提升可读性
RED = "\033[0;31m"      # 错误/失败
GREEN = "\033[0;32m"    # 成功
YELLOW = "\033[1;33m"   # 警告
BLUE = "\033[0;34m"     # 信息
CYAN = "\033[0;36m"     # 强调
NC = "\033[0m"          # 重置颜色


def _print(msg: str, level: str = "info") -> None:
    """打印带颜色的消息并记录日志。

    根据日志级别使用不同的颜色输出消息，同时记录到日志。

    参数：
        msg: 要打印的消息内容。
        level: 日志级别，可选值：'info', 'ok', 'warn', 'error'。
    """
    colors = {"info": BLUE, "ok": GREEN, "warn": YELLOW, "error": RED}
    c = colors.get(level, NC)

    # 日志记录（不带颜色代码）
    level_map = {
        "info": logging.INFO,
        "ok": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }
    logger.log(level_map.get(level, logging.INFO), msg)

    # 终端输出（带颜色）
    print(f"{c}{msg}{NC}")


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------

async def cmd_test(args: argparse.Namespace) -> int:
    """发送测试邮件。

    发送一封测试邮件到指定地址，用于验证邮件配置是否正确。
    邮件包含发送时间和使用的后端信息。

    参数：
        args: 命令行参数，包含：
            - to: 收件人邮箱地址
            - backend: 指定的邮件后端（可选）

    返回：
        int: 退出码，0 表示成功，1 表示失败。
    """
    from common.email import send_email, send_email_with_fallback

    to_addr = args.to
    backend = args.backend

    # 构建邮件内容
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

    # 发送邮件
    if backend:
        # 使用指定后端
        ok, err = send_email(
            subject=subject,
            body=body,
            to_addrs=[to_addr],
            html_body=html_body,
            backend=backend,
        )
    else:
        # 使用 fallback 机制，按优先级尝试所有配置的后端
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
    """触发用户订阅通知。

    手动触发用户订阅通知任务，等同于定时任务 run_notification_job。
    默认发送过去 24 小时内的新文章通知。

    参数：
        args: 命令行参数，包含：
            - since: 文章时间下限（可选）
            - max_users: 最大处理用户数

    返回：
        int: 退出码，0 表示成功，1 表示失败或有部分邮件发送失败。
    """
    from core.database import close_db

    # 预加载所有 ORM 模型，确保 SQLAlchemy mapper 能解析 relationship 中的
    # 字符串引用（如 User.roles -> "Role"）。正常运行时 main.py 的 lifespan
    # 会完成这些导入，但 CLI 脚本跳过了 FastAPI 启动流程，需要手动触发。
    import core.models.user  # noqa: F401
    import core.models.permission  # noqa: F401
    import apps.crawler.models  # noqa: F401

    # 解析 since 参数
    since: Optional[datetime] = None
    if args.since:
        try:
            # 尝试解析 YYYY-MM-DD 格式
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                # 尝试解析 YYYY-MM-DDTHH:MM:SS 格式
                since = datetime.strptime(args.since, "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                _print(f"无法解析日期: {args.since}  (格式: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)", "error")
                return 1

    max_users = args.max_users

    try:
        # 预热 feature_config 缓存
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
            # 自定义参数：直接调用 send_all_user_notifications
            _print(f"触发用户通知 (since={since}, max_users={max_users})")
            results = await send_all_user_notifications(since=since, max_users=max_users)
        else:
            # 默认：调用完整的 run_notification_job（过去 24 小时）
            _print("触发通知任务 (过去 24 小时)")
            results = await run_notification_job()
    finally:
        # 确保在同一事件循环中关闭数据库连接，
        # 避免事件循环关闭后连接清理报错
        await close_db()

    # 打印结果摘要
    logger.info("")
    _print("=" * 50)
    _print("通知任务结果:")
    _print("-" * 50)
    for key, value in results.items():
        logger.info(f"  {key}: {value}")
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
    """发送自定义邮件。

    向指定地址发送自定义内容的邮件。

    参数：
        args: 命令行参数，包含：
            - to: 收件人邮箱地址（多个以逗号分隔）
            - subject: 邮件主题
            - body: 邮件正文（与 body_file 互斥）
            - body_file: 从文件读取邮件正文
            - html: 是否将正文视为 HTML 格式
            - backend: 指定的邮件后端（可选）

    返回：
        int: 退出码，0 表示成功，1 表示失败。
    """
    from common.email import send_email, send_email_with_fallback

    # 解析收件人列表（支持逗号分隔）
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

    # HTML 格式处理
    html_body = None
    if args.html:
        html_body = body  # 如果 --html 标志，将 body 视为 HTML

    _print(f"发送邮件到: {', '.join(to_addrs)}")
    _print(f"主题: {subject}")
    _print(f"后端: {backend or 'fallback (all)'}")
    if args.html:
        _print("格式: HTML")

    # 发送邮件
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
# 命令行参数解析
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    创建主解析器和三个子命令解析器（test, notify, send）。

    返回：
        argparse.ArgumentParser: 配置好的参数解析器。
    """
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

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest="command", help="操作类型")
    subparsers.required = True

    # --- test 子命令：发送测试邮件 ---
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

    # --- notify 子命令：触发用户通知 ---
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

    # --- send 子命令：发送自定义邮件 ---
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
    # body 和 body_file 互斥
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
    """命令行入口函数。

    解析命令行参数并执行对应的子命令。
    """
    parser = build_parser()
    args = parser.parse_args()

    _print("=" * 50)
    _print("ResearchPulse v2 邮件工具")
    _print("=" * 50)

    # 子命令分发字典
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
