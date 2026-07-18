"""Golden regression tests for the minimal checked-in Phase 3 fixture set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.oriented_geometry import DimensionName, measure_product_geometry
from backend.app.vision.product_contours import select_product_contour
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "phase3"


def _load_manifest() -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_golden_hashes_are_fixed() -> None:
    manifest = _load_manifest()
    files = manifest["files"]
    assert isinstance(files, dict)
    for filename, raw_record in files.items():
        assert isinstance(filename, str)
        assert isinstance(raw_record, dict)
        content = (FIXTURE_ROOT / filename).read_bytes()
        assert hashlib.sha256(content).hexdigest() == raw_record["sha256"]


@pytest.mark.parametrize(
    "filename",
    [
        "nominal_top.png",
        "nominal_front.png",
        "nominal_side.png",
        "perspective_top.png",
        "perspective_front.png",
        "perspective_side.png",
    ],
)
def test_golden_geometry_matches_known_source_with_numeric_tolerance(filename: str) -> None:
    manifest = _load_manifest()
    files = manifest["files"]
    assert isinstance(files, dict)
    record = files[filename]
    assert isinstance(record, dict)
    view = ImageView(str(record["view"]))
    image = cv2.imread(str(FIXTURE_ROOT / filename), cv2.IMREAD_COLOR)
    assert image is not None
    policy = GeometryPolicy()
    marker = analyze_marker_image(image, marker_profile())
    plane = rectify_full_plane(image, marker, policy)
    foreground = extract_foreground(plane, plane.marker_polygon_px, view, policy)
    contour = select_product_contour(foreground, policy)
    geometry = measure_product_geometry(contour, view, policy)
    expected = record["expected_dimensions_mm"]
    assert isinstance(expected, dict)

    for dimension, value in expected.items():
        assert geometry.value(DimensionName(str(dimension))) == pytest.approx(
            float(value), abs=2.5
        )


def test_ambiguous_golden_fails_instead_of_using_largest_contour() -> None:
    image = cv2.imread(str(FIXTURE_ROOT / "ambiguous_top.png"), cv2.IMREAD_COLOR)
    assert image is not None
    policy = GeometryPolicy()
    marker = analyze_marker_image(image, marker_profile())
    plane = rectify_full_plane(image, marker, policy)
    foreground = extract_foreground(
        plane, plane.marker_polygon_px, ImageView.TOP, policy
    )
    with pytest.raises(ApplicationError) as captured:
        select_product_contour(foreground, policy)
    assert captured.value.payload.code == "MULTIPLE_OBJECTS_DETECTED"
