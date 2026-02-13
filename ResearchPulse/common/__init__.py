"""Common utilities for ResearchPulse v2."""

from common.email import send_email, send_email_with_fallback, send_notification_email

__all__ = [
    "send_email",
    "send_email_with_fallback",
    "send_notification_email",
]
