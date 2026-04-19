from typing import Literal

from flask import request
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator
from sqlalchemy.orm import sessionmaker
from werkzeug.exceptions import NotFound

from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from controllers.web.error import NotChatAppError
from controllers.web.wraps import WebApiResource
from core.app.entities.app_invoke_entities import InvokeFrom
from extensions.ext_database import db
from fields.conversation_fields import (
    ConversationInfiniteScrollPagination,
    ResultResponse,
    SimpleConversation,
)
from libs.helper import uuid_value
from models.model import AppMode
from services.conversation_service import ConversationService
from services.errors.conversation import ConversationNotExistsError, LastConversationNotExistsError
from services.web_conversation_service import WebConversationService


class ConversationListQuery(BaseModel):
    last_id: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    pinned: bool | None = None
    sort_by: Literal["created_at", "-created_at", "updated_at", "-updated_at"] = "-updated_at"

    @field_validator("last_id")
    @classmethod
    def validate_last_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return uuid_value(value)


class ConversationRenamePayload(BaseModel):
    name: str | None = None
    auto_generate: bool = False

    @model_validator(mode="after")
    def validate_name_requirement(self):
        if not self.auto_generate:
            if self.name is None or not self.name.strip():
                raise ValueError("name is required when auto_generate is false")
        return self


register_schema_models(web_ns, ConversationListQuery, ConversationRenamePayload)


@web_ns.route("/conversations")
class ConversationListApi(WebApiResource):
    @web_ns.doc(
        description="获取对话列表（分页，游标翻页）。仅适用于对话类应用。"
                    "支持按置顶状态过滤和多种排序方式。",
        params={
            "last_id": {"description": "游标，上一页最后一条对话 ID", "type": "string", "required": False},
            "limit": {
                "description": "每页返回数量，范围 1-100，默认 20",
                "type": "integer",
                "required": False,
                "default": 20,
            },
            "pinned": {
                "description": "按置顶状态过滤，true 只返回置顶，false 只返回未置顶",
                "type": "string",
                "enum": ["true", "false"],
                "required": False,
            },
            "sort_by": {
                "description": "排序方式，默认 -updated_at（最新更新在前）",
                "type": "string",
                "enum": ["created_at", "-created_at", "updated_at", "-updated_at"],
                "required": False,
                "default": "-updated_at",
            },
        },
        responses={
            200: "成功，返回对话列表",
            401: "未认证",
            403: "无访问权限",
            404: "应用不存在或非对话类应用",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model, end_user):
        """获取对话列表"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        raw_args = request.args.to_dict()
        query = ConversationListQuery.model_validate(raw_args)

        try:
            with sessionmaker(db.engine).begin() as session:
                pagination = WebConversationService.pagination_by_last_id(
                    session=session,
                    app_model=app_model,
                    user=end_user,
                    last_id=query.last_id,
                    limit=query.limit,
                    invoke_from=InvokeFrom.WEB_APP,
                    pinned=query.pinned,
                    sort_by=query.sort_by,
                )
                adapter = TypeAdapter(SimpleConversation)
                conversations = [adapter.validate_python(item, from_attributes=True) for item in pagination.data]
                return ConversationInfiniteScrollPagination(
                    limit=pagination.limit,
                    has_more=pagination.has_more,
                    data=conversations,
                ).model_dump(mode="json")
        except LastConversationNotExistsError:
            raise NotFound("Last Conversation Not Exists.")


@web_ns.route("/conversations/<uuid:c_id>")
class ConversationApi(WebApiResource):
    @web_ns.doc(
        description="删除指定对话。仅适用于对话类应用。",
        params={"c_id": {"description": "对话 UUID", "type": "string", "required": True}},
        responses={
            204: "删除成功",
            401: "未认证",
            403: "无访问权限",
            404: "对话不存在或非对话类应用",
        },
    )
    def delete(self, app_model, end_user, c_id):
        """删除对话"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)
        try:
            ConversationService.delete(app_model, conversation_id, end_user)
        except ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        return ResultResponse(result="success").model_dump(mode="json"), 204


@web_ns.route("/conversations/<uuid:c_id>/name")
class ConversationRenameApi(WebApiResource):
    @web_ns.expect(web_ns.models[ConversationRenamePayload.__name__])
    @web_ns.doc(
        description="重命名对话，或根据第一条消息自动生成对话名称。",
        params={"c_id": {"description": "对话 UUID", "type": "string", "required": True}},
        responses={
            200: "重命名成功，返回对话信息",
            400: "请求格式错误",
            401: "未认证",
            403: "无访问权限",
            404: "对话不存在或非对话类应用",
        },
    )
    def post(self, app_model, end_user, c_id):
        """重命名对话"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)

        payload = ConversationRenamePayload.model_validate(web_ns.payload or {})

        try:
            conversation = ConversationService.rename(
                app_model, conversation_id, end_user, payload.name, payload.auto_generate
            )
            return (
                TypeAdapter(SimpleConversation)
                .validate_python(conversation, from_attributes=True)
                .model_dump(mode="json")
            )
        except ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")


@web_ns.route("/conversations/<uuid:c_id>/pin")
class ConversationPinApi(WebApiResource):
    @web_ns.doc(
        description="置顶对话，使其显示在对话列表顶部。",
        params={"c_id": {"description": "对话 UUID", "type": "string", "required": True}},
        responses={
            200: "置顶成功",
            401: "未认证",
            403: "无访问权限",
            404: "对话不存在或非对话类应用",
        },
    )
    def patch(self, app_model, end_user, c_id):
        """置顶对话"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)

        try:
            WebConversationService.pin(app_model, conversation_id, end_user)
        except ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")

        return ResultResponse(result="success").model_dump(mode="json")


@web_ns.route("/conversations/<uuid:c_id>/unpin")
class ConversationUnPinApi(WebApiResource):
    @web_ns.doc(
        description="取消置顶对话，将其从置顶位置移除。",
        params={"c_id": {"description": "对话 UUID", "type": "string", "required": True}},
        responses={
            200: "取消置顶成功",
            401: "未认证",
            403: "无访问权限",
            404: "对话不存在或非对话类应用",
        },
    )
    def patch(self, app_model, end_user, c_id):
        """取消置顶对话"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)
        WebConversationService.unpin(app_model, conversation_id, end_user)

        return ResultResponse(result="success").model_dump(mode="json")
