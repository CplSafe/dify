"""User global API key endpoints.

GET    /creator/api-key  — get current user's global API key
POST   /creator/api-key  — generate a new global API key
DELETE /creator/api-key  — revoke current global API key
"""

from flask import request
from flask_restx import Resource
from sqlalchemy import select

from controllers.console import console_ns
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
    def get(self):
        """Return the current user's global API key (masked)."""
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
    def post(self):
        """Generate (or regenerate) the current user's global API key."""
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
    def delete(self):
        """Revoke the current user's global API key."""
        current_user, _ = current_account_with_tenant()
        key = db.session.scalar(
            select(UserGlobalApiKey).where(UserGlobalApiKey.account_id == current_user.id)
        )
        if key:
            db.session.delete(key)
            db.session.commit()
        return {"result": "success"}
