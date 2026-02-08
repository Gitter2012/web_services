from __future__ import annotations

from common.email import send_email


class DummySMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = False
        self.sent = False
        self.msg = ""

    def ehlo(self):
        return None

    def starttls(self):
        self.started_tls = True
        return None

    def login(self, user, password):
        self.logged_in = True
        return None

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent = True
        self.msg = msg
        return None

    def quit(self):
        return None


def test_send_email_html(monkeypatch) -> None:
    dummy = DummySMTP("smtp.example.com", 587)
    monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout=None: dummy)

    ok, _ = send_email(
        subject="Hello",
        body="Plain",
        html_body="<b>HTML</b>",
        from_addr="from@example.com",
        to_addrs=["to@example.com"],
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
        use_tls=True,
        use_ssl=False,
    )

    assert ok is True
    assert dummy.sent is True
    assert "multipart/alternative" in dummy.msg
    assert "text/html" in dummy.msg


def test_send_email_multi_ports(monkeypatch) -> None:
    calls = []

    def smtp_factory(host, port, timeout=None):
        calls.append(port)
        if port == 587:
            raise RuntimeError("fail 587")
        return DummySMTP(host, port)

    monkeypatch.setattr("smtplib.SMTP", smtp_factory)
    monkeypatch.setattr("smtplib.SMTP_SSL", smtp_factory)

    ok, _ = send_email(
        subject="Hello",
        body="Plain",
        from_addr="from@example.com",
        to_addrs=["to@example.com"],
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
        smtp_ports=[587, 465],
        smtp_ssl_ports=[465],
        retries=1,
    )

    assert ok is True
    assert calls == [587, 465]


def test_send_email_missing_host() -> None:
    ok, _ = send_email(
        subject="Hello",
        body="Plain",
        from_addr="from@example.com",
        to_addrs=["to@example.com"],
        smtp_host="",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
    )
    assert ok is False
