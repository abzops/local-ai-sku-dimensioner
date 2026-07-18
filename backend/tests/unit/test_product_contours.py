"""Tests for explicit product candidate evaluation."""

from __future__ import annotations

import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.product_contours import select_product_contour
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def _select(**scene_options: bool):  # type: ignore[no-untyped-def]
    scene = render_scene(ImageView.TOP, **scene_options)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, GeometryPolicy())
    foreground = extract_foreground(
        plane, plane.marker_polygon_px, ImageView.TOP, GeometryPolicy()
    )
    return select_product_contour(foreground, GeometryPolicy())


def test_unique_candidate_is_selected_by_evidence() -> None:
    result = _select(noise_components=True)

    assert result.selected_score >= 0.70
    assert result.scored_candidate_count == 1
    assert result.runner_up_score is None
    assert result.solidity >= 0.65
    assert result.extent >= 0.25
    assert result.marker_clearance_mm >= 3.0
    assert result.border_clearance_mm >= 2.0


def test_close_runner_up_is_rejected_instead_of_selecting_largest() -> None:
    with pytest.raises(ApplicationError) as captured:
        _select(ambiguous=True)
    assert captured.value.payload.code == "MULTIPLE_OBJECTS_DETECTED"


def test_boundary_and_marker_contact_fail_safely() -> None:
    with pytest.raises(ApplicationError) as captured:
        _select(crop=True)
    assert captured.value.payload.code == "PRODUCT_CROPPED"

    with pytest.raises(ApplicationError) as captured:
        _select(marker_near=True)
    assert captured.value.payload.code == "PRODUCT_MARKER_TOO_CLOSE"
