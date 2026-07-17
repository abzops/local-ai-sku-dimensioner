"""Filesystem safety and compensation tests for scan storage."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.services.scan_storage import ScanStorage
from backend.app.upload_contracts import ValidatedUpload


def make_validated_upload(
    content: bytes,
    *,
    image_id: str | None = None,
    filename: str = "untrusted-client-name.jpg",
    declared_size: int | None = None,
) -> ValidatedUpload:
    file = UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "image/jpeg"}),
    )
    return ValidatedUpload(
        image_id=image_id or str(uuid4()),
        view_type=ImageView.TOP,
        canonical_extension=".jpg",
        media_type="image/jpeg",
        size_bytes=len(content) if declared_size is None else declared_size,
        width_px=1280,
        height_px=720,
        file=file,
    )


def stage(
    storage: ScanStorage,
    scan_id: str,
    uploads: tuple[ValidatedUpload, ...],
):  # type: ignore[no-untyped-def]
    return asyncio.run(storage.stage(scan_id, uploads))


def test_stages_and_finalizes_with_server_generated_storage_keys(tmp_path: Path) -> None:
    storage = ScanStorage(tmp_path)
    scan_id = str(uuid4())
    image_id = str(uuid4())
    upload = make_validated_upload(
        b"validated bytes",
        image_id=image_id,
        filename=r"..\..\private\customer-sku.jpg",
    )

    staged = stage(storage, scan_id, (upload,))
    finalized = storage.finalize(staged)

    expected_key = f"scans/{scan_id}/original/{staged.operation_id}/{image_id}.jpg"
    assert finalized.images[0].storage_key == expected_key
    assert finalized.images[0].absolute_path.read_bytes() == b"validated bytes"
    assert "customer-sku" not in finalized.images[0].storage_key
    assert not staged.staging_directory.exists()
    assert finalized.final_directory.is_dir()


def test_finalized_cleanup_removes_only_owned_operation(tmp_path: Path) -> None:
    storage = ScanStorage(tmp_path)
    scan_id = str(uuid4())
    first = storage.finalize(stage(storage, scan_id, (make_validated_upload(b"one"),)))
    second = storage.finalize(stage(storage, scan_id, (make_validated_upload(b"two"),)))

    storage.cleanup_finalized(first)

    assert not first.final_directory.exists()
    assert second.final_directory.is_dir()
    assert second.images[0].absolute_path.read_bytes() == b"two"


def test_stage_failure_cleans_partial_operation_files(tmp_path: Path) -> None:
    storage = ScanStorage(tmp_path)
    scan_id = str(uuid4())
    first = make_validated_upload(b"one")
    changed = make_validated_upload(b"two", declared_size=4)

    with pytest.raises(ApplicationError) as captured:
        stage(storage, scan_id, (first, changed))

    assert captured.value.payload.code == "STORAGE_UNAVAILABLE"
    staging_parent = tmp_path / "scans" / scan_id / ".staging"
    assert staging_parent.is_dir()
    assert list(staging_parent.iterdir()) == []
    assert list(tmp_path.rglob("*.jpg")) == []


def test_finalization_conflict_preserves_existing_unowned_directory(
    tmp_path: Path,
) -> None:
    storage = ScanStorage(tmp_path)
    staged = stage(storage, str(uuid4()), (make_validated_upload(b"new"),))
    staged.final_directory.mkdir()
    existing_file = staged.final_directory / "existing.txt"
    existing_file.write_text("keep", encoding="utf-8")

    with pytest.raises(ApplicationError) as captured:
        storage.finalize(staged)

    assert captured.value.payload.code == "STORAGE_UNAVAILABLE"
    assert existing_file.read_text(encoding="utf-8") == "keep"
    assert not staged.staging_directory.exists()


def test_rejects_non_uuid_identifiers_before_creating_storage(tmp_path: Path) -> None:
    storage = ScanStorage(tmp_path)

    with pytest.raises(ApplicationError) as captured:
        stage(storage, r"..\..\outside", (make_validated_upload(b"content"),))

    assert captured.value.payload.code == "STORAGE_UNAVAILABLE"
    assert not (tmp_path / "scans").exists()


def test_conflicting_data_root_returns_sanitized_storage_error(tmp_path: Path) -> None:
    conflicting_root = tmp_path / "data-root-file"
    conflicting_root.write_text("conflict", encoding="utf-8")
    storage = ScanStorage(conflicting_root)

    with pytest.raises(ApplicationError) as captured:
        stage(storage, str(uuid4()), (make_validated_upload(b"content"),))

    assert captured.value.payload.code == "STORAGE_UNAVAILABLE"
    serialized = captured.value.payload.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "Traceback" not in serialized


def test_staged_cleanup_is_idempotent_after_closed_file_handles(tmp_path: Path) -> None:
    storage = ScanStorage(tmp_path)
    staged = stage(storage, str(uuid4()), (make_validated_upload(b"content"),))

    storage.cleanup_staged(staged)
    storage.cleanup_staged(staged)

    assert not staged.staging_directory.exists()
