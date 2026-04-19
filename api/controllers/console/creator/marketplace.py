"""Marketplace endpoints.

GET  /creator/marketplace/apps          — list active marketplace apps (all authenticated users)
POST /creator/marketplace/apps          — publish an app (super admin only)
DELETE /creator/marketplace/apps/<app_id> — unpublish (super admin only)
GET  /creator/marketplace/apps/<app_id>/status — check publish status
GET  /creator/marketplace/default-app   — get the default creator homepage app
POST /creator/marketplace/default-app   — set the default creator homepage app (super admin only)
"""

from flask import request
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.creator.models import (
    marketplace_app_list_resp,
    marketplace_default_app_req,
    marketplace_default_app_resp,
    marketplace_install_resp,
    marketplace_publish_req,
    marketplace_status_resp,
)
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from services.marketplace_service import MarketplaceService


def _require_system_admin(user):
    if not user.is_system_admin:
        from werkzeug.exceptions import Forbidden
        raise Forbidden("Only system administrators can perform this action")


@console_ns.route("/creator/marketplace/apps")
class MarketplaceAppsApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取已上架的创作者市场应用列表（所有已登录用户可访问）。",
        responses={
            200: ("成功", marketplace_app_list_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(marketplace_app_list_resp)
    def get(self):
        """获取市场应用列表"""
        apps = MarketplaceService.get_marketplace_apps()
        return {"data": apps, "total": len(apps)}

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="将指定 App 上架到创作者市场（仅超级管理员可用）。可同时设置为默认创作者首页应用。",
        responses={
            201: "上架成功，返回 marketplace 记录",
            400: "参数缺失或 App 已上架",
            403: "无权限",
        },
    )
    @console_ns.expect(marketplace_publish_req, validate=False)
    def post(self):
        """上架应用到市场（超级管理员）"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        app_id = payload.get("app_id")
        if not app_id:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("app_id is required")

        is_default = payload.get("is_default", False)

        try:
            marketplace_app = MarketplaceService.publish_app(
                app_id=app_id,
                published_by=current_user.id,
                is_default=is_default,
            )
        except ValueError as e:
            from werkzeug.exceptions import BadRequest
            raise BadRequest(str(e))

        return marketplace_app.to_dict(), 201


@console_ns.route("/creator/marketplace/apps/<string:app_id>")
class MarketplaceAppItemApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="将指定 App 从创作者市场下架（仅超级管理员可用）。",
        responses={
            200: "下架成功",
            403: "无权限",
            404: "App 未在市场中",
        },
    )
    def delete(self, app_id: str):
        """下架应用（超级管理员）"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        MarketplaceService.unpublish_app(app_id=app_id)
        return {"result": "success"}


@console_ns.route("/creator/marketplace/apps/<string:app_id>/status")
class MarketplaceAppStatusApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="查询指定 App 是否已在创作者市场上架。",
        responses={
            200: ("成功", marketplace_status_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(marketplace_status_resp)
    def get(self, app_id: str):
        """查询应用上架状态"""
        is_published = MarketplaceService.is_published(app_id)
        return {"app_id": app_id, "is_published": is_published}


@console_ns.route("/creator/marketplace/apps/<string:app_id>/detail")
class MarketplaceAppDetailApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取市场应用的完整详情（含 App 配置、站点信息等）。"
                    "所有创作者用户可访问，但 App 必须处于上架状态。",
        responses={
            200: "成功，返回 App 完整详情（结构同 /console/api/apps/{id}）",
            401: "未登录",
            404: "App 未上架或不存在",
        },
    )
    def get(self, app_id: str):
        """获取市场应用详情"""
        from sqlalchemy import select

        from controllers.console.app.app import AppDetailWithSite
        from models.creator import MarketplaceApp
        from models.engine import db
        from models.model import App

        # Must be an active marketplace app
        marketplace_entry = db.session.scalar(
            select(MarketplaceApp).where(
                MarketplaceApp.app_id == str(app_id),
                MarketplaceApp.is_active == True,
            )
        )
        if not marketplace_entry:
            from werkzeug.exceptions import NotFound
            raise NotFound("App is not available in the creator marketplace")

        app_model = db.session.get(App, str(app_id))
        if not app_model:
            from werkzeug.exceptions import NotFound
            raise NotFound("App not found")

        from services.app_service import AppService
        app_model = AppService().get_app(app_model)

        response_model = AppDetailWithSite.model_validate(app_model, from_attributes=True)
        return response_model.model_dump(mode="json")


@console_ns.route("/creator/marketplace/apps/<string:app_id>/install")
class MarketplaceAppInstallApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description=(
            "将市场应用安装到当前用户的探索工作空间，返回 installed_app_id。"
            "若已安装则复用旧记录（already_installed=true）。"
            "前端可凭 installed_app_id 跳转 /explore/installed/{id} 使用完整聊天 UI。"
        ),
        responses={
            200: ("已安装（复用旧记录）", marketplace_install_resp),
            201: ("新安装成功", marketplace_install_resp),
            404: "App 未上架或不存在",
        },
    )
    @console_ns.marshal_with(marketplace_install_resp)
    def post(self, app_id: str):
        """安装市场应用到探索工作空间"""
        from sqlalchemy import and_, select

        from libs.datetime_utils import naive_utc_now
        from models.creator import MarketplaceApp
        from models.engine import db
        from models.model import App, InstalledApp

        _, current_tenant_id = current_account_with_tenant()

        # Verify marketplace entry is active
        marketplace_entry = db.session.scalar(
            select(MarketplaceApp).where(
                MarketplaceApp.app_id == str(app_id),
                MarketplaceApp.is_active == True,
            )
        )
        if not marketplace_entry:
            from werkzeug.exceptions import NotFound
            raise NotFound("App is not available in the creator marketplace")

        app_model = db.session.get(App, str(app_id))
        if not app_model:
            from werkzeug.exceptions import NotFound
            raise NotFound("App not found")

        # Return existing installed_app if already installed by this tenant
        existing = db.session.scalar(
            select(InstalledApp).where(
                and_(
                    InstalledApp.app_id == str(app_id),
                    InstalledApp.tenant_id == current_tenant_id,
                )
            )
        )
        if existing:
            existing.last_used_at = naive_utc_now()
            db.session.commit()
            return {"installed_app_id": str(existing.id), "already_installed": True}

        # Create new InstalledApp record
        new_installed_app = InstalledApp(
            app_id=str(app_id),
            tenant_id=current_tenant_id,
            app_owner_tenant_id=app_model.tenant_id,
            is_pinned=False,
            last_used_at=naive_utc_now(),
        )
        db.session.add(new_installed_app)
        db.session.commit()

        return {"installed_app_id": str(new_installed_app.id), "already_installed": False}, 201


@console_ns.route("/creator/marketplace/default-app")
class MarketplaceDefaultAppApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前设置的默认创作者首页应用。未设置时 data 为 null。",
        responses={
            200: ("成功", marketplace_default_app_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(marketplace_default_app_resp)
    def get(self):
        """获取默认创作者首页应用"""
        default_app = MarketplaceService.get_default_app()
        if not default_app:
            return {"data": None}
        return {"data": default_app}

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="设置指定市场应用为默认创作者首页应用（仅超级管理员可用）。该应用必须已上架。",
        responses={
            200: "设置成功，返回更新后的 marketplace 记录",
            400: "参数缺失或 App 未上架",
            403: "无权限",
        },
    )
    @console_ns.expect(marketplace_default_app_req, validate=False)
    def post(self):
        """设置默认创作者首页应用（超级管理员）"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        app_id = payload.get("app_id")
        if not app_id:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("app_id is required")

        try:
            marketplace_app = MarketplaceService.set_default_app(app_id=app_id)
        except ValueError as e:
            from werkzeug.exceptions import BadRequest
            raise BadRequest(str(e))

        return marketplace_app.to_dict()
