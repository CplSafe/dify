"""Unit tests for AgentWalletService.

Centralised wallet read/write — every credit/debit must flow through
this service so it remains the single audit point.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.agent_wallet_service.db")
def test_credit_settled_increments_withdrawable_and_total_earned(mock_db, agent_id):
    from services.agent.agent_wallet_service import AgentWalletService

    wallet = MagicMock(
        withdrawable=Decimal(0),
        total_earned=Decimal(0),
    )
    mock_db.session.scalar.return_value = wallet

    AgentWalletService.credit_settled(agent_id, Decimal("50.5"))
    AgentWalletService.credit_settled(agent_id, Decimal("19.5"))

    assert wallet.withdrawable == Decimal("70.0")
    assert wallet.total_earned == Decimal("70.0")


@patch("services.agent.agent_wallet_service.db")
def test_credit_settled_raises_when_wallet_missing(mock_db, agent_id):
    from services.agent.agent_wallet_service import AgentWalletService

    mock_db.session.scalar.return_value = None

    with pytest.raises(ValueError, match="no wallet"):
        AgentWalletService.credit_settled(agent_id, Decimal(10))


@patch("services.agent.agent_wallet_service.db")
def test_get_wallet_raises_when_missing(mock_db, agent_id):
    from services.agent.agent_wallet_service import AgentWalletService

    mock_db.session.scalar.return_value = None

    with pytest.raises(ValueError, match="no wallet"):
        AgentWalletService.get_wallet(agent_id)
