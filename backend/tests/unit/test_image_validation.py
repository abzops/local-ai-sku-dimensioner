"""Generated-image tests for Phase 1 upload validation."""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.services.image_validation import ImageValidator
from backend.app.upload_contracts import UploadInput


def make_image_bytes(
    *,
    image_format: str = "JPEG",
    size: tuple[int, int] = (1280, 720),
    exif_orientation: int | None = None,
) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(25, 90, 180))
    kwargs: dict[str, object] = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[274] = exif_orientation
        kwargs["exif"] = exif
    image.save(buffer, format=image_format, **kwargs)
    image.close()
    return buffer.getvalue()


def make_upload(
    content: bytes,
    *,
    filename: str = "capture.jpg",
    media_type: str = "image/jpeg",
    view: ImageView = ImageView.TOP,
) -> UploadInput:
    file = UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": media_type}),
    )
    return UploadInput(view_type=view, file=file)


def validate(validator: ImageValidator, upload: UploadInput):  # type: ignore[no-untyped-def]
    return asyncio.run(validator.validate(upload))


@pytest.mark.parametrize(
    ("image_format", "filename", "media_type", "canonical_extension"),
    [
        ("JPEG", "source.jpg", "image/jpeg", ".jpg"),
        ("JPEG", "source.jpeg", "image/jpeg", ".jpg"),
        ("PNG", "source.png", "image/png", ".png"),
        ("WEBP", "source.webp", "image/webp", ".webp"),
    ],
)
def test_accepts_supported_decoded_images(
    image_format: str,
    filename: str,
    media_type: str,
    canonical_extension: str,
) -> None:
    content = make_image_bytes(image_format=image_format)
    upload = make_upload(content, filename=filename, media_type=media_type)

    result = validate(ImageValidator(), upload)

    assert result.canonical_extension == canonical_extension
    assert result.media_type == media_type
    assert result.size_bytes == len(content)
    assert (result.width_px, result.height_px) == (1280, 720)
    assert result.file.file.tell() == 0


def test_uses_exif_orientation_for_reported_resolution() -> None:
    content = make_image_bytes(size=(1280, 720), exif_orientation=6)

    result = validate(ImageValidator(), make_upload(content))

    assert (result.width_px, result.height_px) == (720, 1280)


@pytest.mark.parametrize(
    ("upload", "expected_code"),
    [
        (make_upload(b"not-image", filename="source.gif", media_type="image/gif"),
         "UNSUPPORTED_FILE_EXTENSION"),
        (make_upload(b"not-image", media_type="application/octet-stream"),
         "UNSUPPORTED_MEDIA_TYPE"),
        (make_upload(b"not-image", filename="source.png", media_type="image/jpeg"),
         "IMAGE_FORMAT_MISMATCH"),
        (make_upload(b"not-image"), "IMAGE_DECODE_FAILED"),
    ],
)
def test_rejects_invalid_declarations_or_content(
    upload: UploadInput,
    expected_code: str,
) -> None:
    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(), upload)

    assert captured.value.payload.code == expected_code
    assert captured.value.payload.view is ImageView.TOP


def test_rejects_content_that_differs_from_declared_format() -> None:
    upload = make_upload(make_image_bytes(image_format="PNG"))

    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(), upload)

    assert captured.value.payload.code == "IMAGE_FORMAT_MISMATCH"


def test_enforces_bounded_file_size_and_resets_stream() -> None:
    upload = make_upload(b"a" * 11)

    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(max_file_size_bytes=10), upload)

    assert captured.value.payload.code == "FILE_TOO_LARGE"
    assert upload.file.file.tell() == 0


def test_rejects_image_below_minimum_resolution() -> None:
    upload = make_upload(make_image_bytes(size=(1279, 720)))

    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(), upload)

    assert captured.value.payload.code == "IMAGE_TOO_SMALL"


def test_rejects_image_above_decoded_pixel_ceiling() -> None:
    upload = make_upload(make_image_bytes(size=(100, 100)))
    validator = ImageValidator(
        max_decoded_pixels=9_999,
        min_short_edge_px=1,
        min_long_edge_px=1,
    )

    with pytest.raises(ApplicationError) as captured:
        validate(validator, upload)

    assert captured.value.payload.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_rejects_animated_image() -> None:
    buffer = BytesIO()
    first = Image.new("RGB", (1280, 720), color="red")
    second = Image.new("RGB", (1280, 720), color="blue")
    first.save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    first.close()
    second.close()
    upload = make_upload(
        buffer.getvalue(),
        filename="animated.webp",
        media_type="image/webp",
    )

    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(), upload)

    assert captured.value.payload.code == "ANIMATED_IMAGE_NOT_SUPPORTED"


def test_does_not_disclose_client_filename_in_error_payload() -> None:
    upload = make_upload(
        b"invalid",
        filename=r"C:\Users\Operator\secret-product.jpg",
    )

    with pytest.raises(ApplicationError) as captured:
        validate(ImageValidator(), upload)

    serialized = captured.value.payload.model_dump_json()
    assert "Operator" not in serialized
    assert "secret-product" not in serialized
