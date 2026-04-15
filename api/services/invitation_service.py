"""Invitation binding service.

Centralizes the ``AccountInvitation.status == "used"`` transition so both the
registration path (``POST /email-register``) and the late-bind endpoint
(``POST /creator/invitations/bind``) share one implementation.

The bind flows are slightly different in their failure policy:

- Registration: binding is best-effort — a bad/expired invite code must not
  roll back the account creation. Caller gets a :class:`BindResult` and logs.
- Late-bind: the user already owns an authenticated session and expects user-
  facing validation errors (400/404). The HTTP endpoint maps the same
  :class:`BindOutcome` enum onto ``BadRequest``/``NotFound``.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass

from sqlalchemy import and_, select

from libs.datetime_utils import naive_utc_now
from models.creator import AccountInvitation
from models.engine import db

logger = logging.getLogger(__name__)


class BindOutcome(enum.StrEnum):
    """Discrete outcomes for an invite-bind attempt.

    Grouping the reasons as an enum lets the HTTP layer (late-bind endpoint)
    map them onto 400/404 errors without sprinkling string comparisons, and
    lets the registration path log a single structured reason.
    """

    OK = "ok"
    EMPTY_CODE = "empty_code"
    ALREADY_BOUND = "already_bound"
    NOT_FOUND = "not_found"
    NOT_PENDING = "not_pending"
    SELF_INVITE = "self_invite"


@dataclass(frozen=True)
class BindResult:
    outcome: BindOutcome
    inviter_account_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is BindOutcome.OK


class InvitationService:
    """Service for binding invitation codes to newly registered accounts."""

    @classmethod
    def bind_invite_code(cls, *, invite_code: str | None, invitee_account_id: str) -> BindResult:
        """Mark ``invite_code`` as used by ``invitee_account_id``.

        Stages the mutation on the caller's ``db.session`` but does NOT commit
        — callers compose this into their own transaction so that a bind
        failure either rolls back with the surrounding work (registration) or
        commits together with other changes (late-bind endpoint).

        Idempotency: if the same invitee already has a ``used`` invitation,
        this returns :pyattr:`BindOutcome.ALREADY_BOUND` instead of raising,
        so re-registration attempts do not produce duplicate bindings.
        """
        code = (invite_code or "").strip()
        if not code:
            return BindResult(BindOutcome.EMPTY_CODE)

        # Reject duplicate bind for the same invitee. Prevents a second
        # invite code from attaching to a user who is already in the
        # referral tree.
        existing = db.session.scalar(
            select(AccountInvitation).where(
                and_(
                    AccountInvitation.invitee_account_id == invitee_account_id,
                    AccountInvitation.status == "used",
                )
            )
        )
        if existing:
            return BindResult(BindOutcome.ALREADY_BOUND, inviter_account_id=existing.inviter_account_id)

        invitation = db.session.scalar(
            select(AccountInvitation).where(AccountInvitation.invite_code == code)
        )
        if not invitation:
            return BindResult(BindOutcome.NOT_FOUND)
        if invitation.status != "pending":
            return BindResult(BindOutcome.NOT_PENDING)
        if invitation.inviter_account_id == invitee_account_id:
            return BindResult(BindOutcome.SELF_INVITE)

        invitation.invitee_account_id = invitee_account_id
        invitation.status = "used"
        invitation.used_at = naive_utc_now()
        db.session.add(invitation)

        return BindResult(BindOutcome.OK, inviter_account_id=invitation.inviter_account_id)
