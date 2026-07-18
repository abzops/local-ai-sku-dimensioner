"""Frozen Phase 2 marker-calibration domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, TypeAlias


class ArucoDictionary(StrEnum):
    """The only ArUco dictionaries accepted in Phase 2."""

    DICT_4X4_50 = "DICT_4X4_50"
    DICT_5X5_50 = "DICT_5X5_50"
    DICT_6X6_50 = "DICT_6X6_50"


class CornerLabel(StrEnum):
    """Canonical printed-marker corner labels in detector order."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_LEFT = "bottom_left"


class EdgeName(StrEnum):
    """Canonical printed-marker edge labels."""

    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


APPROVED_ARUCO_DICTIONARIES: Final[tuple[ArucoDictionary, ...]] = tuple(
    ArucoDictionary
)
CORNER_LABEL_ORDER: Final[tuple[CornerLabel, ...]] = tuple(CornerLabel)
EDGE_NAME_ORDER: Final[tuple[EdgeName, ...]] = tuple(EdgeName)
MARKER_ID_MIN: Final[int] = 0
MARKER_ID_MAX: Final[int] = 49
MARKER_BORDER_BITS: Final[int] = 1
MAX_PREVIEW_EDGE_PX: Final[int] = 1280
MAX_RECTIFIED_EDGE_PX: Final[int] = 1800
MAX_PREVIEW_BYTES: Final[int] = 2 * 1024 * 1024

Matrix3x3: TypeAlias = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]
PngMediaType: TypeAlias = Literal["image/png"]


@dataclass(frozen=True, slots=True)
class MarkerProfileSpec:
    """Immutable profile values consumed by deterministic marker primitives."""

    dictionary: ArucoDictionary
    marker_id: int
    marker_size_mm: float
    minimum_marker_side_px: int
    maximum_perspective_ratio: float
    maximum_homography_condition_number: float
    maximum_marker_edge_residual_px: float
    rectified_pixels_per_mm: float
    border_bits: int = MARKER_BORDER_BITS


@dataclass(frozen=True, slots=True)
class OrderedCorner:
    label: CornerLabel
    x_px: float
    y_px: float


@dataclass(frozen=True, slots=True)
class EdgeValues:
    top: float
    right: float
    bottom: float
    left: float


@dataclass(frozen=True, slots=True)
class MarkerEdgeQuality:
    metric_name: Literal["marker_edge_localization_residual"]
    description: str
    rms_px: float
    maximum_px: float
    sample_count: int
    per_edge_rms_px: EdgeValues
    threshold_px: float
    valid: bool


@dataclass(frozen=True, slots=True)
class PreviewImage:
    media_type: PngMediaType
    width_px: int
    height_px: int
    data_base64: str


@dataclass(frozen=True, slots=True)
class MarkerAnalysisResult:
    dictionary: ArucoDictionary
    marker_id: int
    ordered_corners: tuple[OrderedCorner, OrderedCorner, OrderedCorner, OrderedCorner]
    orientation_degrees: float
    edge_lengths_px: EdgeValues
    perspective_ratio: float
    image_to_marker_mm: Matrix3x3
    marker_mm_to_image: Matrix3x3
    homography_condition_number: float
    rectified_width_px: int
    rectified_height_px: int
    rectified_pixels_per_mm: float
    marker_edge_quality: MarkerEdgeQuality
    annotated_preview: PreviewImage
    rectified_preview: PreviewImage
