"""Authentication module for ResearchPulse v2.

认证模块包入口。
"""

from apps.auth.api import router
from apps.auth.service import AuthService

__all__ = ["router", "AuthService"]
