"""Domain errors and the uniform `{"error": {"code", "message"}}` response format."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import log_event

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource.upper()}_NOT_FOUND", f"{resource} not found.", 404)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__("FORBIDDEN", message, 403)


class ConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class AuthenticationError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 401, headers={"WWW-Authenticate": "Bearer"})


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse({"error": error}, status_code=status_code, headers=headers)


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return error_response(
        exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail), headers=exc.headers
    )


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Request validation failed.", details)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log_event(
        logger,
        "http.unhandled_error",
        level=logging.ERROR,
        exc_info=exc,
        path=request.url.path,
        error=type(exc).__name__,
    )
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
