"""AgentWalletService — single audit point for all wallet writes.

Every credit/debit flows through this service so logging, metrics, and
invariants live in one place. Wallets are created at agent creation
time (see ``AgentService.create_agent``) — this service never creates
them, only mutates existing rows.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from extensions.ext_database import db
from models.agent import AgentWallet


class AgentWalletService:
    """Encapsulate AgentWallet read/write."""

    @classmethod
    def get_wallet(cls, agent_id: str) -> AgentWallet:
        wallet = db.session.scalar(
            select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        )
        if wallet is None:
            raise ValueError(f"agent {agent_id} has no wallet")
        return wallet

    @classmethod
    def credit_settled(cls, agent_id: str, amount: Decimal) -> AgentWallet:
        """Credit a settled rebate to withdrawable + total_earned.

        Caller commits.
        """
        wallet = cls.get_wallet(agent_id)
        wallet.withdrawable = wallet.withdrawable + amount
        wallet.total_earned = wallet.total_earned + amount
        return wallet
