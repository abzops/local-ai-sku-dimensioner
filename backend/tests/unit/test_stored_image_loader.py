from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.models.scan import ScanImage
from backend.app.services.stored_image_loader import StoredImageLoader


def _write_png(path: Path, *, size: tuple[int, int] = (12, 8)) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (10, 20, 30))
    image.save(path, format="PNG")
    return path.read_bytes()


def _scan_image(
    storage_key: str,
    *,
    view: ImageView = ImageView.TOP,
    media_type: str = "image/png",
    extension: str = ".png",
    size_bytes: int,
    width_px: int = 12,
    height_px: int = 8,
) -> ScanImage:
    return ScanImage(
        id=str(uuid4()),
        scan_id=str(uuid4()),
        view_type=view,
        storage_key=storage_key,
        media_type=media_type,
        file_extension=extension,
        size_bytes=size_bytes,
        width_px=width_px,
        height_px=height_px,
    )


def _loader(data_root: Path, *, max_bytes: int = 1024 * 1024) -> StoredImageLoader:
    return StoredImageLoader(
        data_root,
        max_file_size_bytes=max_bytes,
        max_decoded_pixels=1_000_000,
    )


def test_load_returns_owned_bgr_and_hashes_without_changing_source(tmp_path: Path) -> None:
    relative = "scans/11111111-1111-4111-8111-111111111111/original/op/top.png"
    source = tmp_path.joinpath(*relative.split("/"))
    original = _write_png(source)
    metadata = _scan_image(relative, size_bytes=len(original))

    loaded = _loader(tmp_path).load(metadata)

    assert loaded.original_sha256 == hashlib.sha256(original).hexdigest()
    assert len(loaded.oriented_pixel_sha256) == 64
    assert loaded.image_bgr.dtype == np.uint8
    assert loaded.image_bgr.shape == (8, 12, 3)
    assert loaded.image_bgr.flags.c_contiguous
    assert loaded.image_bgr[0, 0].tolist() == [30, 20, 10]
    loaded.image_bgr[0, 0] = 0
    assert source.read_bytes() == original


def test_load_applies_exif_orientation_and_validates_oriented_metadata(
    tmp_path: Path,
) -> None:
    relative = "scans/11111111-1111-4111-8111-111111111111/original/op/front.jpg"
    source = tmp_path.joinpath(*relative.split("/"))
    source.parent.mkdir(parents=True)
    image = Image.new("RGB", (12, 8), (80, 90, 100))
    exif = image.getexif()
    exif[274] = 6
    image.save(source, format="JPEG", exif=exif)
    original = source.read_bytes()
    metadata = _scan_image(
        relative,
        view=ImageView.FRONT,
        media_type="image/jpeg",
        extension=".jpg",
        size_bytes=len(original),
        width_px=8,
        height_px=12,
    )

    loaded = _loader(tmp_path).load(metadata)

    assert (loaded.width_px, loaded.height_px) == (8, 12)
    assert loaded.image_bgr.shape == (12, 8, 3)


def test_load_required_ignores_additional_and_orders_required_views(tmp_path: Path) -> None:
    images: list[ScanImage] = []
    for view in (ImageView.SIDE, ImageView.ADDITIONAL, ImageView.TOP, ImageView.FRONT):
        relative = f"scans/11111111-1111-4111-8111-111111111111/original/op/{view}.png"
        payload = _write_png(tmp_path.joinpath(*relative.split("/")))
        images.append(_scan_image(relative, view=view, size_bytes=len(payload)))

    loaded = _loader(tmp_path).load_required(images)

    assert tuple(item.view for item in loaded) == (
        ImageView.TOP,
        ImageView.FRONT,
        ImageView.SIDE,
    )


@pytest.mark.parametrize(
    "storage_key",
    (
        "../outside.png",
        "/absolute.png",
        "C:/outside.png",
        "scans\\outside.png",
        "scans/./outside.png",
    ),
)
def test_load_rejects_non_server_relative_storage_keys(
    tmp_path: Path,
    storage_key: str,
) -> None:
    metadata = _scan_image(storage_key, size_bytes=10)

    with pytest.raises(ApplicationError) as caught:
        _loader(tmp_path).load(metadata)

    assert caught.value.payload.code == "SOURCE_IMAGE_UNAVAILABLE"
    assert str(tmp_path) not in caught.value.payload.message


def test_load_rejects_symlink_or_windows_reparse_component(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"outside-{uuid4()}"
    outside.mkdir()
    _write_png(outside / "top.png")
    link = tmp_path / "scans"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("Creating a Windows reparse point requires local permission")
    metadata = _scan_image("scans/top.png", size_bytes=(outside / "top.png").stat().st_size)

    with pytest.raises(ApplicationError) as caught:
        _loader(tmp_path).load(metadata)

    assert caught.value.payload.code == "SOURCE_IMAGE_UNAVAILABLE"


def test_load_rejects_content_or_metadata_changes(tmp_path: Path) -> None:
    relative = "scans/11111111-1111-4111-8111-111111111111/original/op/top.png"
    source = tmp_path.joinpath(*relative.split("/"))
    original = _write_png(source)
    metadata = _scan_image(relative, size_bytes=len(original) + 1)

    with pytest.raises(ApplicationError) as caught:
        _loader(tmp_path).load(metadata)

    assert caught.value.payload.code == "SOURCE_IMAGE_CHANGED"
    assert caught.value.payload.view == ImageView.TOP


def test_load_rejects_bounded_source_before_decode(tmp_path: Path) -> None:
    relative = "scans/11111111-1111-4111-8111-111111111111/original/op/top.png"
    source = tmp_path.joinpath(*relative.split("/"))
    payload = _write_png(source)
    metadata = _scan_image(relative, size_bytes=len(payload))

    with pytest.raises(ApplicationError) as caught:
        _loader(tmp_path, max_bytes=len(payload) - 1).load(metadata)

    assert caught.value.payload.code == "SOURCE_IMAGE_CHANGED"


def test_load_rejects_missing_required_view_before_filesystem_access(tmp_path: Path) -> None:
    with pytest.raises(ApplicationError) as caught:
        _loader(tmp_path).load_required(())

    assert caught.value.payload.code == "SCAN_NOT_READY"
