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
