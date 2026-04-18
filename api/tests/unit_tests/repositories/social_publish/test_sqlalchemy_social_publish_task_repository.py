"""Repository-level tests for SocialPublishTaskRepository.

Same approach as the account repo tests: real in-memory SQLite so the
WHERE clauses that enforce tenant isolation actually run.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.social_publish import (
    SocialPublishTask,
    SocialPublishTaskStatus,
)
from repositories.sqlalchemy_social_publish_task_repository import (
    DifyAPISQLAlchemySocialPublishTaskRepository,
)


@pytest.fixture
def repository() -> DifyAPISQLAlchemySocialPublishTaskRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[SocialPublishTask.__table__])
    session_maker = sessionmaker(bind=engine, expire_on_commit=False)
    return DifyAPISQLAlchemySocialPublishTaskRepository(session_maker=session_maker)


@pytest.fixture
def tenant_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def tenant_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def actor() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def account() -> str:
    return str(uuid.uuid4())


def _create(
    repo: DifyAPISQLAlchemySocialPublishTaskRepository,
    *,
    tenant_id: str,
    account_id: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    work_id: str | None = None,
) -> SocialPublishTask:
    return repo.create(
        tenant_id=tenant_id,
        account_id=account_id,
        platform="douyin",
        payload=payload or {"title": "hello"},
        created_by=actor,
        work_id=work_id,
    )


class TestCreate:
    def test_inserts_row_in_pending_status(self, repository, tenant_a, account, actor):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        assert row.status == SocialPublishTaskStatus.PENDING.value
        assert row.tenant_id == tenant_a
        assert row.payload == {"title": "hello"}


class TestTenantIsolation:
    def test_get_returns_none_for_other_tenant(
        self, repository, tenant_a, tenant_b, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        assert repository.get_by_id_and_tenant(row.id, tenant_a) is not None
        assert repository.get_by_id_and_tenant(row.id, tenant_b) is None

    def test_attach_sau_task_id_no_op_for_other_tenant(
        self, repository, tenant_a, tenant_b, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        assert (
            repository.attach_sau_task_id(
                task_id=row.id, tenant_id=tenant_b, sau_task_id="evil"
            )
            is None
        )
        # The row in tenant A is untouched.
        fresh = repository.get_by_id_and_tenant(row.id, tenant_a)
        assert fresh is not None
        assert fresh.sau_task_id is None
        assert fresh.status == SocialPublishTaskStatus.PENDING.value

    def test_update_terminal_no_op_for_other_tenant(
        self, repository, tenant_a, tenant_b, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        # Wrong-tenant terminal call — has_active_for_account returns the
        # tenant's view, so nothing should flip in tenant A.
        repository.update_terminal(
            task_id=row.id,
            tenant_id=tenant_b,
            status=SocialPublishTaskStatus.SUCCESS.value,
            result_url="https://x",
        )
        fresh = repository.get_by_id_and_tenant(row.id, tenant_a)
        assert fresh is not None
        assert fresh.status == SocialPublishTaskStatus.PENDING.value
        assert fresh.result_url is None


class TestActivePerAccount:
    def test_pending_counts_as_active_running_too(
        self, repository, tenant_a, account, actor
    ):
        _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        assert (
            repository.has_active_for_account(tenant_id=tenant_a, account_id=account)
            is True
        )

    def test_terminal_does_not_count_as_active(
        self, repository, tenant_a, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        repository.update_terminal(
            task_id=row.id,
            tenant_id=tenant_a,
            status=SocialPublishTaskStatus.SUCCESS.value,
            result_url="https://x",
        )
        assert (
            repository.has_active_for_account(tenant_id=tenant_a, account_id=account)
            is False
        )

    def test_active_check_scoped_to_tenant(
        self, repository, tenant_a, tenant_b, account, actor
    ):
        _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        # Same account_id under tenant_b sees no active rows.
        assert (
            repository.has_active_for_account(tenant_id=tenant_b, account_id=account)
            is False
        )


class TestStateMachine:
    def test_attach_then_running_then_terminal(
        self, repository, tenant_a, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        attached = repository.attach_sau_task_id(
            task_id=row.id, tenant_id=tenant_a, sau_task_id="cel-1"
        )
        assert attached is not None
        assert attached.status == SocialPublishTaskStatus.QUEUED.value
        assert attached.sau_task_id == "cel-1"

        running = repository.update_status_to_running(
            task_id=row.id, tenant_id=tenant_a
        )
        assert running is not None
        assert running.status == SocialPublishTaskStatus.RUNNING.value

        done = repository.update_terminal(
            task_id=row.id,
            tenant_id=tenant_a,
            status=SocialPublishTaskStatus.SUCCESS.value,
            result_url="https://x",
        )
        assert done is not None
        assert done.status == SocialPublishTaskStatus.SUCCESS.value
        assert done.result_url == "https://x"

    def test_terminal_update_is_idempotent(
        self, repository, tenant_a, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        repository.update_terminal(
            task_id=row.id,
            tenant_id=tenant_a,
            status=SocialPublishTaskStatus.SUCCESS.value,
            result_url="https://first",
        )
        # Second call must not overwrite the terminal status — the second
        # poller arriving moments later would otherwise win the race.
        repository.update_terminal(
            task_id=row.id,
            tenant_id=tenant_a,
            status=SocialPublishTaskStatus.FAILED.value,
            error_code="should_not_apply",
        )
        fresh = repository.get_by_id_and_tenant(row.id, tenant_a)
        assert fresh is not None
        assert fresh.status == SocialPublishTaskStatus.SUCCESS.value
        assert fresh.error_code is None

    def test_running_only_advances_from_queued(
        self, repository, tenant_a, account, actor
    ):
        row = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        # Pending row — running transition is a no-op.
        assert (
            repository.update_status_to_running(task_id=row.id, tenant_id=tenant_a)
            is None
        )
        fresh = repository.get_by_id_and_tenant(row.id, tenant_a)
        assert fresh is not None
        assert fresh.status == SocialPublishTaskStatus.PENDING.value


class TestListing:
    def test_list_filters_by_account_and_status_and_sorts_by_created_desc(
        self, repository, tenant_a, account, actor
    ):
        a1 = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        other_account = str(uuid.uuid4())
        _create(repository, tenant_id=tenant_a, account_id=other_account, actor=actor)
        a3 = _create(repository, tenant_id=tenant_a, account_id=account, actor=actor)
        repository.update_terminal(
            task_id=a1.id,
            tenant_id=tenant_a,
            status=SocialPublishTaskStatus.SUCCESS.value,
            result_url="https://x",
        )

        listed = repository.list_by_tenant(tenant_a, account_id=account)
        assert {r.id for r in listed} == {a1.id, a3.id}
        # Newest first.
        assert listed[0].id == a3.id

        succeeded = repository.list_by_tenant(
            tenant_a,
            account_id=account,
            status=SocialPublishTaskStatus.SUCCESS.value,
        )
        assert [r.id for r in succeeded] == [a1.id]
