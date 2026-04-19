from flask import request
from pydantic import BaseModel, Field, TypeAdapter
from werkzeug.exceptions import NotFound

from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from controllers.web.error import NotCompletionAppError
from controllers.web.wraps import WebApiResource
from fields.conversation_fields import ResultResponse
from fields.message_fields import SavedMessageInfiniteScrollPagination, SavedMessageItem
from libs.helper import UUIDStrOrEmpty
from services.errors.message import MessageNotExistsError
from services.saved_message_service import SavedMessageService


class SavedMessageListQuery(BaseModel):
    last_id: UUIDStrOrEmpty | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SavedMessageCreatePayload(BaseModel):
    message_id: UUIDStrOrEmpty


register_schema_models(web_ns, SavedMessageListQuery, SavedMessageCreatePayload)


@web_ns.route("/saved-messages")
class SavedMessageListApi(WebApiResource):
    @web_ns.doc(
        description="获取已保存的消息列表（分页，游标翻页）。仅适用于文本生成类应用。",
        params={
            "last_id": {"description": "游标，上一页最后一条消息 ID", "type": "string", "required": False},
            "limit": {
                "description": "每页返回数量，范围 1-100，默认 20",
                "type": "integer",
                "required": False,
                "default": 20,
            },
        },
        responses={
            200: "成功，返回保存的消息列表",
            400: "请求错误或非文本生成类应用",
            401: "未认证",
            403: "无访问权限",
            404: "应用不存在",
        },
    )
    def get(self, app_model, end_user):
        """获取已保存的消息列表"""
        if app_model.mode != "completion":
            raise NotCompletionAppError()

        raw_args = request.args.to_dict()
        query = SavedMessageListQuery.model_validate(raw_args)

        pagination = SavedMessageService.pagination_by_last_id(app_model, end_user, query.last_id, query.limit)
        adapter = TypeAdapter(SavedMessageItem)
        items = [adapter.validate_python(message, from_attributes=True) for message in pagination.data]
        return SavedMessageInfiniteScrollPagination(
            limit=pagination.limit,
            has_more=pagination.has_more,
            data=items,
        ).model_dump(mode="json")

    @web_ns.expect(web_ns.models[SavedMessageCreatePayload.__name__])
    @web_ns.doc(
        description="收藏指定消息，供后续在已保存列表中查看。仅适用于文本生成类应用。",
        responses={
            200: "收藏成功",
            400: "请求错误或非文本生成类应用",
            401: "未认证",
            403: "无访问权限",
            404: "消息不存在",
        },
    )
    def post(self, app_model, end_user):
        """收藏消息"""
        if app_model.mode != "completion":
            raise NotCompletionAppError()

        payload = SavedMessageCreatePayload.model_validate(web_ns.payload or {})

        try:
            SavedMessageService.save(app_model, end_user, payload.message_id)
        except MessageNotExistsError:
            raise NotFound("Message Not Exists.")

        return ResultResponse(result="success").model_dump(mode="json")


@web_ns.route("/saved-messages/<uuid:message_id>")
class SavedMessageApi(WebApiResource):
    @web_ns.doc(
        description="从已保存列表中移除指定消息。仅适用于文本生成类应用。",
        params={"message_id": {"description": "消息 UUID", "type": "string", "required": True}},
        responses={
            204: "移除成功",
            400: "请求错误或非文本生成类应用",
            401: "未认证",
            403: "无访问权限",
            404: "消息不存在",
        },
    )
    def delete(self, app_model, end_user, message_id):
        """从已保存列表中移除消息"""
        message_id = str(message_id)

        if app_model.mode != "completion":
            raise NotCompletionAppError()

        SavedMessageService.delete(app_model, end_user, message_id)

        return ResultResponse(result="success").model_dump(mode="json"), 204
