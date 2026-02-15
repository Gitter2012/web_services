"""Tests for settings.py — configuration loading and validation.

针对配置加载与校验逻辑的测试用例集合。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestSettingsProperties:
    """Verify Settings fields and computed properties.

    验证配置字段与计算属性是否正确。
    """

    def test_app_name_exists(self):
        """Verify ``app_name`` is set.

        验证 ``app_name`` 配置存在且正确。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.app_name == "ResearchPulse"

    def test_database_url_contains_driver(self):
        """Verify async database URL has a driver.

        验证异步数据库连接字符串包含正确驱动。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert "aiomysql" in s.database_url or "sqlite" in s.database_url.lower()

    def test_database_url_sync_contains_driver(self):
        """Verify sync database URL has a driver.

        验证同步数据库连接字符串包含正确驱动。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert "pymysql" in s.database_url_sync or "sqlite" in s.database_url_sync.lower()

    def test_url_prefix_exists(self):
        """Verify ``url_prefix`` is set.

        验证 ``url_prefix`` 配置存在且正确。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.url_prefix == "/researchpulse"

    def test_arxiv_categories_list_parsing(self):
        """Verify ``arxiv_categories_list`` parsing.

        验证 arXiv 分类列表解析正确。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        cats = s.arxiv_categories_list
        assert isinstance(cats, list)
        assert len(cats) >= 1
        # Each entry should be a trimmed non-empty string
        for c in cats:
            assert c == c.strip()
            assert len(c) > 0


class TestSettingsFeatureToggles:
    """Verify feature toggle behavior.

    验证特性开关相关配置。
    """

    def test_ai_provider_exists(self):
        """Verify ``ai_provider`` is configured.

        验证 AI 服务提供方配置存在。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.ai_provider in ("ollama", "openai")

    def test_embedding_provider_exists(self):
        """Verify ``embedding_provider`` is configured.

        验证向量嵌入提供方配置存在。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.embedding_provider in ("sentence-transformers", "openai")

    def test_embedding_dimension_positive(self):
        """Verify embedding dimension is positive.

        验证嵌入维度为正数。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.embedding_dimension > 0

    def test_milvus_port_valid(self):
        """Verify Milvus port is within valid range.

        验证 Milvus 端口号有效。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert 1 <= s.milvus_port <= 65535

    def test_event_clustering_weights_sum_to_one(self):
        """Verify event clustering weights sum to 1.0.

        验证事件聚类权重之和接近 1.0。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert abs(s.event_rule_weight + s.event_semantic_weight - 1.0) < 0.01

    def test_topic_discovery_settings_positive(self):
        """Verify topic discovery settings are positive.

        验证话题发现相关参数为正数。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.topic_min_frequency >= 1
        assert s.topic_lookback_days >= 1


class TestSettingsJWT:
    """Verify JWT settings.

    验证 JWT 相关配置。
    """

    def test_jwt_secret_key_exists(self):
        """Verify JWT secret key is set.

        验证 JWT 密钥已配置。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.jwt_secret_key
        assert len(s.jwt_secret_key) > 0

    def test_jwt_algorithm_exists(self):
        """Verify JWT algorithm is set.

        验证 JWT 算法配置存在且合法。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.jwt_algorithm in ("HS256", "HS384", "HS512")

    def test_jwt_token_expiry_positive(self):
        """Verify JWT token expiry values are positive.

        验证 JWT 令牌过期时间配置为正数。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.jwt_access_token_expire_minutes > 0
        assert s.jwt_refresh_token_expire_days > 0


class TestSettingsDatabase:
    """Verify database settings.

    验证数据库相关配置。
    """

    def test_db_port_valid(self):
        """Verify database port is within valid range.

        验证数据库端口号有效。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert 1 <= s.db_port <= 65535

    def test_db_pool_size_positive(self):
        """Verify database pool size is positive.

        验证数据库连接池大小为正数。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.db_pool_size >= 1

    def test_db_max_overflow_non_negative(self):
        """Verify database max overflow is non-negative.

        验证数据库连接池溢出参数为非负。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.db_max_overflow >= 0


class TestSettingsArxiv:
    """Verify arXiv settings.

    验证 arXiv 相关配置。
    """

    def test_arxiv_max_results_positive(self):
        """Verify arXiv max results is positive.

        验证 arXiv 最大结果数为正。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.arxiv_max_results > 0

    def test_arxiv_delay_base_positive(self):
        """Verify arXiv delay base is positive.

        验证 arXiv 请求延迟基准为正。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.arxiv_delay_base > 0


class TestSettingsEmail:
    """Verify email settings.

    验证邮件相关配置。
    """

    def test_smtp_port_valid(self):
        """Verify SMTP port is within valid range.

        验证 SMTP 端口号有效。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert 1 <= s.smtp_port <= 65535

    def test_smtp_timeout_positive(self):
        """Verify SMTP timeout is positive.

        验证 SMTP 超时时间为正数。

        Returns:
            None: This test does not return a value.
        """
        from settings import Settings

        s = Settings()
        assert s.smtp_timeout > 0
