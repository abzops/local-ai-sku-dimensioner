from __future__ import annotations

import hashlib
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.services.measurement_storage import (
    MeasurementStorage,
    PreviewWrite,
)


def _png(size: tuple[int, int] = (40, 20), color: int = 100) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (color, color, color)).save(output, format="PNG")
    return output.getvalue()


def _previews() -> tuple[PreviewWrite, PreviewWrite, PreviewWrite]:
    return tuple(
        PreviewWrite(
            view=view,
            media_type="image/png",
            width_px=40,
            height_px=20,
            png_bytes=_png(color=80 + index),
        )
        for index, view in enumerate((ImageView.TOP, ImageView.FRONT, ImageView.SIDE))
    )  # type: ignore[return-value]


def _ids() -> tuple[str, str]:
    return str(uuid4()), str(uuid4())


def test_stage_finalize_and_read_verified_preview(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()

    staged = storage.stage(scan_id, attempt_id, _previews())
    finalized = storage.finalize(staged)
    preview = finalized.previews[0]
    record = SimpleNamespace(
        storage_key=preview.storage_key,
        sha256=preview.sha256,
        media_type=preview.media_type,
        size_bytes=preview.size_bytes,
        width_px=preview.width_px,
        height_px=preview.height_px,
    )

    assert not staged.staging_directory.exists()
    assert finalized.final_directory.is_dir()
    assert storage.read_preview(record) == preview.absolute_path.read_bytes()
    assert preview.storage_key.startswith(f"scans/{scan_id}/measurements/{attempt_id}/")


def test_cleanup_finalized_removes_only_matching_operation(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()
    finalized = storage.finalize(storage.stage(scan_id, attempt_id, _previews()))

    storage.cleanup_finalized(finalized)

    assert not finalized.final_directory.exists()


def test_cleanup_refuses_directory_owned_by_another_operation(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()
    finalized = storage.finalize(storage.stage(scan_id, attempt_id, _previews()))
    (finalized.final_directory / ".operation_id").write_text(str(uuid4()), encoding="ascii")

    with pytest.raises(ApplicationError) as caught:
        storage.cleanup_finalized(finalized)

    assert caught.value.payload.code == "STORAGE_UNAVAILABLE"
    assert finalized.final_directory.exists()


def test_finalize_preserves_preexisting_final_directory(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()
    first = storage.finalize(storage.stage(scan_id, attempt_id, _previews()))
    preserved = first.previews[0].absolute_path.read_bytes()
    second = storage.stage(scan_id, attempt_id, _previews())

    with pytest.raises(ApplicationError):
        storage.finalize(second)

    assert first.previews[0].absolute_path.read_bytes() == preserved
    assert not second.staging_directory.exists()


def test_read_preview_rejects_tampered_bytes_hash_or_path(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()
    finalized = storage.finalize(storage.stage(scan_id, attempt_id, _previews()))
    preview = finalized.previews[0]
    preview.absolute_path.write_bytes(_png(color=240))
    record = SimpleNamespace(
        storage_key=preview.storage_key,
        sha256=preview.sha256,
        media_type="image/png",
        size_bytes=preview.size_bytes,
        width_px=preview.width_px,
        height_px=preview.height_px,
    )

    with pytest.raises(ApplicationError) as caught:
        storage.read_preview(record)

    assert caught.value.payload.code == "STORAGE_UNAVAILABLE"
    record.storage_key = "../outside.png"
    with pytest.raises(ApplicationError):
        storage.read_preview(record)


def test_stage_rejects_missing_duplicate_or_oversized_preview(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path, max_preview_encoded_size=256)
    scan_id, attempt_id = _ids()
    previews = _previews()

    with pytest.raises(ApplicationError):
        storage.stage(scan_id, attempt_id, previews[:2])
    with pytest.raises(ApplicationError):
        storage.stage(scan_id, attempt_id, (previews[0], previews[0], previews[2]))

    oversized = replace(previews[0], png_bytes=b"\x89PNG\r\n\x1a\n" + b"x" * 300)
    with pytest.raises(ApplicationError):
        storage.stage(scan_id, attempt_id, (oversized, previews[1], previews[2]))


def test_read_preview_validates_database_metadata(tmp_path: Path) -> None:
    storage = MeasurementStorage(tmp_path)
    scan_id, attempt_id = _ids()
    finalized = storage.finalize(storage.stage(scan_id, attempt_id, _previews()))
    preview = finalized.previews[0]
    record = SimpleNamespace(
        storage_key=preview.storage_key,
        sha256=hashlib.sha256(b"other").hexdigest(),
        media_type="image/png",
        size_bytes=preview.size_bytes,
        width_px=preview.width_px,
        height_px=preview.height_px,
    )

    with pytest.raises(ApplicationError):
        storage.read_preview(record)

    record.sha256 = preview.sha256
    record.media_type = "image/jpeg"
    with pytest.raises(ApplicationError):
        storage.read_preview(record)
