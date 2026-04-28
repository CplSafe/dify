"""POST /asset-library/prompts — JSON create endpoint for prompt assets.

The handler validates required fields locally then delegates to
``AssetLibraryService.create_prompt_asset``, which re-validates
``prompt_variables`` via Pydantic and persists the row.

Domain errors translate to HTTP 400 BadRequest. File-type assets have a
sibling multipart endpoint at ``POST /asset-library/files``.
"""

from __future__ import annotations

import logging

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.asset_library.assets import attach_creator
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from fields.asset_library_fields import asset_fields
from libs.login import current_account_with_tenant, login_required
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import InvalidPromptVariablesError

logger = logging.getLogger(__name__)


@console_ns.route("/asset-library/prompts")
class AssetPromptCreateApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.marshal_with(asset_fields)
    def post(self):
        """Create a prompt asset from a JSON body.

        Body fields:

        - ``name`` (required): non-empty string
        - ``content`` (required): non-empty string (the prompt template)
        - ``prompt_variables`` (optional): list of variable specs; defaults to ``[]``
        - ``description`` (optional)
        - ``category`` (optional)
        - ``tags`` (optional): list of strings; defaults to ``[]``
        """
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            raise BadRequest("request body must be a JSON object")

        name = body.get("name")
        content = body.get("content")
        if not isinstance(name, str) or not name.strip():
            raise BadRequest("name is required")
        if not isinstance(content, str) or not content:
            raise BadRequest("content is required")

        prompt_variables = body.get("prompt_variables")
        if prompt_variables is None:
            prompt_variables = []
        if not isinstance(prompt_variables, list):
            raise BadRequest("prompt_variables must be a list")

        tags = body.get("tags")
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            raise BadRequest("tags must be a list")

        description = body.get("description")
        category = body.get("category")

        user, tenant_id = current_account_with_tenant()

        try:
            asset = AssetLibraryService.create_prompt_asset(
                tenant_id=tenant_id,
                user=user,
                name=name,
                content=content,
                prompt_variables=prompt_variables,
                description=description,
                tags=tags,
                category=category,
            )
        except InvalidPromptVariablesError as exc:
            raise BadRequest(str(exc)) from exc

        return attach_creator(asset), 201
