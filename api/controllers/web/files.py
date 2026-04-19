from flask import request

import services
from controllers.common.errors import (
    FilenameNotExistsError,
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from controllers.web.wraps import WebApiResource
from extensions.ext_database import db
from fields.file_fields import FileResponse
from services.file_service import FileService

register_schema_models(web_ns, FileResponse)


@web_ns.route("/files/upload")
class FileApi(WebApiResource):
    @web_ns.doc(
        description="上传文件供 Web 应用使用（multipart/form-data）。"
                    "支持图片、文档、音频等多种文件类型，会自动校验文件大小和格式。"
                    "上传成功后返回文件 ID，可在后续消息请求的 files 字段中引用。",
        responses={
            201: "上传成功，返回文件信息",
            400: "请求错误（未上传文件、文件名缺失等）",
            413: "文件过大",
            415: "不支持的文件类型",
        },
    )
    @web_ns.response(201, "上传成功", web_ns.models[FileResponse.__name__])
    def post(self, app_model, end_user):
        """上传文件"""
        if "file" not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        file = request.files["file"]
        if not file.filename:
            raise FilenameNotExistsError

        source = request.form.get("source")
        if source not in ("datasets", None):
            source = None

        try:
            upload_file = FileService(db.engine).upload_file(
                filename=file.filename,
                content=file.read(),
                mimetype=file.mimetype,
                user=end_user,
                source="datasets" if source == "datasets" else None,
            )
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        response = FileResponse.model_validate(upload_file, from_attributes=True)
        return response.model_dump(mode="json"), 201
