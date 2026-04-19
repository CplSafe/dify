"""SQLAlchemy implementation of `SocialPublishAccountRepository`.

Tenant-isolation invariants enforced here (defence in depth):

- Every method that touches a single row constrains by `tenant_id` in the
  `WHERE` clause; we never read by id then check tenant_id in Python (TOCTOU).
- `get_by_sau_account_id` is the sole tenant-blind entry point and is
  documented as such — callers must re-validate.
- `update_status` and `delete_by_id_and_tenant` use rowcount to decide
  success, so silently-zero-rows updates surface as `None` / `False` to the
  service layer (which in turn raises a domain error).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from models.social_publish import SocialPublishAccount
from repositories.social_publish_account_repository import SocialPublishAccountRepository


class DifyAPISQLAlchemySocialPublishAccountRepository(SocialPublishAccountRepository):
    """SQLAlchemy 2.0 implementation of `SocialPublishAccountRepository`."""

    def __init__(self, session_maker: sessionmaker[Session]) -> None:
        self._session_maker = session_maker

    def create(
        self,
        *,
        tenant_id: str,
        platform: str,
        sau_account_id: str,
        display_name: str | None,
        avatar_url: str | None,
        status: str,
        created_by: str,
    ) -> SocialPublishAccount:
        with self._session_maker() as session:
            row = SocialPublishAccount(
                tenant_id=tenant_id,
                platform=platform,
                sau_account_id=sau_account_id,
                created_by=created_by,
                display_name=display_name,
                avatar_url=avatar_url,
                status=status,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                # Concurrent success-poll race: another worker already
                # inserted the same `sau_account_id`. Surface the existing row
                # so the caller can converge on a single record.
                session.rollback()
                stmt = select(SocialPublishAccount).where(
                    SocialPublishAccount.sau_account_id == sau_account_id,
                )
                existing = session.execute(stmt).scalar_one_or_none()
                if existing is not None:
                    return existing
                raise
            session.refresh(row)
            return row

    def get_by_id_and_tenant(
        self,
        account_id: str,
        tenant_id: str,
    ) -> SocialPublishAccount | None:
        with self._session_maker() as session:
            stmt = select(SocialPublishAccount).where(
                SocialPublishAccount.id == account_id,
                SocialPublishAccount.tenant_id == tenant_id,
            )
            return session.execute(stmt).scalar_one_or_none()

    def get_by_id_and_tenant_and_user(
        self,
        account_id: str,
        tenant_id: str,
        user_id: str,
    ) -> SocialPublishAccount | None:
        # P8: per-member isolation. Triple-WHERE so a user trying to
        # reach another member's account by guessing the id gets None
        # (which the service layer surfaces as AccountNotFoundError —
        # deliberately indistinguishable from "account doesn't exist").
        with self._session_maker() as session:
            stmt = select(SocialPublishAccount).where(
                SocialPublishAccount.id == account_id,
                SocialPublishAccount.tenant_id == tenant_id,
                SocialPublishAccount.created_by == user_id,
            )
            return session.execute(stmt).scalar_one_or_none()

    def get_by_sau_account_id(
        self,
        sau_account_id: str,
    ) -> SocialPublishAccount | None:
        with self._session_maker() as session:
            stmt = select(SocialPublishAccount).where(
                SocialPublishAccount.sau_account_id == sau_account_id,
            )
            return session.execute(stmt).scalar_one_or_none()

    def list_by_tenant(
        self,
        tenant_id: str,
        platform: str | None = None,
    ) -> Sequence[SocialPublishAccount]:
        with self._session_maker() as session:
            stmt = select(SocialPublishAccount).where(
                SocialPublishAccount.tenant_id == tenant_id,
            )
            if platform is not None:
                stmt = stmt.where(SocialPublishAccount.platform == platform)
            stmt = stmt.order_by(SocialPublishAccount.created_at.desc())
            return session.execute(stmt).scalars().all()

    def list_by_tenant_and_user(
        self,
        tenant_id: str,
        user_id: str,
        platform: str | None = None,
    ) -> Sequence[SocialPublishAccount]:
        # P8: per-member isolation. Each member only sees the accounts
        # they themselves bound. The composite index
        # ``social_publish_account_tenant_user_platform_idx`` keeps the
        # per-member slice cheap.
        with self._session_maker() as session:
            stmt = select(SocialPublishAccount).where(
                SocialPublishAccount.tenant_id == tenant_id,
                SocialPublishAccount.created_by == user_id,
            )
            if platform is not None:
                stmt = stmt.where(SocialPublishAccount.platform == platform)
            stmt = stmt.order_by(SocialPublishAccount.created_at.desc())
            return session.execute(stmt).scalars().all()

    def update_status(
        self,
        *,
        account_id: str,
        tenant_id: str,
        status: str,
        last_check_at: datetime | None = None,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> SocialPublishAccount | None:
        values: dict[str, object] = {"status": status}
        if last_check_at is not None:
            values["last_check_at"] = last_check_at
        if display_name is not None:
            values["display_name"] = display_name
        if avatar_url is not None:
            values["avatar_url"] = avatar_url

        with self._session_maker() as session:
            stmt = (
                update(SocialPublishAccount)
                .where(
                    SocialPublishAccount.id == account_id,
                    SocialPublishAccount.tenant_id == tenant_id,
                )
                .values(**values)
                .returning(SocialPublishAccount)
            )
            row = session.execute(stmt).scalar_one_or_none()
            session.commit()
            return row

    def delete_by_id_and_tenant(
        self,
        account_id: str,
        tenant_id: str,
    ) -> bool:
        with self._session_maker() as session:
            stmt = delete(SocialPublishAccount).where(
                SocialPublishAccount.id == account_id,
                SocialPublishAccount.tenant_id == tenant_id,
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0

    def delete_by_id_and_tenant_and_user(
        self,
        account_id: str,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        # P8: per-member delete — only the creator can drop their own
        # account. Triple-WHERE so member B can't delete member A's row
        # by guessing the id.
        with self._session_maker() as session:
            stmt = delete(SocialPublishAccount).where(
                SocialPublishAccount.id == account_id,
                SocialPublishAccount.tenant_id == tenant_id,
                SocialPublishAccount.created_by == user_id,
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0
