import logging
from collections.abc import Generator
from json import dumps
from typing import Any, Literal
from uuid import UUID, uuid4

from graphon.model_runtime.errors.invoke import InvokeError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.common.errors import raise_workflow_budget_http_error
from controllers.common.schema import register_schema_models
from controllers.console.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.explore.error import NotChatAppError, NotCompletionAppError
from controllers.console.explore.wraps import InstalledAppResource
from controllers.web.error import InvokeRateLimitError as InvokeRateLimitHttpError
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import (
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from extensions.ext_database import db
from libs import helper
from libs.datetime_utils import naive_utc_now
from libs.login import current_user
from models import Account
from models.creator import MarketplaceApp
from models.model import AppMode
from services.app_generate_service import AppGenerateService
from services.app_task_service import AppTaskService
from services.errors.llm import InvokeRateLimitError
from services.user_billing_service import UserBillingService
from services.wallet.exceptions import WorkflowBudgetExceeded

from .. import console_ns

logger = logging.getLogger(__name__)
# Owner sees a top-up CTA because they control the workspace wallet.
_INSUFFICIENT_OWNER_BALANCE_MESSAGE = "余额不足，请先前往[充值页](/creator/balance)处理后再继续生成。"
# Members can't top up the workspace pool themselves — they must ask the owner.
_INSUFFICIENT_MEMBER_BALANCE_MESSAGE = "您的额度不足，请联系工作区所有者为您分配额度或充值。"


def _creator_marketplace_balance_reason(app_id: str, account: Account, tenant_id: str) -> str | None:
    """Return the localized error message when the marketplace run must be blocked.

    Returns ``None`` when the run may proceed. Differentiates the owner vs
    member case so the UI can direct the owner to top up while telling the
    member to contact their workspace owner.

    The check only applies to marketplace-published apps — private apps keep
    their existing (non-billing) explore flow.
    """
    marketplace_entry = db.session.scalar(
        select(MarketplaceApp).where(
            MarketplaceApp.app_id == str(app_id),
            MarketplaceApp.is_active == True,
        )
    )
    if not marketplace_entry:
        return None

    can_run, error_code = UserBillingService.check_can_run(account.id, tenant_id)
    if can_run:
        return None
    if error_code == "INSUFFICIENT_OWNER_BUDGET":
        return _INSUFFICIENT_OWNER_BALANCE_MESSAGE
    return _INSUFFICIENT_MEMBER_BALANCE_MESSAGE


def _creator_marketplace_balance_stream_response(
    message: str,
    conversation_id: str | None = None,
) -> Generator[str, None, None]:
    message_id = str(uuid4())
    safe_conversation_id = conversation_id or ""
    yield f"data: {dumps({
        'event': 'message',
        'conversation_id': safe_conversation_id,
        'task_id': '',
        'id': message_id,
        'answer': message,
    }, ensure_ascii=False)}\n\n"
    yield f"data: {dumps({
        'event': 'message_end',
        'conversation_id': safe_conversation_id,
        'id': message_id,
        'metadata': {'retriever_resources': []},
        'files': [],
    }, ensure_ascii=False)}\n\n"


class CompletionMessageExplorePayload(BaseModel):
    inputs: dict[str, Any]
    query: str = ""
    files: list[dict[str, Any]] | None = None
    response_mode: Literal["blocking", "streaming"] | None = None
    retriever_from: str = Field(default="explore_app")


class ChatMessagePayload(BaseModel):
    inputs: dict[str, Any]
    query: str
    files: list[dict[str, Any]] | None = None
    conversation_id: str | None = None
    parent_message_id: str | None = None
    retriever_from: str = Field(default="explore_app")

    @field_validator("conversation_id", "parent_message_id", mode="before")
    @classmethod
    def normalize_uuid(cls, value: str | UUID | None) -> str | None:
        """
        Accept blank IDs and validate UUID format when provided.
        """
        if not value:
            return None

        try:
            return helper.uuid_value(value)
        except ValueError as exc:
            raise ValueError("must be a valid UUID") from exc


register_schema_models(console_ns, CompletionMessageExplorePayload, ChatMessagePayload)


# define completion api for user
@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/completion-messages",
    endpoint="installed_app_completion",
)
class CompletionApi(InstalledAppResource):
    @console_ns.expect(console_ns.models[CompletionMessageExplorePayload.__name__])
    def post(self, installed_app):
        app_model = installed_app.app
        if app_model.mode != AppMode.COMPLETION:
            raise NotCompletionAppError()

        payload = CompletionMessageExplorePayload.model_validate(console_ns.payload or {})
        args = payload.model_dump(exclude_none=True)

        streaming = payload.response_mode == "streaming"
        args["auto_generate_name"] = False

        installed_app.last_used_at = naive_utc_now()
        db.session.commit()

        try:
            if not isinstance(current_user, Account):
                raise ValueError("current_user must be an Account instance")
            balance_reason = _creator_marketplace_balance_reason(
                app_model.id, current_user, installed_app.tenant_id
            )
            if balance_reason is not None:
                if streaming:
                    return helper.compact_generate_response(
                        _creator_marketplace_balance_stream_response(balance_reason)
                    )
                return {"message": balance_reason}, 402
            response = AppGenerateService.generate(
                app_model=app_model, user=current_user, args=args, invoke_from=InvokeFrom.EXPLORE, streaming=streaming
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logger.exception("App model config broken.")
            raise AppUnavailableError()
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


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/completion-messages/<string:task_id>/stop",
    endpoint="installed_app_stop_completion",
)
class CompletionStopApi(InstalledAppResource):
    def post(self, installed_app, task_id):
        app_model = installed_app.app
        if app_model.mode != AppMode.COMPLETION:
            raise NotCompletionAppError()

        if not isinstance(current_user, Account):
            raise ValueError("current_user must be an Account instance")

        AppTaskService.stop_task(
            task_id=task_id,
            invoke_from=InvokeFrom.EXPLORE,
            user_id=current_user.id,
            app_mode=AppMode.value_of(app_model.mode),
        )

        return {"result": "success"}, 200


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/chat-messages",
    endpoint="installed_app_chat_completion",
)
class ChatApi(InstalledAppResource):
    @console_ns.expect(console_ns.models[ChatMessagePayload.__name__])
    def post(self, installed_app):
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        payload = ChatMessagePayload.model_validate(console_ns.payload or {})
        args = payload.model_dump(exclude_none=True)

        args["auto_generate_name"] = False

        installed_app.last_used_at = naive_utc_now()
        db.session.commit()

        try:
            if not isinstance(current_user, Account):
                raise ValueError("current_user must be an Account instance")
            balance_reason = _creator_marketplace_balance_reason(
                app_model.id, current_user, installed_app.tenant_id
            )
            if balance_reason is not None:
                return helper.compact_generate_response(
                    _creator_marketplace_balance_stream_response(balance_reason, payload.conversation_id)
                )
            response = AppGenerateService.generate(
                app_model=app_model, user=current_user, args=args, invoke_from=InvokeFrom.EXPLORE, streaming=True
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logger.exception("App model config broken.")
            raise AppUnavailableError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except WorkflowBudgetExceeded as ex:
            raise_workflow_budget_http_error(ex.code)
        except InvokeRateLimitError as ex:
            raise InvokeRateLimitHttpError(ex.description)
        except ValueError as e:
            raise e
        except Exception:
            logger.exception("internal server error.")
            raise InternalServerError()


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/chat-messages/<string:task_id>/stop",
    endpoint="installed_app_stop_chat_completion",
)
class ChatStopApi(InstalledAppResource):
    def post(self, installed_app, task_id):
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        if not isinstance(current_user, Account):
            raise ValueError("current_user must be an Account instance")

        AppTaskService.stop_task(
            task_id=task_id,
            invoke_from=InvokeFrom.EXPLORE,
            user_id=current_user.id,
            app_mode=app_mode,
        )

        return {"result": "success"}, 200
