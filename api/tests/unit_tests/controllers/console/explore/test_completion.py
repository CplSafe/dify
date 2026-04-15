from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from werkzeug.exceptions import InternalServerError

import controllers.console.explore.completion as completion_module
from controllers.console.app.error import (
    ConversationCompletedError,
)
from controllers.console.explore.error import NotChatAppError, NotCompletionAppError
from controllers.web.error import InvokeRateLimitError as InvokeRateLimitHttpError
from models import Account
from models.model import AppMode
from services.errors.llm import InvokeRateLimitError


def unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


@pytest.fixture
def user():
    return MagicMock(spec=Account)


@pytest.fixture
def completion_app():
    return MagicMock(app=MagicMock(mode=AppMode.COMPLETION))


@pytest.fixture
def chat_app():
    return MagicMock(app=MagicMock(mode=AppMode.CHAT))


@pytest.fixture
def payload_data():
    return {"inputs": {}, "query": "hi"}


@pytest.fixture
def payload_patch(payload_data):
    return patch.object(
        type(completion_module.console_ns),
        "payload",
        new_callable=PropertyMock,
        return_value=payload_data,
    )


@pytest.fixture(autouse=True)
def creator_balance_check_patch(request):
    # Tests whose enclosing class sets ``_exercise_real_balance_reason = True``
    # exercise the real gate and must NOT be double-patched.
    cls = getattr(request.node, "cls", None)
    if cls is not None and getattr(cls, "_exercise_real_balance_reason", False):
        yield
        return
    with patch.object(completion_module, "_creator_marketplace_balance_reason", return_value=None):
        yield


class TestCompletionApi:
    def test_post_success(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                return_value={"ok": True},
            ),
            patch.object(
                completion_module.helper,
                "compact_generate_response",
                return_value=("ok", 200),
            ),
        ):
            result = method(completion_app)

        assert result == ("ok", 200)

    def test_post_wrong_app_mode(self):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        installed_app = MagicMock(app=MagicMock(mode=AppMode.CHAT))

        with pytest.raises(NotCompletionAppError):
            method(installed_app)

    def test_conversation_completed(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.conversation.ConversationCompletedError(),
            ),
        ):
            with pytest.raises(ConversationCompletedError):
                method(completion_app)

    def test_internal_error(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=Exception("boom"),
            ),
        ):
            with pytest.raises(InternalServerError):
                method(completion_app)

    def test_conversation_not_exists(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.conversation.ConversationNotExistsError(),
            ),
        ):
            with pytest.raises(completion_module.NotFound):
                method(completion_app)

    def test_app_unavailable(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.app_model_config.AppModelConfigBrokenError(),
            ),
        ):
            with pytest.raises(completion_module.AppUnavailableError):
                method(completion_app)

    def test_provider_not_initialized(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.ProviderTokenNotInitError("not init"),
            ),
        ):
            with pytest.raises(completion_module.ProviderNotInitializeError):
                method(completion_app)

    def test_quota_exceeded(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.QuotaExceededError(),
            ),
        ):
            with pytest.raises(completion_module.ProviderQuotaExceededError):
                method(completion_app)

    def test_model_not_supported(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.ModelCurrentlyNotSupportError(),
            ),
        ):
            with pytest.raises(completion_module.ProviderModelCurrentlyNotSupportError):
                method(completion_app)

    def test_invoke_error(self, app, completion_app, user, payload_patch):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.InvokeError("invoke failed"),
            ),
        ):
            with pytest.raises(completion_module.CompletionRequestError):
                method(completion_app)

    def test_streaming_owner_balance_insufficient_returns_owner_message(self, app, completion_app, user):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)
        payload = {"inputs": {}, "query": "hi", "response_mode": "streaming"}

        with (
            app.test_request_context("/", json={}),
            patch.object(
                type(completion_module.console_ns),
                "payload",
                new_callable=PropertyMock,
                return_value=payload,
            ),
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module,
                "_creator_marketplace_balance_reason",
                return_value=completion_module._INSUFFICIENT_OWNER_BALANCE_MESSAGE,
            ),
        ):
            result = method(completion_app)

        body = result.get_data(as_text=True)
        assert result.status_code == 200
        assert result.mimetype == "text/event-stream"
        assert '"event": "message"' in body
        assert completion_module._INSUFFICIENT_OWNER_BALANCE_MESSAGE in body

    def test_blocking_member_balance_insufficient_returns_member_message(self, app, completion_app, user):
        api = completion_module.CompletionApi()
        method = unwrap(api.post)
        payload = {"inputs": {}, "query": "hi", "response_mode": "blocking"}

        with (
            app.test_request_context("/", json={}),
            patch.object(
                type(completion_module.console_ns),
                "payload",
                new_callable=PropertyMock,
                return_value=payload,
            ),
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module,
                "_creator_marketplace_balance_reason",
                return_value=completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE,
            ),
        ):
            body, status = method(completion_app)

        assert status == 402
        assert body == {"message": completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE}


class TestCompletionStopApi:
    def test_stop_success(self, completion_app, user):
        api = completion_module.CompletionStopApi()
        method = unwrap(api.post)

        user.id = "u1"

        with (
            patch.object(completion_module, "current_user", user),
            patch.object(completion_module.AppTaskService, "stop_task"),
        ):
            resp, status = method(completion_app, "task-1")

        assert status == 200
        assert resp == {"result": "success"}

    def test_stop_wrong_app_mode(self):
        api = completion_module.CompletionStopApi()
        method = unwrap(api.post)

        installed_app = MagicMock(app=MagicMock(mode=AppMode.CHAT))

        with pytest.raises(NotCompletionAppError):
            method(installed_app, "task")


class TestChatApi:
    def test_post_success(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                return_value={"ok": True},
            ),
            patch.object(
                completion_module.helper,
                "compact_generate_response",
                return_value=("ok", 200),
            ),
        ):
            result = method(chat_app)

        assert result == ("ok", 200)

    def test_post_not_chat_app(self):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        installed_app = MagicMock(app=MagicMock(mode=AppMode.COMPLETION))

        with pytest.raises(NotChatAppError):
            method(installed_app)

    def test_rate_limit_error(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=InvokeRateLimitError("limit"),
            ),
        ):
            with pytest.raises(InvokeRateLimitHttpError):
                method(chat_app)

    def test_owner_balance_insufficient_returns_owner_sse_message(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module,
                "_creator_marketplace_balance_reason",
                return_value=completion_module._INSUFFICIENT_OWNER_BALANCE_MESSAGE,
            ),
        ):
            result = method(chat_app)

        body = result.get_data(as_text=True)
        assert result.status_code == 200
        assert result.mimetype == "text/event-stream"
        assert '"event": "message"' in body
        assert completion_module._INSUFFICIENT_OWNER_BALANCE_MESSAGE in body

    def test_member_balance_insufficient_returns_member_sse_message(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module,
                "_creator_marketplace_balance_reason",
                return_value=completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE,
            ),
        ):
            result = method(chat_app)

        body = result.get_data(as_text=True)
        assert result.status_code == 200
        assert result.mimetype == "text/event-stream"
        assert completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE in body

    def test_conversation_completed_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.conversation.ConversationCompletedError(),
            ),
        ):
            with pytest.raises(ConversationCompletedError):
                method(chat_app)

    def test_conversation_not_exists_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.conversation.ConversationNotExistsError(),
            ),
        ):
            with pytest.raises(completion_module.NotFound):
                method(chat_app)

    def test_app_unavailable_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.services.errors.app_model_config.AppModelConfigBrokenError(),
            ),
        ):
            with pytest.raises(completion_module.AppUnavailableError):
                method(chat_app)

    def test_provider_not_initialized_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.ProviderTokenNotInitError("not init"),
            ),
        ):
            with pytest.raises(completion_module.ProviderNotInitializeError):
                method(chat_app)

    def test_quota_exceeded_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.QuotaExceededError(),
            ),
        ):
            with pytest.raises(completion_module.ProviderQuotaExceededError):
                method(chat_app)

    def test_model_not_supported_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.ModelCurrentlyNotSupportError(),
            ),
        ):
            with pytest.raises(completion_module.ProviderModelCurrentlyNotSupportError):
                method(chat_app)

    def test_invoke_error_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=completion_module.InvokeError("invoke failed"),
            ),
        ):
            with pytest.raises(completion_module.CompletionRequestError):
                method(chat_app)

    def test_internal_error_chat(self, app, chat_app, user, payload_patch):
        api = completion_module.ChatApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/", json={}),
            payload_patch,
            patch.object(completion_module, "current_user", user),
            patch.object(
                completion_module.AppGenerateService,
                "generate",
                side_effect=Exception("boom"),
            ),
        ):
            with pytest.raises(InternalServerError):
                method(chat_app)


class TestCreatorMarketplaceBalanceReason:
    """Cover the actual gate used by explore/completion for marketplace apps.

    Regression: members used to call ``check_balance_positive(account_id)``
    which only inspects ``UserBalance`` and blocks owners who hold their funds
    in ``TenantBalance.balance``. The gate now delegates to ``check_can_run``
    so owners with a positive workspace balance are allowed through.
    """

    _exercise_real_balance_reason = True

    def _patch_marketplace_hit(self):
        return patch.object(
            completion_module.db.session,
            "scalar",
            return_value=MagicMock(),
        )

    def _patch_marketplace_miss(self):
        return patch.object(
            completion_module.db.session,
            "scalar",
            return_value=None,
        )

    def test_private_app_skips_billing_check(self):
        user = MagicMock(spec=Account, id="u1")

        with (
            self._patch_marketplace_miss(),
            patch.object(completion_module.UserBillingService, "check_can_run") as check_can_run,
        ):
            result = completion_module._creator_marketplace_balance_reason("app1", user, "tenant1")

        assert result is None
        check_can_run.assert_not_called()

    def test_owner_with_positive_tenant_balance_passes(self):
        user = MagicMock(spec=Account, id="owner1")

        with (
            self._patch_marketplace_hit(),
            patch.object(
                completion_module.UserBillingService,
                "check_can_run",
                return_value=(True, None),
            ),
        ):
            result = completion_module._creator_marketplace_balance_reason("app1", user, "tenant1")

        assert result is None

    def test_owner_without_tenant_balance_returns_owner_message(self):
        user = MagicMock(spec=Account, id="owner1")

        with (
            self._patch_marketplace_hit(),
            patch.object(
                completion_module.UserBillingService,
                "check_can_run",
                return_value=(False, "INSUFFICIENT_OWNER_BUDGET"),
            ),
        ):
            result = completion_module._creator_marketplace_balance_reason("app1", user, "tenant1")

        assert result == completion_module._INSUFFICIENT_OWNER_BALANCE_MESSAGE

    def test_member_without_user_balance_returns_member_message(self):
        user = MagicMock(spec=Account, id="member1")

        with (
            self._patch_marketplace_hit(),
            patch.object(
                completion_module.UserBillingService,
                "check_can_run",
                return_value=(False, "INSUFFICIENT_USER_BUDGET"),
            ),
        ):
            result = completion_module._creator_marketplace_balance_reason("app1", user, "tenant1")

        assert result == completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE

    def test_drained_tenant_pool_returns_member_message(self):
        user = MagicMock(spec=Account, id="member1")

        with (
            self._patch_marketplace_hit(),
            patch.object(
                completion_module.UserBillingService,
                "check_can_run",
                return_value=(False, "INSUFFICIENT_TENANT_BUDGET"),
            ),
        ):
            result = completion_module._creator_marketplace_balance_reason("app1", user, "tenant1")

        assert result == completion_module._INSUFFICIENT_MEMBER_BALANCE_MESSAGE


class TestChatStopApi:
    def test_stop_success(self, chat_app, user):
        api = completion_module.ChatStopApi()
        method = unwrap(api.post)

        user.id = "u1"

        with (
            patch.object(completion_module, "current_user", user),
            patch.object(completion_module.AppTaskService, "stop_task"),
        ):
            resp, status = method(chat_app, "task-1")

        assert status == 200
        assert resp == {"result": "success"}

    def test_stop_not_chat_app(self):
        api = completion_module.ChatStopApi()
        method = unwrap(api.post)

        installed_app = MagicMock(app=MagicMock(mode=AppMode.COMPLETION))

        with pytest.raises(NotChatAppError):
            method(installed_app, "task")
