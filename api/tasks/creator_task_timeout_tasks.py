"""Celery tasks for creator task lifecycle maintenance."""

import logging

from celery import shared_task

from services.creator_task_service import CreatorTaskService

logger = logging.getLogger(__name__)


@shared_task(name="creator_task_timeout.fail_stale", queue="schedule_executor")
def fail_stale_creator_tasks() -> int:
    """Fail stale creator tasks so abandoned rows stop occupying concurrency slots."""
    updated_count = CreatorTaskService.timeout_stale_tasks()
    if updated_count:
        logger.info("Marked %d stale creator task(s) as failed", updated_count)
    return updated_count
