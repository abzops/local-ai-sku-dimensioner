"""Tests for honest independent marker-border localization evidence."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from backend.app.errors import ApplicationError
from backend.app.vision.marker_quality import (
    QUALITY_DESCRIPTION,
    calculate_marker_edge_quality,
    require_valid_marker_edge_quality,
)


def _border_image() -> tuple[NDArray[np.uint8], NDArray[np.float64]]:
    grayscale = np.full((400, 400), 255, dtype=np.uint8)
    grayscale[100:300, 100:300] = 0
    image = cv2.cvtColor(grayscale, cv2.COLOR_GRAY2BGR)
    corners = np.asarray(
        [[99.5, 99.5], [299.5, 99.5], [299.5, 299.5], [99.5, 299.5]],
        dtype=np.float64,
    )
    return image, corners


def test_quality_reports_named_finite_per_edge_evidence() -> None:
    image, corners = _border_image()
    quality = calculate_marker_edge_quality(image, corners, threshold_px=2.0)

    assert quality.metric_name == "marker_edge_localization_residual"
    assert quality.description == QUALITY_DESCRIPTION
    assert quality.sample_count == 64
    assert quality.rms_px == pytest.approx(0.5)
    assert quality.maximum_px == pytest.approx(0.5)
    assert quality.per_edge_rms_px.top == pytest.approx(0.5)
    assert quality.per_edge_rms_px.right == pytest.approx(0.5)
    assert quality.per_edge_rms_px.bottom == pytest.approx(0.5)
    assert quality.per_edge_rms_px.left == pytest.approx(0.5)
    assert quality.valid is True


def test_shifted_fit_exceeds_residual_threshold() -> None:
    image, corners = _border_image()
    shifted = corners + np.asarray([4.0, 4.0])
    quality = calculate_marker_edge_quality(image, shifted, threshold_px=2.0)

    assert quality.maximum_px > 2.0
    assert quality.valid is False
    with pytest.raises(ApplicationError) as captured:
        require_valid_marker_edge_quality(quality)
    assert captured.value.payload.code == "REFERENCE_EDGE_RESIDUAL_EXCESSIVE"


def test_missing_border_evidence_fails() -> None:
    blank = np.full((400, 400, 3), 255, dtype=np.uint8)
    _image, corners = _border_image()

    with pytest.raises(ApplicationError) as captured:
        calculate_marker_edge_quality(blank, corners, threshold_px=2.0)

    assert captured.value.payload.code == "REFERENCE_EDGE_EVIDENCE_INSUFFICIENT"

