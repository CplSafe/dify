import logging
from typing import Literal

from flask import request
from graphon.model_runtime.errors.invoke import InvokeError
from pydantic import BaseModel, Field, TypeAdapter, field_validator
from werkzeug.exceptions import InternalServerError, NotFound

from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from controllers.web.error import (
    AppMoreLikeThisDisabledError,
    AppSuggestedQuestionsAfterAnswerDisabledError,
    CompletionRequestError,
    NotChatAppError,
    NotCompletionAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.web.wraps import WebApiResource
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from fields.conversation_fields import ResultResponse
from fields.message_fields import SuggestedQuestionsResponse, WebMessageInfiniteScrollPagination, WebMessageListItem
from libs import helper
from libs.helper import uuid_value
from models.enums import FeedbackRating
from models.model import AppMode
from services.app_generate_service import AppGenerateService
from services.errors.app import MoreLikeThisDisabledError
from services.errors.conversation import ConversationNotExistsError
from services.errors.message import (
    FirstMessageNotExistsError,
    MessageNotExistsError,
    SuggestedQuestionsAfterAnswerDisabledError,
)
from services.message_service import MessageService

logger = logging.getLogger(__name__)


class MessageListQuery(BaseModel):
    conversation_id: str = Field(description="Conversation UUID")
    first_id: str | None = Field(default=None, description="First message ID for pagination")
    limit: int = Field(default=20, ge=1, le=100, description="Number of messages to return (1-100)")

    @field_validator("conversation_id", "first_id")
    @classmethod
    def validate_uuid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return uuid_value(value)


class MessageFeedbackPayload(BaseModel):
    rating: Literal["like", "dislike"] | None = Field(default=None, description="Feedback rating")
    content: str | None = Field(default=None, description="Feedback content")


class MessageMoreLikeThisQuery(BaseModel):
    response_mode: Literal["blocking", "streaming"] = Field(
        description="Response mode",
    )


register_schema_models(web_ns, MessageListQuery, MessageFeedbackPayload, MessageMoreLikeThisQuery)


@web_ns.route("/messages")
class MessageListApi(WebApiResource):
    @web_ns.doc(
        description="获取对话中的消息列表（分页，游标翻页，从旧到新）。"
                    "仅适用于对话类应用。first_id 为游标，不传则从最新消息开始。",
        params={
            "conversation_id": {"description": "对话 UUID", "type": "string", "required": True},
            "first_id": {
                "description": "游标，当前页第一条消息 ID（用于向前翻页）",
                "type": "string",
                "required": False,
            },
            "limit": {
                "description": "每页返回数量，范围 1-100，默认 20",
                "type": "integer",
                "required": False,
                "default": 20,
            },
        },
        responses={
            200: "成功，返回消息列表",
            401: "未认证",
            403: "无访问权限",
            404: "对话不存在或非对话类应用",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model, end_user):
        """获取对话消息列表"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        raw_args = request.args.to_dict()
        query = MessageListQuery.model_validate(raw_args)

        try:
            pagination = MessageService.pagination_by_first_id(
                app_model, end_user, query.conversation_id, query.first_id, query.limit
            )
            adapter = TypeAdapter(WebMessageListItem)
            items = [adapter.validate_python(message, from_attributes=True) for message in pagination.data]
            return WebMessageInfiniteScrollPagination(
                limit=pagination.limit,
                has_more=pagination.has_more,
                data=items,
            ).model_dump(mode="json")
        except ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except FirstMessageNotExistsError:
            raise NotFound("First Message Not Exists.")


@web_ns.route("/messages/<uuid:message_id>/feedbacks")
class MessageFeedbackApi(WebApiResource):
    @web_ns.expect(web_ns.models[MessageFeedbackPayload.__name__])
    @web_ns.doc(
        description="对指定消息提交反馈（点赞 / 踩）。"
                    "rating 传 null 可撤销已有反馈，content 为可选备注。",
        params={"message_id": {"description": "消息 UUID", "type": "string", "required": True}},
        responses={
            200: "反馈提交成功",
            401: "未认证",
            403: "无访问权限",
            404: "消息不存在",
        },
    )
    def post(self, app_model, end_user, message_id):
        """提交消息反馈"""
        message_id = str(message_id)

        payload = MessageFeedbackPayload.model_validate(web_ns.payload or {})

        try:
            MessageService.create_feedback(
                app_model=app_model,
                message_id=message_id,
                user=end_user,
                rating=FeedbackRating(payload.rating) if payload.rating else None,
                content=payload.content,
            )
        except MessageNotExistsError:
            raise NotFound("Message Not Exists.")

        return ResultResponse(result="success").model_dump(mode="json")


@web_ns.route("/messages/<uuid:message_id>/more-like-this")
class MessageMoreLikeThisApi(WebApiResource):
    @web_ns.doc(
        description="根据已有消息生成类似内容（仅文本生成类应用，且需开启「更多类似结果」功能）。"
                    "通过 response_mode 参数选择 blocking 或 streaming 响应模式。",
        params={
            "message_id": {"description": "消息 UUID", "type": "string", "required": True},
            "response_mode": {
                "description": "响应模式：blocking 或 streaming",
                "type": "string",
                "enum": ["blocking", "streaming"],
                "required": True,
            },
        },
        responses={
            200: "成功，返回生成内容",
            400: "请求错误或功能未开启",
            401: "未认证",
            403: "无访问权限",
            404: "消息不存在",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model, end_user, message_id):
        """生成类似消息内容"""
        if app_model.mode != "completion":
            raise NotCompletionAppError()

        message_id = str(message_id)

        raw_args = request.args.to_dict()
        query = MessageMoreLikeThisQuery.model_validate(raw_args)

        streaming = query.response_mode == "streaming"

        try:
            response = AppGenerateService.generate_more_like_this(
                app_model=app_model,
                user=end_user,
                message_id=message_id,
                invoke_from=InvokeFrom.WEB_APP,
                streaming=streaming,
            )

            return helper.compact_generate_response(response)
        except MessageNotExistsError:
            raise NotFound("Message Not Exists.")
        except MoreLikeThisDisabledError:
            raise AppMoreLikeThisDisabledError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise e
        except Exception:
            logger.exception("internal server error.")
            raise InternalServerError()


@web_ns.route("/messages/<uuid:message_id>/suggested-questions")
class MessageSuggestedQuestionApi(WebApiResource):
    @web_ns.doc(
        description="获取消息的建议追问问题（仅对话类应用，且需开启「回答后建议问题」功能）。",
        params={"message_id": {"description": "消息 UUID", "type": "string", "required": True}},
        responses={
            200: "成功，返回建议问题列表",
            400: "请求错误或功能未开启",
            401: "未认证",
            403: "无访问权限",
            404: "消息或对话不存在",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model, end_user, message_id):
        """获取消息的建议追问问题"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        message_id = str(message_id)

        try:
            questions = MessageService.get_suggested_questions_after_answer(
                app_model=app_model, user=end_user, message_id=message_id, invoke_from=InvokeFrom.WEB_APP
            )
            # questions is a list of strings, not a list of Message objects
        except MessageNotExistsError:
            raise NotFound("Message not found")
        except ConversationNotExistsError:
            raise NotFound("Conversation not found")
        except SuggestedQuestionsAfterAnswerDisabledError:
            raise AppSuggestedQuestionsAfterAnswerDisabledError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except Exception:
            logger.exception("internal server error.")
            raise InternalServerError()

        return SuggestedQuestionsResponse(data=questions).model_dump(mode="json")
