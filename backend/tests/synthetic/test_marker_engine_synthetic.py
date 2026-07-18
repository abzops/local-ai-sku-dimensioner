"""Synthetic end-to-end tests for the deterministic marker-plane engine."""

from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.perspective import transform_points


def _profile(dictionary: ArucoDictionary, marker_id: int) -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=dictionary,
        marker_id=marker_id,
        marker_size_mm=100.0,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


def _perspective_marker(
    dictionary: ArucoDictionary, marker_id: int
) -> tuple[NDArray[np.uint8], NDArray[np.float64]]:
    marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(dictionary), marker_id, 400, borderBits=1
    )
    source = np.asarray(
        [[0.0, 0.0], [399.0, 0.0], [399.0, 399.0], [0.0, 399.0]],
        dtype=np.float32,
    )
    destination = np.asarray(
        [[180.0, 120.0], [650.0, 150.0], [610.0, 590.0], [210.0, 560.0]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(
        marker, transform, (820, 720), flags=cv2.INTER_NEAREST, borderValue=255
    )
    return cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR), destination.astype(np.float64)


@pytest.mark.parametrize("dictionary", list(ArucoDictionary))
@pytest.mark.parametrize("marker_id", [0, 49])
def test_all_supported_dictionaries_and_boundary_ids_under_perspective(
    dictionary: ArucoDictionary, marker_id: int
) -> None:
    image, expected_corners = _perspective_marker(dictionary, marker_id)

    result = analyze_marker_image(image, _profile(dictionary, marker_id))

    actual_corners = np.asarray(
        [[corner.x_px, corner.y_px] for corner in result.ordered_corners]
    )
    marker_mm = transform_points(actual_corners, result.image_to_marker_mm)
    expected_mm = np.asarray(
        [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
    )
    inverse_round_trip = transform_points(marker_mm, result.marker_mm_to_image)

    assert actual_corners == pytest.approx(expected_corners, abs=2.0)
    assert marker_mm == pytest.approx(expected_mm, abs=1e-4)
    assert inverse_round_trip == pytest.approx(actual_corners, abs=1e-4)
    assert result.dictionary == dictionary
    assert result.marker_id == marker_id
    assert result.marker_edge_quality.valid is True
    assert result.marker_edge_quality.sample_count == 64
    assert result.rectified_width_px == 400
    assert result.rectified_height_px == 400
    assert base64.b64decode(result.annotated_preview.data_base64).startswith(b"\x89PNG")
    assert base64.b64decode(result.rectified_preview.data_base64).startswith(b"\x89PNG")


def test_orientation_is_canonical_for_rotated_marker() -> None:
    dictionary = ArucoDictionary.DICT_5X5_50
    marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(dictionary), 17, 300, borderBits=1
    )
    marker = cv2.rotate(marker, cv2.ROTATE_90_COUNTERCLOCKWISE)
    canvas = np.full((600, 600), 255, dtype=np.uint8)
    canvas[150:450, 150:450] = marker

    result = analyze_marker_image(
        cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), _profile(dictionary, 17)
    )

    assert result.orientation_degrees == pytest.approx(-90.0, abs=0.5)
    assert [corner.label.value for corner in result.ordered_corners] == [
        "top_left",
        "top_right",
        "bottom_right",
        "bottom_left",
    ]

