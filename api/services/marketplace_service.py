"""Marketplace service.

Super admins can publish workflow apps to the platform marketplace.
Published apps are automatically visible to all users without requiring
individual installation.
"""

import logging

from sqlalchemy import select

from models.account import Account
from models.creator import MarketplaceApp
from models.engine import db
from models.model import App, AppMode

logger = logging.getLogger(__name__)

# App modes that can be published to the marketplace
PUBLISHABLE_APP_MODES = {AppMode.WORKFLOW, AppMode.ADVANCED_CHAT, AppMode.CHAT}


class MarketplaceService:
    """Handles app marketplace publishing and retrieval."""

    @classmethod
    def publish_app(cls, *, app_id: str, published_by: str, is_default: bool = False) -> MarketplaceApp:
        """Publish a workflow app to the marketplace.

        Only super admins should call this. The app becomes immediately visible
        to all users. If the app was already published, returns the existing entry.

        Raises:
            ValueError: If the app does not exist or is not a publishable type.
        """
        app = db.session.scalar(select(App).where(App.id == app_id))
        if not app:
            raise ValueError(f"App {app_id} not found")

        if AppMode(app.mode) not in PUBLISHABLE_APP_MODES:
            raise ValueError(f"App mode '{app.mode}' cannot be published to marketplace")

        # Check if already published
        existing = db.session.scalar(
            select(MarketplaceApp).where(MarketplaceApp.app_id == app_id)
        )
        if existing:
            # Re-activate if it was de-listed
            if not existing.is_active:
                existing.is_active = True
                db.session.add(existing)
                db.session.commit()
            return existing

        # If setting as default, clear any existing default first
        if is_default:
            cls._clear_default()

        marketplace_app = MarketplaceApp(
            app_id=app_id,
            published_by=published_by,
            is_default=is_default,
        )
        db.session.add(marketplace_app)
        db.session.commit()

        logger.info("Published app %s to marketplace by %s", app_id, published_by)
        return marketplace_app

    @classmethod
    def unpublish_app(cls, *, app_id: str) -> None:
        """Remove an app from the marketplace (soft delete)."""
        marketplace_app = db.session.scalar(
            select(MarketplaceApp).where(MarketplaceApp.app_id == app_id)
        )
        if marketplace_app:
            marketplace_app.is_active = False
            db.session.add(marketplace_app)
            db.session.commit()
            logger.info("Unpublished app %s from marketplace", app_id)

    @classmethod
    def get_marketplace_apps(cls) -> list[dict]:
        """Return all active marketplace apps with their app details."""
        marketplace_apps = list(
            db.session.scalars(
                select(MarketplaceApp)
                .where(MarketplaceApp.is_active.is_(True))
                .order_by(MarketplaceApp.display_order, MarketplaceApp.published_at.desc())
            ).all()
        )

        from graphon.file import helpers as file_helpers

        from models.model import IconType

        result = []
        for ma in marketplace_apps:
            app = db.session.scalar(select(App).where(App.id == ma.app_id))
            if app:
                publisher = db.session.scalar(select(Account).where(Account.id == ma.published_by))
                icon_url = None
                if app.icon_type == IconType.IMAGE and app.icon:
                    try:
                        icon_url = file_helpers.get_signed_file_url(app.icon)
                    except Exception:
                        icon_url = None
                result.append({
                    "id": ma.id,
                    "app_id": ma.app_id,
                    "app_name": app.name,
                    "app_description": app.description,
                    "app_mode": app.mode,
                    "app_icon": app.icon,
                    "app_icon_type": app.icon_type,
                    "app_icon_background": app.icon_background,
                    "icon_url": icon_url,
                    "published_at": ma.published_at.isoformat(),
                    "published_by_name": publisher.name if publisher else "Admin",
                    "display_order": ma.display_order,
                })
        return result

    @classmethod
    def is_published(cls, app_id: str) -> bool:
        """Check if an app is currently published in the marketplace."""
        return db.session.scalar(
            select(MarketplaceApp)
            .where(MarketplaceApp.app_id == app_id, MarketplaceApp.is_active.is_(True))
        ) is not None

    @classmethod
    def set_default_app(cls, *, app_id: str) -> MarketplaceApp:
        """Set a marketplace app as the default creator homepage app.

        Only one app can be default at a time. The previous default is unset.
        """
        marketplace_app = db.session.scalar(
            select(MarketplaceApp).where(
                MarketplaceApp.app_id == app_id,
                MarketplaceApp.is_active.is_(True),
            )
        )
        if not marketplace_app:
            raise ValueError(f"App {app_id} is not published in the marketplace")

        cls._clear_default()
        marketplace_app.is_default = True
        db.session.commit()
        logger.info("Set app %s as default creator app", app_id)
        return marketplace_app

    @classmethod
    def get_default_app(cls) -> dict | None:
        """Return the default creator homepage app, or the first active app."""
        marketplace_app = db.session.scalar(
            select(MarketplaceApp).where(
                MarketplaceApp.is_active.is_(True),
                MarketplaceApp.is_default.is_(True),
            )
        )
        # Fallback: first active app by display_order
        if not marketplace_app:
            marketplace_app = db.session.scalar(
                select(MarketplaceApp)
                .where(MarketplaceApp.is_active.is_(True))
                .order_by(MarketplaceApp.display_order, MarketplaceApp.published_at.desc())
                .limit(1)
            )
        if not marketplace_app:
            return None

        app = db.session.scalar(select(App).where(App.id == marketplace_app.app_id))
        if not app:
            return None

        from graphon.file import helpers as file_helpers

        from models.model import IconType

        icon_url = None
        if app.icon_type == IconType.IMAGE and app.icon:
            try:
                icon_url = file_helpers.get_signed_file_url(app.icon)
            except Exception:
                icon_url = None

        return {
            "id": marketplace_app.id,
            "app_id": marketplace_app.app_id,
            "app_name": app.name,
            "app_description": app.description,
            "app_mode": app.mode,
            "app_icon": app.icon,
            "app_icon_type": app.icon_type,
            "app_icon_background": app.icon_background,
            "icon_url": icon_url,
            "is_default": marketplace_app.is_default,
        }

    @classmethod
    def _clear_default(cls) -> None:
        """Clear the is_default flag on all marketplace apps."""
        current_defaults = list(
            db.session.scalars(
                select(MarketplaceApp).where(MarketplaceApp.is_default.is_(True))
            ).all()
        )
        for app in current_defaults:
            app.is_default = False
        if current_defaults:
            db.session.flush()
