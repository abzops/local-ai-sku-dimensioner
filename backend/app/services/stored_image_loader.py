"""Securely load immutable Phase 1 scan images for Phase 3 processing."""

from __future__ import annotations

import hashlib
import os
import stat
import struct
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Final, cast

import cv2
import numpy as np
from fastapi import status
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.contracts import REQUIRED_IMAGE_VIEW_ORDER, ImageView
from backend.app.errors import ApplicationError
from backend.app.models.scan import ScanImage

READ_CHUNK_SIZE: Final[int] = 1024 * 1024
PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
FILE_ATTRIBUTE_REPARSE_POINT: Final[int] = 0x400

_SOURCE_FORMATS: Final[dict[str, tuple[str, str]]] = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
    ".webp": ("image/webp", "WEBP"),
}


@dataclass(frozen=True, slots=True)
class LoadedStoredImage:
    """One validated source plus private storage evidence and an owned BGR array."""

    scan_image_id: str
    view: ImageView
    storage_key: str
    original_sha256: str
    oriented_pixel_sha256: str
    media_type: str
    size_bytes: int
    width_px: int
    height_px: int
    image_bgr: NDArray[np.uint8] = field(repr=False, compare=False)


class StoredImageLoader:
    """Resolve and decode server-owned storage keys without following reparse points."""

    def __init__(
        self,
        data_root: Path,
        *,
        max_file_size_bytes: int,
        max_decoded_pixels: int,
    ) -> None:
        if max_file_size_bytes <= 0 or max_decoded_pixels <= 0:
            raise ValueError("Stored-image limits must be positive")
        self.data_root = data_root.expanduser().resolve(strict=False)
        self.max_file_size_bytes = max_file_size_bytes
        self.max_decoded_pixels = max_decoded_pixels

    def load_required(
        self,
        images: Iterable[ScanImage],
    ) -> tuple[LoadedStoredImage, LoadedStoredImage, LoadedStoredImage]:
        """Load top, front, and side in canonical order; optional images are ignored."""
        required: dict[ImageView, ScanImage] = {}
        for image in images:
            if image.view_type not in REQUIRED_IMAGE_VIEW_ORDER:
                continue
            if image.view_type in required:
                raise _source_changed_error(image.view_type)
            required[image.view_type] = image
        if tuple(view for view in REQUIRED_IMAGE_VIEW_ORDER if view not in required):
            raise ApplicationError(
                status_code=status.HTTP_409_CONFLICT,
                code="SCAN_NOT_READY",
                message="The scan does not contain every required measurement view.",
                recoverable=True,
                suggested_action="Upload valid top, front, and side images before processing.",
            )
        loaded = tuple(self.load(required[view]) for view in REQUIRED_IMAGE_VIEW_ORDER)
        return cast(
            tuple[LoadedStoredImage, LoadedStoredImage, LoadedStoredImage],
            loaded,
        )

    def load(self, image: ScanImage) -> LoadedStoredImage:
        """Return validated immutable source evidence without changing the original file."""
        view = image.view_type
        if view not in REQUIRED_IMAGE_VIEW_ORDER:
            raise _source_changed_error(view)
        expected = _SOURCE_FORMATS.get(image.file_extension.lower())
        if expected is None or expected[0] != image.media_type:
            raise _source_changed_error(view)
        if image.size_bytes <= 0 or image.size_bytes > self.max_file_size_bytes:
            raise _source_changed_error(view)
        if image.width_px <= 0 or image.height_px <= 0:
            raise _source_changed_error(view)
        if image.width_px * image.height_px > self.max_decoded_pixels:
            raise _source_changed_error(view)

        source_path = self._resolve_source(image.storage_key, view)
        content = self._read_bounded(source_path, image.size_bytes, view)
        image_bgr, width_px, height_px = self._decode(
            content,
            extension=image.file_extension.lower(),
            media_type=image.media_type,
            view=view,
        )
        if (width_px, height_px) != (image.width_px, image.height_px):
            raise _source_changed_error(view)

        original_sha256 = hashlib.sha256(content).hexdigest()
        oriented_digest = hashlib.sha256()
        oriented_digest.update(b"phase3-bgr8\x00")
        oriented_digest.update(struct.pack(">II", height_px, width_px))
        oriented_digest.update(image_bgr.tobytes(order="C"))
        return LoadedStoredImage(
            scan_image_id=image.id,
            view=view,
            storage_key=image.storage_key,
            original_sha256=original_sha256,
            oriented_pixel_sha256=oriented_digest.hexdigest(),
            media_type=image.media_type,
            size_bytes=len(content),
            width_px=width_px,
            height_px=height_px,
            image_bgr=image_bgr,
        )

    def _resolve_source(self, storage_key: str, view: ImageView) -> Path:
        if not storage_key or "\\" in storage_key or ":" in storage_key:
            raise _source_unavailable_error(view)
        relative = PurePosixPath(storage_key)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise _source_unavailable_error(view)
        candidate = self.data_root.joinpath(*relative.parts)
        try:
            _assert_no_reparse_points(self.data_root, candidate)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.data_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise _source_unavailable_error(view) from error
        if resolved.suffix.lower() not in _SOURCE_FORMATS:
            raise _source_changed_error(view)
        return resolved

    def _read_bounded(
        self,
        source_path: Path,
        expected_size: int,
        view: ImageView,
    ) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            before = source_path.stat(follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or _stat_is_reparse(before):
                raise OSError("Source is not a regular file")
            descriptor = os.open(source_path, flags)
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
                    raise OSError("Source identity changed")
                content = bytearray()
                while True:
                    chunk = os.read(descriptor, READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > self.max_file_size_bytes:
                        raise ValueError("Source exceeds configured limit")
            finally:
                os.close(descriptor)
            _assert_no_reparse_points(self.data_root, source_path)
            after = source_path.stat(follow_symlinks=False)
            if not os.path.samestat(before, after):
                raise ValueError("Source identity changed")
        except ValueError as error:
            raise _source_changed_error(view) from error
        except OSError as error:
            raise _source_unavailable_error(view) from error
        if len(content) != expected_size or after.st_size != expected_size:
            raise _source_changed_error(view)
        return bytes(content)

    def _decode(
        self,
        content: bytes,
        *,
        extension: str,
        media_type: str,
        view: ImageView,
    ) -> tuple[NDArray[np.uint8], int, int]:
        expected_media_type, expected_format = _SOURCE_FORMATS[extension]
        if media_type != expected_media_type:
            raise _source_changed_error(view)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as decoded:
                    decoded_format = (decoded.format or "").upper()
                    raw_width, raw_height = decoded.size
                    if raw_width * raw_height > self.max_decoded_pixels:
                        raise ValueError("Decoded source exceeds pixel limit")
                    if getattr(decoded, "n_frames", 1) != 1:
                        raise ValueError("Animated source is invalid")
                    decoded.load()
                    if decoded_format != expected_format:
                        raise ValueError("Decoded format changed")
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
            image_bgr = np.asarray(
                cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR),
                dtype=np.uint8,
            ).copy(order="C")
        except ApplicationError:
            raise
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            MemoryError,
            OSError,
            SyntaxError,
            UnidentifiedImageError,
            ValueError,
            cv2.error,
        ) as error:
            raise _source_changed_error(view) from error
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise _source_changed_error(view)
        height_px, width_px = image_bgr.shape[:2]
        if width_px * height_px > self.max_decoded_pixels:
            raise _source_changed_error(view)
        return image_bgr, int(width_px), int(height_px)


def _assert_no_reparse_points(root: Path, candidate: Path) -> None:
    """Reject symlinks and Windows junction/reparse points from root through candidate."""
    candidate.relative_to(root)
    current = root
    metadata = current.stat(follow_symlinks=False)
    if current.is_symlink() or _stat_is_reparse(metadata):
        raise OSError("Reparse points are not valid storage components")
    for part in candidate.relative_to(root).parts:
        current = current / part
        metadata = current.stat(follow_symlinks=False)
        if current.is_symlink() or _stat_is_reparse(metadata):
            raise OSError("Reparse points are not valid storage components")


def _stat_is_reparse(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _source_unavailable_error(view: ImageView) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="SOURCE_IMAGE_UNAVAILABLE",
        message="A required stored image is unavailable for processing.",
        recoverable=True,
        suggested_action="Verify local storage access, then retry or upload a new scan.",
        field=view.value,
        view=view,
    )


def _source_changed_error(view: ImageView) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="SOURCE_IMAGE_CHANGED",
        message="A required stored image no longer matches its saved metadata.",
        recoverable=True,
        suggested_action="Create a new scan with the original unmodified image.",
        field=view.value,
        view=view,
    )
