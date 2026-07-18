"""Tests for oriented geometry and frozen view-axis mapping."""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.oriented_geometry import (
    AxisMeasurement,
    AxisVariantSpan,
    DimensionName,
    _reject_unstable_shadow_or_reflection,
    measure_product_geometry,
)
from backend.app.vision.product_contours import select_product_contour
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def _measure(view: ImageView, *, rotation_degrees: float = 0.0):
    scene = render_scene(view, rotation_degrees=rotation_degrees)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, GeometryPolicy())
    foreground = extract_foreground(plane, plane.marker_polygon_px, view, GeometryPolicy())
    product = select_product_contour(foreground, GeometryPolicy())
    return measure_product_geometry(product, view, GeometryPolicy())


def _product(view: ImageView = ImageView.TOP):  # type: ignore[no-untyped-def]
    scene = render_scene(view)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, GeometryPolicy())
    foreground = extract_foreground(plane, plane.marker_polygon_px, view, GeometryPolicy())
    return select_product_contour(foreground, GeometryPolicy())


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        (ImageView.TOP, {DimensionName.LENGTH: 240.0, DimensionName.WIDTH: 140.0}),
        (ImageView.FRONT, {DimensionName.WIDTH: 140.0, DimensionName.HEIGHT: 120.0}),
        (ImageView.SIDE, {DimensionName.LENGTH: 240.0, DimensionName.HEIGHT: 120.0}),
    ],
)
def test_required_axis_mapping(view: ImageView, expected: dict[DimensionName, float]) -> None:
    result = _measure(view)

    assert {item.dimension for item in result.raw_dimensions} == set(expected)
    for dimension, expected_value in expected.items():
        assert result.value(dimension) == pytest.approx(expected_value, abs=2.0)
    assert result.threshold_variant_span_mm >= 0.0
    assert result.morphology_variant_span_mm >= 0.0
    assert len(result.oriented_box_corners_mm) == 4


def test_top_rotation_preserves_length_and_width() -> None:
    result = _measure(ImageView.TOP, rotation_degrees=30.0)

    assert result.value(DimensionName.LENGTH) == pytest.approx(240.0, abs=2.5)
    assert result.value(DimensionName.WIDTH) == pytest.approx(140.0, abs=2.5)


def test_front_axis_misalignment_is_rejected() -> None:
    with pytest.raises(ApplicationError) as captured:
        _measure(ImageView.FRONT, rotation_degrees=10.0)
    assert captured.value.payload.code == "PRODUCT_AXIS_MISALIGNED"


def test_stable_high_reflection_is_rejected_as_unsupported() -> None:
    product = _product()
    reflective = replace(
        product,
        foreground=replace(product.foreground, reflection_fraction=0.05),
    )

    with pytest.raises(ApplicationError) as captured:
        measure_product_geometry(reflective, ImageView.TOP, GeometryPolicy())

    assert captured.value.payload.code == "REFLECTION_INTERFERENCE"


def test_unstable_shadow_geometry_returns_structured_shadow_failure() -> None:
    product = _product()
    shadowed = replace(
        product,
        foreground=replace(product.foreground, shadow_fraction=0.10),
    )
    measurements = (
        AxisMeasurement(DimensionName.LENGTH, 200.0),
        AxisMeasurement(DimensionName.WIDTH, 100.0),
    )
    spans = (
        AxisVariantSpan(DimensionName.LENGTH, 195.0, 205.0, 10.0),
        AxisVariantSpan(DimensionName.WIDTH, 99.0, 101.0, 2.0),
    )

    with pytest.raises(ApplicationError) as captured:
        _reject_unstable_shadow_or_reflection(
            shadowed, measurements, spans, GeometryPolicy()
        )

    assert captured.value.payload.code == "SHADOW_INTERFERENCE"
