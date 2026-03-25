"""
M4 tests: Semantic cache with pgvector + SWR (stale-while-revalidate).

Run: pytest tests/test_m4_semantic_cache.py -v
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────


class TestSemanticCacheConfig:
    def test_semantic_cache_enabled_setting_exists(self):
        from app.config import settings
        assert hasattr(settings, "semantic_cache_enabled")
        assert isinstance(settings.semantic_cache_enabled, bool)

    def test_semantic_cache_threshold_exists(self):
        from app.config import settings
        assert hasattr(settings, "semantic_cache_threshold")
        assert 0.9 <= settings.semantic_cache_threshold <= 1.0

    def test_semantic_cache_swr_ttl_exists(self):
        from app.config import settings
        assert hasattr(settings, "semantic_cache_swr_ttl_seconds")
        assert settings.semantic_cache_swr_ttl_seconds > 0


# ──────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("sqlalchemy"),
    reason="sqlalchemy not installed in test env",
)
class TestQueryCacheModel:
    def test_model_importable(self):
        from app.models.query_cache import QueryCache
        assert QueryCache is not None

    def test_model_has_required_columns(self):
        from app.models.query_cache import QueryCache
        cols = {c.name for c in QueryCache.__table__.columns}
        assert "id" in cols
        assert "query_text" in cols
        assert "query_type" in cols
        assert "model_id" in cols
        assert "query_embedding" in cols
        assert "response_json" in cols
        assert "last_verified_at" in cols

    def test_model_table_name(self):
        from app.models.query_cache import QueryCache
        assert QueryCache.__tablename__ == "query_cache"


# ──────────────────────────────────────────────
# Stale / fresh logic
# ──────────────────────────────────────────────


class TestSemanticCacheStaleness:
    def test_fresh_entry_not_stale(self):
        from app.services.semantic_cache import is_stale

        last_verified = datetime.now(timezone.utc) - timedelta(hours=1)
        assert not is_stale(last_verified, swr_ttl_seconds=86400)

    def test_old_entry_is_stale(self):
        from app.services.semantic_cache import is_stale

        last_verified = datetime.now(timezone.utc) - timedelta(days=10)
        assert is_stale(last_verified, swr_ttl_seconds=86400)

    def test_exactly_at_boundary_is_stale(self):
        from app.services.semantic_cache import is_stale

        last_verified = datetime.now(timezone.utc) - timedelta(seconds=86401)
        assert is_stale(last_verified, swr_ttl_seconds=86400)

    def test_none_last_verified_is_stale(self):
        from app.services.semantic_cache import is_stale

        assert is_stale(None, swr_ttl_seconds=86400)


# ──────────────────────────────────────────────
# Threshold check
# ──────────────────────────────────────────────


class TestThresholdCheck:
    def test_above_threshold_is_hit(self):
        from app.services.semantic_cache import is_cache_hit

        assert is_cache_hit(similarity=0.97, threshold=0.95)

    def test_exact_threshold_is_hit(self):
        from app.services.semantic_cache import is_cache_hit

        assert is_cache_hit(similarity=0.95, threshold=0.95)

    def test_below_threshold_is_miss(self):
        from app.services.semantic_cache import is_cache_hit

        assert not is_cache_hit(similarity=0.94, threshold=0.95)

    def test_zero_similarity_is_miss(self):
        from app.services.semantic_cache import is_cache_hit

        assert not is_cache_hit(similarity=0.0, threshold=0.95)


# ──────────────────────────────────────────────
# Service functions (no real DB — guard against disabled)
# ──────────────────────────────────────────────


class TestSemanticCacheServiceDisabled:
    def test_get_returns_none_when_disabled(self):
        import asyncio
        from unittest.mock import patch

        with patch("app.config.settings") as mock_settings:
            mock_settings.semantic_cache_enabled = False
            mock_settings.semantic_cache_threshold = 0.95
            mock_settings.semantic_cache_swr_ttl_seconds = 604800
            mock_settings.embedding_dim = 384

            from app.services.semantic_cache import semantic_cache_get
            result = asyncio.get_event_loop().run_until_complete(
                semantic_cache_get("metformin for diabetes", "drug", "claude-haiku")
            )
        assert result == (None, None)

    def test_set_noop_when_disabled(self):
        import asyncio
        from unittest.mock import patch

        with patch("app.config.settings") as mock_settings:
            mock_settings.semantic_cache_enabled = False
            mock_settings.semantic_cache_threshold = 0.95
            mock_settings.semantic_cache_swr_ttl_seconds = 604800
            mock_settings.embedding_dim = 384

            from app.services.semantic_cache import semantic_cache_set
            # Must not raise
            asyncio.get_event_loop().run_until_complete(
                semantic_cache_set("metformin", "drug", "claude-haiku", {"drug_name": "metformin"})
            )
