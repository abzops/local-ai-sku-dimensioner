"""Tests for bounded annotated geometry previews."""

from __future__ import annotations

import cv2
import numpy as np

from backend.app.contracts import ImageView
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.geometry_previews import create_geometry_preview
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.oriented_geometry import measure_product_geometry
from backend.app.vision.product_contours import select_product_contour
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def test_preview_is_bounded_png_and_does_not_mutate_rectified_image() -> None:
    policy = GeometryPolicy(maximum_preview_edge_px=640, maximum_preview_bytes=500_000)
    scene = render_scene(ImageView.TOP)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, policy)
    original = plane.image_bgr.copy()
    foreground = extract_foreground(plane, plane.marker_polygon_px, ImageView.TOP, policy)
    contour = select_product_contour(foreground, policy)
    geometry = measure_product_geometry(contour, ImageView.TOP, policy)

    preview = create_geometry_preview(plane, geometry, policy)
    decoded = cv2.imdecode(np.frombuffer(preview.data, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert preview.media_type == "image/png"
    assert preview.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert preview.size_bytes == len(preview.data)
    assert max(preview.width_px, preview.height_px) <= 640
    assert preview.size_bytes <= 500_000
    assert decoded.shape[:2] == (preview.height_px, preview.width_px)
    assert np.array_equal(plane.image_bgr, original)
