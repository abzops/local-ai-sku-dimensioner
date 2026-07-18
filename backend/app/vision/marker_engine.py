"""Orchestration for deterministic Phase 2 marker-plane analysis."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import (
    CornerLabel,
    EdgeValues,
    MarkerAnalysisResult,
    MarkerProfileSpec,
    OrderedCorner,
)
from backend.app.vision.marker_detection import (
    detect_expected_marker,
    marker_edge_lengths,
)
from backend.app.vision.marker_quality import (
    calculate_marker_edge_quality,
    require_valid_marker_edge_quality,
)
from backend.app.vision.perspective import (
    calculate_marker_homography,
    rectify_marker_plane,
)
from backend.app.vision.previews import (
    create_annotated_preview,
    create_rectified_preview,
)


def analyze_marker_image(
    oriented_image_bgr: NDArray[np.uint8],
    profile: MarkerProfileSpec,
) -> MarkerAnalysisResult:
    """Return marker-plane evidence without persistence or product measurement."""
    detected = detect_expected_marker(oriented_image_bgr, profile)
    corners = detected.corners
    edge_lengths = marker_edge_lengths(corners)
    minimum_edge = min(edge_lengths)
    maximum_edge = max(edge_lengths)
    perspective_ratio = maximum_edge / minimum_edge
    orientation = math.degrees(
        math.atan2(
            float(corners[1, 1] - corners[0, 1]),
            float(corners[1, 0] - corners[0, 0]),
        )
    )
    orientation = ((orientation + 180.0) % 360.0) - 180.0

    homography = calculate_marker_homography(corners, profile)
    quality = calculate_marker_edge_quality(
        oriented_image_bgr, corners, profile.maximum_marker_edge_residual_px
    )
    require_valid_marker_edge_quality(quality)
    rectified = rectify_marker_plane(oriented_image_bgr, corners, profile)

    labels = tuple(CornerLabel)
    ordered_corners = tuple(
        OrderedCorner(
            label=labels[index],
            x_px=float(corners[index, 0]),
            y_px=float(corners[index, 1]),
        )
        for index in range(4)
    )
    if len(ordered_corners) != 4:
        raise AssertionError("A marker must have four corners")
    rectified_height, rectified_width = rectified.shape[:2]
    return MarkerAnalysisResult(
        dictionary=profile.dictionary,
        marker_id=detected.marker_id,
        ordered_corners=(
            ordered_corners[0],
            ordered_corners[1],
            ordered_corners[2],
            ordered_corners[3],
        ),
        orientation_degrees=orientation,
        edge_lengths_px=EdgeValues(
            top=edge_lengths[0],
            right=edge_lengths[1],
            bottom=edge_lengths[2],
            left=edge_lengths[3],
        ),
        perspective_ratio=perspective_ratio,
        image_to_marker_mm=homography.image_to_marker_mm,
        marker_mm_to_image=homography.marker_mm_to_image,
        homography_condition_number=homography.condition_number,
        rectified_width_px=int(rectified_width),
        rectified_height_px=int(rectified_height),
        rectified_pixels_per_mm=profile.rectified_pixels_per_mm,
        marker_edge_quality=quality,
        annotated_preview=create_annotated_preview(
            oriented_image_bgr, corners, profile
        ),
        rectified_preview=create_rectified_preview(rectified),
    )

