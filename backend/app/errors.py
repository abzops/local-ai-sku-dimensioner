"""Safe application errors shared by Phase 1 API and service layers."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.contracts import ImageView
from backend.app.schemas.errors import RequestErrorResponse


class ApplicationError(Exception):
    """An expected public error with no internal exception or path details."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        recoverable: bool,
        suggested_action: str,
        field: str | None = None,
        view: ImageView | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.payload = RequestErrorResponse(
            code=code,
            message=message,
            recoverable=recoverable,
            suggested_action=suggested_action,
            field=field,
            view=view,
        )


async def application_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    """Render an expected application error without optional null fields."""
    if not isinstance(error, ApplicationError):
        raise error
    return JSONResponse(
        status_code=error.status_code,
        content=error.payload.model_dump(mode="json", exclude_none=True),
    )


async def request_validation_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    """Map framework validation failures to the stable public error shape."""
    if not isinstance(error, RequestValidationError):
        raise error
    field: str | None = None
    for validation_error in error.errors():
        location = validation_error.get("loc", ())
        if location:
            candidate = location[-1]
            if isinstance(candidate, str):
                field = candidate
                break
    payload = RequestErrorResponse(
        code="INVALID_REQUEST",
        message="The request contains invalid or missing fields.",
        recoverable=True,
        suggested_action="Correct the request fields and try again.",
        field=field,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=payload.model_dump(mode="json", exclude_none=True),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register safe handlers without changing FastAPI's general HTTP errors."""
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )
