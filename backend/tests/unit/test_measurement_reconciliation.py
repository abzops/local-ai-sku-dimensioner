"""Tests for deterministic cross-view disagreement rules."""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.contracts import ImageView
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.measurement_quality import (
    ViewQualityEvidence,
    ViewUncertaintyEvidence,
)
from backend.app.vision.oriented_geometry import (
    AxisMeasurement,
    DimensionName,
    measure_product_geometry,
)
from backend.app.vision.product_contours import select_product_contour
from backend.app.vision.reconciliation import (
    DimensionValidationStatus,
    ReconciliationRule,
    ViewMeasurementInput,
    reconcile_measurements,
)
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def _geometry(view: ImageView):  # type: ignore[no-untyped-def]
    policy = GeometryPolicy()
    scene = render_scene(view)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, policy)
    foreground = extract_foreground(plane, plane.marker_polygon_px, view, policy)
    contour = select_product_contour(foreground, policy)
    return measure_product_geometry(contour, view, policy)


def _quality(score: float) -> ViewQualityEvidence:
    return ViewQualityEvidence(score, score, score, score, score, score, score)


def _uncertainty(total: float) -> ViewUncertaintyEvidence:
    return ViewUncertaintyEvidence(
        marker_size_mm=0.0,
        marker_localization_mm=0.0,
        raster_mm=0.0,
        foreground_stability_mm=0.0,
        rig_plane_mm=0.0,
        rig_orthogonality_mm=0.0,
        mount_standoff_mm=0.0,
        off_plane_parallax_mm=total,
        total_mm=total,
    )


def _inputs(
    *,
    top_length: float = 200.0,
    side_length: float = 202.0,
    top_quality: float = 0.8,
    side_quality: float = 0.8,
    top_uncertainty: float = 2.0,
    side_uncertainty: float = 2.0,
) -> tuple[ViewMeasurementInput, ViewMeasurementInput, ViewMeasurementInput]:
    top_geometry = replace(
        _geometry(ImageView.TOP),
        raw_dimensions=(
            AxisMeasurement(DimensionName.LENGTH, top_length),
            AxisMeasurement(DimensionName.WIDTH, 100.0),
        ),
    )
    front_geometry = replace(
        _geometry(ImageView.FRONT),
        raw_dimensions=(
            AxisMeasurement(DimensionName.WIDTH, 101.0),
            AxisMeasurement(DimensionName.HEIGHT, 150.0),
        ),
    )
    side_geometry = replace(
        _geometry(ImageView.SIDE),
        raw_dimensions=(
            AxisMeasurement(DimensionName.LENGTH, side_length),
            AxisMeasurement(DimensionName.HEIGHT, 151.0),
        ),
    )
    return (
        ViewMeasurementInput(
            ImageView.TOP,
            top_geometry,
            _quality(top_quality),
            _uncertainty(top_uncertainty),
        ),
        ViewMeasurementInput(
            ImageView.FRONT,
            front_geometry,
            _quality(0.8),
            _uncertainty(2.0),
        ),
        ViewMeasurementInput(
            ImageView.SIDE,
            side_geometry,
            _quality(side_quality),
            _uncertainty(side_uncertainty),
        ),
    )


def test_acceptable_comparable_sources_use_quality_uncertainty_weighting() -> None:
    result = reconcile_measurements(*_inputs(), GeometryPolicy())
    length = result.dimensions[0]

    assert result.succeeded is True
    assert length.dimension is DimensionName.LENGTH
    assert length.value_mm == pytest.approx(201.0)
    assert length.reconciliation_rule is ReconciliationRule.QUALITY_UNCERTAINTY_WEIGHTED
    assert length.validation_status is DimensionValidationStatus.ACCEPTABLE
    assert length.absolute_disagreement_mm == pytest.approx(2.0)


def test_acceptable_stronger_source_is_selected_without_blending() -> None:
    result = reconcile_measurements(
        *_inputs(top_quality=0.95, side_quality=0.70), GeometryPolicy()
    )
    length = result.dimensions[0]

    assert length.value_mm == pytest.approx(200.0)
    assert length.reconciliation_rule is ReconciliationRule.STRONGER_SOURCE


def test_warning_requires_dominant_higher_quality_lower_uncertainty_source() -> None:
    result = reconcile_measurements(
        *_inputs(
            side_length=208.0,
            top_quality=0.95,
            side_quality=0.70,
            top_uncertainty=1.0,
            side_uncertainty=3.0,
        ),
        GeometryPolicy(),
    )
    length = result.dimensions[0]

    assert result.succeeded is True
    assert length.value_mm == pytest.approx(200.0)
    assert length.validation_status is DimensionValidationStatus.WARNING
    assert length.uncertainty_mm == pytest.approx(7.0)


def test_warning_without_dominance_and_invalid_disagreement_fail_entire_tuple() -> None:
    comparable_warning = reconcile_measurements(
        *_inputs(side_length=208.0), GeometryPolicy()
    )
    invalid = reconcile_measurements(
        *_inputs(side_length=215.0, top_quality=0.95, side_quality=0.70),
        GeometryPolicy(),
    )

    assert comparable_warning.succeeded is False
    assert comparable_warning.final_dimensions_mm is None
    assert comparable_warning.dimensions[0].value_mm is None
    assert invalid.succeeded is False
    assert invalid.dimensions[0].validation_status is DimensionValidationStatus.INVALID


def test_one_invalid_view_quality_fails_instead_of_single_source_output() -> None:
    result = reconcile_measurements(
        *_inputs(side_quality=0.50), GeometryPolicy()
    )

    assert result.succeeded is False
    assert result.dimensions[0].warnings == ("MEASUREMENT_QUALITY_INSUFFICIENT",)


def test_uncertainty_that_reaches_a_raw_dimension_fails_entire_tuple() -> None:
    result = reconcile_measurements(
        *_inputs(top_uncertainty=200.0), GeometryPolicy()
    )

    assert result.succeeded is False
    assert result.final_dimensions_mm is None
    assert result.failure_code == "MEASUREMENT_UNCERTAINTY_EXCESSIVE"
    assert result.dimensions[0].warnings == ("MEASUREMENT_UNCERTAINTY_EXCESSIVE",)
