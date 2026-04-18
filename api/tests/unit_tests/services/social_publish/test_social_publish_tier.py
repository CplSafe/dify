"""TierResolver unit tests.

Threshold-only logic (``_resolve_from_consume``) is exercised against
edge cases without touching Redis or the DB. The class-level path is
covered with mocked db.session + a fake redis to keep the suite hermetic.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.social_publish_tier import (
    TIER_THRESHOLDS,
    TenantTier,
    TierResolver,
    _resolve_from_consume,
)


class TestThresholdResolution:
    @pytest.mark.parametrize(
        ("consume_cny", "expected_tier"),
        [
            (Decimal(1000), "high"),
            (Decimal(500), "high"),  # exact match
            (Decimal("499.99"), "mid"),
            (Decimal(50), "mid"),  # exact match
            (Decimal("49.99"), "low"),
            (Decimal(0), "low"),
        ],
    )
    def test_picks_highest_satisfied_tier(self, consume_cny, expected_tier):
        tier = _resolve_from_consume(consume_cny)
        assert tier.name == expected_tier

    def test_thresholds_are_in_descending_order(self):
        # Future maintainers might re-shuffle TIER_THRESHOLDS — guard that
        # the descending invariant we rely on stays intact.
        thresholds = [t[1] for t in TIER_THRESHOLDS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_low_tier_has_zero_threshold(self):
        # The "low" tier is the catch-all — its threshold MUST be 0 so
        # _resolve_from_consume never falls off the end.
        names_to_threshold = {t[0]: t[1] for t in TIER_THRESHOLDS}
        assert names_to_threshold["low"] == 0


class TestRedisCache:
    @pytest.fixture
    def fake_redis(self) -> MagicMock:
        rc = MagicMock()
        rc.get = MagicMock(return_value=None)
        rc.setex = MagicMock(return_value=True)
        rc.delete = MagicMock(return_value=1)
        return rc

    def test_cache_miss_then_hit(self, fake_redis):
        resolver = TierResolver(cache_ttl_seconds=300, redis=fake_redis)
        # First call hits the DB (mocked) and writes to cache.
        with patch("services.social_publish_tier.db") as db:
            db.session.execute.return_value.scalar.return_value = Decimal(1000)
            tier = resolver.get_tier("tenant-a")
            assert tier.name == "high"

        # Second call returns from cache — no DB query.
        fake_redis.get.return_value = (
            b'{"name":"high","concurrent":10,"priority":9,"max_pending":200}'
        )
        with patch("services.social_publish_tier.db") as db:
            tier2 = resolver.get_tier("tenant-a")
            assert tier2.name == "high"
            db.session.execute.assert_not_called()

    def test_corrupt_cache_falls_through_to_db(self, fake_redis):
        # Garbage in Redis must not 500 the request — we re-query the DB.
        fake_redis.get.return_value = b"not json"
        resolver = TierResolver(cache_ttl_seconds=300, redis=fake_redis)
        with patch("services.social_publish_tier.db") as db:
            db.session.execute.return_value.scalar.return_value = Decimal(0)
            tier = resolver.get_tier("tenant-a")
            assert tier.name == "low"

    def test_invalidate_deletes_cache_key(self, fake_redis):
        resolver = TierResolver(cache_ttl_seconds=300, redis=fake_redis)
        resolver.invalidate("tenant-x")
        fake_redis.delete.assert_called_once_with("sau:tier:tenant-x")

    def test_zero_consumption_returns_low_tier(self, fake_redis):
        resolver = TierResolver(cache_ttl_seconds=300, redis=fake_redis)
        with patch("services.social_publish_tier.db") as db:
            db.session.execute.return_value.scalar.return_value = None
            tier = resolver.get_tier("tenant-a")
        assert tier == TenantTier(
            name="low", concurrent=2, priority=1, max_pending=50
        )
