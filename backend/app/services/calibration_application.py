"""Coordinate bounded image validation with deterministic marker analysis."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from typing import cast

import cv2
import numpy as np
from fastapi import UploadFile, status
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.schemas.calibration import CalibrationTestResponse
from backend.app.services.calibration_profiles import get_profile_model, profile_spec
from backend.app.services.image_validation import ImageValidator
from backend.app.upload_contracts import UploadInput
from backend.app.vision.marker_engine import analyze_marker_image


class CalibrationApplicationService:
    """Run one in-memory calibration test without persisting the source or previews."""

    def __init__(self, settings: Settings) -> None:
        self.validator = ImageValidator(
            max_file_size_bytes=settings.max_upload_bytes,
            max_decoded_pixels=settings.max_image_pixels,
            min_short_edge_px=settings.min_image_short_edge,
            min_long_edge_px=settings.min_image_long_edge,
        )
        self.max_upload_bytes = settings.max_upload_bytes

    async def test_profile(
        self,
        session: Session,
        profile_id: str,
        image: UploadFile,
    ) -> CalibrationTestResponse:
        """Validate and analyze exactly one client image entirely in memory."""
        profile = get_profile_model(session, profile_id)
        image_bgr = await self._validated_oriented_bgr(image)
        try:
            result = analyze_marker_image(image_bgr, profile_spec(profile))
            return CalibrationTestResponse(
                profile_id=profile.id,
                marker_size_mm=profile.marker_size_mm,
                **asdict(result),
            )
        except ApplicationError:
            raise
        except (ArithmeticError, MemoryError, ValueError, cv2.error) as error:
            raise _safe_analysis_error() from error

    async def _validated_oriented_bgr(self, image: UploadFile) -> np.ndarray:
        upload = UploadInput(view_type=ImageView.ADDITIONAL, file=image)
        try:
            await self.validator.validate(upload)
        except ApplicationError as error:
            raise _calibration_upload_error(error) from error

        await image.seek(0)
        content = await image.read(self.max_upload_bytes + 1)
        await image.seek(0)
        try:
            with Image.open(BytesIO(content)) as decoded:
                oriented = ImageOps.exif_transpose(decoded)
                try:
                    rgb = oriented.convert("RGB")
                    try:
                        rgb_array = np.asarray(rgb, dtype=np.uint8).copy()
                    finally:
                        rgb.close()
                finally:
                    if oriented is not decoded:
                        oriented.close()
            return cast(np.ndarray, cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR))
        except (OSError, ValueError, cv2.error) as error:
            raise ApplicationError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="IMAGE_DECODE_FAILED",
                message="The image content could not be decoded.",
                recoverable=True,
                suggested_action="Choose a valid, unmodified image and retry.",
                field="image",
            ) from error


def _calibration_upload_error(error: ApplicationError) -> ApplicationError:
    payload = error.payload
    return ApplicationError(
        status_code=error.status_code,
        code=payload.code,
        message=payload.message,
        recoverable=payload.recoverable,
        suggested_action=payload.suggested_action,
        field="image",
    )


def _safe_analysis_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="CALIBRATION_TEST_FAILED",
        message="The marker image could not be analyzed safely.",
        recoverable=True,
        suggested_action="Retake the image with the complete marker clearly visible and retry.",
        field="image",
    )
