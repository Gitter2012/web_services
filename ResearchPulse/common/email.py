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
    """Send email via SMTP with multi-port retry support."""
    if not smtp_host or not from_addr:
        msg = "SMTP configuration error: host or from_addr missing"
        logger.error(msg)
        return False, msg
    if not to_addrs:
        msg = "No recipients provided for SMTP send"
        logger.error(msg)
        return False, msg

    # Build message
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    # Deduplicate ports
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
    """Send email via SendGrid API."""
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
    """Send email via Mailgun API."""
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
    """Send email via Brevo (formerly Sendinblue) API."""
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
    Unified email sending interface with multiple backend support.

    Args:
        subject: Email subject
        body: Plain text body
        to_addrs: Recipient email addresses
        html_body: Optional HTML body
        backend: Email backend ('smtp', 'sendgrid', 'mailgun', 'brevo')
        from_addr: Sender email address
        **kwargs: Backend-specific parameters

    Returns:
        Tuple[bool, str]: (success, error_message)

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
    to_list = [e.strip() for e in to_addrs if e.strip()]
    if not to_list:
        msg = "Email send aborted: no valid recipients"
        logger.error(msg)
        return False, msg

    # Auto-fill from_addr (priority order)
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
        msg = f"Unsupported email backend: {backend}"
        logger.error(msg)
        return False, msg
    except Exception:
        tb = traceback.format_exc()
        logger.error("Unexpected error in send_email (backend=%s)\n%s", backend, tb)
        return False, tb


# ======================
# 6. 多后端 Fallback
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

    Args:
        subject: Email subject
        body: Plain text body
        to_addrs: Recipient email addresses
        html_body: Optional HTML body
        backends: List of backends to try in order
        **kwargs: Backend-specific parameters

    Returns:
        Tuple[bool, str]: (success, error_message)
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


# ======================
# 7. Convenience function for notifications
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

    Args:
        to_addr: Recipient email address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML body

    Returns:
        bool: True if sent successfully
    """
    import asyncio

    def _send():
        # Get backend from settings
        from settings import settings
        backend = settings.email_backend
        backends = backend.split(",") if "," in backend else [backend]
        backends = [b.strip() for b in backends if b.strip()]

        # Try backends in order
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

    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send)
