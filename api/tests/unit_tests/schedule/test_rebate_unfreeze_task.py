"""Unit tests for the rebate unfreeze task.

The task moves PENDING rebates into ``AgentWallet.withdrawable`` (and
``total_earned``) once the freeze window elapses. All wallet writes go
through ``AgentWalletService.credit_settled``.

Tests mock the DB session + AgentWalletService so we can verify:
- disabled config short-circuits with no mutation
- ready records flow through credit_settled and flip to SETTLED
- zero/negative amounts are closed out without crediting
- a missing AgentWallet logs + skips rather than crashing the batch
- multiple records share a single batch commit
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from models.creator import RebateRecordStatus
from schedule.rebate_unfreeze_task import rebate_unfreeze_task


def _mock_config(*, freeze_days: int = 7, is_enabled: bool = True) -> MagicMock:
    cfg = MagicMock()
    cfg.freeze_days = freeze_days
    cfg.is_enabled = is_enabled
    return cfg


def _mock_record(
    *, record_id: str, agent_id: str = "agent-1",
    amount: str = "5", consumption: str = "50",
) -> MagicMock:
    r = MagicMock()
    r.id = record_id
    r.agent_id = agent_id
    r.rebate_amount = Decimal(amount)
    r.consumption_amount = Decimal(consumption)
    r.status = RebateRecordStatus.PENDING.value
    r.unfrozen_at = None
    return r


@patch("schedule.rebate_unfreeze_task.db")
def test_disabled_config_short_circuits(mock_db):
    """A disabled rebate config must not scan or mutate anything."""
    mock_db.session.scalar.return_value = _mock_config(is_enabled=False)

    rebate_unfreeze_task()

    mock_db.session.scalars.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("schedule.rebate_unfreeze_task.db")
def test_missing_config_short_circuits(mock_db):
    """No RebateConfig row at all (fresh deploy) — must skip cleanly."""
    mock_db.session.scalar.return_value = None

    rebate_unfreeze_task()

    mock_db.session.scalars.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("schedule.rebate_unfreeze_task.AgentWalletService")
@patch("schedule.rebate_unfreeze_task.db")
def test_no_pending_records_skips_without_commit(mock_db, mock_wallet_svc):
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = []

    rebate_unfreeze_task()

    mock_wallet_svc.credit_settled.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("schedule.rebate_unfreeze_task.AgentWalletService")
@patch("schedule.rebate_unfreeze_task.db")
def test_ready_record_credits_wallet_and_flips_to_settled(mock_db, mock_wallet_svc):
    """Happy path: a record past freeze_days is credited via
    credit_settled and flipped to SETTLED in one commit."""
    record = _mock_record(record_id="rec-1", agent_id="agent-1", amount="10")
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    mock_wallet_svc.credit_settled.assert_called_once_with("agent-1", Decimal(10))
    assert record.status == RebateRecordStatus.SETTLED.value
    assert record.unfrozen_at is not None
    mock_db.session.commit.assert_called_once()


@patch("schedule.rebate_unfreeze_task.AgentWalletService")
@patch("schedule.rebate_unfreeze_task.db")
def test_zero_amount_record_closes_without_credit(mock_db, mock_wallet_svc):
    """Defensive: a zero-amount record is closed out without crediting,
    so it doesn't get re-picked on the next sweep."""
    record = _mock_record(record_id="rec-zero", amount="0")
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    mock_wallet_svc.credit_settled.assert_not_called()
    assert record.status == RebateRecordStatus.SETTLED.value
    assert record.unfrozen_at is not None


@patch("schedule.rebate_unfreeze_task.AgentWalletService")
@patch("schedule.rebate_unfreeze_task.db")
def test_missing_wallet_logs_and_skips_without_blocking_batch(mock_db, mock_wallet_svc):
    """If AgentWalletService raises ValueError (wallet was deleted out-of-band),
    the record stays PENDING and the loop continues with the next record."""
    bad = _mock_record(record_id="rec-bad", agent_id="agent-deleted", amount="5")
    good = _mock_record(record_id="rec-good", agent_id="agent-1", amount="3")
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = [bad, good]

    mock_wallet_svc.credit_settled.side_effect = [ValueError("no wallet"), None]

    rebate_unfreeze_task()

    assert bad.status == RebateRecordStatus.PENDING.value
    assert bad.unfrozen_at is None
    assert good.status == RebateRecordStatus.SETTLED.value
    assert good.unfrozen_at is not None
    assert mock_wallet_svc.credit_settled.call_count == 2
    mock_db.session.commit.assert_called_once()


@patch("schedule.rebate_unfreeze_task.AgentWalletService")
@patch("schedule.rebate_unfreeze_task.db")
def test_multiple_records_aggregated_into_single_commit(mock_db, mock_wallet_svc):
    """Three ready records → three credit calls → one batch commit."""
    records = [
        _mock_record(record_id=f"rec-{i}", agent_id=f"agent-{i}", amount="5")
        for i in range(3)
    ]
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = records

    rebate_unfreeze_task()

    assert mock_wallet_svc.credit_settled.call_count == 3
    assert all(r.status == RebateRecordStatus.SETTLED.value for r in records)
    mock_db.session.commit.assert_called_once()
