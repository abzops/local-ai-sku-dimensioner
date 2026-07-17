"""In-memory calibration-profile test endpoint."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Path, Request, UploadFile, status
from starlette.datastructures import UploadFile as StarletteUploadFile

from backend.app.dependencies import SessionDependency, SettingsDependency
from backend.app.errors import ApplicationError
from backend.app.multipart import parse_single_image_form
from backend.app.schemas.calibration import CalibrationTestResponse
from backend.app.services.calibration_application import CalibrationApplicationService

router = APIRouter(prefix="/calibration/profiles")

CALIBRATION_TEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["image"],
                    "properties": {"image": {"type": "string", "format": "binary"}},
                    "additionalProperties": False,
                }
            }
        },
    }
}


@router.post(
    "/{profile_id}/test",
    response_model=CalibrationTestResponse,
    openapi_extra=CALIBRATION_TEST_OPENAPI,
)
async def test_calibration_profile_endpoint(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    profile_id: Annotated[UUID, Path(description="Server-generated calibration profile UUID")],
) -> CalibrationTestResponse:
    form = await parse_single_image_form(request, settings)
    try:
        items = form.multi_items()
        if not items:
            raise ApplicationError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="NO_FILES_PROVIDED",
                message="A calibration test image is required.",
                recoverable=True,
                suggested_action="Choose one marker image and try again.",
                field="image",
            )
        if (
            len(items) != 1
            or items[0][0] != "image"
            or not isinstance(items[0][1], StarletteUploadFile)
        ):
            raise _invalid_calibration_upload_field_error()

        service = CalibrationApplicationService(settings)
        return await service.test_profile(
            session,
            str(profile_id),
            cast(UploadFile, items[0][1]),
        )
    finally:
        await form.close()


def _invalid_calibration_upload_field_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_UPLOAD_FIELD",
        message="The calibration test accepts exactly one image field.",
        recoverable=True,
        suggested_action="Upload one file using only the image field.",
        field="image",
    )
