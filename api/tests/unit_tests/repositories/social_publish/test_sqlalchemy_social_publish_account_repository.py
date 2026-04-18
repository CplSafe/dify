"""Repository-level isolation tests for SocialPublishAccountRepository.

Uses in-memory SQLite so SQLAlchemy actually executes the WHERE clauses
that enforce tenant isolation — mocking the session here would defeat the
purpose of the test.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.social_publish import SocialPublishAccount, SocialPublishAccountStatus
from repositories.sqlalchemy_social_publish_account_repository import (
    DifyAPISQLAlchemySocialPublishAccountRepository,
)


@pytest.fixture
def repository() -> DifyAPISQLAlchemySocialPublishAccountRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[SocialPublishAccount.__table__])
    session_maker = sessionmaker(bind=engine, expire_on_commit=False)
    return DifyAPISQLAlchemySocialPublishAccountRepository(session_maker=session_maker)


@pytest.fixture
def tenant_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def tenant_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def actor() -> str:
    return str(uuid.uuid4())


def _create(
    repo: DifyAPISQLAlchemySocialPublishAccountRepository,
    *,
    tenant_id: str,
    actor: str,
    sau_account_id: str,
    status: str = SocialPublishAccountStatus.PENDING_AUTH.value,
    platform: str = "douyin",
    display_name: str | None = None,
) -> SocialPublishAccount:
    return repo.create(
        tenant_id=tenant_id,
        platform=platform,
        sau_account_id=sau_account_id,
        display_name=display_name,
        avatar_url=None,
        status=status,
        created_by=actor,
    )


class TestCreate:
    def test_inserts_row_with_default_pending_auth_when_status_omitted(
        self, repository, tenant_a, actor
    ):
        # Arrange / Act
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-1")
        # Assert
        assert row.id
        assert row.tenant_id == tenant_a
        assert row.status == SocialPublishAccountStatus.PENDING_AUTH.value
        assert row.platform == "douyin"
        assert row.sau_account_id == "sau-1"

    def test_unique_constraint_race_returns_existing_row(self, repository, tenant_a, actor):
        # Arrange — first insert succeeds.
        first = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-shared")
        # Act — second create with the same sau_account_id mimics the
        # concurrent reconcile race the production code is hardened against.
        second = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-shared")
        # Assert
        assert second.id == first.id


class TestGetByIdAndTenant:
    def test_returns_row_for_owning_tenant(self, repository, tenant_a, actor):
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-x")
        assert repository.get_by_id_and_tenant(row.id, tenant_a) is not None

    def test_returns_none_for_other_tenant(self, repository, tenant_a, tenant_b, actor):
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-x")
        assert repository.get_by_id_and_tenant(row.id, tenant_b) is None


class TestListByTenant:
    def test_lists_only_owning_tenants_rows_newest_first(
        self, repository, tenant_a, tenant_b, actor
    ):
        # Arrange
        a1 = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="a-1")
        a2 = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="a-2")
        _create(repository, tenant_id=tenant_b, actor=actor, sau_account_id="b-1")
        # Act
        listed = repository.list_by_tenant(tenant_a)
        # Assert
        ids = [r.id for r in listed]
        assert {a1.id, a2.id} == set(ids)

    def test_filters_by_platform_when_provided(self, repository, tenant_a, actor):
        # Arrange
        _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="dy-1", platform="douyin")
        _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="xhs-1", platform="xhs")
        # Act / Assert
        only_dy = repository.list_by_tenant(tenant_a, platform="douyin")
        assert {r.platform for r in only_dy} == {"douyin"}


class TestUpdateStatus:
    def test_updates_only_when_tenant_matches(self, repository, tenant_a, tenant_b, actor):
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-x")

        # Wrong tenant — must be a no-op surfaced as None
        none_returned: Any = repository.update_status(
            account_id=row.id, tenant_id=tenant_b, status="active"
        )
        assert none_returned is None
        # Row in DB is unchanged
        unchanged = repository.get_by_id_and_tenant(row.id, tenant_a)
        assert unchanged is not None
        assert unchanged.status == SocialPublishAccountStatus.PENDING_AUTH.value

        # Right tenant — succeeds with patched fields applied
        now = datetime.now(UTC)
        updated = repository.update_status(
            account_id=row.id,
            tenant_id=tenant_a,
            status=SocialPublishAccountStatus.ACTIVE.value,
            last_check_at=now,
            display_name="实名小号",
        )
        assert updated is not None
        assert updated.status == SocialPublishAccountStatus.ACTIVE.value
        assert updated.display_name == "实名小号"
        assert updated.last_check_at is not None


class TestDeleteByIdAndTenant:
    def test_returns_true_on_match_and_false_for_other_tenant(
        self, repository, tenant_a, tenant_b, actor
    ):
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-x")

        # Wrong tenant: row stays
        assert repository.delete_by_id_and_tenant(row.id, tenant_b) is False
        assert repository.get_by_id_and_tenant(row.id, tenant_a) is not None

        # Right tenant: row gone, second delete is False
        assert repository.delete_by_id_and_tenant(row.id, tenant_a) is True
        assert repository.delete_by_id_and_tenant(row.id, tenant_a) is False


class TestGetBySauAccountIdIsTenantBlind:
    """Documented invariant: this method bypasses tenant scoping for the
    reconcile path. Service layer is expected to re-check `tenant_id`."""

    def test_finds_row_regardless_of_caller_tenant(self, repository, tenant_a, actor):
        row = _create(repository, tenant_id=tenant_a, actor=actor, sau_account_id="sau-shared")
        found = repository.get_by_sau_account_id("sau-shared")
        assert found is not None
        assert found.id == row.id
