"""Synthetic end-to-end tests for physically coplanar product geometry."""

from __future__ import annotations

import cv2
import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.measurement_quality import (
    RigUncertaintySpec,
    calculate_view_quality,
    calculate_view_uncertainty,
)
from backend.app.vision.oriented_geometry import DimensionName, measure_product_geometry
from backend.app.vision.product_contours import select_product_contour
from backend.app.vision.reconciliation import (
    ViewMeasurementInput,
    reconcile_measurements,
)
from backend.tests.fixtures.phase3_synthetic_factory import (
    MARKER_SIDE_PX,
    marker_profile,
    render_scene,
)


def _process(view: ImageView, **options: bool):  # type: ignore[no-untyped-def]
    policy = GeometryPolicy()
    scene = render_scene(view, **options)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, policy)
    foreground = extract_foreground(plane, plane.marker_polygon_px, view, policy)
    contour = select_product_contour(foreground, policy)
    geometry = measure_product_geometry(contour, view, policy)
    quality = calculate_view_quality(marker, plane, contour, geometry, policy)
    uncertainty = calculate_view_uncertainty(
        marker,
        plane,
        geometry,
        RigUncertaintySpec(0.2, 0.5, 0.2, 0.4, 0.5),
    )
    return scene, geometry, quality, uncertainty


@pytest.mark.parametrize("perspective", [False, True])
@pytest.mark.parametrize("view", [ImageView.TOP, ImageView.FRONT, ImageView.SIDE])
def test_known_coplanar_dimensions_survive_perspective(
    view: ImageView, perspective: bool
) -> None:
    scene, geometry, quality, uncertainty = _process(view, perspective=perspective)

    for dimension, expected in scene.expected_dimensions_mm.items():
        assert geometry.value(DimensionName(dimension)) == pytest.approx(expected, abs=2.5)
    assert quality.score >= 0.55
    assert uncertainty.total_mm > 0.0


def test_rotated_top_shadow_and_noise_remain_bounded() -> None:
    scene, geometry, _quality, _uncertainty = _process(
        ImageView.TOP,
        rotation_degrees=30.0,  # type: ignore[arg-type]
        shadow=True,
        noise_components=True,
    )

    for dimension, expected in scene.expected_dimensions_mm.items():
        assert geometry.value(DimensionName(dimension)) == pytest.approx(expected, abs=3.0)


@pytest.mark.parametrize(
    ("options", "error_code"),
    [
        ({"ambiguous": True}, "MULTIPLE_OBJECTS_DETECTED"),
        ({"crop": True}, "PRODUCT_CROPPED"),
        ({"marker_near": True}, "PRODUCT_MARKER_TOO_CLOSE"),
        ({"low_contrast": True}, "FOREGROUND_LOW_CONTRAST"),
    ],
)
def test_insufficient_silhouette_evidence_fails_safely(
    options: dict[str, bool], error_code: str
) -> None:
    with pytest.raises(ApplicationError) as captured:
        _process(ImageView.TOP, **options)
    assert captured.value.payload.code == error_code


def test_missing_wrong_and_duplicate_markers_stop_before_product_geometry() -> None:
    profile = marker_profile()
    missing = render_scene(ImageView.TOP).image_bgr.copy()
    missing[45 : 55 + MARKER_SIDE_PX, 45 : 55 + MARKER_SIDE_PX] = (235, 235, 235)
    with pytest.raises(ApplicationError) as captured:
        analyze_marker_image(missing, profile)
    assert captured.value.payload.code == "REFERENCE_NOT_DETECTED"

    wrong = render_scene(ImageView.TOP).image_bgr.copy()
    wrong_marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(profile.dictionary), 1, MARKER_SIDE_PX, borderBits=1
    )
    wrong[50 : 50 + MARKER_SIDE_PX, 50 : 50 + MARKER_SIDE_PX] = cv2.cvtColor(
        wrong_marker, cv2.COLOR_GRAY2BGR
    )
    with pytest.raises(ApplicationError) as captured:
        analyze_marker_image(wrong, profile)
    assert captured.value.payload.code == "REFERENCE_WRONG_ID"

    duplicate = render_scene(ImageView.TOP).image_bgr.copy()
    duplicate_marker = duplicate[50 : 50 + MARKER_SIDE_PX, 50 : 50 + MARKER_SIDE_PX].copy()
    duplicate[275 : 275 + MARKER_SIDE_PX, 50 : 50 + MARKER_SIDE_PX] = duplicate_marker
    with pytest.raises(ApplicationError) as captured:
        analyze_marker_image(duplicate, profile)
    assert captured.value.payload.code == "REFERENCE_AMBIGUOUS"


def test_three_view_reconciliation_retains_both_sources() -> None:
    processed = {
        view: _process(view)
        for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    }
    inputs = tuple(
        ViewMeasurementInput(
            view=view,
            geometry=processed[view][1],
            quality=processed[view][2],
            uncertainty=processed[view][3],
        )
        for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    )

    result = reconcile_measurements(inputs[0], inputs[1], inputs[2], GeometryPolicy())

    assert result.succeeded is True
    assert result.final_dimensions_mm is not None
    assert [item.contributing_views for item in result.dimensions] == [
        (ImageView.TOP, ImageView.SIDE),
        (ImageView.TOP, ImageView.FRONT),
        (ImageView.FRONT, ImageView.SIDE),
    ]
