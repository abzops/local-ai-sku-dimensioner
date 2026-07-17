"""Structured public error payloads."""

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Safe error information suitable for display in the client."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    recoverable: bool
    suggested_action: str

