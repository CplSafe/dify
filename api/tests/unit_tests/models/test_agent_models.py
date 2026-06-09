"""Sanity tests for agent models — verify columns + import. Business
behaviour is covered in service-level tests in Phase 1.
"""


def test_agent_model_has_required_columns():
    from models.agent import Agent
    cols = {c.name for c in Agent.__table__.columns}
    for required in (
        "id", "account_id", "name", "status", "rebate_rate",
        "level", "region_province", "region_city",
        "contact_phone", "notes", "signed_at", "expires_at",
        "created_by", "created_at", "updated_at",
    ):
        assert required in cols, f"Agent missing column {required}"


def test_agent_wallet_has_required_columns():
    from models.agent import AgentWallet
    cols = {c.name for c in AgentWallet.__table__.columns}
    for required in (
        "id", "agent_id", "withdrawable", "total_earned",
        "total_withdrawn", "updated_at",
    ):
        assert required in cols, f"AgentWallet missing column {required}"


def test_rebind_request_has_required_columns():
    from models.agent import RebindRequest
    cols = {c.name for c in RebindRequest.__table__.columns}
    for required in (
        "id", "account_id", "from_agent_id", "to_agent_id",
        "status", "reviewer_id", "review_note",
        "created_at", "reviewed_at",
    ):
        assert required in cols, f"RebindRequest missing column {required}"


def test_withdrawal_request_has_required_columns():
    from models.agent import WithdrawalRequest
    cols = {c.name for c in WithdrawalRequest.__table__.columns}
    for required in (
        "id", "agent_id", "amount", "payout_method",
        "payout_payload", "status", "reviewer_id",
        "review_note", "created_at", "reviewed_at",
    ):
        assert required in cols, f"WithdrawalRequest missing column {required}"


def test_account_invitation_has_agent_id_column():
    from models.creator import AccountInvitation
    cols = {c.name for c in AccountInvitation.__table__.columns}
    assert "agent_id" in cols, "AccountInvitation must reference agent"


def test_account_invitation_invite_code_no_longer_unique():
    """Code is reusable now — same code can have multiple invitee rows."""
    from models.creator import AccountInvitation
    for idx in AccountInvitation.__table__.indexes:
        if idx.name == "account_invitation_code_idx":
            assert not idx.unique, "code index must not be unique anymore"
            return
    raise AssertionError("account_invitation_code_idx not found")


def test_rebate_record_has_agent_id_column():
    from models.creator import RebateRecord
    cols = {c.name for c in RebateRecord.__table__.columns}
    assert "agent_id" in cols, "RebateRecord must reference agent"


def test_user_balance_no_longer_has_rebate_pending():
    from models.creator import UserBalance
    cols = {c.name for c in UserBalance.__table__.columns}
    assert "rebate_pending" not in cols, "rebate_pending should be removed"
