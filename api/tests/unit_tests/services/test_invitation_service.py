"""Unit tests for InvitationService.bind_invite_code.

The registration path (``POST /email-register``) and the late-bind endpoint
(``POST /creator/invitations/bind``) share this service. The tests pin down:

- outcome mapping for every rejection reason (so the HTTP layer's 400/404
  mapping cannot silently drift),
- that the service stages changes on ``db.session.add`` but never commits
  — the caller owns the transaction boundary (registration wants to roll
  back with the outer tx on failure, late-bind commits explicitly after).
"""

from unittest.mock import MagicMock, patch

from services.invitation_service import BindOutcome, InvitationService


def _make_invitation(*, code: str = "abc", inviter: str = "i-1", status: str = "pending"):
    """Build a plain mock that quacks like an AccountInvitation row.

    Using MagicMock instead of the real SQLAlchemy model avoids pulling the
    Flask app + registry at import time; these tests only care about
    attribute mutations on the invitation object.
    """
    inv = MagicMock()
    inv.invite_code = code
    inv.inviter_account_id = inviter
    inv.status = status
    inv.invitee_account_id = None
    inv.used_at = None
    return inv


@patch("services.invitation_service.db")
def test_empty_code_returns_empty_code_outcome(mock_db):
    """Whitespace-only / missing codes short-circuit before any DB lookup."""
    for code in (None, "", "   "):
        result = InvitationService.bind_invite_code(invite_code=code, invitee_account_id="u-1")
        assert result.outcome is BindOutcome.EMPTY_CODE
        assert result.inviter_account_id is None

    mock_db.session.scalar.assert_not_called()
    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.invitation_service.db")
def test_already_bound_invitee_rejects_second_bind(mock_db):
    """A user already attached to an inviter must not pick up a second code.

    Prevents the referral tree from accepting multiple parents and exposes
    the existing inviter so the caller can show a helpful error.
    """
    existing = _make_invitation(inviter="old-inviter", status="used")
    # First scalar() = lookup for "already used by this invitee" → hit.
    mock_db.session.scalar.return_value = existing

    result = InvitationService.bind_invite_code(invite_code="new-code", invitee_account_id="u-1")

    assert result.outcome is BindOutcome.ALREADY_BOUND
    assert result.inviter_account_id == "old-inviter"
    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.invitation_service.db")
def test_code_not_found_returns_not_found(mock_db):
    """Unknown invite codes surface as NOT_FOUND so the HTTP layer can 404."""
    # First scalar() = no prior binding, second scalar() = no such code.
    mock_db.session.scalar.side_effect = [None, None]

    result = InvitationService.bind_invite_code(invite_code="zzz", invitee_account_id="u-1")

    assert result.outcome is BindOutcome.NOT_FOUND
    mock_db.session.add.assert_not_called()


@patch("services.invitation_service.db")
def test_revoked_or_used_code_returns_not_pending(mock_db):
    """Only ``pending`` codes are bindable — used/revoked codes reject."""
    for bad_status in ("used", "revoked"):
        inv = _make_invitation(status=bad_status)
        mock_db.session.scalar.side_effect = [None, inv]

        result = InvitationService.bind_invite_code(invite_code="abc", invitee_account_id="u-1")

        assert result.outcome is BindOutcome.NOT_PENDING, f"status={bad_status}"
        mock_db.session.add.assert_not_called()
        mock_db.session.reset_mock()


@patch("services.invitation_service.db")
def test_self_invite_is_rejected(mock_db):
    """An owner using their own code would inflate their own rebates."""
    inv = _make_invitation(inviter="u-1")
    mock_db.session.scalar.side_effect = [None, inv]

    result = InvitationService.bind_invite_code(invite_code="abc", invitee_account_id="u-1")

    assert result.outcome is BindOutcome.SELF_INVITE
    mock_db.session.add.assert_not_called()


@patch("services.invitation_service.db")
def test_successful_bind_stages_mutations_without_committing(mock_db):
    """Happy path: invitation gets marked ``used`` and staged on the session.

    Critically, no ``commit()`` is issued — the caller (registration tx or
    late-bind endpoint) owns that boundary. The registration path needs
    this so a mid-flow rollback doesn't strand a partially-bound invite.
    """
    inv = _make_invitation(code="abc", inviter="i-1")
    mock_db.session.scalar.side_effect = [None, inv]

    result = InvitationService.bind_invite_code(invite_code="abc", invitee_account_id="u-1")

    assert result.ok
    assert result.outcome is BindOutcome.OK
    assert result.inviter_account_id == "i-1"
    # Mutations were applied to the invitation row.
    assert inv.invitee_account_id == "u-1"
    assert inv.status == "used"
    assert inv.used_at is not None
    mock_db.session.add.assert_called_once_with(inv)
    mock_db.session.commit.assert_not_called()


@patch("services.invitation_service.db")
def test_code_is_stripped_before_lookup(mock_db):
    """Leading/trailing whitespace in the URL must not cause NOT_FOUND.

    Users occasionally copy invite codes with trailing newlines / spaces.
    The service must normalise before the DB lookup so URL-encoded
    whitespace doesn't block legitimate registrations.
    """
    inv = _make_invitation(code="abc", inviter="i-1")
    mock_db.session.scalar.side_effect = [None, inv]

    result = InvitationService.bind_invite_code(invite_code="  abc  \n", invitee_account_id="u-1")

    assert result.ok
