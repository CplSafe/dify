from libs.exception import BaseHTTPException


class ApiKeyAuthFailedError(BaseHTTPException):
    error_code = "auth_failed"
    description = "{message}"
    code = 500


class InvalidEmailError(BaseHTTPException):
    error_code = "invalid_email"
    description = "邮箱地址格式不正确"
    code = 400


class PasswordMismatchError(BaseHTTPException):
    error_code = "password_mismatch"
    description = "两次输入的密码不一致"
    code = 400


class InvalidTokenError(BaseHTTPException):
    error_code = "invalid_or_expired_token"
    description = "验证链接无效或已过期，请重新操作"
    code = 400


class PasswordResetRateLimitExceededError(BaseHTTPException):
    error_code = "password_reset_rate_limit_exceeded"
    description = "发送重置密码邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 1):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class EmailRegisterRateLimitExceededError(BaseHTTPException):
    error_code = "email_register_rate_limit_exceeded"
    description = "发送注册邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 1):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class EmailChangeRateLimitExceededError(BaseHTTPException):
    error_code = "email_change_rate_limit_exceeded"
    description = "发送邮箱变更邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 1):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class OwnerTransferRateLimitExceededError(BaseHTTPException):
    error_code = "owner_transfer_rate_limit_exceeded"
    description = "发送所有权转移邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 1):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class EmailCodeError(BaseHTTPException):
    error_code = "email_code_error"
    description = "验证码无效或已过期，请重新获取"
    code = 400


class EmailOrPasswordMismatchError(BaseHTTPException):
    error_code = "email_or_password_mismatch"
    description = "邮箱或密码错误"
    code = 400


class AuthenticationFailedError(BaseHTTPException):
    error_code = "authentication_failed"
    description = "邮箱或密码错误"
    code = 401


class EmailPasswordLoginLimitError(BaseHTTPException):
    error_code = "email_code_login_limit"
    description = "密码错误次数过多，请稍后再试"
    code = 429


class EmailCodeLoginRateLimitExceededError(BaseHTTPException):
    error_code = "email_code_login_rate_limit_exceeded"
    description = "发送登录邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 5):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class EmailCodeAccountDeletionRateLimitExceededError(BaseHTTPException):
    error_code = "email_code_account_deletion_rate_limit_exceeded"
    description = "发送账号注销邮件过于频繁，请 {minutes} 分钟后再试"
    code = 429

    def __init__(self, minutes: int = 5):
        description = self.description.format(minutes=int(minutes)) if self.description else None
        super().__init__(description=description)


class EmailPasswordResetLimitError(BaseHTTPException):
    error_code = "email_password_reset_limit"
    description = "重置密码失败次数过多，请 24 小时后再试"
    code = 429


class EmailRegisterLimitError(BaseHTTPException):
    error_code = "email_register_limit"
    description = "注册验证失败次数过多，请 24 小时后再试"
    code = 429


class EmailChangeLimitError(BaseHTTPException):
    error_code = "email_change_limit"
    description = "邮箱变更失败次数过多，请 24 小时后再试"
    code = 429


class EmailAlreadyInUseError(BaseHTTPException):
    error_code = "email_already_in_use"
    description = "该邮箱已被注册"
    code = 400


class OwnerTransferLimitError(BaseHTTPException):
    error_code = "owner_transfer_limit"
    description = "所有权转移失败次数过多，请 24 小时后再试"
    code = 429


class NotOwnerError(BaseHTTPException):
    error_code = "not_owner"
    description = "您不是该工作空间的所有者"
    code = 400


class CannotTransferOwnerToSelfError(BaseHTTPException):
    error_code = "cannot_transfer_owner_to_self"
    description = "不能将所有权转移给自己"
    code = 400


class MemberNotInTenantError(BaseHTTPException):
    error_code = "member_not_in_tenant"
    description = "该成员不在此工作空间中"
    code = 400
