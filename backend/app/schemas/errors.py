"""Structured public error payloads."""

from pydantic import BaseModel, ConfigDict

from backend.app.contracts import ImageView


class ErrorResponse(BaseModel):
    """Safe error information suitable for display in the client."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    recoverable: bool
    suggested_action: str


class RequestErrorResponse(ErrorResponse):
    """Phase 1 request error with optional safe field and view context."""

    field: str | None = None
    view: ImageView | None = None
