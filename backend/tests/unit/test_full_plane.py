"""Tests for bounded full-plane rectification."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.full_plane import (
    GeometryPolicy,
    rectified_pixels_to_mm,
    rectify_full_plane,
)
from backend.app.vision.marker_engine import analyze_marker_image
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def test_full_plane_preserves_metric_marker_and_source_footprint() -> None:
    scene = render_scene(ImageView.TOP)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())

    plane = rectify_full_plane(scene.image_bgr, marker, GeometryPolicy())
    marker_mm = rectified_pixels_to_mm(plane.marker_polygon_px, plane)

    assert plane.image_bgr.dtype == np.uint8
    assert plane.valid_mask.shape == plane.image_bgr.shape[:2]
    assert plane.image_bgr.flags.owndata
    assert plane.physical_width_mm == pytest.approx(500.0, abs=1.0)
    assert plane.physical_height_mm == pytest.approx(400.0, abs=1.0)
    assert np.linalg.norm(marker_mm[1] - marker_mm[0]) == pytest.approx(100.0, abs=0.1)
    assert np.isfinite(np.asarray(plane.source_to_rectified)).all()
    assert np.isfinite(np.asarray(plane.rectified_to_source)).all()


def test_rectification_rejects_resource_limit_and_invalid_transform() -> None:
    scene = render_scene(ImageView.TOP)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    with pytest.raises(ApplicationError) as captured:
        rectify_full_plane(
            scene.image_bgr,
            marker,
            GeometryPolicy(maximum_rectified_edge_px=500),
        )
    assert captured.value.payload.code == "RECTIFICATION_LIMIT_EXCEEDED"

    invalid = replace(
        marker,
        image_to_marker_mm=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    )
    with pytest.raises(ApplicationError) as captured:
        rectify_full_plane(scene.image_bgr, invalid, GeometryPolicy())
    assert captured.value.payload.code == "RECTIFICATION_INVALID"


def test_rectification_rejects_non_uint8_input() -> None:
    scene = render_scene(ImageView.TOP)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    with pytest.raises(ApplicationError) as captured:
        rectify_full_plane(scene.image_bgr.astype(np.float32), marker, GeometryPolicy())
    assert captured.value.payload.code == "RECTIFICATION_INVALID"
