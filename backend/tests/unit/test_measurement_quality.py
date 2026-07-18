"""Tests for named quality and conservative uncertainty evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.measurement_quality import (
    RigUncertaintySpec,
    calculate_view_quality,
    calculate_view_uncertainty,
    require_minimum_view_quality,
)
from backend.app.vision.oriented_geometry import measure_product_geometry
from backend.app.vision.product_contours import select_product_contour
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def _evidence():  # type: ignore[no-untyped-def]
    scene = render_scene(ImageView.TOP)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    policy = GeometryPolicy()
    plane = rectify_full_plane(scene.image_bgr, marker, policy)
    foreground = extract_foreground(plane, plane.marker_polygon_px, ImageView.TOP, policy)
    contour = select_product_contour(foreground, policy)
    geometry = measure_product_geometry(contour, ImageView.TOP, policy)
    quality = calculate_view_quality(marker, plane, contour, geometry, policy)
    uncertainty = calculate_view_uncertainty(
        marker,
        plane,
        geometry,
        RigUncertaintySpec(
            marker_size_mm=0.2,
            plane_mm=0.5,
            orthogonality_degrees=0.2,
            mount_standoff_mm=0.4,
            maximum_off_plane_mm=0.5,
        ),
    )
    return policy, geometry, quality, uncertainty


def test_quality_has_all_named_finite_components() -> None:
    _policy, _geometry, quality, _uncertainty = _evidence()

    assert 0.0 <= quality.score <= 1.0
    assert quality.score >= 0.55
    assert all(
        0.0 <= component <= 1.0
        for component in (
            quality.marker,
            quality.homography,
            quality.background,
            quality.mask_stability,
            quality.candidate_uniqueness,
            quality.visibility,
        )
    )


def test_uncertainty_is_conservative_component_sum() -> None:
    _policy, _geometry, _quality, uncertainty = _evidence()
    components = (
        uncertainty.marker_size_mm,
        uncertainty.marker_localization_mm,
        uncertainty.raster_mm,
        uncertainty.foreground_stability_mm,
        uncertainty.rig_plane_mm,
        uncertainty.rig_orthogonality_mm,
        uncertainty.mount_standoff_mm,
        uncertainty.off_plane_parallax_mm,
    )

    assert uncertainty.total_mm == pytest.approx(sum(components))
    assert uncertainty.total_mm > 0.0


def test_quality_below_weak_floor_fails_safely() -> None:
    policy, geometry, quality, _uncertainty = _evidence()
    with pytest.raises(ApplicationError) as captured:
        require_minimum_view_quality(replace(quality, score=0.2), geometry, policy)
    assert captured.value.payload.code == "MEASUREMENT_QUALITY_INSUFFICIENT"
