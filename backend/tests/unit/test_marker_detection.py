"""Tests for safe detection, canonical corners, and ambiguity handling."""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.errors import ApplicationError
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary
from backend.app.vision.marker_detection import (
    detect_expected_marker,
    validate_marker_corners,
    validate_marker_scale_and_perspective,
)


def _profile(marker_id: int = 0) -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=marker_id,
        marker_size_mm=100.0,
        minimum_marker_side_px=40,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


def _marker(marker_id: int, side_px: int = 180) -> NDArray[np.uint8]:
    return cv2.aruco.generateImageMarker(
        get_aruco_dictionary(ArucoDictionary.DICT_4X4_50),
        marker_id,
        side_px,
        borderBits=1,
    )


def _canvas(markers: list[tuple[int, int, int]]) -> NDArray[np.uint8]:
    canvas = np.full((520, 760), 255, dtype=np.uint8)
    for marker_id, x, y in markers:
        canvas[y : y + 180, x : x + 180] = _marker(marker_id)
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def test_detects_expected_id_and_preserves_canonical_rotation_order() -> None:
    marker = _marker(0, 240)
    rotated = cv2.rotate(marker, cv2.ROTATE_90_CLOCKWISE)
    canvas = np.full((500, 500), 255, dtype=np.uint8)
    canvas[120:360, 140:380] = rotated

    result = detect_expected_marker(
        cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), _profile()
    )

    assert result.marker_id == 0
    # Canonical top-left rotates to the visually top-right position.
    assert result.corners[0, 0] == pytest.approx(result.corners[1, 0], abs=0.1)
    assert result.corners[0, 1] < result.corners[1, 1]
    assert result.corners[0, 0] > result.corners[3, 0]


@pytest.mark.parametrize(
    ("image", "profile", "code"),
    [
        (np.full((300, 300, 3), 255, np.uint8), _profile(), "REFERENCE_NOT_DETECTED"),
        (_canvas([(1, 100, 100)]), _profile(0), "REFERENCE_WRONG_ID"),
        (
            _canvas([(0, 60, 120), (0, 420, 120)]),
            _profile(0),
            "REFERENCE_AMBIGUOUS",
        ),
        (
            _canvas([(0, 60, 120), (1, 420, 120)]),
            _profile(0),
            "REFERENCE_AMBIGUOUS",
        ),
    ],
)
def test_detection_failures_are_structured_and_safe(
    image: NDArray[np.uint8], profile: MarkerProfileSpec, code: str
) -> None:
    with pytest.raises(ApplicationError) as captured:
        detect_expected_marker(image, profile)

    assert captured.value.payload.code == code
    serialized = captured.value.payload.model_dump_json()
    assert "opencv" not in serialized.lower()
    assert "\\" not in serialized


@pytest.mark.parametrize(
    ("corners", "code"),
    [
        (
            np.asarray([[20.0, 20.0], [20.0, 20.0], [80.0, 80.0], [20.0, 80.0]]),
            "REFERENCE_CORNERS_INVALID",
        ),
        (
            np.asarray([[20.0, 20.0], [80.0, 80.0], [80.0, 20.0], [20.0, 80.0]]),
            "REFERENCE_CORNERS_INVALID",
        ),
        (
            np.asarray([[0.0, 20.0], [80.0, 20.0], [80.0, 80.0], [20.0, 80.0]]),
            "REFERENCE_CROPPED",
        ),
    ],
)
def test_invalid_or_cropped_corners_fail_safely(
    corners: NDArray[np.float64], code: str
) -> None:
    with pytest.raises(ApplicationError) as captured:
        validate_marker_corners(corners, 100, 100)

    assert captured.value.payload.code == code


def test_small_and_excessively_distorted_markers_are_rejected() -> None:
    small = np.asarray(
        [[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [10.0, 30.0]],
        dtype=np.float64,
    )
    with pytest.raises(ApplicationError) as captured:
        validate_marker_scale_and_perspective(small, _profile())
    assert captured.value.payload.code == "REFERENCE_TOO_SMALL"

    distorted = np.asarray(
        [[10.0, 10.0], [210.0, 10.0], [210.0, 60.0], [10.0, 60.0]],
        dtype=np.float64,
    )
    with pytest.raises(ApplicationError) as captured:
        validate_marker_scale_and_perspective(
            distorted, replace(_profile(), maximum_perspective_ratio=2.0)
        )
    assert captured.value.payload.code == "EXCESSIVE_PERSPECTIVE"

