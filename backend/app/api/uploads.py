"""Multipart image upload endpoint for Phase 1 scans."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Path, Request, UploadFile, status
from starlette.datastructures import UploadFile as StarletteUploadFile

from backend.app.contracts import ImageView
from backend.app.dependencies import SessionDependency, SettingsDependency
from backend.app.errors import ApplicationError
from backend.app.multipart import parse_upload_form
from backend.app.schemas.scans import UploadBatchResponse
from backend.app.services.upload_application import UploadApplicationService
from backend.app.upload_contracts import UploadInput

router = APIRouter(prefix="/scans")

UPLOAD_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "top": {"type": "string", "format": "binary"},
                        "front": {"type": "string", "format": "binary"},
                        "side": {"type": "string", "format": "binary"},
                        "additional": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                        },
                    },
                }
            }
        },
    }
}


@router.post(
    "/{scan_id}/images",
    response_model=UploadBatchResponse,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=UPLOAD_REQUEST_OPENAPI,
)
async def upload_scan_images_endpoint(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
) -> UploadBatchResponse:
    form = await parse_upload_form(request, settings)
    uploads: list[UploadInput] = []
    try:
        for field_name, value in form.multi_items():
            try:
                view = ImageView(field_name)
            except ValueError as error:
                raise _invalid_upload_field_error() from error
            if not isinstance(value, StarletteUploadFile):
                raise _invalid_upload_field_error()
            uploads.append(
                UploadInput(view_type=view, file=cast(UploadFile, value))
            )

        service = UploadApplicationService(settings)
        return await service.upload(session, str(scan_id), uploads)
    finally:
        await form.close()


def _invalid_upload_field_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_UPLOAD_FIELD",
        message="The multipart upload contains an unsupported field.",
        recoverable=True,
        suggested_action="Use only top, front, side, and additional image fields.",
    )
