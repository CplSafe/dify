"""Invitation endpoints for workspace owners.

GET    /creator/invitations            — 查询当前用户创建的邀请码列表（含被邀请人信息）
POST   /creator/invitations            — 生成新的邀请码
DELETE /creator/invitations/<id>       — 撤销未使用的邀请码
POST   /creator/invitations/bind       — 绑定邀请码到当前用户（注册后显式绑定）
GET    /creator/invitations/my-inviter — 查询邀请当前用户的邀请人信息
"""

import secrets

from flask import request
from flask_restx import Resource, fields
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
    """生成短 URL 安全邀请码（约 11 字符）。"""
    return secrets.token_urlsafe(8)  # ~11 chars


# ---------------------------------------------------------------------------
# Model 定义
# ---------------------------------------------------------------------------

_invitation_item = console_ns.model(
    "CreatorInvitationItem",
    {
        "id": fields.String(description="邀请记录 ID"),
        "invite_code": fields.String(description="邀请码字符串"),
        "status": fields.String(description="邀请状态：pending / used / revoked"),
        "inviter_account_id": fields.String(description="邀请人账号 ID"),
        "invitee_account_id": fields.String(description="被邀请人账号 ID，未使用时为空"),
        "invitee_name": fields.String(description="被邀请人昵称（列表接口补充字段）"),
        "invitee_email": fields.String(description="被邀请人邮箱（列表接口补充字段）"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

_invitation_list_resp = console_ns.model(
    "CreatorInvitationListResp",
    {
        "data": fields.List(fields.Nested(_invitation_item), description="邀请记录列表"),
        "total": fields.Integer(description="总条数"),
    },
)

_bind_invite_req = console_ns.model(
    "CreatorInvitationBindReq",
    {
        "invite_code": fields.String(
            required=True,
            description="要绑定的邀请码",
            example="abc123xyz",
        ),
    },
)

_bind_invite_resp = console_ns.model(
    "CreatorInvitationBindResp",
    {
        "result": fields.String(description="固定返回 success"),
        "inviter_account_id": fields.String(description="邀请人的账号 ID"),
    },
)

_inviter_info = console_ns.model(
    "CreatorInviterInfo",
    {
        "account_id": fields.String(description="邀请人账号 ID"),
        "name": fields.String(description="邀请人昵称"),
        "email": fields.String(description="邀请人邮箱"),
    },
)

_my_inviter_resp = console_ns.model(
    "CreatorMyInviterResp",
    {
        "has_inviter": fields.Boolean(description="当前用户是否有邀请人"),
        "inviter": fields.Nested(_inviter_info, allow_null=True, description="邀请人信息，无则为 null"),
    },
)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@console_ns.route("/creator/invitations")
class InvitationListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="查询当前用户（工作区 Owner）创建的所有邀请码，"
                    "并附带被邀请人的昵称和邮箱（已使用的邀请码才有）。"
                    "仅 Owner 可调用，非 Owner 返回 403。",
        responses={
            200: ("成功", _invitation_list_resp),
            401: "未登录",
            403: "非工作区 Owner",
        },
    )
    @console_ns.marshal_with(_invitation_list_resp)
    def get(self):
        """查询当前用户创建的邀请码列表"""
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
    @console_ns.doc(
        description="生成一条新的邀请码，邀请码为 URL 安全随机字符串（约 11 位）。"
                    "仅 Owner 可调用，成功后返回 201。",
        responses={
            201: ("创建成功", _invitation_item),
            401: "未登录",
            403: "非工作区 Owner",
        },
    )
    def post(self):
        """生成新的邀请码"""
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
    @console_ns.doc(
        description="撤销一条未使用的邀请码（将其 status 改为 revoked）。"
                    "已使用的邀请码无法撤销（返回 400）。"
                    "只有邀请码创建者可撤销（非创建者返回 403）。",
        responses={
            200: "撤销成功",
            400: "邀请码已使用，无法撤销",
            401: "未登录",
            403: "非邀请码创建者",
            404: "邀请码不存在",
        },
    )
    def delete(self, invitation_id: str):
        """撤销未使用的邀请码"""
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
    @console_ns.doc(
        description="将邀请码绑定到当前登录用户（显式后绑定流程）。"
                    "注册流程中的自动绑定由 POST /email-register 内部处理。"
                    "同一用户只能绑定一次邀请人，重复绑定返回 400。"
                    "不能使用自己的邀请码。",
        responses={
            200: ("绑定成功", _bind_invite_resp),
            400: "邀请码无效、已使用、已撤销或已绑定邀请人",
            401: "未登录",
            404: "邀请码不存在",
        },
    )
    @console_ns.expect(_bind_invite_req, validate=False)
    @console_ns.marshal_with(_bind_invite_resp)
    def post(self):
        """绑定邀请码到当前用户"""
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
    @console_ns.doc(
        description="查询邀请当前用户的邀请人信息。"
                    "若当前用户没有邀请人（直接注册），返回 has_inviter=false，inviter=null。",
        responses={
            200: ("成功", _my_inviter_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(_my_inviter_resp)
    def get(self):
        """查询邀请当前用户的邀请人信息"""
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
