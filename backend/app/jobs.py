"""Periodic jobs that run inside the API process.

There is no worker or cron in this deployment, and the free hosting tier sleeps when idle, so
a job cannot rely on running on time. Each run catches up on everything overdue, and the first
run happens at startup, before the API serves its first request.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.api.deps import get_session_factory
from app.core.config import get_settings
from app.core.logger import log_event
from app.services import ticket_service

logger = logging.getLogger(__name__)


def close_stale_resolved_tickets(session_factory: Callable[[], Session]) -> None:
    with session_factory() as db:
        ticket_service.close_stale_resolved_tickets(db)


async def _run_safely(session_factory: Callable[[], Session]) -> None:
    try:
        await asyncio.to_thread(close_stale_resolved_tickets, session_factory)
    except Exception as exc:  # A failed run must not take the API down; the next one retries.
        log_event(logger, "job.failed", level=logging.ERROR, exc_info=exc, job="auto_close")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    interval_minutes = get_settings().auto_close_interval_minutes
    if interval_minutes <= 0:
        yield
        return

    # Same override lookup as request dependencies, so tests point the job at their database.
    session_factory = app.dependency_overrides.get(get_session_factory, get_session_factory)()
    await _run_safely(session_factory)

    async def repeat() -> None:
        while True:
            await asyncio.sleep(interval_minutes * 60)
            await _run_safely(session_factory)

    task = asyncio.create_task(repeat())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
