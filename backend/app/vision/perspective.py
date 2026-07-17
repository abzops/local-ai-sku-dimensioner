"""Planar marker homography, conditioning, inverse mapping, and rectification."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import (
    MAX_RECTIFIED_EDGE_PX,
    MarkerProfileSpec,
    Matrix3x3,
)
from backend.app.vision.marker_detection import reference_error


@dataclass(frozen=True, slots=True)
class MarkerHomography:
    """A validated image/marker-plane transform pair."""

    image_to_marker_mm: Matrix3x3
    marker_mm_to_image: Matrix3x3
    condition_number: float


def calculate_marker_homography(
    corners: NDArray[np.float64],
    profile: MarkerProfileSpec,
) -> MarkerHomography:
    """Calculate finite inverse transforms and normalized DLT conditioning."""
    image_points = np.asarray(corners, dtype=np.float64)
    marker_size = float(profile.marker_size_mm)
    marker_points = np.asarray(
        [
            [0.0, 0.0],
            [marker_size, 0.0],
            [marker_size, marker_size],
            [0.0, marker_size],
        ],
        dtype=np.float64,
    )
    if (
        image_points.shape != (4, 2)
        or not np.isfinite(image_points).all()
        or not np.isfinite(marker_points).all()
        or marker_size <= 0.0
    ):
        raise _homography_invalid_error()

    try:
        image_to_marker = cv2.getPerspectiveTransform(
            image_points.astype(np.float32), marker_points.astype(np.float32)
        ).astype(np.float64)
        if not np.isfinite(image_to_marker).all():
            raise np.linalg.LinAlgError
        determinant = float(np.linalg.det(image_to_marker))
        if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
            raise np.linalg.LinAlgError
        marker_to_image = np.asarray(
            np.linalg.inv(image_to_marker), dtype=np.float64
        )
        image_to_marker = _normalize_matrix(image_to_marker)
        marker_to_image = _normalize_matrix(marker_to_image)
        condition_number = normalized_homography_condition_number(
            image_to_marker, image_points, marker_points
        )
    except (cv2.error, np.linalg.LinAlgError, ValueError, FloatingPointError) as error:
        raise _homography_invalid_error() from error

    if not math.isfinite(condition_number):
        raise _homography_invalid_error()
    if condition_number > profile.maximum_homography_condition_number:
        raise reference_error(
            code="HOMOGRAPHY_ILL_CONDITIONED",
            message="The marker-plane transform is not numerically stable.",
            suggested_action="Retake the image with less tilt and a larger, sharper marker.",
        )
    return MarkerHomography(
        image_to_marker_mm=_as_matrix_tuple(image_to_marker),
        marker_mm_to_image=_as_matrix_tuple(marker_to_image),
        condition_number=condition_number,
    )


def normalized_homography_condition_number(
    image_to_marker: NDArray[np.float64],
    image_points: NDArray[np.float64],
    marker_points: NDArray[np.float64],
) -> float:
    """Measure transform conditioning after Hartley point normalization."""
    source_normalization = _point_normalization_matrix(image_points)
    destination_normalization = _point_normalization_matrix(marker_points)
    normalized_homography = (
        destination_normalization
        @ image_to_marker
        @ np.linalg.inv(source_normalization)
    )
    scale = float(np.linalg.norm(normalized_homography))
    if not math.isfinite(scale) or scale <= 1e-15:
        raise ValueError("Homography normalization failed")
    normalized_homography /= scale
    return float(np.linalg.cond(normalized_homography))


def rectify_marker_plane(
    image_bgr: NDArray[np.uint8],
    corners: NDArray[np.float64],
    profile: MarkerProfileSpec,
) -> NDArray[np.uint8]:
    """Rectify only the printed marker square at the configured pixel density."""
    edge_px = int(round(profile.marker_size_mm * profile.rectified_pixels_per_mm))
    if edge_px < 2 or edge_px > MAX_RECTIFIED_EDGE_PX:
        raise _homography_invalid_error()
    destination = np.asarray(
        [
            [0.0, 0.0],
            [float(edge_px - 1), 0.0],
            [float(edge_px - 1), float(edge_px - 1)],
            [0.0, float(edge_px - 1)],
        ],
        dtype=np.float32,
    )
    try:
        transform = cv2.getPerspectiveTransform(corners.astype(np.float32), destination)
        rectified = np.asarray(
            cv2.warpPerspective(
                image_bgr,
                transform,
                (edge_px, edge_px),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            ),
            dtype=np.uint8,
        )
    except cv2.error as error:
        raise _homography_invalid_error() from error
    if rectified.shape[:2] != (edge_px, edge_px) or rectified.dtype != np.uint8:
        raise _homography_invalid_error()
    return rectified


def transform_points(
    points: NDArray[np.float64], matrix: Matrix3x3
) -> NDArray[np.float64]:
    """Apply one public 3 by 3 planar transform to testable points."""
    transform = np.asarray(matrix, dtype=np.float64)
    homogeneous = np.column_stack((points, np.ones(len(points), dtype=np.float64)))
    mapped = homogeneous @ transform.T
    divisors = mapped[:, 2]
    if np.any(np.abs(divisors) <= 1e-15):
        raise ValueError("Point maps to infinity")
    return mapped[:, :2] / divisors[:, np.newaxis]


def _point_normalization_matrix(points: NDArray[np.float64]) -> NDArray[np.float64]:
    centroid = np.mean(points, axis=0)
    distances = np.linalg.norm(points - centroid, axis=1)
    mean_distance = float(np.mean(distances))
    if not math.isfinite(mean_distance) or mean_distance <= 1e-12:
        raise ValueError("Cannot normalize coincident points")
    scale = math.sqrt(2.0) / mean_distance
    return np.asarray(
        [
            [scale, 0.0, -scale * centroid[0]],
            [0.0, scale, -scale * centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _normalize_matrix(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    if not np.isfinite(matrix).all():
        raise ValueError("Matrix must be finite")
    denominator = float(matrix[2, 2])
    if abs(denominator) > 1e-15:
        normalized = matrix / denominator
    else:
        norm = float(np.linalg.norm(matrix))
        if norm <= 1e-15:
            raise ValueError("Matrix cannot be normalized")
        normalized = matrix / norm
    if not np.isfinite(normalized).all():
        raise ValueError("Matrix must be finite")
    return normalized


def _as_matrix_tuple(matrix: NDArray[np.float64]) -> Matrix3x3:
    return (
        (float(matrix[0, 0]), float(matrix[0, 1]), float(matrix[0, 2])),
        (float(matrix[1, 0]), float(matrix[1, 1]), float(matrix[1, 2])),
        (float(matrix[2, 0]), float(matrix[2, 1]), float(matrix[2, 2])),
    )


def _homography_invalid_error() -> Exception:
    return reference_error(
        code="HOMOGRAPHY_INVALID",
        message="A valid marker-plane transform could not be calculated.",
        suggested_action="Retake the image with the complete marker flat and clearly visible.",
    )

