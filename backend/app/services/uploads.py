"""File-layer orchestration for Phase 1 image upload batches."""

from __future__ import annotations

from collections.abc import Iterable

from backend.app.contracts import REQUIRED_IMAGE_VIEWS, ImageView
from backend.app.errors import ApplicationError
from backend.app.services.image_validation import ImageValidator
from backend.app.services.scan_storage import ScanStorage
from backend.app.upload_contracts import (
    FinalizedUploadBatch,
    StagedUploadBatch,
    UploadInput,
    ValidatedUpload,
)

MAX_FILES_PER_REQUEST = 8
MAX_ADDITIONAL_FILES_PER_REQUEST = 5
VIEW_ORDER = {
    ImageView.TOP: 0,
    ImageView.FRONT: 1,
    ImageView.SIDE: 2,
    ImageView.ADDITIONAL: 3,
}


class UploadService:
    """Validate every input before creating an operation-owned staging batch."""

    def __init__(
        self,
        validator: ImageValidator,
        storage: ScanStorage,
        *,
        max_files_per_request: int = MAX_FILES_PER_REQUEST,
        max_additional_files_per_request: int = MAX_ADDITIONAL_FILES_PER_REQUEST,
    ) -> None:
        if max_files_per_request <= 0 or max_additional_files_per_request <= 0:
            raise ValueError("Upload request limits must be positive")
        if max_additional_files_per_request > max_files_per_request:
            raise ValueError("Additional image limit cannot exceed total file limit")
        self.validator = validator
        self.storage = storage
        self.max_files_per_request = max_files_per_request
        self.max_additional_files_per_request = max_additional_files_per_request

    async def validate_and_stage(
        self,
        scan_id: str,
        uploads: Iterable[UploadInput],
    ) -> StagedUploadBatch:
        """Validate a request-local batch and stage it only after all files pass."""
        ordered_uploads = self._validate_request(tuple(uploads))
        validated: list[ValidatedUpload] = []
        for upload in ordered_uploads:
            validated.append(await self.validator.validate(upload))
        return await self.storage.stage(scan_id, tuple(validated))

    def finalize(self, batch: StagedUploadBatch) -> FinalizedUploadBatch:
        """Move the staged operation to final storage before metadata insertion."""
        return self.storage.finalize(batch)

    def compensate(
        self,
        batch: StagedUploadBatch | FinalizedUploadBatch,
    ) -> None:
        """Remove only files owned by the supplied upload operation."""
        if isinstance(batch, StagedUploadBatch):
            self.storage.cleanup_staged(batch)
        else:
            self.storage.cleanup_finalized(batch)

    def _validate_request(
        self,
        uploads: tuple[UploadInput, ...],
    ) -> tuple[UploadInput, ...]:
        if not uploads:
            raise _batch_error(
                status_code=400,
                code="NO_FILES_PROVIDED",
                message="At least one image is required.",
                suggested_action="Choose an image and retry the upload.",
            )
        if len(uploads) > self.max_files_per_request:
            raise _batch_error(
                status_code=400,
                code="UPLOAD_LIMIT_EXCEEDED",
                message="The upload contains too many images.",
                suggested_action=(
                    f"Upload no more than {self.max_files_per_request} images at once."
                ),
            )

        seen_required: set[ImageView] = set()
        for upload in uploads:
            if upload.view_type in REQUIRED_IMAGE_VIEWS:
                if upload.view_type in seen_required:
                    raise _batch_error(
                        status_code=409,
                        code="DUPLICATE_VIEW",
                        message="A required image view appears more than once.",
                        suggested_action="Choose only one top, front, and side image.",
                        view=upload.view_type,
                    )
                seen_required.add(upload.view_type)

        additional_count = sum(
            upload.view_type is ImageView.ADDITIONAL for upload in uploads
        )
        if additional_count > self.max_additional_files_per_request:
            raise _batch_error(
                status_code=409,
                code="ADDITIONAL_IMAGE_LIMIT_EXCEEDED",
                message="The upload contains too many additional images.",
                suggested_action=(
                    "Choose no more than "
                    f"{self.max_additional_files_per_request} additional images."
                ),
                view=ImageView.ADDITIONAL,
            )

        return tuple(
            upload
            for _, upload in sorted(
                enumerate(uploads),
                key=lambda item: (VIEW_ORDER[item[1].view_type], item[0]),
            )
        )


def _batch_error(
    *,
    status_code: int,
    code: str,
    message: str,
    suggested_action: str,
    view: ImageView | None = None,
) -> ApplicationError:
    return ApplicationError(
        status_code=status_code,
        code=code,
        message=message,
        recoverable=True,
        suggested_action=suggested_action,
        field=view.value if view is not None else None,
        view=view,
    )
