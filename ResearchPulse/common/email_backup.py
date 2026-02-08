from __future__ import annotations

import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, Optional


def send_email(
    subject: str,
    body: str,
    from_addr: str,
    to_addrs: Iterable[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    use_tls: bool = True,
    use_ssl: bool = False,
    html_body: Optional[str] = None,
    smtp_ports: Optional[Iterable[int]] = None,
    smtp_ssl_ports: Optional[Iterable[int]] = None,
    timeout: float = 10.0,
    retries: int = 5,
    retry_backoff: float = 30.0,
) -> None:
    if not smtp_host:
        raise ValueError("SMTP host is required")
    if not from_addr:
        raise ValueError("From address is required")

    if html_body:
        msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    ports = list(smtp_ports) if smtp_ports else [smtp_port]
    ssl_ports = set(smtp_ssl_ports or [])
    if smtp_ssl_ports:
        for ssl_port in smtp_ssl_ports:
            if ssl_port not in ports:
                ports.append(ssl_port)
    attempts = max(retries, 1)
    last_error: Optional[Exception] = None

    for port in ports:
        for attempt in range(attempts):
            server = None
            try:
                use_ssl_port = port in ssl_ports if ssl_ports else use_ssl
                use_tls_port = use_tls and not use_ssl_port

                if use_ssl_port:
                    server = smtplib.SMTP_SSL(smtp_host, port, timeout=timeout)
                else:
                    server = smtplib.SMTP(smtp_host, port, timeout=timeout)

                server.ehlo()
                if use_tls_port:
                    server.starttls()
                    server.ehlo()
                if smtp_user:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, list(to_addrs), msg.as_string())
                server.quit()
                return
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = exc
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass
                if attempt < attempts - 1:
                    time.sleep(retry_backoff)

    if last_error:
        raise RuntimeError(
            f"SMTP send failed after trying ports {ports}: {last_error}"
        ) from last_error
    raise RuntimeError(f"SMTP send failed after trying ports {ports}: {last_error}")
