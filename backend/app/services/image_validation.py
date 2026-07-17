"""Phase 1 image validation without measurement or processing behavior."""

from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path
from typing import Final
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.errors import ApplicationError
from backend.app.upload_contracts import (
    CanonicalExtension,
    CanonicalMediaType,
    UploadInput,
    ValidatedUpload,
)

DEFAULT_MAX_FILE_SIZE_BYTES: Final[int] = 25 * 1024 * 1024
DEFAULT_MAX_DECODED_PIXELS: Final[int] = 50_000_000
DEFAULT_MIN_SHORT_EDGE_PX: Final[int] = 720
DEFAULT_MIN_LONG_EDGE_PX: Final[int] = 1280
READ_CHUNK_SIZE: Final[int] = 1024 * 1024

EXTENSION_RULES: Final[
    dict[str, tuple[CanonicalExtension, CanonicalMediaType, str]]
] = {
    ".jpg": (".jpg", "image/jpeg", "JPEG"),
    ".jpeg": (".jpg", "image/jpeg", "JPEG"),
    ".png": (".png", "image/png", "PNG"),
    ".webp": (".webp", "image/webp", "WEBP"),
}
MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
FORMAT_RULES: Final[
    dict[str, tuple[CanonicalExtension, CanonicalMediaType]]
] = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


class ImageValidator:
    """Validate an upload's declaration, bytes, decoded format, and dimensions."""

    def __init__(
        self,
        *,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        max_decoded_pixels: int = DEFAULT_MAX_DECODED_PIXELS,
        min_short_edge_px: int = DEFAULT_MIN_SHORT_EDGE_PX,
        min_long_edge_px: int = DEFAULT_MIN_LONG_EDGE_PX,
    ) -> None:
        if min(
            max_file_size_bytes,
            max_decoded_pixels,
            min_short_edge_px,
            min_long_edge_px,
        ) <= 0:
            raise ValueError("Image validation limits must be positive")
        if min_short_edge_px > min_long_edge_px:
            raise ValueError("Minimum short edge cannot exceed minimum long edge")
        self.max_file_size_bytes = max_file_size_bytes
        self.max_decoded_pixels = max_decoded_pixels
        self.min_short_edge_px = min_short_edge_px
        self.min_long_edge_px = min_long_edge_px

    async def validate(self, upload: UploadInput) -> ValidatedUpload:
        """Return safe metadata after fully validating one uploaded image."""
        client_extension = Path(upload.file.filename or "").suffix.lower()
        extension_rule = EXTENSION_RULES.get(client_extension)
        if extension_rule is None:
            raise _upload_error(
                status_code=415,
                code="UNSUPPORTED_FILE_EXTENSION",
                message="The image file extension is not supported.",
                suggested_action="Choose a JPEG, PNG, or WebP image.",
                upload=upload,
            )

        canonical_extension, expected_media_type, expected_format = extension_rule
        declared_media_type = (upload.file.content_type or "").lower()
        if declared_media_type not in MEDIA_TYPES:
            raise _upload_error(
                status_code=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                message="The image media type is not supported.",
                suggested_action="Choose a JPEG, PNG, or WebP image.",
                upload=upload,
            )
        if declared_media_type != expected_media_type:
            raise _upload_error(
                status_code=415,
                code="IMAGE_FORMAT_MISMATCH",
                message="The image extension and media type do not match.",
                suggested_action="Choose the original image again and retry.",
                upload=upload,
            )

        try:
            content = await self._read_bounded(upload)
        finally:
            await upload.file.seek(0)

        decoded_format, width_px, height_px = self._decode(content, upload)
        decoded_rule = FORMAT_RULES.get(decoded_format)
        if (
            decoded_rule is None
            or decoded_format != expected_format
            or decoded_rule != (canonical_extension, expected_media_type)
        ):
            raise _upload_error(
                status_code=415,
                code="IMAGE_FORMAT_MISMATCH",
                message="The image content does not match its declared format.",
                suggested_action="Choose the original image again and retry.",
                upload=upload,
            )

        return ValidatedUpload(
            image_id=str(uuid4()),
            view_type=upload.view_type,
            canonical_extension=canonical_extension,
            media_type=expected_media_type,
            size_bytes=len(content),
            width_px=width_px,
            height_px=height_px,
            file=upload.file,
        )

    async def _read_bounded(self, upload: UploadInput) -> bytes:
        content = bytearray()
        while True:
            chunk = await upload.file.read(READ_CHUNK_SIZE)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > self.max_file_size_bytes:
                raise _upload_error(
                    status_code=413,
                    code="FILE_TOO_LARGE",
                    message="The image exceeds the maximum upload size.",
                    suggested_action=(
                        "Choose an image no larger than "
                        f"{self.max_file_size_bytes // (1024 * 1024)} MiB."
                    ),
                    upload=upload,
                )
        return bytes(content)

    def _decode(self, content: bytes, upload: UploadInput) -> tuple[str, int, int]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    decoded_format = (image.format or "").upper()
                    raw_width, raw_height = image.size
                    if raw_width * raw_height > self.max_decoded_pixels:
                        raise _upload_error(
                            status_code=422,
                            code="IMAGE_PIXEL_LIMIT_EXCEEDED",
                            message="The decoded image is too large to validate safely.",
                            suggested_action="Choose an image with a lower pixel resolution.",
                            upload=upload,
                        )
                    if getattr(image, "n_frames", 1) != 1:
                        raise _upload_error(
                            status_code=422,
                            code="ANIMATED_IMAGE_NOT_SUPPORTED",
                            message="Animated images are not supported.",
                            suggested_action="Choose a single-frame image.",
                            upload=upload,
                        )
                    image.load()
                    oriented = ImageOps.exif_transpose(image)
                    try:
                        width_px, height_px = oriented.size
                    finally:
                        if oriented is not image:
                            oriented.close()
        except ApplicationError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise _upload_error(
                status_code=422,
                code="IMAGE_PIXEL_LIMIT_EXCEEDED",
                message="The decoded image is too large to validate safely.",
                suggested_action="Choose an image with a lower pixel resolution.",
                upload=upload,
            ) from error
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise _upload_error(
                status_code=422,
                code="IMAGE_DECODE_FAILED",
                message="The image content could not be decoded.",
                suggested_action="Choose a valid, unmodified image and retry.",
                upload=upload,
            ) from error

        short_edge, long_edge = sorted((width_px, height_px))
        if (
            short_edge < self.min_short_edge_px
            or long_edge < self.min_long_edge_px
        ):
            raise _upload_error(
                status_code=422,
                code="IMAGE_TOO_SMALL",
                message="The image does not meet the minimum resolution.",
                suggested_action=(
                    f"Capture an image with a long edge of at least "
                    f"{self.min_long_edge_px} pixels and a short edge of at least "
                    f"{self.min_short_edge_px} pixels."
                ),
                upload=upload,
            )
        return decoded_format, width_px, height_px


def _upload_error(
    *,
    status_code: int,
    code: str,
    message: str,
    suggested_action: str,
    upload: UploadInput,
) -> ApplicationError:
    return ApplicationError(
        status_code=status_code,
        code=code,
        message=message,
        recoverable=True,
        suggested_action=suggested_action,
        field=upload.view_type.value,
        view=upload.view_type,
    )
