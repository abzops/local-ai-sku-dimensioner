"""Minimal deterministic golden expectation for marker-engine regression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

import cv2
import numpy as np
import pytest

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary
from backend.app.vision.marker_engine import analyze_marker_image


class GoldenMarker(TypedDict):
    dictionary: str
    marker_id: int
    marker_side_px: int
    canvas_width_px: int
    canvas_height_px: int
    marker_left_px: int
    marker_top_px: int
    marker_size_mm: float
    rectified_pixels_per_mm: float
    expected_orientation_degrees: float
    expected_corner_tolerance_px: float
    expected_residual_min_px: float
    expected_residual_max_px: float


def test_deterministic_golden_marker_geometry_and_quality() -> None:
    fixture_path = (
        Path(__file__).parents[1] / "fixtures" / "phase2_golden_marker.json"
    )
    golden = cast(GoldenMarker, json.loads(fixture_path.read_text(encoding="utf-8")))
    dictionary = ArucoDictionary(golden["dictionary"])
    marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(dictionary),
        golden["marker_id"],
        golden["marker_side_px"],
        borderBits=1,
    )
    canvas = np.full(
        (golden["canvas_height_px"], golden["canvas_width_px"]),
        255,
        dtype=np.uint8,
    )
    top = golden["marker_top_px"]
    left = golden["marker_left_px"]
    side = golden["marker_side_px"]
    canvas[top : top + side, left : left + side] = marker
    profile = MarkerProfileSpec(
        dictionary=dictionary,
        marker_id=golden["marker_id"],
        marker_size_mm=golden["marker_size_mm"],
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=golden["rectified_pixels_per_mm"],
    )

    result = analyze_marker_image(
        cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), profile
    )
    expected_corners = np.asarray(
        [
            [left, top],
            [left + side - 1, top],
            [left + side - 1, top + side - 1],
            [left, top + side - 1],
        ],
        dtype=np.float64,
    )
    actual_corners = np.asarray(
        [[corner.x_px, corner.y_px] for corner in result.ordered_corners]
    )

    assert actual_corners == pytest.approx(
        expected_corners, abs=golden["expected_corner_tolerance_px"]
    )
    assert result.orientation_degrees == pytest.approx(
        golden["expected_orientation_degrees"], abs=0.1
    )
    assert golden["expected_residual_min_px"] <= result.marker_edge_quality.rms_px
    assert result.marker_edge_quality.rms_px <= golden["expected_residual_max_px"]
    assert result.rectified_width_px == round(
        golden["marker_size_mm"] * golden["rectified_pixels_per_mm"]
    )
    assert result.rectified_height_px == result.rectified_width_px

