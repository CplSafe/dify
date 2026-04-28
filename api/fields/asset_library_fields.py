"""Flask-RESTx field definitions for asset-library responses.

Used by ``controllers.console.asset_library.*`` to marshal ``AssetLibrary``
ORM rows + paginated lists into JSON. File-type assets carry a transient
``signed_url`` that controllers populate from ``upload_files`` before
returning the response — the model itself doesn't store URLs. Controllers
are also responsible for attaching a ``created_by`` ``Account`` reference
(name/avatar) when present; the model only stores the creator's UUID.
"""

from flask_restx import fields

from libs.helper import TimestampField

asset_creator_fields = {
    "id": fields.String,
    "name": fields.String,
    "avatar": fields.String,
}


asset_fields = {
    "id": fields.String,
    "tenant_id": fields.String,
    "asset_type": fields.String,
    "name": fields.String,
    "description": fields.String,
    "tags": fields.Raw,
    "category": fields.String,
    # File-only fields (NULL for prompt assets)
    "upload_file_id": fields.String,
    "cover_url": fields.String,
    "signed_url": fields.String,  # populated by controller
    "duration": fields.Float,
    "width": fields.Integer,
    "height": fields.Integer,
    "file_size": fields.Integer,
    # Prompt-only fields (NULL for file assets)
    "content": fields.String,
    "prompt_variables": fields.Raw,
    "created_by": fields.Nested(asset_creator_fields, allow_null=True),
    "created_at": TimestampField,
    "updated_at": TimestampField,
}


asset_pagination_fields = {
    "data": fields.List(fields.Nested(asset_fields)),
    "total": fields.Integer,
    "page": fields.Integer,
    "limit": fields.Integer,
    "has_more": fields.Boolean,
}
