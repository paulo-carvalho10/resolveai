"""Structured key=value logging.

2026-09-14T14:35:12+00:00 INFO ticket.created ticket_id=527 user_id=42
"""

import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="seconds")
        parts = [timestamp, record.levelname, record.getMessage()]
        fields: dict[str, Any] = getattr(record, "fields", {})
        parts.extend(f"{key}={value}" for key, value in fields.items())
        line = " ".join(parts)
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Our middleware already logs each request.
    logging.getLogger("uvicorn.access").disabled = True


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    exc_info: BaseException | None = None,
    **fields: Any,
) -> None:
    logger.log(level, event, exc_info=exc_info, extra={"fields": fields})


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("app.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            log_event(
                self.logger,
                "http.request",
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
