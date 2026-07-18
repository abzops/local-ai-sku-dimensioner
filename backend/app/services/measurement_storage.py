"""Operation-owned storage for Phase 3 annotated measurement previews."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Protocol
from uuid import UUID, uuid4

from fastapi import status
from PIL import Image, UnidentifiedImageError

from backend.app.contracts import REQUIRED_IMAGE_VIEW_ORDER, ImageView
from backend.app.errors import ApplicationError
from backend.app.services.stored_image_loader import (
    _assert_no_reparse_points,
    _stat_is_reparse,
)

PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
READ_CHUNK_SIZE: Final[int] = 1024 * 1024
OWNERSHIP_FILENAME: Final[str] = ".operation_id"


@dataclass(frozen=True, slots=True)
class PreviewWrite:
    """One bounded trusted geometry preview awaiting local persistence."""

    view: ImageView
    media_type: Literal["image/png"]
    width_px: int
    height_px: int
    png_bytes: bytes


class MeasurementStorageSettings(Protocol):
    data_root: Path


class MeasurementPreviewRecord(Protocol):
    storage_key: str
    sha256: str
    media_type: str
    size_bytes: int
    width_px: int
    height_px: int


@dataclass(frozen=True, slots=True)
class StagedMeasurementPreview:
    view: ImageView
    media_type: Literal["image/png"]
    width_px: int
    height_px: int
    size_bytes: int
    sha256: str
    staging_path: Path


@dataclass(frozen=True, slots=True)
class StagedMeasurementPreviewBatch:
    scan_id: str
    attempt_id: str
    operation_id: str
    staging_directory: Path
    final_directory: Path
    previews: tuple[
        StagedMeasurementPreview,
        StagedMeasurementPreview,
        StagedMeasurementPreview,
    ]


@dataclass(frozen=True, slots=True)
class FinalizedMeasurementPreview:
    view: ImageView
    kind: Literal["annotated"]
    storage_key: str
    sha256: str
    media_type: Literal["image/png"]
    size_bytes: int
    width_px: int
    height_px: int
    absolute_path: Path


@dataclass(frozen=True, slots=True)
class FinalizedMeasurementPreviewBatch:
    scan_id: str
    attempt_id: str
    operation_id: str
    final_directory: Path
    previews: tuple[
        FinalizedMeasurementPreview,
        FinalizedMeasurementPreview,
        FinalizedMeasurementPreview,
    ]


class MeasurementStorage:
    """Stage, atomically finalize, verify, and compensate attempt-owned previews."""

    def __init__(
        self,
        settings: Path | MeasurementStorageSettings,
        *,
        max_preview_long_edge: int = 1280,
        max_preview_encoded_size: int = 2 * 1024 * 1024,
    ) -> None:
        if max_preview_long_edge <= 0 or max_preview_encoded_size <= 0:
            raise ValueError("Preview limits must be positive")
        data_root = settings if isinstance(settings, Path) else settings.data_root
        self.data_root = data_root.expanduser().resolve(strict=False)
        self.max_preview_long_edge = max_preview_long_edge
        self.max_preview_encoded_size = max_preview_encoded_size

    def stage(
        self,
        scan_id: str,
        attempt_id: str,
        previews: tuple[PreviewWrite, ...],
    ) -> StagedMeasurementPreviewBatch:
        """Write exactly three annotated previews to one exclusive operation directory."""
        safe_scan_id = _canonical_uuid(scan_id)
        safe_attempt_id = _canonical_uuid(attempt_id)
        operation_id = str(uuid4())
        staging_directory = self._staging_directory(
            safe_scan_id,
            safe_attempt_id,
            operation_id,
        )
        final_directory = self._final_directory(safe_scan_id, safe_attempt_id)
        ordered = self._validate_preview_set(previews)
        owns_staging = False
        try:
            self._create_safe_directory_tree(staging_directory.parent)
            self._create_safe_directory_tree(final_directory.parent)
            staging_directory.mkdir(exist_ok=False)
            owns_staging = True
            _assert_no_reparse_points(self.data_root, staging_directory)
            ownership_path = staging_directory / OWNERSHIP_FILENAME
            with ownership_path.open("x", encoding="ascii", newline="\n") as ownership_file:
                ownership_file.write(operation_id)

            staged: list[StagedMeasurementPreview] = []
            for preview in ordered:
                filename = f"{preview.view.value}.annotated.png"
                staging_path = staging_directory / filename
                self._assert_contained(staging_path)
                digest = hashlib.sha256(preview.png_bytes).hexdigest()
                with staging_path.open("xb") as destination:
                    destination.write(preview.png_bytes)
                    destination.flush()
                staged.append(
                    StagedMeasurementPreview(
                        view=preview.view,
                        media_type="image/png",
                        width_px=preview.width_px,
                        height_px=preview.height_px,
                        size_bytes=len(preview.png_bytes),
                        sha256=digest,
                        staging_path=staging_path,
                    )
                )
            staged_tuple = tuple(staged)
            return StagedMeasurementPreviewBatch(
                scan_id=safe_scan_id,
                attempt_id=safe_attempt_id,
                operation_id=operation_id,
                staging_directory=staging_directory,
                final_directory=final_directory,
                previews=(staged_tuple[0], staged_tuple[1], staged_tuple[2]),
            )
        except ApplicationError:
            if owns_staging:
                self._remove_owned_directory(staging_directory)
            raise
        except (OSError, ValueError) as error:
            if owns_staging:
                self._remove_owned_directory(staging_directory)
            raise _storage_error("Measurement previews could not be staged.") from error

    def finalize(
        self,
        batch: StagedMeasurementPreviewBatch,
    ) -> FinalizedMeasurementPreviewBatch:
        """Atomically rename one operation directory to the attempt's final preview path."""
        expected_staging = self._staging_directory(
            batch.scan_id,
            batch.attempt_id,
            batch.operation_id,
        )
        expected_final = self._final_directory(batch.scan_id, batch.attempt_id)
        moved = False
        try:
            if batch.staging_directory.resolve(strict=False) != expected_staging:
                raise ValueError("Unexpected measurement staging directory")
            if batch.final_directory.resolve(strict=False) != expected_final:
                raise ValueError("Unexpected measurement final directory")
            self._verify_owned_directory(expected_staging, batch.operation_id)
            if expected_final.exists():
                raise OSError("Measurement preview destination already exists")
            for preview in batch.previews:
                expected_path = expected_staging / f"{preview.view.value}.annotated.png"
                if preview.staging_path.resolve(strict=False) != expected_path:
                    raise ValueError("Unexpected staged preview path")
                payload = self._read_regular_file(
                    expected_path,
                    maximum_bytes=self.max_preview_encoded_size,
                )
                self._verify_png(
                    payload,
                    width_px=preview.width_px,
                    height_px=preview.height_px,
                )
                if (
                    len(payload) != preview.size_bytes
                    or hashlib.sha256(payload).hexdigest() != preview.sha256
                ):
                    raise ValueError("Staged preview changed")
            expected_staging.replace(expected_final)
            moved = True
            self._verify_owned_directory(expected_final, batch.operation_id)
            finalized = tuple(
                FinalizedMeasurementPreview(
                    view=preview.view,
                    kind="annotated",
                    storage_key=(
                        expected_final / preview.staging_path.name
                    ).relative_to(self.data_root).as_posix(),
                    sha256=preview.sha256,
                    media_type="image/png",
                    size_bytes=preview.size_bytes,
                    width_px=preview.width_px,
                    height_px=preview.height_px,
                    absolute_path=expected_final / preview.staging_path.name,
                )
                for preview in batch.previews
            )
            return FinalizedMeasurementPreviewBatch(
                scan_id=batch.scan_id,
                attempt_id=batch.attempt_id,
                operation_id=batch.operation_id,
                final_directory=expected_final,
                previews=(finalized[0], finalized[1], finalized[2]),
            )
        except (OSError, ValueError) as error:
            owned = expected_final if moved else expected_staging
            if owned.exists():
                self._remove_owned_directory(owned, operation_id=batch.operation_id)
            raise _storage_error("Measurement previews could not be finalized.") from error

    def cleanup_staged(self, batch: StagedMeasurementPreviewBatch) -> None:
        expected = self._staging_directory(
            batch.scan_id,
            batch.attempt_id,
            batch.operation_id,
        )
        if batch.staging_directory.resolve(strict=False) != expected:
            raise _storage_error("Measurement preview staging could not be cleaned up.")
        self._remove_owned_directory(expected, operation_id=batch.operation_id)

    def cleanup_finalized(self, batch: FinalizedMeasurementPreviewBatch) -> None:
        expected = self._final_directory(batch.scan_id, batch.attempt_id)
        if batch.final_directory.resolve(strict=False) != expected:
            raise _storage_error("Measurement previews could not be compensated.")
        self._remove_owned_directory(expected, operation_id=batch.operation_id)

    def read_preview(
        self,
        preview: MeasurementPreviewRecord,
    ) -> bytes:
        """Read one DB-owned preview after containment, reparse, hash, and PNG checks."""
        if preview.media_type != "image/png":
            raise _storage_error("The measurement preview is unavailable.")
        path = self._resolve_private_storage_key(preview.storage_key)
        try:
            payload = self._read_regular_file(
                path,
                maximum_bytes=self.max_preview_encoded_size,
            )
            if (
                len(payload) != preview.size_bytes
                or len(preview.sha256) != 64
                or hashlib.sha256(payload).hexdigest() != preview.sha256.lower()
            ):
                raise ValueError("Preview metadata mismatch")
            self._verify_png(
                payload,
                width_px=preview.width_px,
                height_px=preview.height_px,
            )
            return payload
        except (OSError, ValueError) as error:
            raise _storage_error("The measurement preview is unavailable.") from error

    def _validate_preview_set(
        self,
        previews: tuple[PreviewWrite, ...],
    ) -> tuple[PreviewWrite, PreviewWrite, PreviewWrite]:
        by_view: dict[ImageView, PreviewWrite] = {}
        for preview in previews:
            if preview.view not in REQUIRED_IMAGE_VIEW_ORDER or preview.view in by_view:
                raise _storage_error("The measurement preview set is invalid.")
            if preview.media_type != "image/png":
                raise _storage_error("The measurement preview set is invalid.")
            if (
                preview.width_px <= 0
                or preview.height_px <= 0
                or max(preview.width_px, preview.height_px)
                > self.max_preview_long_edge
                or len(preview.png_bytes) <= 0
                or len(preview.png_bytes) > self.max_preview_encoded_size
            ):
                raise _storage_error("The measurement preview set is invalid.")
            self._verify_png(
                preview.png_bytes,
                width_px=preview.width_px,
                height_px=preview.height_px,
            )
            by_view[preview.view] = preview
        if set(by_view) != set(REQUIRED_IMAGE_VIEW_ORDER):
            raise _storage_error("The measurement preview set is invalid.")
        return (by_view[ImageView.TOP], by_view[ImageView.FRONT], by_view[ImageView.SIDE])

    def _staging_directory(
        self,
        scan_id: str,
        attempt_id: str,
        operation_id: str,
    ) -> Path:
        path = (
            self.data_root
            / "scans"
            / _canonical_uuid(scan_id)
            / ".staging"
            / "measurements"
            / _canonical_uuid(attempt_id)
            / _canonical_uuid(operation_id)
        ).resolve(strict=False)
        self._assert_contained(path)
        return path

    def _final_directory(self, scan_id: str, attempt_id: str) -> Path:
        path = (
            self.data_root
            / "scans"
            / _canonical_uuid(scan_id)
            / "measurements"
            / _canonical_uuid(attempt_id)
            / "previews"
        ).resolve(strict=False)
        self._assert_contained(path)
        return path

    def _create_safe_directory_tree(self, directory: Path) -> None:
        self._assert_contained(directory)
        self.data_root.mkdir(parents=True, exist_ok=True)
        _assert_no_reparse_points(self.data_root, self.data_root)
        current = self.data_root
        for part in directory.relative_to(self.data_root).parts:
            current = current / part
            current.mkdir(exist_ok=True)
            _assert_no_reparse_points(self.data_root, current)

    def _resolve_private_storage_key(self, storage_key: str) -> Path:
        if not storage_key or "\\" in storage_key or ":" in storage_key:
            raise _storage_error("The measurement preview is unavailable.")
        relative = PurePosixPath(storage_key)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.suffix.lower() != ".png"
        ):
            raise _storage_error("The measurement preview is unavailable.")
        candidate = self.data_root.joinpath(*relative.parts)
        try:
            _assert_no_reparse_points(self.data_root, candidate)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.data_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise _storage_error("The measurement preview is unavailable.") from error
        return resolved

    def _read_regular_file(self, path: Path, *, maximum_bytes: int) -> bytes:
        _assert_no_reparse_points(self.data_root, path)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or _stat_is_reparse(before):
            raise OSError("Preview is not a regular file")
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
                raise OSError("Preview identity changed")
            content = bytearray()
            while True:
                chunk = os.read(descriptor, READ_CHUNK_SIZE)
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > maximum_bytes:
                    raise ValueError("Preview exceeds configured limit")
        finally:
            os.close(descriptor)
        _assert_no_reparse_points(self.data_root, path)
        after = path.stat(follow_symlinks=False)
        if not os.path.samestat(before, after) or after.st_size != len(content):
            raise ValueError("Preview identity changed")
        return bytes(content)

    def _verify_png(self, payload: bytes, *, width_px: int, height_px: int) -> None:
        if not payload.startswith(PNG_SIGNATURE):
            raise ValueError("Preview is not PNG")
        try:
            with Image.open(BytesIO(payload)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Preview is not a single PNG")
                image.load()
                if image.size != (width_px, height_px):
                    raise ValueError("Preview dimensions changed")
        except (OSError, UnidentifiedImageError) as error:
            raise ValueError("Preview cannot be decoded") from error

    def _verify_owned_directory(self, directory: Path, operation_id: str) -> None:
        _assert_no_reparse_points(self.data_root, directory)
        ownership_path = directory / OWNERSHIP_FILENAME
        payload = self._read_regular_file(ownership_path, maximum_bytes=64)
        if payload.decode("ascii") != _canonical_uuid(operation_id):
            raise ValueError("Measurement preview ownership mismatch")

    def _remove_owned_directory(
        self,
        directory: Path,
        *,
        operation_id: str | None = None,
    ) -> None:
        self._assert_contained(directory)
        if not directory.exists():
            return
        if operation_id is not None:
            try:
                self._verify_owned_directory(directory, operation_id)
            except (OSError, UnicodeError, ValueError) as error:
                raise _storage_error(
                    "Measurement preview ownership could not be verified."
                ) from error
        for root, directories, files in os.walk(directory, topdown=True, followlinks=False):
            for name in (*directories, *files):
                metadata = (Path(root) / name).stat(follow_symlinks=False)
                if _stat_is_reparse(metadata) or (Path(root) / name).is_symlink():
                    raise _storage_error("Measurement preview cleanup was blocked safely.")
        try:
            shutil.rmtree(directory)
        except OSError as error:
            raise _storage_error("Measurement previews could not be cleaned up.") from error

    def _assert_contained(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self.data_root)
        except ValueError as error:
            raise _storage_error("The measurement preview destination is invalid.") from error


def _canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise _storage_error("The measurement storage identifier is invalid.") from error


def _storage_error(message: str) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="STORAGE_UNAVAILABLE",
        message=message,
        recoverable=True,
        suggested_action="Retry processing. If the problem continues, check local storage access.",
    )
