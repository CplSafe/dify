"""Unit tests for CreatorTaskService."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from werkzeug.exceptions import TooManyRequests

from models.creator_task import CreatorTask, CreatorTaskStatus
from services.creator_task_service import CreatorTaskService


@patch("services.creator_task_service.db")
def test_create_task_uses_configured_in_progress_limit(mock_db):
    """The creator task gate should use the deploy-time configured limit."""
    config = SimpleNamespace(CREATOR_TASK_MAX_IN_PROGRESS=20)
    mock_db.session.scalar.return_value = 19

    with patch("services.creator_task_service.dify_config", config, create=True):
        task = CreatorTaskService.create_task(
            account_id="account-1",
            tenant_id="tenant-1",
            app_id="app-1",
            installed_app_id="installed-1",
            conversation_id=None,
            workflow_run_id=None,
            title="video task",
        )

    assert task.status == CreatorTaskStatus.RUNNING.value
    mock_db.session.add.assert_called_once_with(task)
    mock_db.session.commit.assert_called_once()


@patch("services.creator_task_service.db")
def test_create_task_rejects_at_configured_in_progress_limit(mock_db):
    """The 429 message should report the configured limit, not a hard-coded value."""
    config = SimpleNamespace(CREATOR_TASK_MAX_IN_PROGRESS=20)
    mock_db.session.scalar.return_value = 20

    with patch("services.creator_task_service.dify_config", config, create=True):
        with pytest.raises(TooManyRequests, match="Maximum of 20 concurrent tasks"):
            CreatorTaskService.create_task(
                account_id="account-1",
                tenant_id="tenant-1",
                app_id="app-1",
                installed_app_id="installed-1",
                conversation_id=None,
                workflow_run_id=None,
                title=None,
            )

    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.creator_task_service.timedelta")
@patch("services.creator_task_service.db")
def test_timeout_stale_tasks_uses_configured_timeout_hours(mock_db, mock_timedelta):
    """Scheduled cleanup should use the configured stale-task timeout window."""
    config = SimpleNamespace(CREATOR_TASK_TIMEOUT_HOURS=2)
    mock_timedelta.return_value = timedelta(hours=2)
    stale_task = CreatorTask(
        account_id="account-1",
        tenant_id="tenant-1",
        app_id="app-1",
        installed_app_id="installed-1",
        status=CreatorTaskStatus.RUNNING.value,
    )
    mock_db.session.scalars.return_value.all.return_value = [stale_task]

    with patch("services.creator_task_service.dify_config", config, create=True):
        updated_count = CreatorTaskService.timeout_stale_tasks()

    assert updated_count == 1
    assert stale_task.status == CreatorTaskStatus.FAILED.value
    mock_timedelta.assert_called_once_with(hours=2)
    mock_db.session.add.assert_called_once_with(stale_task)
    mock_db.session.commit.assert_called_once()


def test_creator_task_timeout_task_invokes_service(monkeypatch):
    """Celery beat task should delegate to the service cleanup method."""
    calls: list[bool] = []

    def fake_timeout_stale_tasks() -> int:
        calls.append(True)
        return 3

    monkeypatch.setattr(CreatorTaskService, "timeout_stale_tasks", staticmethod(fake_timeout_stale_tasks))

    from tasks.creator_task_timeout_tasks import fail_stale_creator_tasks

    assert fail_stale_creator_tasks() == 3
    assert calls == [True]
