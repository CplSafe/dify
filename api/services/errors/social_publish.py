"""Domain errors for social publishing.

The HTTP-status mapping lives at
``api/controllers/console/social_publish/error.py`` so that this module stays
free of Werkzeug imports and can be reused by Celery workers in P2.
"""

from services.errors.base import BaseServiceError


class SocialPublishError(BaseServiceError):
    """Base class for all social-publish domain errors."""

    code: str = "social_publish_error"


class FeatureDisabledError(SocialPublishError):
    code = "feature_disabled"


class PlatformUnsupportedError(SocialPublishError):
    code = "platform_unsupported"


class AccountNotFoundError(SocialPublishError):
    code = "account_not_found"


class TenantMismatchError(SocialPublishError):
    """Raised when an actor tries to act on another tenant's resource.

    Surfaced as 403 in the HTTP layer; service layer raises this whenever the
    repository returns ``None`` for an `(id, tenant_id)` lookup that the
    caller had a reason to believe should exist.
    """

    code = "tenant_mismatch"


class AccountExpiredError(SocialPublishError):
    code = "account_expired"


class SessionExpiredError(SocialPublishError):
    code = "session_expired"


class SauUnreachableError(SocialPublishError):
    """Network/timeout failures to sau."""

    code = "sau_unreachable"


class SauApiError(SocialPublishError):
    """Non-2xx response from sau."""

    code = "sau_api_error"

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"sau {status_code}: {body[:200]}")
        self.status_code = status_code
        self.body = body


# ---------- P2: publish flow ----------


class TaskNotFoundError(SocialPublishError):
    code = "task_not_found"


class TaskInvalidPayloadError(SocialPublishError):
    """Surfaced when title is missing / over the length cap, tags overshoot
    the platform limit, etc. The HTTP layer maps this to 400."""

    code = "task_invalid_payload"


class WorkNotFoundError(SocialPublishError):
    code = "work_not_found"


class TaskAlreadyInFlightError(SocialPublishError):
    """Same account already has a non-terminal publish task. The HTTP layer
    maps this to 409 so the FE can show a clear "wait or cancel" message."""

    code = "task_already_in_flight"


class VideoTooLargeError(SocialPublishError):
    """Video exceeds SOCIAL_PUBLISH_MAX_VIDEO_BYTES — multipart upload would
    overload the api process. P3 will route large files via presigned URL."""

    code = "video_too_large"


class VideoNotFoundError(SocialPublishError):
    """Couldn't load CreatorWork.file_key bytes from storage."""

    code = "video_not_found"


# ---------- P3: tier / queue ----------


class TaskQuotaExceededError(SocialPublishError):
    """Tenant has hit its tier-derived max-pending quota. The HTTP layer
    maps this to 429 so the FE can surface a "wait or upgrade" message."""

    code = "task_quota_exceeded"
