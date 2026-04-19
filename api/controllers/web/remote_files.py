import urllib.parse

import httpx
from graphon.file import helpers as file_helpers
from pydantic import BaseModel, Field, HttpUrl

import services
from controllers.common import helpers
from controllers.common.errors import (
    FileTooLargeError,
    RemoteFileUploadError,
    UnsupportedFileTypeError,
)
from core.helper import ssrf_proxy
from extensions.ext_database import db
from fields.file_fields import FileWithSignedUrl, RemoteFileInfo
from services.file_service import FileService

from ..common.schema import register_schema_models
from . import web_ns
from .wraps import WebApiResource


class RemoteFileUploadPayload(BaseModel):
    url: HttpUrl = Field(description="Remote file URL")


register_schema_models(web_ns, RemoteFileUploadPayload, RemoteFileInfo, FileWithSignedUrl)


@web_ns.route("/remote-files/<path:url>")
class RemoteFileInfoApi(WebApiResource):
    @web_ns.doc(
        description="获取远程文件的基本信息（Content-Type、Content-Length）。"
                    "URL 需经过 URL 编码后作为路径参数传入。",
        params={"url": {"description": "远程文件 URL（URL 编码后的路径参数）", "type": "string"}},
        responses={
            200: "成功，返回文件类型和大小",
            400: "URL 格式错误",
            404: "远程文件不存在",
            500: "获取远程文件失败",
        },
    )
    @web_ns.response(200, "远程文件信息", web_ns.models[RemoteFileInfo.__name__])
    def get(self, app_model, end_user, url):
        """获取远程文件信息"""
        decoded_url = urllib.parse.unquote(url)
        resp = ssrf_proxy.head(decoded_url)
        if resp.status_code != httpx.codes.OK:
            # failed back to get method
            resp = ssrf_proxy.get(decoded_url, timeout=3)
        resp.raise_for_status()
        info = RemoteFileInfo(
            file_type=resp.headers.get("Content-Type", "application/octet-stream"),
            file_length=int(resp.headers.get("Content-Length", -1)),
        )
        return info.model_dump(mode="json")


@web_ns.route("/remote-files/upload")
class RemoteFileUploadApi(WebApiResource):
    @web_ns.expect(web_ns.models[RemoteFileUploadPayload.__name__])
    @web_ns.doc(
        description="从远程 URL 下载文件并上传至平台存储，供 Web 应用使用。"
                    "系统会自动获取文件内容、校验文件大小和格式，"
                    "上传成功后返回含签名 URL 的文件信息。",
        responses={
            201: "上传成功，返回文件信息（含签名 URL）",
            400: "请求格式错误",
            413: "文件过大",
            415: "不支持的文件类型",
            500: "获取或上传远程文件失败",
        },
    )
    @web_ns.response(201, "上传成功", web_ns.models[FileWithSignedUrl.__name__])
    def post(self, app_model, end_user):
        """从远程 URL 上传文件"""
        payload = RemoteFileUploadPayload.model_validate(web_ns.payload or {})
        url = str(payload.url)

        try:
            resp = ssrf_proxy.head(url=url)
            if resp.status_code != httpx.codes.OK:
                resp = ssrf_proxy.get(url=url, timeout=3, follow_redirects=True)
            if resp.status_code != httpx.codes.OK:
                raise RemoteFileUploadError(f"Failed to fetch file from {url}: {resp.text}")
        except httpx.RequestError as e:
            raise RemoteFileUploadError(f"Failed to fetch file from {url}: {str(e)}")

        file_info = helpers.guess_file_info_from_response(resp)

        if not FileService.is_file_size_within_limit(extension=file_info.extension, file_size=file_info.size):
            raise FileTooLargeError

        content = resp.content if resp.request.method == "GET" else ssrf_proxy.get(url).content

        try:
            upload_file = FileService(db.engine).upload_file(
                filename=file_info.filename,
                content=content,
                mimetype=file_info.mimetype,
                user=end_user,
                source_url=url,
            )
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError

        payload1 = FileWithSignedUrl(
            id=upload_file.id,
            name=upload_file.name,
            size=upload_file.size,
            extension=upload_file.extension,
            url=file_helpers.get_signed_file_url(upload_file_id=upload_file.id),
            mime_type=upload_file.mime_type,
            created_by=upload_file.created_by,
            created_at=int(upload_file.created_at.timestamp()),
        )
        return payload1.model_dump(mode="json"), 201
