from __future__ import annotations

import os
import time
import smtplib
import httpx
import logging
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, Optional, List, Dict, Any, Literal, Tuple

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
    if not smtp_host or not from_addr:
        msg = "SMTP configuration error: host or from_addr missing"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients provided for SMTP send"
        logger.error(msg)
        return False, msg

    # 构建消息
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    # 端口去重
    ports = list(dict.fromkeys((smtp_ports or [smtp_port]) + (smtp_ssl_ports or [])))
    ssl_ports_set = set(smtp_ssl_ports or [])
    retries = max(retries, 1)

    last_tb = ""
    for port in ports:
        for attempt in range(retries):
            server = None
            try:
                use_ssl_port = port in ssl_ports_set or use_ssl
                use_tls_port = use_tls and not use_ssl_port
                server = (
                    smtplib.SMTP_SSL(smtp_host, port, timeout=timeout)
                    if use_ssl_port
                    else smtplib.SMTP(smtp_host, port, timeout=timeout)
                )
                server.ehlo()
                if use_tls_port and smtp_host.lower() != "localhost":
                    server.starttls()
                    server.ehlo()
                if smtp_user:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
                logger.info(f"✓ Email sent via SMTP (port {port})")
                return True, ""
            except Exception:
                if attempt == retries - 1:
                    last_tb = traceback.format_exc()
                    logger.error(
                        "✗ SMTP failed on port %s after %s attempts\n%s",
                        port,
                        retries,
                        last_tb,
                    )
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass
                if attempt < retries - 1:
                    time.sleep(retry_backoff)
        if last_tb:
            continue
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
            data = {"from": from_addr, "to": to_addrs, "subject": subject, "text": body}
            if html_body:
                data["html"] = html_body
            resp = httpx.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),
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
# 4. Brevo API
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
    统一邮件发送接口，支持多后端灵活配置。

    Args:
        subject: 邮件主题
        body: 纯文本正文
        to_addrs: 收件人列表
        html_body: 可选HTML正文
        backend: 后端类型 ('smtp', 'sendgrid', 'mailgun', 'brevo')
        from_addr: 发件人地址（若未提供，从环境变量读取）
        **kwargs: 后端特定参数（自动透传）

    Returns:
        Tuple[bool, str]: (success, traceback_msg)

    示例:
        # SendGrid（推荐）
        send_email("Test", "Hi", ["a@b.com"], backend="sendgrid")

        # SMTP（指定端口）
        send_email("Test", "Hi", ["a@b.com"], backend="smtp",
                   smtp_host="smtp.example.com", smtp_port=587,
                   smtp_user="user", smtp_password="pass")

        # Brevo（指定发件人名称）
        send_email("Test", "Hi", ["a@b.com"], backend="brevo", from_name="MyApp")
    """
    to_list = [e.strip() for e in to_addrs if e.strip()]
    if not to_list:
        msg = "Email send aborted: no valid recipients"
        logger.error(msg)
        return False, msg

    # 自动补全 from_addr（按优先级）
    if not from_addr:
        from_addr = (
            kwargs.get("smtp_user")  # SMTP场景
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
                smtp_ports=kwargs.get("smtp_ports", [587, 465, 2525, 2587]),
                smtp_ssl_ports=kwargs.get("smtp_ssl_ports", [465]),
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
                retries=int(kwargs.get("retries", 1)),
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
                retries=int(kwargs.get("retries", 1)),
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
                retries=int(kwargs.get("retries", 1)),
                retry_backoff=float(kwargs.get("retry_backoff", 10.0)),
            )
        msg = f"Unsupported email backend: {backend}"
        logger.error(msg)
        return False, msg
    except Exception:
        tb = traceback.format_exc()
        logger.error("Unexpected error in send_email (backend=%s)\n%s", backend, tb)
        return False, tb


# ======================
# 6. 多后端 Fallback（可选）
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
    按优先级尝试多个后端，任一成功即返回。
    默认顺序: SendGrid > Brevo > Mailgun > SMTP（适配受限网络）
    """
    backends = backends or ["sendgrid", "brevo", "mailgun", "smtp"]
    for bk in backends:
        logger.info(f"→ Attempting email send via '{bk}'...")
        ok, tb = send_email(subject, body, to_addrs, html_body=html_body, backend=bk, **kwargs)
        if ok:
            return True, ""
    msg = "✗ All email backends failed"
    logger.error(msg)
    return False, msg
