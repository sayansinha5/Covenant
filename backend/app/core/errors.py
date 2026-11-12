"""RFC 9457 problem details with a stable machine `code` on every error response."""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.ids import new_request_id
from app.core.logging import get_logger

PROBLEM_CONTENT_TYPE = "application/problem+json"

logger = get_logger("covenant.errors")


class AppError(Exception):
    """A failure the client should see. `code` is stable and documented; `detail` is for humans."""

    status: int = 400
    code: str = "BAD_REQUEST"
    title: str = "Bad request"

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.extra = extra or {}


class NotFoundError(AppError):
    status = 404
    code = "NOT_FOUND"
    title = "Not found"


class ForbiddenError(AppError):
    status = 403
    code = "FORBIDDEN"
    title = "Forbidden"


class ConflictError(AppError):
    status = 409
    code = "CONFLICT"
    title = "Conflict"


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or new_request_id()
    body: dict[str, Any] = {
        "type": f"urn:covenant:problem:{code.lower()}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": request_id,
        **(extra or {}),
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_CONTENT_TYPE)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101  (registered for AppError only)
    return problem_response(
        request,
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra,
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {
            "field": ".".join(str(p) for p in err["loc"][1:]),
            "message": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="VALIDATION_ERROR",
        title="Validation error",
        detail="Some fields are missing or invalid.",
        extra={"errors": errors},
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    phrase = HTTPStatus(exc.status_code).phrase
    return problem_response(
        request,
        status=exc.status_code,
        code=phrase.upper().replace(" ", "_").replace("-", "_"),
        title=phrase,
        detail=str(exc.detail) if exc.detail else phrase,
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error_type=type(exc).__name__)
    return problem_response(
        request,
        status=500,
        code="INTERNAL_ERROR",
        title="Internal server error",
        detail="Something went wrong on our side. Quote the request ID if you report it.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
