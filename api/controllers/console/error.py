from libs.exception import BaseHTTPException


class AlreadySetupError(BaseHTTPException):
    error_code = "already_setup"
    description = "系统已完成安装，请刷新页面或返回首页"
    code = 403


class NotSetupError(BaseHTTPException):
    error_code = "not_setup"
    description = "系统尚未初始化，请先完成初始化设置"
    code = 401


class NotInitValidateError(BaseHTTPException):
    error_code = "not_init_validated"
    description = "初始化验证尚未完成，请先完成验证"
    code = 401


class InitValidateFailedError(BaseHTTPException):
    error_code = "init_validate_failed"
    description = "初始化验证失败，请检查密码后重试"
    code = 401


class AccountNotLinkTenantError(BaseHTTPException):
    error_code = "account_not_link_tenant"
    description = "账号未关联工作空间"
    code = 403


class AlreadyActivateError(BaseHTTPException):
    error_code = "already_activate"
    description = "链接无效或账号已激活，请重新检查"
    code = 403


class NotAllowedCreateWorkspace(BaseHTTPException):
    error_code = "not_allowed_create_workspace"
    description = "未找到工作空间，请联系管理员邀请您加入"
    code = 400


class WorkspaceMembersLimitExceeded(BaseHTTPException):
    error_code = "limit_exceeded"
    description = "无法添加成员，已超出工作空间成员数量上限"
    code = 400


class WorkspacesLimitExceeded(BaseHTTPException):
    error_code = "limit_exceeded"
    description = "无法创建工作空间，已超出工作空间数量上限"
    code = 400


class AccountBannedError(BaseHTTPException):
    error_code = "account_banned"
    description = "该账号已被禁用"
    code = 400


class AccountNotFound(BaseHTTPException):
    error_code = "account_not_found"
    description = "未找到该账号"
    code = 400


class EmailSendIpLimitError(BaseHTTPException):
    error_code = "email_send_ip_limit"
    description = "该 IP 发送邮件过于频繁，请稍后再试"
    code = 429


class UnauthorizedAndForceLogout(BaseHTTPException):
    error_code = "unauthorized_and_force_logout"
    description = "登录状态已失效，请重新登录"
    code = 401


class AccountInFreezeError(BaseHTTPException):
    error_code = "account_in_freeze"
    code = 400
    description = "该邮箱账号在 30 天内已被注销，暂时无法重新注册"


class EducationVerifyLimitError(BaseHTTPException):
    error_code = "education_verify_limit"
    description = "Rate limit exceeded"
    code = 429


class EducationActivateLimitError(BaseHTTPException):
    error_code = "education_activate_limit"
    description = "Rate limit exceeded"
    code = 429


class ComplianceRateLimitError(BaseHTTPException):
    error_code = "compliance_rate_limit"
    description = "Rate limit exceeded for downloading compliance report."
    code = 429


class SystemAdminRequired(BaseHTTPException):
    error_code = "system_admin_required"
    description = "This API is restricted to system administrators only."
    code = 403
