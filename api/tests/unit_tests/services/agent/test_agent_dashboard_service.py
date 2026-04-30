"""Unit tests for AgentDashboardService.

Aggregations are mocked at db.session level — test focus is on:
- correct shape (4 wallet keys, N trend rows, per-invitee dicts)
- empty-data edge cases (no invitees, no consumption)
- N+1 protection (assert single GROUP BY query, not per-row loop)
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.agent_dashboard_service.db")
def test_wallet_summary_returns_four_metrics(mock_db, agent_id):
    from services.agent.agent_dashboard_service import AgentDashboardService

    wallet = MagicMock(
        withdrawable=Decimal("100"),
        total_earned=Decimal("150"),
        total_withdrawn=Decimal("50"),
    )
    # scalar() calls: wallet lookup, pending sum
    mock_db.session.scalar.side_effect = [wallet, Decimal("25")]

    summary = AgentDashboardService.wallet_summary(agent_id)

    assert set(summary.keys()) == {
        "withdrawable", "total_earned", "total_withdrawn", "pending",
    }
    assert summary["withdrawable"] == Decimal("100")
    assert summary["pending"] == Decimal("25")


@patch("services.agent.agent_dashboard_service.db")
def test_wallet_summary_handles_zero_pending(mock_db, agent_id):
    """When no pending RebateRecords, sum returns None — coalesce to 0."""
    from services.agent.agent_dashboard_service import AgentDashboardService

    wallet = MagicMock(
        withdrawable=Decimal("0"),
        total_earned=Decimal("0"),
        total_withdrawn=Decimal("0"),
    )
    mock_db.session.scalar.side_effect = [wallet, None]

    summary = AgentDashboardService.wallet_summary(agent_id)
    assert summary["pending"] == Decimal("0")


@patch("services.agent.agent_dashboard_service.db")
def test_wallet_summary_raises_when_no_wallet(mock_db, agent_id):
    from services.agent.agent_dashboard_service import AgentDashboardService

    mock_db.session.scalar.return_value = None

    with pytest.raises(ValueError, match="no wallet"):
        AgentDashboardService.wallet_summary(agent_id)


@patch("services.agent.agent_dashboard_service.db")
def test_daily_consumption_returns_zeroed_days_when_no_invitees(mock_db, agent_id):
    """No invitees → 7 zero rows, NOT empty list."""
    from services.agent.agent_dashboard_service import AgentDashboardService

    mock_db.session.scalars.return_value.all.return_value = []

    result = AgentDashboardService.daily_consumption(agent_id, days=7)

    assert len(result) == 7
    assert all(r["consumption"] == Decimal("0") for r in result)
    # Dates ordered oldest → newest
    dates = [r["date"] for r in result]
    assert dates == sorted(dates)


@patch("services.agent.agent_dashboard_service.db")
def test_daily_consumption_rejects_zero_or_negative_days(mock_db, agent_id):
    from services.agent.agent_dashboard_service import AgentDashboardService

    with pytest.raises(ValueError, match="days must be positive"):
        AgentDashboardService.daily_consumption(agent_id, days=0)
    with pytest.raises(ValueError, match="days must be positive"):
        AgentDashboardService.daily_consumption(agent_id, days=-1)


@patch("services.agent.agent_dashboard_service.db")
def test_invitees_returns_empty_when_no_bindings(mock_db, agent_id):
    from services.agent.agent_dashboard_service import AgentDashboardService

    mock_db.session.execute.return_value.all.return_value = []

    assert AgentDashboardService.invitees(agent_id) == []


@patch("services.agent.agent_dashboard_service.db")
def test_invitees_aggregates_with_single_group_by_per_metric(mock_db, agent_id):
    """N+1 protection: with 3 invitees and 1 agent, expect at most 3
    db.session.execute calls (bindings + month consumption + lifetime
    rebate) — NOT 3 per invitee."""
    from datetime import datetime
    from services.agent.agent_dashboard_service import AgentDashboardService

    bindings = [
        MagicMock(invitee_account_id="inv-1", used_at=datetime(2026, 4, 1)),
        MagicMock(invitee_account_id="inv-2", used_at=datetime(2026, 4, 2)),
        MagicMock(invitee_account_id="inv-3", used_at=datetime(2026, 4, 3)),
    ]
    consumption_rows = [("inv-1", Decimal("50")), ("inv-3", Decimal("20"))]
    rebate_rows = [("inv-1", Decimal("5")), ("inv-3", Decimal("2"))]

    mock_db.session.execute.side_effect = [
        MagicMock(all=lambda: bindings),
        MagicMock(all=lambda: consumption_rows),
        MagicMock(all=lambda: rebate_rows),
    ]

    result = AgentDashboardService.invitees(agent_id)

    assert len(result) == 3
    # Exactly 3 execute() calls — single GROUP BY each, no per-invitee fan-out
    assert mock_db.session.execute.call_count == 3
    # inv-1 has data, inv-2 doesn't (gets defaults)
    by_id = {r["invitee_account_id"]: r for r in result}
    assert by_id["inv-1"]["month_consumption"] == Decimal("50")
    assert by_id["inv-1"]["total_rebate"] == Decimal("5")
    assert by_id["inv-2"]["month_consumption"] == Decimal("0")
    assert by_id["inv-2"]["total_rebate"] == Decimal("0")
