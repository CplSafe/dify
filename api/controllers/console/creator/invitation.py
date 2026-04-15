"""Invitation endpoints for workspace owners.

GET  /creator/invitations         — list my invitation codes & invitees
POST /creator/invitations         — generate a new invite code
DELETE /creator/invitations/<id>  — revoke an unused invite code
POST /creator/invitations/bind    — bind invite code during registration (called internally)
GET  /creator/invitations/my-inviter — who invited me?
"""

import secrets

from flask import request
from flask_restx import Resource
from sqlalchemy import and_, select
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    tenant_owner_required,
)
from extensions.ext_database import db
from libs.login import current_account_with_tenant, login_required
from models.creator import AccountInvitation
from services.invitation_service import BindOutcome, InvitationService


def _generate_invite_code() -> str:
    """Generate a short, URL-safe invite code."""
    return secrets.token_urlsafe(8)  # ~11 chars


@console_ns.route("/creator/invitations")
class InvitationListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    def get(self):
        """List all invitation codes created by the current user, with invitee info."""
        current_user, _ = current_account_with_tenant()

        invitations = db.session.scalars(
            select(AccountInvitation)
            .where(AccountInvitation.inviter_account_id == current_user.id)
            .order_by(AccountInvitation.created_at.desc())
        ).all()

        # Batch-load invitee names
        from models.account import Account
        invitee_ids = [inv.invitee_account_id for inv in invitations if inv.invitee_account_id]
        invitee_map: dict[str, dict] = {}
        if invitee_ids:
            accounts = db.session.scalars(
                select(Account).where(Account.id.in_(invitee_ids))
            ).all()
            invitee_map = {a.id: {"name": a.name, "email": a.email} for a in accounts}

        result = []
        for inv in invitations:
            d = inv.to_dict()
            if inv.invitee_account_id and inv.invitee_account_id in invitee_map:
                d["invitee_name"] = invitee_map[inv.invitee_account_id]["name"]
                d["invitee_email"] = invitee_map[inv.invitee_account_id]["email"]
            result.append(d)

        return {"data": result, "total": len(result)}

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    def post(self):
        """Generate a new invitation code for the current user."""
        current_user, _ = current_account_with_tenant()

        invite_code = _generate_invite_code()

        invitation = AccountInvitation(
            invite_code=invite_code,
            inviter_account_id=current_user.id,
        )
        db.session.add(invitation)
        db.session.commit()

        return invitation.to_dict(), 201


@console_ns.route("/creator/invitations/<string:invitation_id>")
class InvitationItemApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    def delete(self, invitation_id: str):
        """Revoke an unused invitation code."""
        current_user, _ = current_account_with_tenant()

        invitation = db.session.get(AccountInvitation, invitation_id)
        if not invitation:
            raise NotFound("Invitation not found")
        if invitation.inviter_account_id != current_user.id:
            raise Forbidden("Not your invitation")
        if invitation.status == "used":
            raise BadRequest("Cannot revoke a used invitation")

        invitation.status = "revoked"
        db.session.commit()

        return {"result": "success"}


@console_ns.route("/creator/invitations/bind")
class InvitationBindApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """Bind an invite code to the current (newly registered) user.

        Used for explicit late-bind flows (e.g. a member who joined without an
        invite code and wants to attach one afterwards). The registration path
        binds transactionally inside ``POST /email-register`` via
        :class:`services.invitation_service.InvitationService` so that a dead
        auth cookie on the freshly created account can no longer swallow the
        bind silently — see git blame for context.
        """
        current_user, _ = current_account_with_tenant()
        payload = request.get_json() or {}
        invite_code = (payload.get("invite_code") or "").strip()

        if not invite_code:
            raise BadRequest("invite_code is required")

        result = InvitationService.bind_invite_code(
            invite_code=invite_code,
            invitee_account_id=current_user.id,
        )

        if result.outcome is BindOutcome.ALREADY_BOUND:
            raise BadRequest("您已绑定邀请人，无法重复绑定")
        if result.outcome is BindOutcome.NOT_FOUND:
            raise NotFound("邀请码不存在")
        if result.outcome is BindOutcome.NOT_PENDING:
            raise BadRequest("邀请码已使用或已撤销")
        if result.outcome is BindOutcome.SELF_INVITE:
            raise BadRequest("不能使用自己的邀请码")
        # EMPTY_CODE is pre-checked above; any non-OK outcome is user-facing.

        db.session.commit()
        return {"result": "success", "inviter_account_id": result.inviter_account_id}


@console_ns.route("/creator/invitations/my-inviter")
class MyInviterApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """Get the inviter who invited the current user (if any)."""
        current_user, _ = current_account_with_tenant()

        invitation = db.session.scalar(
            select(AccountInvitation).where(
                and_(
                    AccountInvitation.invitee_account_id == current_user.id,
                    AccountInvitation.status == "used",
                )
            )
        )
        if not invitation:
            return {"has_inviter": False, "inviter": None}

        from models.account import Account
        inviter = db.session.get(Account, invitation.inviter_account_id)
        return {
            "has_inviter": True,
            "inviter": {
                "account_id": inviter.id,
                "name": inviter.name,
                "email": inviter.email,
            } if inviter else None,
        }
