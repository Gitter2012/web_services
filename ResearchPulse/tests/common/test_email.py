"""Tests for common/email.py — email sending module.

邮件发送模块测试。

Run with: pytest tests/common/test_email.py -v
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock
import smtplib


class TestSendEmailValidation:
    """Test email sending validation.

    验证邮件发送参数校验。
    """

    def test_send_email_no_recipients(self):
        """Verify send_email rejects empty recipients.

        验证空收件人列表会触发错误。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=[],
            backend="smtp",
        )
        assert ok is False
        assert "no valid recipients" in err.lower()

    def test_send_email_whitespace_recipients(self):
        """Verify send_email filters whitespace recipients.

        验证空白收件人会被过滤。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["  ", ""],
            backend="smtp",
        )
        assert ok is False
        assert "no valid recipients" in err.lower()

    def test_send_email_missing_from_addr(self):
        """Verify send_email requires from_addr.

        验证缺少发件人地址会触发错误。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            ok, err = send_email(
                subject="Test",
                body="Hello",
                to_addrs=["user@example.com"],
                backend="smtp",
                from_addr=None,
            )
            assert ok is False
            assert "from_addr" in err.lower()

    def test_send_email_unsupported_backend(self):
        """Verify send_email rejects unsupported backend.

        验证不支持的后端会触发错误。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="invalid_backend",
            from_addr="sender@example.com",
        )
        assert ok is False
        assert "unsupported" in err.lower()


class TestSMTPBackend:
    """Test SMTP backend.

    验证 SMTP 后端功能。
    """

    def test_smtp_missing_host(self):
        """Verify SMTP requires host.

        验证 SMTP 需要主机名。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="smtp",
            from_addr="sender@example.com",
            smtp_host="",
        )
        assert ok is False
        assert "host" in err.lower() or "missing" in err.lower()

    @patch("smtplib.SMTP")
    def test_smtp_send_success(self, mock_smtp_class):
        """Verify successful SMTP send.

        验证 SMTP 发送成功。

        Args:
            mock_smtp_class: Mocked SMTP class.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        ok, err = send_email(
            subject="Test Subject",
            body="Test Body",
            to_addrs=["user@example.com"],
            backend="smtp",
            from_addr="sender@example.com",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user",
            smtp_password="password",
        )

        # Should attempt connection
        mock_smtp_class.assert_called_once()

    @patch("smtplib.SMTP")
    def test_smtp_send_with_html(self, mock_smtp_class):
        """Verify SMTP sends multipart with HTML.

        验证 SMTP 发送 HTML 邮件。

        Args:
            mock_smtp_class: Mocked SMTP class.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        ok, err = send_email(
            subject="Test",
            body="Plain text",
            html_body="<p>HTML content</p>",
            to_addrs=["user@example.com"],
            backend="smtp",
            from_addr="sender@example.com",
            smtp_host="smtp.example.com",
            smtp_port=587,
        )

        mock_smtp_class.assert_called_once()


class TestSendGridBackend:
    """Test SendGrid backend.

    验证 SendGrid 后端功能。
    """

    def test_sendgrid_missing_api_key(self):
        """Verify SendGrid requires API key.

        验证 SendGrid 需要 API 密钥。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        with patch.dict(os.environ, {}, clear=True):
            ok, err = send_email(
                subject="Test",
                body="Hello",
                to_addrs=["user@example.com"],
                backend="sendgrid",
                from_addr="sender@example.com",
            )
            assert ok is False
            assert "api key" in err.lower() or "missing" in err.lower()

    @patch("httpx.post")
    def test_sendgrid_send_success(self, mock_post):
        """Verify successful SendGrid send.

        验证 SendGrid 发送成功。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="sendgrid",
            from_addr="sender@example.com",
            api_key="SG.test_key",
        )

        assert ok is True
        assert err == ""

    @patch("httpx.post")
    def test_sendgrid_send_failure(self, mock_post):
        """Verify SendGrid failure handling.

        验证 SendGrid 失败处理。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="sendgrid",
            from_addr="sender@example.com",
            api_key="invalid_key",
            retries=1,
        )

        assert ok is False


class TestMailgunBackend:
    """Test Mailgun backend.

    验证 Mailgun 后端功能。
    """

    def test_mailgun_missing_config(self):
        """Verify Mailgun requires API key and domain.

        验证 Mailgun 需要 API 密钥和域名。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        with patch.dict(os.environ, {}, clear=True):
            ok, err = send_email(
                subject="Test",
                body="Hello",
                to_addrs=["user@example.com"],
                backend="mailgun",
                from_addr="sender@example.com",
            )
            assert ok is False
            assert "api key" in err.lower() or "domain" in err.lower() or "missing" in err.lower()

    @patch("httpx.post")
    def test_mailgun_send_success(self, mock_post):
        """Verify successful Mailgun send.

        验证 Mailgun 发送成功。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="mailgun",
            from_addr="sender@example.com",
            api_key="key-test",
            domain="mg.example.com",
        )

        assert ok is True
        assert err == ""


class TestBrevoBackend:
    """Test Brevo backend.

    验证 Brevo 后端功能。
    """

    def test_brevo_missing_api_key(self):
        """Verify Brevo requires API key.

        验证 Brevo 需要 API 密钥。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        with patch.dict(os.environ, {}, clear=True):
            ok, err = send_email(
                subject="Test",
                body="Hello",
                to_addrs=["user@example.com"],
                backend="brevo",
                from_addr="sender@example.com",
            )
            assert ok is False
            assert "api key" in err.lower()

    @patch("httpx.post")
    def test_brevo_send_success(self, mock_post):
        """Verify successful Brevo send.

        验证 Brevo 发送成功。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        ok, err = send_email(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backend="brevo",
            from_addr="sender@example.com",
            api_key="xkeysib-test",
        )

        assert ok is True
        assert err == ""


class TestFallbackMechanism:
    """Test multi-backend fallback.

    验证多后端降级机制。
    """

    @patch("httpx.post")
    def test_fallback_to_second_backend(self, mock_post):
        """Verify fallback to second backend on failure.

        验证第一个后端失败后降级到第二个后端。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email_with_fallback

        # First call fails (SendGrid 401), second call succeeds (Brevo 201)
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] == 1:
                mock_response.status_code = 401
                mock_response.text = "Unauthorized"
            else:
                mock_response.status_code = 201
            return mock_response

        mock_post.side_effect = side_effect

        ok, err = send_email_with_fallback(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backends=["sendgrid", "brevo"],
            from_addr="sender@example.com",
            api_key="test_key",
            retries=1,
        )

        assert ok is True
        assert call_count[0] == 2

    @patch("httpx.post")
    def test_all_backends_fail(self, mock_post):
        """Verify error when all backends fail.

        验证所有后端都失败时返回错误。

        Args:
            mock_post: Mocked httpx.post.

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email_with_fallback

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        ok, err = send_email_with_fallback(
            subject="Test",
            body="Hello",
            to_addrs=["user@example.com"],
            backends=["sendgrid", "brevo"],
            from_addr="sender@example.com",
            api_key="test_key",
            retries=1,
        )

        assert ok is False
        assert "all" in err.lower() or "failed" in err.lower()


class TestNotificationEmail:
    """Test notification email async wrapper.

    验证通知邮件异步包装器。
    """

    @pytest.mark.asyncio
    async def test_send_notification_email_success(self):
        """Verify send_notification_email works.

        验证通知邮件发送成功。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_notification_email

        with patch("common.email.send_email") as mock_send:
            mock_send.return_value = (True, "")

            with patch("settings.settings") as mock_settings:
                mock_settings.email_backend = "smtp"
                mock_settings.email_from = "sender@example.com"

                ok = await send_notification_email(
                    to_addr="user@example.com",
                    subject="Test",
                    body="Hello",
                )

                assert ok is True

    @pytest.mark.asyncio
    async def test_send_notification_email_with_html(self):
        """Verify send_notification_email with HTML.

        验证带 HTML 的通知邮件发送。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_notification_email

        with patch("common.email.send_email") as mock_send:
            mock_send.return_value = (True, "")

            with patch("settings.settings") as mock_settings:
                mock_settings.email_backend = "smtp"
                mock_settings.email_from = "sender@example.com"

                ok = await send_notification_email(
                    to_addr="user@example.com",
                    subject="Test",
                    body="Plain text",
                    html_body="<p>HTML</p>",
                )

                assert ok is True


class TestRecipientCleaning:
    """Test recipient list cleaning.

    验证收件人列表清理。
    """

    def test_clean_whitespace_from_recipients(self):
        """Verify whitespace is stripped from recipients.

        验证收件人地址空白被去除。

        Returns:
            None: This test does not return a value.
        """
        from common.email import send_email

        with patch("common.email._send_via_smtp") as mock_smtp:
            mock_smtp.return_value = (True, "")

            send_email(
                subject="Test",
                body="Hello",
                to_addrs=["  user@example.com  ", "  other@example.com"],
                backend="smtp",
                from_addr="sender@example.com",
                smtp_host="smtp.example.com",
            )

            # Check that whitespace was stripped
            called_to_addrs = mock_smtp.call_args[1]["to_addrs"]
            assert called_to_addrs == ["user@example.com", "other@example.com"]
