"""Smoke tests that AssetLibrary model is importable and has expected columns/indexes."""

from models.asset_library import AssetLibrary


def test_asset_library_has_required_columns():
    cols = {c.name for c in AssetLibrary.__table__.columns}
    required = {
        "id",
        "tenant_id",
        "created_by",
        "asset_type",
        "name",
        "description",
        "tags",
        "category",
        "upload_file_id",
        "cover_url",
        "duration",
        "width",
        "height",
        "file_size",
        "content",
        "prompt_variables",
        "created_at",
        "updated_at",
    }
    assert required.issubset(cols)


def test_asset_library_table_name():
    assert AssetLibrary.__tablename__ == "asset_libraries"


def test_asset_library_index_present():
    index_names = {idx.name for idx in AssetLibrary.__table__.indexes}
    assert "idx_asset_lib_tenant_type_created" in index_names
