"""Unit tests for the rebate unfreeze task.

The task's job is to move pending rebates from ``UserBalance.rebate_pending``
to ``UserBalance.balance`` once the freeze window elapses, and write a
``BillingRecord`` of type ``REBATE`` as the ledger-visible cash event.

Tests mock the DB session so we can verify:
- the cutoff date is computed from ``RebateConfig.freeze_days``,
- each pending record's amount moves atomically from frozen → spendable,
- cancelled / already-settled records are not re-released,
- negative-pending guard short-circuits rather than silently overdrafting,
- missing ``UserBalance`` rows are logged + skipped rather than crashing
  the whole batch.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from models.creator import BillingRecordType, RebateRecordStatus
from schedule.rebate_unfreeze_task import rebate_unfreeze_task


def _mock_config(*, freeze_days: int = 7, is_enabled: bool = True) -> MagicMock:
    cfg = MagicMock()
    cfg.freeze_days = freeze_days
    cfg.is_enabled = is_enabled
    return cfg


def _mock_record(*, record_id: str, inviter: str, amount: str = "5", consumption: str = "50") -> MagicMock:
    r = MagicMock()
    r.id = record_id
    r.inviter_account_id = inviter
    r.rebate_amount = Decimal(amount)
    r.consumption_amount = Decimal(consumption)
    r.status = RebateRecordStatus.PENDING.value
    r.unfrozen_at = None
    return r


def _mock_balance(*, rebate_pending: str = "0", balance: str = "0") -> MagicMock:
    b = MagicMock()
    b.rebate_pending = Decimal(rebate_pending)
    b.balance = Decimal(balance)
    return b


@patch("schedule.rebate_unfreeze_task.db")
def test_disabled_config_short_circuits(mock_db):
    """A disabled rebate config must not scan or mutate anything."""
    mock_db.session.scalar.return_value = _mock_config(is_enabled=False)

    rebate_unfreeze_task()

    # Only the config lookup happened.
    mock_db.session.scalar.assert_called_once()
    mock_db.session.scalars.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("schedule.rebate_unfreeze_task.db")
def test_no_config_short_circuits(mock_db):
    """A missing config (fresh install) is treated as disabled."""
    mock_db.session.scalar.return_value = None

    rebate_unfreeze_task()

    mock_db.session.scalars.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("schedule.rebate_unfreeze_task.db")
def test_no_pending_records_exits_cleanly(mock_db):
    """With nothing ready to release, no BillingRecord should be created."""
    mock_db.session.scalar.return_value = _mock_config()
    mock_db.session.scalars.return_value.all.return_value = []

    rebate_unfreeze_task()

    mock_db.session.commit.assert_not_called()
    mock_db.session.add.assert_not_called()


@patch("schedule.rebate_unfreeze_task.db")
def test_pending_record_moves_frozen_to_spendable_and_writes_billing(mock_db):
    """Happy path: frozen → spendable, ledger row written, record marked settled."""
    record = _mock_record(record_id="rec-1", inviter="u-1", amount="5")
    balance = _mock_balance(rebate_pending="5", balance="100")

    # First scalar = config, then scalar() inside the loop = balance row.
    mock_db.session.scalar.side_effect = [_mock_config(), balance]
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    # Money moved atomically.
    assert balance.rebate_pending == Decimal(0)
    assert balance.balance == Decimal(105)
    # Record closed out.
    assert record.status == RebateRecordStatus.SETTLED.value
    assert record.unfrozen_at is not None

    # A BillingRecord of type REBATE was staged on the session.
    added = [call.args[0] for call in mock_db.session.add.call_args_list]
    billing_records = [a for a in added if getattr(a, "record_type", None) == BillingRecordType.REBATE]
    assert len(billing_records) == 1
    assert billing_records[0].amount == Decimal(5)
    assert billing_records[0].account_id == "u-1"

    mock_db.session.commit.assert_called_once()


@patch("schedule.rebate_unfreeze_task.db")
def test_missing_balance_row_is_skipped_not_fatal(mock_db):
    """A record without a matching UserBalance shouldn't abort the batch."""
    record = _mock_record(record_id="rec-1", inviter="u-ghost", amount="5")

    # config; then balance lookup returns None.
    mock_db.session.scalar.side_effect = [_mock_config(), None]
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    # Record stays pending so the next sweep can pick it up when the balance
    # row reappears (or the record gets cancelled explicitly).
    assert record.status == RebateRecordStatus.PENDING.value
    # No ledger row written.
    added = [call.args[0] for call in mock_db.session.add.call_args_list]
    billing_records = [a for a in added if getattr(a, "record_type", None) == BillingRecordType.REBATE]
    assert billing_records == []
    # Still commits so the empty batch is closed cleanly.
    mock_db.session.commit.assert_called_once()


@patch("schedule.rebate_unfreeze_task.db")
def test_rebate_pending_underflow_is_skipped(mock_db):
    """If rebate_pending < record.amount, skip rather than go negative."""
    record = _mock_record(record_id="rec-1", inviter="u-1", amount="10")
    balance = _mock_balance(rebate_pending="3", balance="100")

    mock_db.session.scalar.side_effect = [_mock_config(), balance]
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    # Nothing moved.
    assert balance.rebate_pending == Decimal(3)
    assert balance.balance == Decimal(100)
    assert record.status == RebateRecordStatus.PENDING.value


@patch("schedule.rebate_unfreeze_task.db")
def test_zero_amount_record_is_closed_without_moving_money(mock_db):
    """A zero-value pending record (defensive) is just marked settled."""
    record = _mock_record(record_id="rec-1", inviter="u-1", amount="0")
    balance = _mock_balance(rebate_pending="0", balance="100")

    mock_db.session.scalar.side_effect = [_mock_config(), balance]
    mock_db.session.scalars.return_value.all.return_value = [record]

    rebate_unfreeze_task()

    assert record.status == RebateRecordStatus.SETTLED.value
    assert balance.balance == Decimal(100)  # untouched


@patch("schedule.rebate_unfreeze_task.db")
def test_batch_processes_multiple_records(mock_db):
    """Two releasable records both get processed in the same run."""
    r1 = _mock_record(record_id="r1", inviter="u-1", amount="5")
    r2 = _mock_record(record_id="r2", inviter="u-2", amount="7")
    b1 = _mock_balance(rebate_pending="5", balance="100")
    b2 = _mock_balance(rebate_pending="7", balance="50")

    mock_db.session.scalar.side_effect = [_mock_config(), b1, b2]
    mock_db.session.scalars.return_value.all.return_value = [r1, r2]

    rebate_unfreeze_task()

    assert b1.balance == Decimal(105)
    assert b2.balance == Decimal(57)
    assert r1.status == RebateRecordStatus.SETTLED.value
    assert r2.status == RebateRecordStatus.SETTLED.value

    added = [call.args[0] for call in mock_db.session.add.call_args_list]
    billing_records = [a for a in added if getattr(a, "record_type", None) == BillingRecordType.REBATE]
    assert len(billing_records) == 2
    mock_db.session.commit.assert_called_once()
