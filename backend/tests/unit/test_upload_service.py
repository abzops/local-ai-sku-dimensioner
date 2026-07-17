"""Request-local orchestration tests for the Phase 1 upload service."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.services.image_validation import ImageValidator
from backend.app.services.scan_storage import ScanStorage
from backend.app.services.uploads import UploadService
from backend.app.upload_contracts import StagedUploadBatch, UploadInput


def image_bytes() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (1280, 720), color=(15, 60, 125))
    image.save(buffer, format="JPEG")
    image.close()
    return buffer.getvalue()


def upload(
    view: ImageView,
    *,
    content: bytes | None = None,
    filename: str = "capture.jpg",
    media_type: str = "image/jpeg",
) -> UploadInput:
    file = UploadFile(
        BytesIO(image_bytes() if content is None else content),
        filename=filename,
        headers=Headers({"content-type": media_type}),
    )
    return UploadInput(view_type=view, file=file)


def validate_and_stage(
    service: UploadService,
    scan_id: str,
    uploads: tuple[UploadInput, ...],
) -> StagedUploadBatch:
    return asyncio.run(service.validate_and_stage(scan_id, uploads))


def service_for(tmp_path: Path) -> UploadService:
    return UploadService(ImageValidator(), ScanStorage(tmp_path))


def test_rejects_empty_batch_before_storage_writes(tmp_path: Path) -> None:
    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), ())

    assert captured.value.payload.code == "NO_FILES_PROVIDED"
    assert not (tmp_path / "scans").exists()


def test_rejects_request_file_limit_before_validation(tmp_path: Path) -> None:
    uploads = tuple(upload(ImageView.ADDITIONAL) for _ in range(9))

    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), uploads)

    assert captured.value.payload.code == "UPLOAD_LIMIT_EXCEEDED"
    assert not (tmp_path / "scans").exists()


def test_rejects_duplicate_required_view_before_validation(tmp_path: Path) -> None:
    uploads = (upload(ImageView.TOP), upload(ImageView.TOP))

    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), uploads)

    assert captured.value.payload.code == "DUPLICATE_VIEW"
    assert captured.value.payload.view is ImageView.TOP
    assert not (tmp_path / "scans").exists()


def test_rejects_more_than_five_additional_images(tmp_path: Path) -> None:
    uploads = tuple(upload(ImageView.ADDITIONAL) for _ in range(6))

    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), uploads)

    assert captured.value.payload.code == "ADDITIONAL_IMAGE_LIMIT_EXCEEDED"
    assert not (tmp_path / "scans").exists()


def test_validates_all_files_before_any_storage_write(tmp_path: Path) -> None:
    uploads = (
        upload(ImageView.TOP),
        upload(ImageView.FRONT),
        upload(ImageView.SIDE, content=b"not an image"),
    )

    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), uploads)

    assert captured.value.payload.code == "IMAGE_DECODE_FAILED"
    assert captured.value.payload.view is ImageView.SIDE
    assert not (tmp_path / "scans").exists()


def test_validation_failure_order_is_top_front_side_then_additional(
    tmp_path: Path,
) -> None:
    uploads = (
        upload(ImageView.ADDITIONAL, filename="bad.gif", media_type="image/gif"),
        upload(ImageView.TOP, filename="bad.bmp", media_type="image/bmp"),
    )

    with pytest.raises(ApplicationError) as captured:
        validate_and_stage(service_for(tmp_path), str(uuid4()), uploads)

    assert captured.value.payload.code == "UNSUPPORTED_FILE_EXTENSION"
    assert captured.value.payload.view is ImageView.TOP


def test_successful_batch_can_finalize_and_compensate_exactly(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    scan_id = str(uuid4())
    staged = validate_and_stage(
        service,
        scan_id,
        (
            upload(ImageView.SIDE),
            upload(ImageView.ADDITIONAL),
            upload(ImageView.TOP),
            upload(ImageView.FRONT),
        ),
    )

    assert [image.view_type for image in staged.images] == [
        ImageView.TOP,
        ImageView.FRONT,
        ImageView.SIDE,
        ImageView.ADDITIONAL,
    ]
    finalized = service.finalize(staged)
    sibling = finalized.final_directory.parent / str(uuid4())
    sibling.mkdir()
    marker = sibling / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    service.compensate(finalized)

    assert not finalized.final_directory.exists()
    assert marker.read_text(encoding="utf-8") == "keep"
