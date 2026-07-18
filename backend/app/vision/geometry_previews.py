"""Bounded annotated PNG previews for deterministic product geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.errors import ApplicationError
from backend.app.vision.full_plane import GeometryPolicy, RectifiedPlane
from backend.app.vision.oriented_geometry import ViewGeometryResult


@dataclass(frozen=True, slots=True)
class EncodedGeometryPreview:
    media_type: Literal["image/png"]
    width_px: int
    height_px: int
    size_bytes: int
    data: bytes


def create_geometry_preview(
    rectified_plane: RectifiedPlane,
    view_geometry: ViewGeometryResult,
    policy: GeometryPolicy,
) -> EncodedGeometryPreview:
    """Draw marker guard, selected contour, OBB, axes, and raw values."""
    image = np.asarray(rectified_plane.image_bgr)
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or image.size == 0
        or view_geometry.view is not view_geometry.contour_result.foreground.view
    ):
        raise _preview_error(view_geometry)
    annotated = image.copy()
    marker_polygon = np.rint(rectified_plane.marker_polygon_px).astype(np.int32)
    contour = np.rint(view_geometry.contour_px).astype(np.int32)
    box = np.rint(view_geometry.oriented_box_corners_px).astype(np.int32)
    try:
        guard_overlay = annotated.copy()
        guard_overlay[view_geometry.contour_result.foreground.marker_guard_mask > 0] = (
            40,
            40,
            180,
        )
        annotated = np.asarray(
            cv2.addWeighted(guard_overlay, 0.18, annotated, 0.82, 0.0),
            dtype=np.uint8,
        )
        cv2.polylines(
            annotated,
            [marker_polygon.reshape((-1, 1, 2))],
            True,
            (0, 215, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.drawContours(annotated, [contour], -1, (50, 220, 50), 2, cv2.LINE_AA)
        cv2.polylines(
            annotated,
            [box.reshape((-1, 1, 2))],
            True,
            (255, 120, 20),
            3,
            cv2.LINE_AA,
        )
        for index, point in enumerate(box):
            location = (int(point[0]), int(point[1]))
            cv2.circle(annotated, location, 5, (255, 120, 20), -1, cv2.LINE_AA)
            cv2.putText(
                annotated,
                str(index + 1),
                (location[0] + 6, location[1] - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 120, 20),
                1,
                cv2.LINE_AA,
            )
        labels = " / ".join(
            f"{measurement.dimension.value}: {measurement.value_mm:.1f} mm"
            for measurement in view_geometry.raw_dimensions
        )
        cv2.rectangle(annotated, (0, 0), (min(annotated.shape[1] - 1, 900), 62), (0, 0, 0), -1)
        cv2.putText(
            annotated,
            f"{view_geometry.view.value.upper()} - deterministic plane geometry",
            (14, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            labels,
            (14, 49),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (230, 230, 230),
            1,
            cv2.LINE_AA,
        )
    except cv2.error as error:
        raise _preview_error(view_geometry) from error
    return _encode_bounded(annotated, view_geometry, policy)


def _encode_bounded(
    image: NDArray[np.uint8],
    geometry: ViewGeometryResult,
    policy: GeometryPolicy,
) -> EncodedGeometryPreview:
    bounded = _resize_to_edge(image, policy.maximum_preview_edge_px)
    while True:
        try:
            success, encoded = cv2.imencode(
                ".png", bounded, [cv2.IMWRITE_PNG_COMPRESSION, 9]
            )
        except cv2.error as error:
            raise _preview_error(geometry) from error
        if not success:
            raise _preview_error(geometry)
        data = encoded.tobytes()
        if len(data) <= policy.maximum_preview_bytes:
            height, width = bounded.shape[:2]
            return EncodedGeometryPreview(
                media_type="image/png",
                width_px=int(width),
                height_px=int(height),
                size_bytes=len(data),
                data=data,
            )
        height, width = bounded.shape[:2]
        if max(height, width) <= 32:
            raise _preview_error(geometry)
        ratio = max(
            0.5,
            min(
                0.9,
                math.sqrt(policy.maximum_preview_bytes / len(data)) * 0.95,
            ),
        )
        bounded = np.asarray(
            cv2.resize(
                bounded,
                (max(1, int(width * ratio)), max(1, int(height * ratio))),
                interpolation=cv2.INTER_AREA,
            ),
            dtype=np.uint8,
        )


def _resize_to_edge(
    image: NDArray[np.uint8], maximum_edge_px: int
) -> NDArray[np.uint8]:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= maximum_edge_px:
        return image.copy()
    ratio = maximum_edge_px / longest
    return np.asarray(
        cv2.resize(
            image,
            (max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))),
            interpolation=cv2.INTER_AREA,
        ),
        dtype=np.uint8,
    )


def _preview_error(geometry: ViewGeometryResult) -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="RECTIFICATION_INVALID",
        message="A safe annotated geometry preview could not be generated.",
        recoverable=True,
        suggested_action="Retake the view using the qualified rig and complete reference plane.",
        field=geometry.view.value,
        view=geometry.view,
    )
