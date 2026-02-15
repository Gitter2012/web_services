# =============================================================================
# 模块: common/email.py
# 功能: 统一邮件发送模块，支持多后端和自动降级
# 架构角色: 作为通用基础设施层，为整个应用提供邮件发送能力。
#   被通知系统、报告导出、用户注册确认等场景调用。
#   主要特点：
#   1. 多后端支持：SMTP、SendGrid、Mailgun、Brevo（原 Sendinblue）
#   2. SMTP 多端口重试：当某个端口不可用时自动尝试其他端口
#   3. 多后端自动降级（Fallback）：一个后端失败自动尝试下一个
#   4. 指数退避重试机制
#   5. 支持纯文本和 HTML 邮件
#
# 设计决策:
#   - 每个后端封装为独立的私有函数（_send_via_*），便于维护和扩展
#   - send_email 作为统一入口，通过 backend 参数路由到具体实现
#   - send_email_with_fallback 提供多后端降级策略
#   - send_notification_email 是异步包装器，在线程池中执行同步发送
#   - API 密钥优先从参数获取，其次从环境变量，保持灵活性
# =============================================================================
"""Email sending module for ResearchPulse v2.

Supports multiple backends:
- SMTP (with multi-port retry)
- SendGrid API
- Mailgun API
- Brevo API

Features:
- Multi-backend fallback
- Retry with backoff
- HTML email support
"""

from __future__ import annotations

import logging
import os
import smtplib
import time
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# ======================
# 1. SMTP 发送（支持多端口重试）
# ======================
def _send_via_smtp(
    subject: str,
    body: str,
    from_addr: str,
    to_addrs: List[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    html_body: Optional[str] = None,
    smtp_ports: Optional[List[int]] = None,
    smtp_ssl_ports: Optional[List[int]] = None,
    timeout: float = 10.0,
    retries: int = 3,
    retry_backoff: float = 10.0,
    use_tls: bool = True,
    use_ssl: bool = False,
) -> Tuple[bool, str]:
    """Send email via SMTP with multi-port retry support.

    通过 SMTP 协议发送邮件，支持多端口重试策略。
    当某个端口连接失败时，自动尝试 smtp_ports 列表中的下一个端口。
    每个端口内部还有独立的重试次数（retries）。

    参数:
        subject: 邮件主题
        body: 纯文本正文
        from_addr: 发件人地址
        to_addrs: 收件人地址列表
        smtp_host: SMTP 服务器主机名
        smtp_port: 默认 SMTP 端口
        smtp_user: SMTP 认证用户名
        smtp_password: SMTP 认证密码
        html_body: 可选的 HTML 正文（发送 multipart/alternative 邮件）
        smtp_ports: 可选的端口列表，用于多端口重试
        smtp_ssl_ports: 使用 SSL 直连的端口列表
        timeout: 连接超时（秒）
        retries: 每个端口的重试次数
        retry_backoff: 重试间隔退避时间（秒）
        use_tls: 是否启用 STARTTLS
        use_ssl: 是否使用 SSL 直连

    返回值:
        Tuple[bool, str]: (是否成功, 错误信息)
    """
    # 参数校验
    if not smtp_host or not from_addr:
        msg = "SMTP configuration error: host or from_addr missing"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients provided for SMTP send"
        logger.error(msg)
        return False, msg

    # 构建邮件消息
    # 如果有 HTML 正文，使用 multipart/alternative 格式（同时包含纯文本和 HTML）
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    # 端口去重并合并：默认端口 + 额外端口 + SSL 端口
    # dict.fromkeys 保持顺序的同时去重
    ports = list(dict.fromkeys((smtp_ports or [smtp_port]) + (smtp_ssl_ports or [])))
    ssl_ports_set = set(smtp_ssl_ports or [])
    retries = max(retries, 1)  # 至少尝试一次

    last_tb = ""
    # 外层循环：遍历所有可用端口
    for port in ports:
        # 内层循环：每个端口的重试
        for attempt in range(retries):
            server = None
            try:
                # 判断当前端口是否应使用 SSL 直连
                use_ssl_port = port in ssl_ports_set or use_ssl
                # STARTTLS 和 SSL 互斥
                use_tls_port = use_tls and not use_ssl_port
                # 根据是否 SSL 选择不同的 SMTP 类
                server = (
                    smtplib.SMTP_SSL(smtp_host, port, timeout=timeout)
                    if use_ssl_port
                    else smtplib.SMTP(smtp_host, port, timeout=timeout)
                )
                server.ehlo()  # 向服务器发送 EHLO 命令标识自己
                # 非 SSL 端口且非 localhost 时启用 STARTTLS 加密
                if use_tls_port and smtp_host.lower() != "localhost":
                    server.starttls()
                    server.ehlo()  # TLS 升级后需要重新 EHLO
                # 有认证信息时执行登录
                if smtp_user:
                    server.login(smtp_user, smtp_password)
                # 发送邮件
                server.sendmail(from_addr, to_addrs, msg.as_string())
                logger.info(f"✓ Email sent via SMTP (port {port})")
                return True, ""
            except Exception:
                # 最后一次重试失败时记录详细的异常堆栈
                if attempt == retries - 1:
                    last_tb = traceback.format_exc()
                    logger.error(
                        "✗ SMTP failed on port %s after %s attempts\n%s",
                        port,
                        retries,
                        last_tb,
                    )
                # 确保关闭 SMTP 连接
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass
                # 非最后一次重试时等待退避时间
                if attempt < retries - 1:
                    time.sleep(retry_backoff)
        # 当前端口所有重试失败，继续尝试下一个端口
        if last_tb:
            continue
    # 所有端口都失败
    return False, last_tb


# ======================
# 2. SendGrid API
# ======================
def _send_via_sendgrid(
    subject: str,
    body: str,
    to_addrs: List[str],
    from_addr: str,
    html_body: Optional[str] = None,
    api_key: Optional[str] = None,
    retries: int = 1,
    retry_backoff: float = 10.0,
) -> Tuple[bool, str]:
    """Send email via SendGrid API.

    通过 SendGrid REST API 发送邮件。
    SendGrid 返回 202 表示邮件已被接受（异步发送）。

    参数:
        subject: 邮件主题
        body: 纯文本正文
        to_addrs: 收件人列表
        from_addr: 发件人地址
        html_body: 可选的 HTML 正文
        api_key: SendGrid API 密钥，为空时从环境变量获取
        retries: 重试次数
        retry_backoff: 重试退避时间（秒）

    返回值:
        Tuple[bool, str]: (是否成功, 错误信息)
    """
    # API 密钥优先从参数获取，其次从环境变量
    api_key = api_key or os.getenv("SENDGRID_API_KEY")
    if not api_key or not from_addr:
        msg = "SendGrid config missing: API key or from_addr"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients for SendGrid"
        logger.error(msg)
        return False, msg

    attempts = max(retries, 1)
    last_tb = ""
    for attempt in range(attempts):
        try:
            # 构建 SendGrid v3 API 请求体
            content = [{"type": "text/plain", "value": body}]
            if html_body:
                content.append({"type": "text/html", "value": html_body})

            resp = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                json={
                    "personalizations": [{"to": [{"email": e} for e in to_addrs]}],
                    "from": {"email": from_addr},
                    "subject": subject,
                    "content": content,
                },
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=30,
            )
            # SendGrid 成功接受邮件返回 202
            if resp.status_code == 202:
                logger.info("✓ Email sent via SendGrid")
                return True, ""
            msg = f"SendGrid API error {resp.status_code}: {resp.text[:200]}"
            logger.error(msg)
            last_tb = msg
        except Exception:
            last_tb = traceback.format_exc()
            logger.error("✗ SendGrid send failed (attempt %s/%s)\n%s", attempt + 1, attempts, last_tb)
        if attempt < attempts - 1:
            time.sleep(retry_backoff)
    return False, last_tb


# ======================
# 3. Mailgun API
# ======================
def _send_via_mailgun(
    subject: str,
    body: str,
    to_addrs: List[str],
    from_addr: str,
    html_body: Optional[str] = None,
    api_key: Optional[str] = None,
    domain: Optional[str] = None,
    retries: int = 1,
    retry_backoff: float = 10.0,
) -> Tuple[bool, str]:
    """Send email via Mailgun API.

    通过 Mailgun REST API 发送邮件。
    使用 HTTP Basic Auth 认证（用户名固定为 "api"）。

    参数:
        subject: 邮件主题
        body: 纯文本正文
        to_addrs: 收件人列表
        from_addr: 发件人地址
        html_body: 可选的 HTML 正文
        api_key: Mailgun API 密钥
        domain: Mailgun 发送域名
        retries: 重试次数
        retry_backoff: 重试退避时间（秒）

    返回值:
        Tuple[bool, str]: (是否成功, 错误信息)
    """
    api_key = api_key or os.getenv("MAILGUN_API_KEY")
    domain = domain or os.getenv("MAILGUN_DOMAIN")
    if not api_key or not domain or not from_addr:
        msg = "Mailgun config missing: API key, domain, or from_addr"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients for Mailgun"
        logger.error(msg)
        return False, msg

    attempts = max(retries, 1)
    last_tb = ""
    for attempt in range(attempts):
        try:
            # Mailgun 使用 form-data 格式提交
            data = {"from": from_addr, "to": to_addrs, "subject": subject, "text": body}
            if html_body:
                data["html"] = html_body
            resp = httpx.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),  # Mailgun 使用 HTTP Basic Auth
                data=data,
                timeout=30,
            )
            if resp.status_code == 200:
                logger.info("✓ Email sent via Mailgun")
                return True, ""
            msg = f"Mailgun API error {resp.status_code}: {resp.text[:200]}"
            logger.error(msg)
            last_tb = msg
        except Exception:
            last_tb = traceback.format_exc()
            logger.error("✗ Mailgun send failed (attempt %s/%s)\n%s", attempt + 1, attempts, last_tb)
        if attempt < attempts - 1:
            time.sleep(retry_backoff)
    return False, last_tb


# ======================
# 4. Brevo API（原 Sendinblue）
# ======================
def _send_via_brevo(
    subject: str,
    body: str,
    to_addrs: List[str],
    from_addr: Optional[str] = None,
    html_body: Optional[str] = None,
    api_key: Optional[str] = None,
    from_name: str = "ResearchPulse",
    retries: int = 1,
    retry_backoff: float = 10.0,
) -> Tuple[bool, str]:
    """Send email via Brevo (formerly Sendinblue) API.

    通过 Brevo REST API 发送邮件。
    Brevo 成功返回 200 或 201。

    参数:
        subject: 邮件主题
        body: 纯文本正文
        to_addrs: 收件人列表
        from_addr: 可选的发件人地址
        html_body: 可选的 HTML 正文
        api_key: Brevo API 密钥
        from_name: 发件人显示名称
        retries: 重试次数
        retry_backoff: 重试退避时间（秒）

    返回值:
        Tuple[bool, str]: (是否成功, 错误信息)
    """
    api_key = api_key or os.getenv("BREVO_API_KEY")
    if not api_key:
        msg = "Brevo config missing: API key"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients for Brevo"
        logger.error(msg)
        return False, msg

    attempts = max(retries, 1)
    last_tb = ""
    for attempt in range(attempts):
        try:
            # 构建 Brevo API 请求体
            payload: Dict[str, Any] = {
                "sender": {"name": from_name, **({"email": from_addr} if from_addr else {})},
                "to": [{"email": e} for e in to_addrs],
                "subject": subject,
                "textContent": body,
            }
            if html_body:
                payload["htmlContent"] = html_body

            resp = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                timeout=30,
            )
            # Brevo 成功返回 200 或 201
            if resp.status_code in (200, 201):
                logger.info("✓ Email sent via Brevo")
                return True, ""
            msg = f"Brevo API error {resp.status_code}: {resp.text[:200]}"
            logger.error(msg)
            last_tb = msg
        except Exception:
            last_tb = traceback.format_exc()
            logger.error("✗ Brevo send failed (attempt %s/%s)\n%s", attempt + 1, attempts, last_tb)
        if attempt < attempts - 1:
            time.sleep(retry_backoff)
    return False, last_tb


# ======================
# 5. 统一发送接口（核心）
# 作为所有邮件发送的单一入口，根据 backend 参数路由到对应的后端实现
# ======================
def send_email(
    subject: str,
    body: str,
    to_addrs: Iterable[str],
    *,
    html_body: Optional[str] = None,
    backend: Literal["smtp", "sendgrid", "mailgun", "brevo"] = "smtp",
    from_addr: Optional[str] = None,
    **kwargs: Any,
) -> Tuple[bool, str]:
    """
    Unified email sending interface with multiple backend support.

    统一邮件发送接口。根据 backend 参数将请求路由到对应的后端实现。
    from_addr 如果未提供，会按优先级从 kwargs 和环境变量中自动获取。

    Args:
        subject: Email subject
            邮件主题
        body: Plain text body
            纯文本正文
        to_addrs: Recipient email addresses
            收件人地址（可迭代对象）
        html_body: Optional HTML body
            可选的 HTML 正文
        backend: Email backend ('smtp', 'sendgrid', 'mailgun', 'brevo')
            邮件发送后端
        from_addr: Sender email address
            发件人地址
        **kwargs: Backend-specific parameters
            各后端特有的参数（如 smtp_host, api_key 等）

    Returns:
        Tuple[bool, str]: (success, error_message)
            (是否成功, 错误信息字符串)

    Example:
        # SMTP with custom port
        send_email("Test", "Hi", ["user@example.com"], backend="smtp",
                   smtp_host="smtp.gmail.com", smtp_port=587,
                   smtp_user="user@gmail.com", smtp_password="password")

        # SendGrid
        send_email("Test", "Hi", ["user@example.com"], backend="sendgrid",
                   api_key="SG.xxx")

        # Brevo with custom sender name
        send_email("Test", "Hi", ["user@example.com"], backend="brevo",
                   from_name="MyApp")
    """
    # 清理收件人列表：去除空白和空字符串
    to_list = [e.strip() for e in to_addrs if e.strip()]
    if not to_list:
        msg = "Email send aborted: no valid recipients"
        logger.error(msg)
        return False, msg

    # 自动填充发件人地址（按优先级从多个来源获取）
    if not from_addr:
        from_addr = (
            kwargs.get("smtp_user")
            or os.getenv("EMAIL_FROM")
            or os.getenv("SENDGRID_FROM_EMAIL")
            or os.getenv("MAILGUN_FROM_EMAIL")
            or os.getenv("BREVO_FROM_EMAIL")
            or os.getenv("SMTP_USER")
        )
    if not from_addr:
        msg = f"Missing 'from_addr' for backend '{backend}'"
        logger.error(msg)
        return False, msg

    try:
        # 根据 backend 参数路由到对应的发送函数
        if backend == "smtp":
            return _send_via_smtp(
                subject=subject,
                body=body,
                from_addr=from_addr,
                to_addrs=to_list,
                html_body=html_body,
                smtp_host=kwargs.get("smtp_host", os.getenv("SMTP_HOST", "")),
                smtp_port=int(kwargs.get("smtp_port", os.getenv("SMTP_PORT", 587))),
                smtp_user=kwargs.get("smtp_user", os.getenv("SMTP_USER", "")),
                smtp_password=kwargs.get("smtp_password", os.getenv("SMTP_PASSWORD", "")),
                smtp_ports=kwargs.get("smtp_ports"),
                smtp_ssl_ports=kwargs.get("smtp_ssl_ports"),
                timeout=float(kwargs.get("timeout", 10.0)),
                retries=int(kwargs.get("retries", 3)),
                retry_backoff=float(kwargs.get("retry_backoff", 10.0)),
                use_tls=bool(kwargs.get("use_tls", True)),
                use_ssl=bool(kwargs.get("use_ssl", False)),
            )
        if backend == "sendgrid":
            return _send_via_sendgrid(
                subject=subject,
                body=body,
                to_addrs=to_list,
                from_addr=from_addr,
                html_body=html_body,
                api_key=kwargs.get("api_key", os.getenv("SENDGRID_API_KEY")),
                retries=int(kwargs.get("retries", 3)),
                retry_backoff=float(kwargs.get("retry_backoff", 10.0)),
            )
        if backend == "mailgun":
            return _send_via_mailgun(
                subject=subject,
                body=body,
                to_addrs=to_list,
                from_addr=from_addr,
                html_body=html_body,
                api_key=kwargs.get("api_key", os.getenv("MAILGUN_API_KEY")),
                domain=kwargs.get("domain", os.getenv("MAILGUN_DOMAIN")),
                retries=int(kwargs.get("retries", 3)),
                retry_backoff=float(kwargs.get("retry_backoff", 10.0)),
            )
        if backend == "brevo":
            return _send_via_brevo(
                subject=subject,
                body=body,
                to_addrs=to_list,
                from_addr=from_addr,
                html_body=html_body,
                api_key=kwargs.get("api_key", os.getenv("BREVO_API_KEY")),
                from_name=kwargs.get("from_name", os.getenv("BREVO_FROM_NAME", "ResearchPulse")),
                retries=int(kwargs.get("retries", 3)),
                retry_backoff=float(kwargs.get("retry_backoff", 10.0)),
            )
        # 不支持的后端
        msg = f"Unsupported email backend: {backend}"
        logger.error(msg)
        return False, msg
    except Exception:
        # 捕获所有未预期的异常，确保不会因为邮件发送失败而崩溃
        tb = traceback.format_exc()
        logger.error("Unexpected error in send_email (backend=%s)\n%s", backend, tb)
        return False, tb


# ======================
# 6. 多后端 Fallback（降级策略）
# 按优先级依次尝试多个后端，直到一个成功为止
# ======================
def send_email_with_fallback(
    subject: str,
    body: str,
    to_addrs: Iterable[str],
    *,
    html_body: Optional[str] = None,
    backends: Optional[List[Literal["smtp", "sendgrid", "mailgun", "brevo"]]] = None,
    **kwargs: Any,
) -> Tuple[bool, str]:
    """
    Try multiple backends in priority order until one succeeds.

    Default order: SendGrid > Brevo > Mailgun > SMTP

    按优先级依次尝试多个邮件后端，直到一个成功发送。
    默认优先级：SendGrid（最快） > Brevo > Mailgun > SMTP（最后兜底）

    Args:
        subject: Email subject
            邮件主题
        body: Plain text body
            纯文本正文
        to_addrs: Recipient email addresses
            收件人地址
        html_body: Optional HTML body
            可选的 HTML 正文
        backends: List of backends to try in order
            后端优先级列表，自定义降级顺序
        **kwargs: Backend-specific parameters
            各后端特有的参数

    Returns:
        Tuple[bool, str]: (success, error_message)
            (是否成功, 错误信息)
    """
    backends = backends or ["sendgrid", "brevo", "mailgun", "smtp"]
    for bk in backends:
        logger.info(f"→ Attempting email send via '{bk}'...")
        ok, tb = send_email(subject, body, to_addrs, html_body=html_body, backend=bk, **kwargs)
        if ok:
            return True, ""
    # 所有后端均失败
    msg = "✗ All email backends failed"
    logger.error(msg)
    return False, msg


# ======================
# 7. 通知邮件便捷函数
# 提供异步接口，内部通过线程池执行同步发送，避免阻塞事件循环
# ======================
async def send_notification_email(
    to_addr: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
) -> bool:
    """
    Send a notification email using configured backend.

    This is an async wrapper for the sync send_email function.

    使用配置中指定的后端发送通知邮件。
    这是一个异步包装器，将同步的邮件发送操作放到线程池中执行，
    避免阻塞 FastAPI 的异步事件循环。

    Args:
        to_addr: Recipient email address
            收件人邮箱地址
        subject: Email subject
            邮件主题
        body: Plain text body
            纯文本正文
        html_body: Optional HTML body
            可选的 HTML 正文

    Returns:
        bool: True if sent successfully
            发送成功返回 True
    """
    import asyncio

    def _send():
        # 从全局配置中获取邮件后端设置
        from settings import settings
        backend = settings.email_backend
        # 支持逗号分隔的多后端配置（依次尝试）
        backends = backend.split(",") if "," in backend else [backend]
        backends = [b.strip() for b in backends if b.strip()]

        # 按配置顺序尝试各后端
        for bk in backends:
            ok, _ = send_email(
                subject=subject,
                body=body,
                to_addrs=[to_addr],
                html_body=html_body,
                backend=bk,
                from_addr=settings.email_from,
            )
            if ok:
                return True
        return False

    # 在线程池中执行同步发送操作，避免阻塞异步事件循环
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send)


# ======================
# 8. 基于数据库配置的优先级发送
# 从数据库读取配置，按优先级顺序尝试发送，直到成功或全部失败
# ======================
async def send_email_with_priority(
    to_addrs: List[str],
    subject: str,
    body: str,
    session: Any,  # AsyncSession
    html_body: Optional[str] = None,
    backend_type: Optional[str] = None,  # 可选：限定后端类型
) -> Tuple[bool, str]:
    """Send email using database configs with priority-based failover.

    从数据库读取邮件配置，按优先级顺序尝试发送，直到成功或全部失败。
    这是推荐的通知邮件发送方式，支持多配置自动切换。

    Args:
        to_addrs: List of recipient email addresses
            收件人邮箱地址列表
        subject: Email subject
            邮件主题
        body: Plain text body
            纯文本正文
        session: Async database session
            异步数据库会话
        html_body: Optional HTML body
            可选的 HTML 正文
        backend_type: Optional backend type filter (smtp, sendgrid, mailgun, brevo)
            可选的后端类型筛选

    Returns:
        Tuple[bool, str]: (success, error_message)
            (是否成功, 错误信息)
    """
    from sqlalchemy import select
    from apps.crawler.models.config import EmailConfig

    # 构建查询：获取所有活跃配置，按优先级排序
    query = select(EmailConfig).where(
        EmailConfig.is_active == True
    )
    if backend_type:
        query = query.where(EmailConfig.backend_type == backend_type)
    query = query.order_by(EmailConfig.priority.asc())

    result = await session.execute(query)
    configs = result.scalars().all()

    if not configs:
        msg = "No active email configuration found in database"
        logger.error(msg)
        return False, msg

    # 按优先级尝试每个配置
    last_error = ""
    for config in configs:
        logger.info(f"→ Attempting email send via '{config.name}' (backend: {config.backend_type}, priority: {config.priority})...")

        ok, err = await _send_with_config(
            to_addrs=to_addrs,
            subject=subject,
            body=body,
            config=config,
            html_body=html_body,
        )

        if ok:
            logger.info(f"✓ Email sent successfully via '{config.name}'")
            return True, ""

        last_error = err
        logger.warning(f"✗ Failed to send via '{config.name}': {err}")

    # 所有配置都失败
    msg = f"All email configurations failed. Last error: {last_error}"
    logger.error(msg)
    return False, msg


async def _send_with_config(
    to_addrs: List[str],
    subject: str,
    body: str,
    config: Any,  # EmailConfig
    html_body: Optional[str] = None,
) -> Tuple[bool, str]:
    """Send email using a specific EmailConfig.

    使用指定的邮件配置发送邮件。
    """
    import asyncio

    def _send():
        from_addr = config.sender_email or ""

        if config.backend_type == "smtp":
            return send_email(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                html_body=html_body,
                backend="smtp",
                from_addr=from_addr or config.smtp_user,
                smtp_host=config.smtp_host,
                smtp_port=config.smtp_port,
                smtp_user=config.smtp_user,
                smtp_password=config.smtp_password,
                use_tls=config.smtp_use_tls,
            )
        elif config.backend_type == "sendgrid":
            return send_email(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                html_body=html_body,
                backend="sendgrid",
                from_addr=from_addr,
                sendgrid_api_key=config.sendgrid_api_key,
            )
        elif config.backend_type == "mailgun":
            return send_email(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                html_body=html_body,
                backend="mailgun",
                from_addr=from_addr,
                mailgun_api_key=config.mailgun_api_key,
                mailgun_domain=config.mailgun_domain,
            )
        elif config.backend_type == "brevo":
            return send_email(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                html_body=html_body,
                backend="brevo",
                from_addr=from_addr,
                brevo_api_key=config.brevo_api_key,
                brevo_from_name=config.brevo_from_name,
            )
        else:
            return False, f"Unknown backend type: {config.backend_type}"

    # 在线程池中执行同步发送
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send)
