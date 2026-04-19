"""User global API key endpoints.

GET    /creator/api-key  — get current user's global API key
POST   /creator/api-key  — generate a new global API key
DELETE /creator/api-key  — revoke current global API key
"""

from flask import request
from flask_restx import Resource
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.creator.models import (
    api_key_create_req,
    api_key_resp,
)
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.creator import UserGlobalApiKey
from models.engine import db
from services.user_billing_service import generate_api_key


@console_ns.route("/creator/api-key")
class UserGlobalApiKeyApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前用户的全局 API Key（脱敏展示，token 字段仅显示前后几位）。未创建时 api_key 为 null。",
        responses={
            200: ("成功", api_key_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(api_key_resp)
    def get(self):
        """获取当前用户的 API Key（脱敏）"""
        current_user, _ = current_account_with_tenant()
        key = db.session.scalar(
            select(UserGlobalApiKey).where(UserGlobalApiKey.account_id == current_user.id)
        )
        if not key:
            return {"api_key": None}
        return {"api_key": key.to_dict(masked=True)}

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description=(
            "生成（或重新生成）当前用户的全局 API Key。"
            "若已存在旧 Key，旧 Key 将立即作废。"
            "响应中 token 字段为明文，仅此次返回，后续查询会脱敏。"
        ),
        responses={
            201: ("创建成功，返回明文 token", api_key_resp),
            401: "未登录",
        },
    )
    @console_ns.expect(api_key_create_req, validate=False)
    @console_ns.marshal_with(api_key_resp, code=201)
    def post(self):
        """生成（或重置）当前用户的 API Key"""
        current_user, _ = current_account_with_tenant()

        # Delete existing key if present
        existing = db.session.scalar(
            select(UserGlobalApiKey).where(UserGlobalApiKey.account_id == current_user.id)
        )
        if existing:
            db.session.delete(existing)
            db.session.flush()

        payload = request.get_json() or {}
        description = payload.get("description", "")

        new_token = generate_api_key()
        key = UserGlobalApiKey(
            account_id=current_user.id,
            token=new_token,
            description=description,
        )
        db.session.add(key)
        db.session.commit()

        # Return the full (unmasked) token only on creation
        return {
            "api_key": {
                **key.to_dict(masked=False),
                "token": new_token,
            }
        }, 201

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="撤销（删除）当前用户的全局 API Key。Key 不存在时也返回成功。",
        responses={
            200: "撤销成功",
            401: "未登录",
        },
    )
    def delete(self):
        """撤销当前用户的 API Key"""
        current_user, _ = current_account_with_tenant()
        key = db.session.scalar(
            select(UserGlobalApiKey).where(UserGlobalApiKey.account_id == current_user.id)
        )
        if key:
            db.session.delete(key)
            db.session.commit()
        return {"result": "success"}
