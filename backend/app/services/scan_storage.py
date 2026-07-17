"""Safe local filesystem storage for validated Phase 1 scan uploads."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID, uuid4

from backend.app.errors import ApplicationError
from backend.app.upload_contracts import (
    FinalizedImage,
    FinalizedUploadBatch,
    StagedImage,
    StagedUploadBatch,
    ValidatedUpload,
)

WRITE_CHUNK_SIZE = 1024 * 1024


class ScanStorage:
    """Own staging and final operation directories beneath one data root."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.expanduser().resolve(strict=False)
        self.scans_root = self.data_root / "scans"

    async def stage(
        self,
        scan_id: str,
        uploads: tuple[ValidatedUpload, ...],
    ) -> StagedUploadBatch:
        """Write validated bytes into one exclusively owned staging directory."""
        safe_scan_id = _canonical_uuid(scan_id)
        operation_id = str(uuid4())
        staging_directory = self._staging_directory(safe_scan_id, operation_id)
        final_directory = self._final_directory(safe_scan_id, operation_id)
        owns_staging_directory = False
        try:
            staging_directory.parent.mkdir(parents=True, exist_ok=True)
            final_directory.parent.mkdir(parents=True, exist_ok=True)
            staging_directory.mkdir(exist_ok=False)
            owns_staging_directory = True

            staged_images: list[StagedImage] = []
            for upload in uploads:
                image_id = _canonical_uuid(upload.image_id)
                staging_path = staging_directory / (
                    f"{image_id}{upload.canonical_extension}"
                )
                self._assert_contained(staging_path)
                written = 0
                try:
                    await upload.file.seek(0)
                    with staging_path.open("xb") as destination:
                        while True:
                            chunk = await upload.file.read(WRITE_CHUNK_SIZE)
                            if not chunk:
                                break
                            destination.write(chunk)
                            written += len(chunk)
                        destination.flush()
                finally:
                    await upload.file.seek(0)
                if written != upload.size_bytes:
                    raise _storage_error(
                        "The validated upload changed before it could be stored."
                    )
                staged_images.append(
                    StagedImage(
                        image_id=image_id,
                        view_type=upload.view_type,
                        canonical_extension=upload.canonical_extension,
                        media_type=upload.media_type,
                        size_bytes=upload.size_bytes,
                        width_px=upload.width_px,
                        height_px=upload.height_px,
                        staging_path=staging_path,
                    )
                )
            return StagedUploadBatch(
                scan_id=safe_scan_id,
                operation_id=operation_id,
                staging_directory=staging_directory,
                final_directory=final_directory,
                images=tuple(staged_images),
            )
        except ApplicationError:
            if owns_staging_directory:
                self._remove_owned_directory(staging_directory)
            raise
        except (OSError, ValueError) as error:
            if owns_staging_directory:
                self._remove_owned_directory(staging_directory)
            raise _storage_error(
                "The upload could not be staged in local storage."
            ) from error

    def finalize(self, batch: StagedUploadBatch) -> FinalizedUploadBatch:
        """Atomically move one staging directory to its final same-volume location."""
        expected_staging = self._staging_directory(batch.scan_id, batch.operation_id)
        expected_final = self._final_directory(batch.scan_id, batch.operation_id)
        moved = False
        try:
            if batch.staging_directory.resolve(strict=False) != expected_staging:
                raise ValueError("Unexpected staging directory")
            if batch.final_directory.resolve(strict=False) != expected_final:
                raise ValueError("Unexpected final directory")
            if not expected_staging.is_dir() or expected_final.exists():
                raise OSError("Storage operation directory is unavailable")

            for image in batch.images:
                expected_path = expected_staging / (
                    f"{_canonical_uuid(image.image_id)}{image.canonical_extension}"
                )
                if image.staging_path.resolve(strict=False) != expected_path:
                    raise ValueError("Unexpected staged image path")
                if not expected_path.is_file():
                    raise OSError("Staged image is unavailable")

            expected_staging.replace(expected_final)
            moved = True
            finalized_images = tuple(
                FinalizedImage(
                    image_id=image.image_id,
                    view_type=image.view_type,
                    storage_key=(
                        expected_final / image.staging_path.name
                    ).relative_to(self.data_root).as_posix(),
                    canonical_extension=image.canonical_extension,
                    media_type=image.media_type,
                    size_bytes=image.size_bytes,
                    width_px=image.width_px,
                    height_px=image.height_px,
                    absolute_path=expected_final / image.staging_path.name,
                )
                for image in batch.images
            )
            return FinalizedUploadBatch(
                scan_id=batch.scan_id,
                operation_id=batch.operation_id,
                final_directory=expected_final,
                images=finalized_images,
            )
        except (OSError, ValueError) as error:
            owned_directory = expected_final if moved else expected_staging
            self._remove_owned_directory(owned_directory)
            raise _storage_error(
                "The upload could not be finalized in local storage."
            ) from error

    def cleanup_staged(self, batch: StagedUploadBatch) -> None:
        """Remove only the operation directory owned by a staged batch."""
        expected = self._staging_directory(batch.scan_id, batch.operation_id)
        if batch.staging_directory.resolve(strict=False) != expected:
            raise _storage_error("The upload staging directory could not be cleaned up.")
        self._remove_owned_directory(expected)

    def cleanup_finalized(self, batch: FinalizedUploadBatch) -> None:
        """Remove only the operation directory owned by a finalized batch."""
        expected = self._final_directory(batch.scan_id, batch.operation_id)
        if batch.final_directory.resolve(strict=False) != expected:
            raise _storage_error("The upload directory could not be cleaned up.")
        self._remove_owned_directory(expected)

    def _staging_directory(self, scan_id: str, operation_id: str) -> Path:
        path = (
            self.scans_root
            / _canonical_uuid(scan_id)
            / ".staging"
            / _canonical_uuid(operation_id)
        ).resolve(strict=False)
        self._assert_contained(path)
        return path

    def _final_directory(self, scan_id: str, operation_id: str) -> Path:
        path = (
            self.scans_root
            / _canonical_uuid(scan_id)
            / "original"
            / _canonical_uuid(operation_id)
        ).resolve(strict=False)
        self._assert_contained(path)
        return path

    def _assert_contained(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self.data_root)
        except ValueError as error:
            raise _storage_error("The upload storage destination is invalid.") from error

    def _remove_owned_directory(self, directory: Path) -> None:
        self._assert_contained(directory)
        if not directory.exists():
            return
        try:
            shutil.rmtree(directory)
        except OSError as error:
            raise _storage_error("The upload directory could not be cleaned up.") from error


def _canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise _storage_error("The upload storage identifier is invalid.") from error


def _storage_error(message: str) -> ApplicationError:
    return ApplicationError(
        status_code=503,
        code="STORAGE_UNAVAILABLE",
        message=message,
        recoverable=True,
        suggested_action="Retry the upload. If the problem continues, check local storage access.",
    )
