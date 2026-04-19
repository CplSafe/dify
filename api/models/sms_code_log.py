"""SMS verification code log for admin audit."""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import StringUUID


class SmsCodeLog(TypeBase):
    __tablename__ = "sms_code_logs"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="sms_code_log_pkey"),
        sa.Index("sms_code_log_phone_idx", "phone"),
        sa.Index("sms_code_log_sent_at_idx", "sent_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    phone: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(10))
    purpose: Mapped[str] = mapped_column(String(32))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
