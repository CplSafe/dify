"""Marketplace endpoints.

GET  /creator/marketplace/apps    — list active marketplace apps (all authenticated users)
POST /creator/marketplace/apps    — publish an app (super admin only)
DELETE /creator/marketplace/apps/<app_id> — unpublish (super admin only)
GET  /creator/marketplace/apps/<app_id>/status — check publish status
"""

from flask import request
from flask_restx import Resource

from controllers.console import console_ns
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
    def get(self):
        """List all published marketplace apps."""
        apps = MarketplaceService.get_marketplace_apps()
        return {"data": apps, "total": len(apps)}

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """Publish an app to the marketplace (super admin only)."""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        app_id = payload.get("app_id")
        if not app_id:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("app_id is required")

        try:
            marketplace_app = MarketplaceService.publish_app(
                app_id=app_id,
                published_by=current_user.id,
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
    def delete(self, app_id: str):
        """Unpublish an app from the marketplace (super admin only)."""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        MarketplaceService.unpublish_app(app_id=app_id)
        return {"result": "success"}


@console_ns.route("/creator/marketplace/apps/<string:app_id>/status")
class MarketplaceAppStatusApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id: str):
        """Check if an app is published in the marketplace."""
        is_published = MarketplaceService.is_published(app_id)
        return {"app_id": app_id, "is_published": is_published}


@console_ns.route("/creator/marketplace/apps/<string:app_id>/detail")
class MarketplaceAppDetailApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id: str):
        """Get full app detail for a marketplace app (accessible to all creator users)."""
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
    def post(self, app_id: str):
        """Install a marketplace app into the current user's explore workspace.

        Unlike the standard POST /installed-apps, this does NOT require a RecommendedApp entry —
        any active marketplace app can be installed directly.

        Returns the installed_app_id so the frontend can navigate to
        /explore/installed/{installed_app_id} and use the full Dify explore chat UI.
        """
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
