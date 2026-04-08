"""Global exception handlers that turn application errors into consistent JSON.

Register these on the FastAPI app via :func:`register_error_handlers`.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import AppError
from app.middleware.request_context import request_id_ctx

logger = logging.getLogger(__name__)


def _error_body(*, code: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_ctx.get(""),
        }
    }


async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    logger.warning("AppError %s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code=exc.code, message=exc.message),
    )


async def _unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_error_body(code="INTERNAL_ERROR", message="Internal server error"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach exception handlers to *app*."""
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
