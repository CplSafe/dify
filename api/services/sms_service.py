"""Aliyun SMS service for sending verification codes."""

import json
import logging
import secrets
import string
from datetime import UTC, datetime

from configs import dify_config
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.sms_code_log import SmsCodeLog

logger = logging.getLogger(__name__)

SMS_CODE_LENGTH = 6
SMS_CODE_TTL_SECONDS = 300  # 5 minutes
SMS_SEND_RATE_LIMIT_SECONDS = 60  # 1 code per minute per phone


def _generate_code() -> str:
    # Use `secrets` (CSPRNG) — these codes grant authentication, so a
    # predictable seed in the standard `random` module would be a real risk.
    return "".join(secrets.choice(string.digits) for _ in range(SMS_CODE_LENGTH))


def _redis_key(phone: str) -> str:
    return f"sms_code:{phone}"


def _rate_limit_key(phone: str) -> str:
    return f"sms_code_rate:{phone}"


class SmsService:
    _client = None

    @classmethod
    def _get_client(cls):
        """Lazily initialise the Aliyun SMS client (thread-safe singleton)."""
        if cls._client is not None:
            return cls._client

        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_tea_openapi.models import Config

        config = Config(
            access_key_id=dify_config.ALIYUN_SMS_ACCESS_KEY_ID,
            access_key_secret=dify_config.ALIYUN_SMS_ACCESS_KEY_SECRET,
            endpoint="dysmsapi.aliyuncs.com",
        )
        cls._client = Client(config)
        return cls._client

    @classmethod
    def send_verification_code(cls, phone: str) -> str:
        """Send a verification code to *phone*.

        Returns a token (the Redis key suffix) that the caller stores and
        later passes back for verification.

        Raises ``RuntimeError`` on Aliyun API failure.
        """
        # Rate-limit: one code per minute per phone
        if redis_client.exists(_rate_limit_key(phone)):
            raise ValueError("发送短信过于频繁，请稍后再试")

        code = _generate_code()

        # Send via Aliyun first — only persist state on success
        cls._send_aliyun_sms(phone, code, dify_config.ALIYUN_SMS_TEMPLATE_CODE)

        # Persist to Redis only after successful send
        payload = json.dumps({"phone": phone, "code": code})
        redis_client.setex(_redis_key(phone), SMS_CODE_TTL_SECONDS, payload)
        redis_client.setex(_rate_limit_key(phone), SMS_SEND_RATE_LIMIT_SECONDS, "1")

        # Persist log for admin audit
        cls._log_sms(phone, code, "login_verify")

        return phone  # token is the phone itself (matched against Redis)

    @classmethod
    def send_invite_sms(cls, phone: str, workspace_name: str, token: str) -> None:
        """Send an invitation SMS with a token to *phone*.

        The activate URL domain is baked into the Aliyun SMS template
        (required by Aliyun policy — variables cannot contain full URLs).
        The template uses ${workspace} and ${token} variables.
        """
        template_code = dify_config.ALIYUN_SMS_INVITE_TEMPLATE_CODE
        if not template_code:
            raise RuntimeError("ALIYUN_SMS_INVITE_TEMPLATE_CODE is not configured")

        template_param = json.dumps({"workspace": workspace_name, "token": token})
        cls._send_aliyun_sms_raw(phone, template_code, template_param)
        cls._log_sms(phone, "", "invite")

    @classmethod
    def verify_code(cls, phone: str, code: str) -> bool:
        """Verify *code* for *phone*. Consumes the code on success."""
        data_raw = redis_client.get(_redis_key(phone))
        if data_raw is None:
            return False
        data = json.loads(data_raw)
        if data.get("code") != code:
            return False
        # Consume
        redis_client.delete(_redis_key(phone))
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _send_aliyun_sms(cls, phone: str, code: str, template_code: str) -> None:
        template_param = json.dumps({"code": code})
        cls._send_aliyun_sms_raw(phone, template_code, template_param)

    @classmethod
    def _send_aliyun_sms_raw(cls, phone: str, template_code: str, template_param: str) -> None:
        from alibabacloud_dysmsapi20170525.models import SendSmsRequest

        client = cls._get_client()
        req = SendSmsRequest(
            phone_numbers=phone,
            sign_name=dify_config.ALIYUN_SMS_SIGN_NAME,
            template_code=template_code,
            template_param=template_param,
        )
        resp = client.send_sms(req)
        body = resp.body
        if body.code != "OK":
            logger.error("Aliyun SMS send failed: code=%s message=%s", body.code, body.message)
            raise RuntimeError(f"短信发送失败: {body.message}")
        logger.info("SMS sent to %s, biz_id=%s", phone, body.biz_id)

    @classmethod
    def _log_sms(cls, phone: str, code: str, purpose: str) -> None:
        log = SmsCodeLog(
            phone=phone,
            code=code,
            purpose=purpose,
            sent_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.session.add(log)
        db.session.commit()

    # ------------------------------------------------------------------
    # Admin log query
    # ------------------------------------------------------------------

    @classmethod
    def get_sms_logs(cls, page: int = 1, per_page: int = 20, phone: str | None = None):
        """Return paginated SMS logs for admin UI."""
        query = db.session.query(SmsCodeLog).order_by(SmsCodeLog.sent_at.desc())
        if phone:
            query = query.filter(SmsCodeLog.phone.ilike(f"%{phone}%"))
        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "items": [
                {
                    "id": item.id,
                    "phone": item.phone,
                    "code": item.code[:2] + "****" if item.code and len(item.code) >= 2 else "******",
                    "purpose": item.purpose,
                    "sent_at": item.sent_at.isoformat() if item.sent_at else None,
                }
                for item in items
            ],
        }
