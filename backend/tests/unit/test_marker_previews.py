"""Tests for local in-memory bounded PNG calibration previews."""

from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest

from backend.app.calibration_contracts import (
    MAX_PREVIEW_BYTES,
    ArucoDictionary,
    MarkerProfileSpec,
)
from backend.app.errors import ApplicationError
from backend.app.vision.previews import (
    create_annotated_preview,
    create_rectified_preview,
)


def _profile() -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=0,
        marker_size_mm=100.0,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


def test_annotated_preview_is_bounded_png_and_does_not_mutate_input() -> None:
    generator = np.random.default_rng(12345)
    image = generator.integers(0, 256, size=(1600, 2200, 3), dtype=np.uint8)
    original = image.copy()
    corners = np.asarray(
        [[300.0, 250.0], [1700.0, 300.0], [1650.0, 1300.0], [350.0, 1250.0]],
        dtype=np.float64,
    )

    preview = create_annotated_preview(image, corners, _profile())
    encoded = base64.b64decode(preview.data_base64, validate=True)
    decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert np.array_equal(image, original)
    assert preview.media_type == "image/png"
    assert max(preview.width_px, preview.height_px) <= 1280
    assert len(encoded) <= MAX_PREVIEW_BYTES
    assert decoded.shape[:2] == (preview.height_px, preview.width_px)


def test_rectified_preview_respects_rectified_limits() -> None:
    image = np.full((2000, 2000, 3), 255, dtype=np.uint8)
    preview = create_rectified_preview(image)

    assert preview.width_px == 1800
    assert preview.height_px == 1800
    assert len(base64.b64decode(preview.data_base64)) <= MAX_PREVIEW_BYTES


def test_rectified_preview_fails_safely_instead_of_changing_geometry() -> None:
    generator = np.random.default_rng(20260718)
    image = generator.integers(0, 256, size=(1800, 1800, 3), dtype=np.uint8)

    with pytest.raises(ApplicationError) as caught:
        create_rectified_preview(image)

    assert caught.value.payload.code == "HOMOGRAPHY_INVALID"
