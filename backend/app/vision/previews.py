"""Bounded in-memory PNG previews for calibration evidence."""

from __future__ import annotations

import base64
import math

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import (
    MAX_PREVIEW_BYTES,
    MAX_PREVIEW_EDGE_PX,
    MAX_RECTIFIED_EDGE_PX,
    MarkerProfileSpec,
    PreviewImage,
)
from backend.app.vision.marker_detection import reference_error


def create_annotated_preview(
    image_bgr: NDArray[np.uint8],
    corners: NDArray[np.float64],
    profile: MarkerProfileSpec,
) -> PreviewImage:
    """Draw canonical marker evidence without mutating the caller's image."""
    source_height, source_width = image_bgr.shape[:2]
    if source_height <= 0 or source_width <= 0:
        raise _preview_error()
    annotated = _resize_to_edge(image_bgr, MAX_PREVIEW_EDGE_PX).copy()
    target_height, target_width = annotated.shape[:2]
    scaled_corners = corners * np.asarray(
        [target_width / source_width, target_height / source_height], dtype=np.float64
    )
    polygon = np.rint(scaled_corners).astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(annotated, [polygon], True, (40, 220, 40), 3, cv2.LINE_AA)
    labels = ("TL", "TR", "BR", "BL")
    colors = ((0, 0, 255), (0, 165, 255), (255, 0, 0), (255, 0, 255))
    for point, label, color in zip(scaled_corners, labels, colors, strict=True):
        location = (int(round(float(point[0]))), int(round(float(point[1]))))
        cv2.circle(annotated, location, 6, color, -1, cv2.LINE_AA)
        cv2.putText(
            annotated,
            label,
            (location[0] + 8, location[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        annotated,
        f"{profile.dictionary.value} / ID {profile.marker_id}",
        (16, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (40, 220, 40),
        2,
        cv2.LINE_AA,
    )
    return _bounded_png(annotated, MAX_PREVIEW_EDGE_PX)


def create_rectified_preview(rectified_bgr: NDArray[np.uint8]) -> PreviewImage:
    """Encode the marker-only rectification within Phase 2 resource limits."""
    return _bounded_png(
        rectified_bgr,
        MAX_RECTIFIED_EDGE_PX,
        preserve_dimensions=True,
    )


def _bounded_png(
    image: NDArray[np.uint8],
    maximum_edge_px: int,
    *,
    preserve_dimensions: bool = False,
) -> PreviewImage:
    if image.dtype != np.uint8 or image.size == 0 or image.ndim not in (2, 3):
        raise _preview_error()
    bounded = _resize_to_edge(image, maximum_edge_px)
    while True:
        try:
            encoded_ok, encoded = cv2.imencode(
                ".png", bounded, [cv2.IMWRITE_PNG_COMPRESSION, 9]
            )
        except cv2.error as error:
            raise _preview_error() from error
        if not encoded_ok:
            raise _preview_error()
        encoded_bytes = encoded.tobytes()
        if len(encoded_bytes) <= MAX_PREVIEW_BYTES:
            height_px, width_px = bounded.shape[:2]
            return PreviewImage(
                media_type="image/png",
                width_px=int(width_px),
                height_px=int(height_px),
                data_base64=base64.b64encode(encoded_bytes).decode("ascii"),
            )
        if preserve_dimensions:
            raise _preview_error()
        height_px, width_px = bounded.shape[:2]
        if max(width_px, height_px) <= 32:
            raise _preview_error()
        ratio = max(0.5, min(0.9, math.sqrt(MAX_PREVIEW_BYTES / len(encoded_bytes)) * 0.95))
        next_width = max(1, int(width_px * ratio))
        next_height = max(1, int(height_px * ratio))
        bounded = np.asarray(
            cv2.resize(
                bounded, (next_width, next_height), interpolation=cv2.INTER_AREA
            ),
            dtype=np.uint8,
        )


def _resize_to_edge(
    image: NDArray[np.uint8], maximum_edge_px: int
) -> NDArray[np.uint8]:
    height_px, width_px = image.shape[:2]
    longest_edge = max(height_px, width_px)
    if longest_edge <= maximum_edge_px:
        return image
    ratio = maximum_edge_px / longest_edge
    target_width = max(1, int(round(width_px * ratio)))
    target_height = max(1, int(round(height_px * ratio)))
    return np.asarray(
        cv2.resize(
            image, (target_width, target_height), interpolation=cv2.INTER_AREA
        ),
        dtype=np.uint8,
    )


def _preview_error() -> Exception:
    return reference_error(
        code="HOMOGRAPHY_INVALID",
        message="A safe calibration preview could not be generated.",
        suggested_action="Retake the image with the complete marker clearly visible.",
    )
