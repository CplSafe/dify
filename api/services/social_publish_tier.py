"""Tenant tiering for the publish-center.

Each workspace is assigned a tier based on its 90-day spend (sum of
``BillingRecord`` rows with ``record_type='deduction'``). The tier
determines:

- the Celery task priority sent to sau (high tier publishes jump the
  queue),
- the per-tenant concurrent worker cap (sau side enforces),
- the per-tenant max-pending quota (Dify side enforces in
  ``TaskService.create_task``).

Resolution is cached in Redis for ``SOCIAL_PUBLISH_TIER_CACHE_TTL_SECONDS``
to keep the aggregate(BillingRecord) query off the hot path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func

from configs import dify_config
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.creator import BillingRecord, BillingRecordType

logger = logging.getLogger(__name__)

TierName = Literal["high", "mid", "low"]


@dataclass(frozen=True)
class TenantTier:
    name: TierName
    concurrent: int
    priority: int
    max_pending: int


# Higher tiers MUST come first — TierResolver picks the first row whose
# ``min_consume_90d`` threshold is satisfied.
TIER_THRESHOLDS: tuple[tuple[TierName, int, int, int, int], ...] = (
    # (name, min_consume_90d_cny, concurrent, priority, max_pending)
    ("high", 500, 10, 9, 200),
    ("mid", 50, 5, 5, 100),
    ("low", 0, 2, 1, 50),
)


def _resolve_from_consume(consume_cny: Decimal) -> TenantTier:
    for name, threshold, concurrent, priority, max_pending in TIER_THRESHOLDS:
        if consume_cny >= Decimal(threshold):
            return TenantTier(
                name=name,
                concurrent=concurrent,
                priority=priority,
                max_pending=max_pending,
            )
    # Unreachable: the lowest tier has threshold 0. Defensive default
    # mirrors the ``low`` row so a config typo doesn't 500 the request.
    return TenantTier(name="low", concurrent=2, priority=1, max_pending=50)


class TierResolver:
    """Resolves a tenant_id to its current tier with Redis caching.

    Tests inject the cache by passing a custom redis_client / db_session;
    in production both default to the module-level singletons.
    """

    CACHE_PREFIX = "sau:tier:"

    def __init__(
        self,
        *,
        cache_ttl_seconds: int | None = None,
        redis=redis_client,
    ) -> None:
        self._ttl = cache_ttl_seconds or int(
            dify_config.SOCIAL_PUBLISH_TIER_CACHE_TTL_SECONDS
        )
        self._redis = redis

    def get_tier(self, tenant_id: str) -> TenantTier:
        cached = self._read_cache(tenant_id)
        if cached is not None:
            return cached
        consume = self._sum_consumption_90d(tenant_id)
        tier = _resolve_from_consume(consume)
        self._write_cache(tenant_id, tier)
        return tier

    def invalidate(self, tenant_id: str) -> None:
        try:
            self._redis.delete(self._cache_key(tenant_id))
        except Exception:
            logger.exception("failed to invalidate tier cache for %s", tenant_id)

    # ----- internals -----

    def _cache_key(self, tenant_id: str) -> str:
        return f"{self.CACHE_PREFIX}{tenant_id}"

    def _read_cache(self, tenant_id: str) -> TenantTier | None:
        try:
            raw = self._redis.get(self._cache_key(tenant_id))
        except Exception:
            logger.exception("redis get failed for tier cache; falling through")
            return None
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(raw)
            cached_name = str(payload["name"])
        except (ValueError, KeyError, TypeError):
            logger.warning("corrupt tier cache for %s; ignoring", tenant_id)
            return None
        # Defence against a forged Redis value: only the tier *name* is
        # trusted from the cache; the concurrent/priority/max_pending
        # fields are re-derived from TIER_THRESHOLDS so anyone who can
        # write to redis can't push e.g. ``{"max_pending": 99999}`` to
        # bypass the quota.
        canonical = self._canonical_tier(cached_name)
        if canonical is None:
            logger.warning(
                "tier cache for %s names an unknown tier %r; ignoring",
                tenant_id,
                cached_name,
            )
            return None
        return canonical

    @staticmethod
    def _canonical_tier(name: str) -> TenantTier | None:
        """Return the canonical TenantTier for ``name``, or None if the
        name doesn't match a configured tier."""
        for tier_name, _, concurrent, priority, max_pending in TIER_THRESHOLDS:
            if tier_name == name:
                return TenantTier(
                    name=tier_name,
                    concurrent=concurrent,
                    priority=priority,
                    max_pending=max_pending,
                )
        return None

    def _write_cache(self, tenant_id: str, tier: TenantTier) -> None:
        payload = json.dumps(
            {
                "name": tier.name,
                "concurrent": tier.concurrent,
                "priority": tier.priority,
                "max_pending": tier.max_pending,
            }
        )
        try:
            self._redis.setex(self._cache_key(tenant_id), self._ttl, payload)
        except Exception:
            logger.exception("redis setex failed for tier cache; continuing")

    def _sum_consumption_90d(self, tenant_id: str) -> Decimal:
        # Historical BillingRecord rows have nullable tenant_id — those
        # never contribute to a tenant's tier (they pre-date workspace
        # accounting), which is consistent with treating unknowable spend
        # as zero rather than falsely promoting a tenant.
        cutoff = datetime.now(UTC) - timedelta(days=90)
        stmt = (
            db.select(func.coalesce(func.sum(BillingRecord.amount), 0))
            .where(
                BillingRecord.tenant_id == tenant_id,
                BillingRecord.record_type == BillingRecordType.DEDUCTION.value,
                BillingRecord.created_at >= cutoff,
            )
        )
        try:
            value = db.session.execute(stmt).scalar()
        except Exception:
            logger.exception(
                "failed to sum 90d consumption for tenant %s; defaulting to 0",
                tenant_id,
            )
            return Decimal(0)
        if value is None:
            return Decimal(0)
        return Decimal(value)
