"""HTTP-shaped subclasses of social-publish domain errors.

The service layer raises plain ``services.errors.social_publish`` exceptions;
the controller layer translates them into these Werkzeug-aware classes so
``ExternalApi`` serialises a uniform ``{code, message, status}`` body.
"""

from libs.exception import BaseHTTPException


class FeatureDisabledHTTPError(BaseHTTPException):
    error_code = "feature_disabled"
    description = "发布中心当前未启用，请联系管理员"
    code = 503


class PlatformUnsupportedHTTPError(BaseHTTPException):
    error_code = "platform_unsupported"
    description = "暂不支持该平台"
    code = 400


class AccountNotFoundHTTPError(BaseHTTPException):
    error_code = "account_not_found"
    description = "账号不存在"
    code = 404


class TenantMismatchHTTPError(BaseHTTPException):
    error_code = "tenant_mismatch"
    description = "无权访问此账号"
    code = 403


class AccountExpiredHTTPError(BaseHTTPException):
    error_code = "account_expired"
    description = "账号授权已过期，请重新授权"
    code = 409


class SessionExpiredHTTPError(BaseHTTPException):
    error_code = "session_expired"
    description = "扫码会话已过期，请重新发起授权"
    code = 404


class SauUnreachableHTTPError(BaseHTTPException):
    error_code = "sau_unreachable"
    description = "发布服务暂不可用，请稍后再试"
    code = 502


class SauApiHTTPError(BaseHTTPException):
    error_code = "sau_api_error"
    description = "发布服务返回错误"
    code = 502


# ---------- P2: publish flow ----------


class TaskNotFoundHTTPError(BaseHTTPException):
    error_code = "task_not_found"
    description = "发布任务不存在"
    code = 404


class TaskInvalidPayloadHTTPError(BaseHTTPException):
    error_code = "task_invalid_payload"
    description = "发布参数不合法，请检查标题/话题/简介"
    code = 400


class TaskAlreadyInFlightHTTPError(BaseHTTPException):
    error_code = "task_already_in_flight"
    description = "该账号当前已有发布任务，请等待结束后再试"
    code = 409


class WorkNotFoundHTTPError(BaseHTTPException):
    error_code = "work_not_found"
    description = "作品不存在"
    code = 404


class VideoNotFoundHTTPError(BaseHTTPException):
    error_code = "video_not_found"
    description = "视频文件不存在或已过期"
    code = 404


class VideoTooLargeHTTPError(BaseHTTPException):
    error_code = "video_too_large"
    description = "视频文件过大，请联系管理员或将其压缩后重试"
    code = 413
