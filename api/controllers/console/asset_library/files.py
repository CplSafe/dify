"""POST /asset-library/files — multipart upload for image / audio / video assets.

The handler parses multipart form data (file + metadata fields), translates
``asset_type`` into the service-layer enum, and delegates everything else
(MIME whitelist, ``FileService.upload_file``, metadata extraction, persistence)
to :meth:`AssetLibraryService.create_file_asset`.

Domain errors are translated into HTTP responses:

- 400 BadRequest for unsupported MIME, malformed input, or unsupported file type
- 413 RequestEntityTooLarge for size violations

Prompt assets are explicitly rejected here — they have a JSON-only sibling
endpoint at ``POST /asset-library/prompts``.
"""

from __future__ import annotations

import json
import logging

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from controllers.console import console_ns
from controllers.console.asset_library.assets import attach_creator
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from fields.asset_library_fields import asset_fields
from libs.login import current_account_with_tenant, login_required
from services.asset_library.constants import AssetType
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    FileSizeLimitExceededError,
    UnsupportedMimeTypeError,
)
from services.errors.file import FileTooLargeError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)


@console_ns.route("/asset-library/files")
class AssetFileUploadApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.marshal_with(asset_fields)
    def post(self):
        """Upload a file asset (image / audio / video).

        Multipart form fields:

        - ``file`` (required): the binary upload
        - ``asset_type`` (required): one of ``image``, ``audio``, ``video``
        - ``name`` (optional): defaults to the uploaded filename
        - ``description`` (optional)
        - ``category`` (optional)
        - ``tags`` (optional): JSON-encoded array of strings, e.g. ``["a","b"]``
        """
        if "file" not in request.files:
            raise BadRequest("file part is required")
        file = request.files["file"]
        if not file.filename:
            raise BadRequest("uploaded file has no filename")

        try:
            asset_type = AssetType(request.form.get("asset_type", ""))
        except ValueError as exc:
            raise BadRequest("asset_type must be one of: image, audio, video") from exc

        if asset_type is AssetType.PROMPT:
            raise BadRequest("use POST /asset-library/prompts for prompt assets")

        name = request.form.get("name") or file.filename or "untitled"
        description = request.form.get("description")
        category = request.form.get("category")
        tags_raw = request.form.get("tags") or "[]"
        try:
            parsed_tags = json.loads(tags_raw)
        except (TypeError, ValueError) as exc:
            raise BadRequest("tags must be a JSON array of strings") from exc
        if not isinstance(parsed_tags, list):
            raise BadRequest("tags must be a JSON array of strings")
        tags = [str(t) for t in parsed_tags]

        content = file.read()

        user, tenant_id = current_account_with_tenant()
        try:
            asset = AssetLibraryService.create_file_asset(
                tenant_id=tenant_id,
                user=user,
                file_content=content,
                filename=file.filename,
                mimetype=file.mimetype or "application/octet-stream",
                asset_type=asset_type,
                name=name,
                description=description,
                tags=tags,
                category=category,
            )
        except UnsupportedMimeTypeError as exc:
            raise BadRequest(str(exc)) from exc
        except UnsupportedFileTypeError as exc:
            raise BadRequest("unsupported file type") from exc
        except (FileSizeLimitExceededError, FileTooLargeError) as exc:
            raise RequestEntityTooLarge(str(exc)) from exc

        return attach_creator(asset), 201
