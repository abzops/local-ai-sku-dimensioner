"""Deterministic, physically coplanar Phase 3 scene factory."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.contracts import ImageView
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary

PIXELS_PER_MM = 2.0
CANVAS_WIDTH_PX = 1000
CANVAS_HEIGHT_PX = 800
MARKER_SIZE_MM = 100.0
MARKER_SIDE_PX = int(MARKER_SIZE_MM * PIXELS_PER_MM)


@dataclass(frozen=True, slots=True)
class SyntheticScene:
    view: ImageView
    image_bgr: NDArray[np.uint8]
    marker_corners_px: NDArray[np.float64]
    expected_dimensions_mm: dict[str, float]


def marker_profile() -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=0,
        marker_size_mm=MARKER_SIZE_MM,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=PIXELS_PER_MM,
    )


def render_scene(
    view: ImageView,
    *,
    perspective: bool = False,
    ambiguous: bool = False,
    rotation_degrees: float = 0.0,
    shadow: bool = False,
    low_contrast: bool = False,
    crop: bool = False,
    noise_components: bool = False,
    marker_near: bool = False,
) -> SyntheticScene:
    """Render marker and silhouette in the same known physical plane."""
    canvas = np.full(
        (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX, 3),
        (235, 235, 235),
        dtype=np.uint8,
    )
    marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(ArucoDictionary.DICT_4X4_50),
        0,
        MARKER_SIDE_PX,
        borderBits=1,
    )
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    marker_left = 50
    marker_top = 50
    canvas[
        marker_top : marker_top + MARKER_SIDE_PX,
        marker_left : marker_left + MARKER_SIDE_PX,
    ] = marker_bgr
    marker_corners = np.asarray(
        [
            [marker_left, marker_top],
            [marker_left + MARKER_SIDE_PX - 1, marker_top],
            [marker_left + MARKER_SIDE_PX - 1, marker_top + MARKER_SIDE_PX - 1],
            [marker_left, marker_top + MARKER_SIDE_PX - 1],
        ],
        dtype=np.float64,
    )

    physical_dimensions = {
        ImageView.TOP: (240.0, 140.0),
        ImageView.FRONT: (140.0, 120.0),
        ImageView.SIDE: (240.0, 120.0),
    }
    horizontal_mm, vertical_mm = physical_dimensions[view]
    center = (720.0, 490.0) if ambiguous else (650.0, 490.0)
    if crop:
        center = (950.0, 490.0)
    if marker_near:
        center = (489.0, 390.0)
    product_color = (225, 225, 225) if low_contrast else (45, 90, 170)
    rectangle = (
        center,
        (horizontal_mm * PIXELS_PER_MM, vertical_mm * PIXELS_PER_MM),
        rotation_degrees,
    )
    product_box = np.rint(cv2.boxPoints(rectangle)).astype(np.int32)
    cv2.fillConvexPoly(canvas, product_box, product_color, lineType=cv2.LINE_AA)

    if shadow:
        shadow_layer = canvas.copy()
        cv2.ellipse(
            shadow_layer,
            (int(center[0] + 35), int(center[1] + vertical_mm)),
            (int(horizontal_mm), 35),
            0.0,
            0.0,
            360.0,
            (180, 180, 180),
            thickness=cv2.FILLED,
            lineType=cv2.LINE_AA,
        )
        canvas = cv2.addWeighted(shadow_layer, 0.45, canvas, 0.55, 0.0)
        cv2.fillConvexPoly(canvas, product_box, product_color, lineType=cv2.LINE_AA)

    if ambiguous:
        second = (
            (280.0, 500.0),
            (
                horizontal_mm * PIXELS_PER_MM * 0.70,
                vertical_mm * PIXELS_PER_MM,
            ),
            rotation_degrees,
        )
        cv2.fillConvexPoly(
            canvas,
            np.rint(cv2.boxPoints(second)).astype(np.int32),
            product_color,
            lineType=cv2.LINE_AA,
        )

    if noise_components:
        for index in range(25):
            x = 280 + ((index * 29) % 650)
            y = 40 + ((index * 47) % 700)
            cv2.circle(canvas, (x, y), 2, (40, 40, 40), thickness=cv2.FILLED)

    if perspective:
        source = np.asarray(
            [
                [0.0, 0.0],
                [CANVAS_WIDTH_PX - 1.0, 0.0],
                [CANVAS_WIDTH_PX - 1.0, CANVAS_HEIGHT_PX - 1.0],
                [0.0, CANVAS_HEIGHT_PX - 1.0],
            ],
            dtype=np.float32,
        )
        destination = np.asarray(
            [[95.0, 75.0], [1110.0, 35.0], [1160.0, 835.0], [55.0, 875.0]],
            dtype=np.float32,
        )
        transform = cv2.getPerspectiveTransform(source, destination)
        canvas = np.asarray(
            cv2.warpPerspective(
                canvas,
                transform,
                (1220, 920),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            ),
            dtype=np.uint8,
        )
        marker_corners = cv2.perspectiveTransform(
            marker_corners.astype(np.float32).reshape((1, 4, 2)), transform
        ).reshape((4, 2)).astype(np.float64)

    expected = (
        {"length": horizontal_mm, "width": vertical_mm}
        if view is ImageView.TOP
        else (
            {"width": horizontal_mm, "height": vertical_mm}
            if view is ImageView.FRONT
            else {"length": horizontal_mm, "height": vertical_mm}
        )
    )
    return SyntheticScene(
        view=view,
        image_bgr=np.asarray(canvas, dtype=np.uint8),
        marker_corners_px=marker_corners,
        expected_dimensions_mm=expected,
    )
