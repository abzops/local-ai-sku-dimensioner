"""Tests for marker-plane homography, inverse mapping, and conditioning."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from numpy.typing import NDArray

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.errors import ApplicationError
from backend.app.vision.perspective import (
    calculate_marker_homography,
    rectify_marker_plane,
    transform_points,
)


def _profile() -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=0,
        marker_size_mm=100.0,
        minimum_marker_side_px=24,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


def _corners() -> NDArray[np.float64]:
    return np.asarray(
        [[80.0, 60.0], [430.0, 95.0], [390.0, 410.0], [110.0, 380.0]],
        dtype=np.float64,
    )


def test_homography_maps_corners_to_marker_mm_and_inverse_round_trips() -> None:
    profile = _profile()
    corners = _corners()
    result = calculate_marker_homography(corners, profile)
    expected_mm = np.asarray(
        [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]],
        dtype=np.float64,
    )

    marker_points = transform_points(corners, result.image_to_marker_mm)
    round_trip = transform_points(marker_points, result.marker_mm_to_image)

    assert marker_points == pytest.approx(expected_mm, abs=1e-4)
    assert round_trip == pytest.approx(corners, abs=1e-4)
    assert np.isfinite(np.asarray(result.image_to_marker_mm)).all()
    assert 1.0 <= result.condition_number < 10.0


def test_condition_number_is_translation_and_scale_normalized() -> None:
    first = calculate_marker_homography(_corners(), _profile())
    translated_and_scaled = (_corners() * 4.0) + np.asarray([5000.0, 9000.0])
    second = calculate_marker_homography(translated_and_scaled, _profile())

    assert second.condition_number == pytest.approx(first.condition_number, rel=1e-5)


def test_ill_conditioned_and_singular_homographies_fail_safely() -> None:
    with pytest.raises(ApplicationError) as captured:
        calculate_marker_homography(
            _corners(), replace(_profile(), maximum_homography_condition_number=1.01)
        )
    assert captured.value.payload.code == "HOMOGRAPHY_ILL_CONDITIONED"

    singular = np.asarray(
        [[10.0, 10.0], [20.0, 10.0], [30.0, 10.0], [40.0, 10.0]],
        dtype=np.float64,
    )
    with pytest.raises(ApplicationError) as captured:
        calculate_marker_homography(singular, _profile())
    assert captured.value.payload.code == "HOMOGRAPHY_INVALID"


def test_rectification_has_configured_marker_plane_density() -> None:
    image = np.zeros((500, 500, 3), dtype=np.uint8)
    rectified = rectify_marker_plane(image, _corners(), _profile())

    assert rectified.shape == (400, 400, 3)
    assert rectified.dtype == np.uint8

