"""Bounded full-plane rectification for deterministic Phase 3 geometry.

The transform is valid only for evidence represented in the calibrated marker
plane.  Numerical success is deliberately not treated as proof of physical
coplanarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import MarkerAnalysisResult, Matrix3x3
from backend.app.errors import ApplicationError

DEFAULT_MAXIMUM_RECTIFIED_EDGE_PX: Final[int] = 4096
DEFAULT_MAXIMUM_RECTIFIED_PIXELS: Final[int] = 16_000_000
DEFAULT_MAXIMUM_PHYSICAL_EXTENT_MM: Final[float] = 1500.0


@dataclass(frozen=True, slots=True)
class GeometryPolicy:
    """Frozen numeric policy consumed by pure geometry functions.

    Capture-setup uncertainty is supplied separately because it belongs to the
    producing deployment snapshot, while these values describe deterministic
    processing limits and thresholds.
    """

    acceptable_absolute_mm: float = 5.0
    acceptable_relative_percent: float = 3.0
    warning_absolute_mm: float = 10.0
    warning_relative_percent: float = 6.0
    usable_quality: float = 0.70
    weak_quality: float = 0.55
    stronger_source_quality_lead: float = 0.15
    weaker_source_uncertainty_ratio: float = 2.0
    maximum_rectified_edge_px: int = DEFAULT_MAXIMUM_RECTIFIED_EDGE_PX
    maximum_rectified_pixels: int = DEFAULT_MAXIMUM_RECTIFIED_PIXELS
    maximum_physical_extent_mm: float = DEFAULT_MAXIMUM_PHYSICAL_EXTENT_MM
    maximum_connected_components: int = 1024
    maximum_scored_candidates: int = 64
    maximum_preview_edge_px: int = 1280
    maximum_preview_bytes: int = 2 * 1024 * 1024
    minimum_object_mm: float = 75.0
    maximum_object_mm: float = 400.0
    background_lab_mad_maximum: float = 10.0
    minimum_lab_difference: float = 15.0
    minimum_grayscale_difference: float = 20.0
    morphology_open_mm: float = 1.0
    morphology_close_mm: float = 2.0
    marker_clearance_mm: float = 3.0
    border_clearance_mm: float = 2.0
    minimum_candidate_area_mm2: float = 100.0
    minimum_candidate_area_fraction: float = 0.0025
    maximum_candidate_area_fraction: float = 0.85
    minimum_solidity: float = 0.65
    minimum_extent: float = 0.25
    minimum_candidate_score: float = 0.70
    minimum_candidate_score_margin: float = 0.15
    maximum_axis_misalignment_degrees: float = 5.0
    maximum_shadow_geometry_change_mm: float = 2.0
    maximum_shadow_geometry_change_percent: float = 2.0

    def __post_init__(self) -> None:
        numeric_values = (
            self.acceptable_absolute_mm,
            self.acceptable_relative_percent,
            self.warning_absolute_mm,
            self.warning_relative_percent,
            self.usable_quality,
            self.weak_quality,
            self.stronger_source_quality_lead,
            self.weaker_source_uncertainty_ratio,
            self.maximum_physical_extent_mm,
            self.minimum_object_mm,
            self.maximum_object_mm,
            self.background_lab_mad_maximum,
            self.minimum_lab_difference,
            self.minimum_grayscale_difference,
            self.morphology_open_mm,
            self.morphology_close_mm,
            self.marker_clearance_mm,
            self.border_clearance_mm,
            self.minimum_candidate_area_mm2,
            self.minimum_candidate_area_fraction,
            self.maximum_candidate_area_fraction,
            self.minimum_solidity,
            self.minimum_extent,
            self.minimum_candidate_score,
            self.minimum_candidate_score_margin,
            self.maximum_axis_misalignment_degrees,
            self.maximum_shadow_geometry_change_mm,
            self.maximum_shadow_geometry_change_percent,
        )
        if not all(math.isfinite(value) and value >= 0.0 for value in numeric_values):
            raise ValueError("Geometry policy values must be finite and non-negative")
        if not 0.0 <= self.weak_quality <= self.usable_quality <= 1.0:
            raise ValueError("Quality thresholds must be ordered in the range 0 through 1")
        if self.acceptable_absolute_mm > self.warning_absolute_mm or (
            self.acceptable_relative_percent > self.warning_relative_percent
        ):
            raise ValueError("Disagreement thresholds must be ordered")
        if self.minimum_object_mm <= 0.0 or self.minimum_object_mm > self.maximum_object_mm:
            raise ValueError("Object-size limits must be positive and ordered")
        if not 0.0 < self.minimum_candidate_area_fraction < self.maximum_candidate_area_fraction:
            raise ValueError("Candidate-area fractions must be ordered")
        if min(
            self.maximum_rectified_edge_px,
            self.maximum_rectified_pixels,
            self.maximum_connected_components,
            self.maximum_scored_candidates,
            self.maximum_preview_edge_px,
            self.maximum_preview_bytes,
        ) <= 0:
            raise ValueError("Geometry resource limits must be positive")


@dataclass(frozen=True, slots=True)
class RectifiedPlane:
    """An owned full-plane image, validity mask, and auditable transforms."""

    image_bgr: NDArray[np.uint8]
    valid_mask: NDArray[np.uint8]
    marker_polygon_px: NDArray[np.float64]
    pixels_per_mm: float
    origin_mm: tuple[float, float]
    source_to_rectified: Matrix3x3
    rectified_to_source: Matrix3x3
    physical_width_mm: float
    physical_height_mm: float

    @property
    def width_px(self) -> int:
        return int(self.image_bgr.shape[1])

    @property
    def height_px(self) -> int:
        return int(self.image_bgr.shape[0])


def rectify_full_plane(
    image_bgr: NDArray[np.uint8],
    marker_evidence: MarkerAnalysisResult,
    policy: GeometryPolicy,
) -> RectifiedPlane:
    """Rectify the source-image footprint into the configured marker plane.

    This function validates numerical geometry only.  Callers must separately
    enforce the physically qualified coplanar capture contract.
    """
    source = _validate_image(image_bgr)
    pixels_per_mm = float(marker_evidence.rectified_pixels_per_mm)
    if not math.isfinite(pixels_per_mm) or pixels_per_mm <= 0.0:
        raise _rectification_error()
    image_to_mm = _matrix(marker_evidence.image_to_marker_mm)
    source_height, source_width = source.shape[:2]
    source_corners = np.asarray(
        [
            [0.0, 0.0],
            [float(source_width - 1), 0.0],
            [float(source_width - 1), float(source_height - 1)],
            [0.0, float(source_height - 1)],
        ],
        dtype=np.float64,
    )
    physical_corners = _transform_points(source_corners, image_to_mm)
    minimum = np.min(physical_corners, axis=0)
    maximum = np.max(physical_corners, axis=0)
    extent = maximum - minimum
    if (
        not np.isfinite(extent).all()
        or np.any(extent <= 0.0)
        or np.any(extent > policy.maximum_physical_extent_mm)
    ):
        raise _physical_extent_error()

    width_px = int(math.ceil(float(extent[0]) * pixels_per_mm)) + 1
    height_px = int(math.ceil(float(extent[1]) * pixels_per_mm)) + 1
    if (
        width_px < 2
        or height_px < 2
        or max(width_px, height_px) > policy.maximum_rectified_edge_px
        or width_px * height_px > policy.maximum_rectified_pixels
    ):
        raise _rectification_limit_error()

    metric_to_canvas = np.asarray(
        [
            [pixels_per_mm, 0.0, -float(minimum[0]) * pixels_per_mm],
            [0.0, pixels_per_mm, -float(minimum[1]) * pixels_per_mm],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    source_to_rectified = _normalize_matrix(metric_to_canvas @ image_to_mm)
    try:
        rectified_to_source = _normalize_matrix(
            np.asarray(np.linalg.inv(source_to_rectified), dtype=np.float64)
        )
        rectified = np.asarray(
            cv2.warpPerspective(
                source,
                source_to_rectified,
                (width_px, height_px),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            ),
            dtype=np.uint8,
        )
        source_valid = np.full((source_height, source_width), 255, dtype=np.uint8)
        valid_mask = np.asarray(
            cv2.warpPerspective(
                source_valid,
                source_to_rectified,
                (width_px, height_px),
                flags=cv2.INTER_NEAREST,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            ),
            dtype=np.uint8,
        )
    except (cv2.error, np.linalg.LinAlgError, ValueError) as error:
        raise _rectification_error() from error

    if rectified.shape != (height_px, width_px, 3) or valid_mask.shape != (
        height_px,
        width_px,
    ):
        raise _rectification_error()
    if int(np.count_nonzero(valid_mask)) == 0:
        raise _rectification_error()

    raw_marker_corners = np.asarray(
        [[corner.x_px, corner.y_px] for corner in marker_evidence.ordered_corners],
        dtype=np.float64,
    )
    marker_polygon = _transform_points(raw_marker_corners, source_to_rectified)
    if marker_polygon.shape != (4, 2) or not np.isfinite(marker_polygon).all():
        raise _rectification_error()

    return RectifiedPlane(
        image_bgr=rectified.copy(),
        valid_mask=np.where(valid_mask > 0, 255, 0).astype(np.uint8),
        marker_polygon_px=marker_polygon.copy(),
        pixels_per_mm=pixels_per_mm,
        origin_mm=(float(minimum[0]), float(minimum[1])),
        source_to_rectified=_as_matrix_tuple(source_to_rectified),
        rectified_to_source=_as_matrix_tuple(rectified_to_source),
        physical_width_mm=float(extent[0]),
        physical_height_mm=float(extent[1]),
    )


def rectified_pixels_to_mm(
    points_px: NDArray[np.float64], plane: RectifiedPlane
) -> NDArray[np.float64]:
    """Convert rectified canvas pixels into marker-plane millimetres."""
    points = np.asarray(points_px, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("Rectified points must be a finite N by 2 array")
    return np.column_stack(
        (
            (points[:, 0] / plane.pixels_per_mm) + plane.origin_mm[0],
            (points[:, 1] / plane.pixels_per_mm) + plane.origin_mm[1],
        )
    )


def _validate_image(image_bgr: NDArray[np.uint8]) -> NDArray[np.uint8]:
    image = np.asarray(image_bgr)
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or image.shape[0] < 2
        or image.shape[1] < 2
        or image.size == 0
    ):
        raise _rectification_error()
    return image


def _matrix(value: Matrix3x3) -> NDArray[np.float64]:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise _rectification_error()
    determinant = float(np.linalg.det(matrix))
    if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise _rectification_error()
    return _normalize_matrix(matrix)


def _transform_points(
    points: NDArray[np.float64], matrix: NDArray[np.float64]
) -> NDArray[np.float64]:
    homogeneous = np.column_stack((points, np.ones(len(points), dtype=np.float64)))
    mapped = homogeneous @ matrix.T
    divisors = mapped[:, 2]
    if not np.isfinite(mapped).all() or np.any(np.abs(divisors) <= 1e-12):
        raise _rectification_error()
    result = mapped[:, :2] / divisors[:, np.newaxis]
    if not np.isfinite(result).all():
        raise _rectification_error()
    return result


def _normalize_matrix(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise _rectification_error()
    divisor = float(matrix[2, 2])
    if abs(divisor) <= 1e-12:
        norm = float(np.linalg.norm(matrix))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise _rectification_error()
        normalized = matrix / norm
    else:
        normalized = matrix / divisor
    if not np.isfinite(normalized).all():
        raise _rectification_error()
    return normalized


def _as_matrix_tuple(matrix: NDArray[np.float64]) -> Matrix3x3:
    return (
        (float(matrix[0, 0]), float(matrix[0, 1]), float(matrix[0, 2])),
        (float(matrix[1, 0]), float(matrix[1, 1]), float(matrix[1, 2])),
        (float(matrix[2, 0]), float(matrix[2, 1]), float(matrix[2, 2])),
    )


def _rectification_error() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="RECTIFICATION_INVALID",
        message="The required measurement plane could not be rectified safely.",
        recoverable=True,
        suggested_action="Retake the image using the qualified rig and complete reference plane.",
    )


def _rectification_limit_error() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="RECTIFICATION_LIMIT_EXCEEDED",
        message="The rectified measurement plane exceeds safe processing limits.",
        recoverable=True,
        suggested_action="Retake the image closer to the qualified rig measurement area.",
    )


def _physical_extent_error() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="PHYSICAL_EXTENT_EXCEEDED",
        message="The calibrated image extent is outside the supported physical range.",
        recoverable=True,
        suggested_action="Retake the image with the complete qualified rig plane visible.",
    )
