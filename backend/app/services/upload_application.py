"""Coordinate Phase 1 upload validation, filesystem storage, and persistence."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from fastapi import status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.contracts import REQUIRED_IMAGE_VIEWS, ImageView
from backend.app.errors import ApplicationError
from backend.app.models.scan import Scan, ScanImage, utc_now
from backend.app.schemas.scans import UploadBatchResponse
from backend.app.services.image_validation import ImageValidator
from backend.app.services.scan_storage import ScanStorage
from backend.app.services.scans import (
    calculate_scan_status,
    get_scan_model,
    image_response,
    scan_detail,
)
from backend.app.services.uploads import UploadService
from backend.app.upload_contracts import (
    FinalizedUploadBatch,
    StagedUploadBatch,
    UploadInput,
)

logger = logging.getLogger(__name__)


class UploadApplicationService:
    """Keep one upload batch consistent across SQLite and local storage."""

    def __init__(self, settings: Settings) -> None:
        validator = ImageValidator(
            max_file_size_bytes=settings.max_upload_bytes,
            max_decoded_pixels=settings.max_image_pixels,
            min_short_edge_px=settings.min_image_short_edge,
            min_long_edge_px=settings.min_image_long_edge,
        )
        storage = ScanStorage(settings.data_root)
        self.upload_service = UploadService(
            validator,
            storage,
            max_files_per_request=settings.max_upload_files_per_request,
            max_additional_files_per_request=settings.max_additional_images,
        )
        self.max_additional_images = settings.max_additional_images

    async def upload(
        self,
        session: Session,
        scan_id: str,
        uploads: Iterable[UploadInput],
    ) -> UploadBatchResponse:
        """Validate, stage, finalize, and persist an all-or-nothing upload batch."""
        upload_tuple = tuple(uploads)
        staged: StagedUploadBatch | None = None
        finalized: FinalizedUploadBatch | None = None
        committed = False

        try:
            scan = get_scan_model(session, scan_id)
            self._validate_scan_capacity(scan, upload_tuple)
            session.rollback()

            staged = await self.upload_service.validate_and_stage(scan_id, upload_tuple)

            with session.begin():
                scan = get_scan_model(session, scan_id)
                self._validate_scan_capacity(scan, upload_tuple)
                finalized = self.upload_service.finalize(staged)

                inserted = [
                    ScanImage(
                        id=image.image_id,
                        scan_id=scan.id,
                        view_type=image.view_type,
                        storage_key=image.storage_key,
                        media_type=image.media_type,
                        file_extension=image.canonical_extension,
                        size_bytes=image.size_bytes,
                        width_px=image.width_px,
                        height_px=image.height_px,
                    )
                    for image in finalized.images
                ]
                scan.images.extend(inserted)
                scan.status = calculate_scan_status(
                    image.view_type for image in scan.images
                )
                scan.updated_at = utc_now()
                session.flush()

            committed = True
            return UploadBatchResponse(
                scan=scan_detail(scan),
                uploaded_images=[image_response(image) for image in inserted],
            )
        except ApplicationError:
            if not committed:
                self._compensate_safely(finalized or staged)
            raise
        except IntegrityError as error:
            if not committed:
                self._compensate_safely(finalized or staged)
            if "scan_images.scan_id, scan_images.view_type" in str(error.orig):
                raise _duplicate_view_error() from error
            raise _database_error() from error
        except SQLAlchemyError as error:
            if not committed:
                self._compensate_safely(finalized or staged)
            raise _database_error() from error
        except Exception:
            if not committed:
                self._compensate_safely(finalized or staged)
            raise

    def _validate_scan_capacity(
        self,
        scan: Scan,
        uploads: tuple[UploadInput, ...],
    ) -> None:
        existing_required = {
            image.view_type
            for image in scan.images
            if image.view_type in REQUIRED_IMAGE_VIEWS
        }
        for upload in uploads:
            if (
                upload.view_type in REQUIRED_IMAGE_VIEWS
                and upload.view_type in existing_required
            ):
                raise _duplicate_view_error(upload.view_type)

        existing_additional = sum(
            image.view_type == ImageView.ADDITIONAL for image in scan.images
        )
        requested_additional = sum(
            upload.view_type == ImageView.ADDITIONAL for upload in uploads
        )
        if existing_additional + requested_additional > self.max_additional_images:
            raise ApplicationError(
                status_code=status.HTTP_409_CONFLICT,
                code="ADDITIONAL_IMAGE_LIMIT_EXCEEDED",
                message="The scan cannot accept more additional images.",
                recoverable=True,
                suggested_action=(
                    "Remove additional images so the scan stays within its limit."
                ),
                field=ImageView.ADDITIONAL.value,
                view=ImageView.ADDITIONAL,
            )

    def _compensate_safely(
        self,
        batch: StagedUploadBatch | FinalizedUploadBatch | None,
    ) -> None:
        if batch is None:
            return
        try:
            self.upload_service.compensate(batch)
        except ApplicationError:
            logger.error(
                "Upload compensation failed for scan %s operation %s.",
                batch.scan_id,
                batch.operation_id,
            )


def _duplicate_view_error(view: ImageView | None = None) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="DUPLICATE_VIEW",
        message="The scan already contains one of the requested required views.",
        recoverable=True,
        suggested_action="Upload only missing top, front, or side views.",
        field=view.value if view is not None else None,
        view=view,
    )


def _database_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The upload metadata could not be saved locally.",
        recoverable=True,
        suggested_action="Retry the upload. If the problem continues, restart the app.",
    )
