"""Tests for common/feature_config.py — in-memory behaviour (no DB).

特性配置内存行为测试（不依赖数据库）。
"""

from __future__ import annotations

import pytest


class TestFeatureConfigDefaults:
    """Verify DEFAULT_CONFIGS constants.

    验证默认配置常量内容。
    """

    def test_default_configs_is_dict(self):
        """Verify DEFAULT_CONFIGS is a non-empty dict.

        验证 DEFAULT_CONFIGS 为非空字典。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        assert isinstance(DEFAULT_CONFIGS, dict)
        assert len(DEFAULT_CONFIGS) > 0

    def test_all_feature_keys_have_prefix(self):
        """Verify all feature keys use the ``feature.`` prefix.

        验证特性开关键使用 ``feature.`` 前缀。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        feature_keys = [k for k in DEFAULT_CONFIGS if k.startswith("feature.")]
        assert len(feature_keys) == 10  # 10 feature toggles

    def test_all_values_are_tuples(self):
        """Verify DEFAULT_CONFIGS values are tuples.

        验证默认配置值为二元组且类型正确。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        for key, val in DEFAULT_CONFIGS.items():
            assert isinstance(val, tuple), f"Key {key} value is not a tuple"
            assert len(val) == 2, f"Key {key} tuple has wrong length"
            assert isinstance(val[0], str), f"Key {key} default value not str"
            assert isinstance(val[1], str), f"Key {key} description not str"

    def test_extended_features_default_false(self):
        """Verify extended feature toggles default to false.

        验证扩展功能默认关闭。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        extended_features = [
            "feature.ai_processor",
            "feature.embedding",
            "feature.event_clustering",
            "feature.topic_radar",
            "feature.action_items",
            "feature.report_generation",
        ]
        for key in extended_features:
            assert key in DEFAULT_CONFIGS
            assert DEFAULT_CONFIGS[key][0] == "false"

    def test_original_features_default_true(self):
        """Verify core feature toggles default to true.

        验证基础功能默认开启。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        for key in ["feature.crawler", "feature.backup", "feature.cleanup"]:
            assert key in DEFAULT_CONFIGS
            assert DEFAULT_CONFIGS[key][0] == "true"

    def test_scheduler_keys_present(self):
        """Verify scheduler config keys exist.

        验证调度器相关配置键存在。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        scheduler_keys = [k for k in DEFAULT_CONFIGS if k.startswith("scheduler.")]
        assert len(scheduler_keys) >= 7

    def test_ai_keys_present(self):
        """Verify AI config keys exist.

        验证 AI 相关配置键存在。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        ai_keys = [k for k in DEFAULT_CONFIGS if k.startswith("ai.")]
        assert len(ai_keys) >= 5

    def test_embedding_keys_present(self):
        """Verify embedding config keys exist.

        验证嵌入计算相关配置键存在。

        Returns:
            None: This test does not return a value.
        """
        from common.feature_config import DEFAULT_CONFIGS

        emb_keys = [k for k in DEFAULT_CONFIGS if k.startswith("embedding.")]
        assert len(emb_keys) >= 5


class TestFeatureConfigServiceInMemory:
    """Test FeatureConfigService with pre-populated cache (no DB).

    验证配置服务在内存缓存场景下的行为。
    """

    def _make_service(self):
        """Create a service instance with cached defaults.

        构建加载默认配置到缓存的服务实例。

        Returns:
            common.feature_config.FeatureConfigService: Config service instance.
        """
        from common.feature_config import DEFAULT_CONFIGS, FeatureConfigService
        import time

        svc = FeatureConfigService()
        # Bypass DB by loading defaults directly into cache
        svc._cache = {k: v for k, (v, _) in DEFAULT_CONFIGS.items()}
        svc._cache_ts = time.monotonic()
        return svc

    def test_get_existing_key(self):
        """Verify retrieving an existing key.

        验证可获取已存在的配置键。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get("feature.crawler") == "true"

    def test_get_missing_key_returns_default(self):
        """Verify missing key returns default value.

        验证缺失键返回默认值。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get("nonexistent.key") is None
        assert svc.get("nonexistent.key", "fallback") == "fallback"

    def test_get_bool_true(self):
        """Verify boolean getter returns True.

        验证布尔读取返回 True。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get_bool("feature.crawler") is True

    def test_get_bool_false(self):
        """Verify boolean getter returns False.

        验证布尔读取返回 False。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get_bool("feature.ai_processor") is False

    def test_get_bool_missing_returns_default(self):
        """Verify boolean getter fallback value.

        验证布尔读取在缺失键时返回默认值。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get_bool("missing.key") is False
        assert svc.get_bool("missing.key", True) is True

    def test_get_int(self):
        """Verify integer getter parsing.

        验证整数读取与解析结果。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get_int("scheduler.crawl_interval_hours") == 6

    def test_get_int_invalid_returns_default(self):
        """Verify invalid integer returns default.

        验证无法解析为整数时返回默认值。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        # "true" cannot be parsed as int
        assert svc.get_int("feature.crawler", 99) == 99

    def test_get_float(self):
        """Verify float getter parsing.

        验证浮点数读取与解析结果。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert abs(svc.get_float("event.rule_weight") - 0.4) < 0.01

    def test_get_float_invalid_returns_default(self):
        """Verify invalid float returns default.

        验证无法解析为浮点数时返回默认值。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        assert svc.get_float("feature.crawler", 1.5) == 1.5

    def test_get_all(self):
        """Verify retrieving all configs.

        验证获取全部配置。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        all_configs = svc.get_all()
        assert isinstance(all_configs, dict)
        assert "feature.crawler" in all_configs

    def test_get_all_with_prefix(self):
        """Verify retrieving configs by prefix.

        验证按前缀筛选配置。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        features = svc.get_all("feature.")
        assert all(k.startswith("feature.") for k in features)
        assert len(features) == 10

    def test_get_all_prefix_no_match(self):
        """Verify prefix with no match returns empty dict.

        验证前缀无匹配时返回空字典。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        result = svc.get_all("nonexistent.")
        assert result == {}

    def test_cache_update_reflected(self):
        """Verify direct cache updates are visible.

        验证直接写入缓存后读取立即生效。

        Returns:
            None: This test does not return a value.
        """
        svc = self._make_service()
        svc._cache["feature.ai_processor"] = "true"
        assert svc.get_bool("feature.ai_processor") is True
