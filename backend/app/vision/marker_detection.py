"""Safe ArUco detection and canonical corner validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import MarkerProfileSpec
from backend.app.errors import ApplicationError
from backend.app.vision.aruco_dictionaries import get_aruco_dictionary


@dataclass(frozen=True, slots=True)
class DetectedMarker:
    """One configured marker with OpenCV's canonical printed-marker corners."""

    marker_id: int
    corners: NDArray[np.float64]


def detect_expected_marker(
    image_bgr: NDArray[np.uint8],
    profile: MarkerProfileSpec,
) -> DetectedMarker:
    """Detect exactly one expected marker and reject every ambiguous scene."""
    grayscale = _as_grayscale(image_bgr)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = 5
    parameters.cornerRefinementMaxIterations = 30
    parameters.cornerRefinementMinAccuracy = 0.01
    detector = cv2.aruco.ArucoDetector(
        get_aruco_dictionary(profile.dictionary), parameters
    )
    try:
        detected_corners, detected_ids, _rejected = detector.detectMarkers(grayscale)
    except cv2.error as error:
        raise reference_error(
            code="REFERENCE_NOT_DETECTED",
            message="The configured reference marker could not be detected.",
            suggested_action="Retake the image with the complete marker clearly visible.",
        ) from error

    if detected_ids is None or len(detected_corners) == 0:
        raise reference_error(
            code="REFERENCE_NOT_DETECTED",
            message="The configured reference marker was not detected.",
            suggested_action="Retake the image with the complete marker clearly visible.",
        )

    ids = [int(marker_id) for marker_id in detected_ids.reshape(-1)]
    expected_indexes = [
        index for index, marker_id in enumerate(ids) if marker_id == profile.marker_id
    ]
    if not expected_indexes:
        raise reference_error(
            code="REFERENCE_WRONG_ID",
            message="A marker was detected, but it does not match the calibration profile.",
            suggested_action="Use the marker generated for the selected calibration profile.",
        )
    if len(expected_indexes) != 1 or len(ids) != 1:
        raise reference_error(
            code="REFERENCE_AMBIGUOUS",
            message="The image contains duplicate or additional recognized markers.",
            suggested_action="Retake the image with only one configured marker visible.",
        )

    raw_corners = np.asarray(
        detected_corners[expected_indexes[0]], dtype=np.float64
    ).reshape(4, 2)
    corners = validate_marker_corners(raw_corners, grayscale.shape[1], grayscale.shape[0])
    validate_marker_scale_and_perspective(corners, profile)
    return DetectedMarker(marker_id=profile.marker_id, corners=corners)


def validate_marker_corners(
    corners: NDArray[np.float64],
    image_width_px: int,
    image_height_px: int,
) -> NDArray[np.float64]:
    """Validate detector corners while preserving their canonical order."""
    points = np.asarray(corners, dtype=np.float64)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise _invalid_corners_error()

    for index in range(4):
        for other_index in range(index + 1, 4):
            if float(np.linalg.norm(points[index] - points[other_index])) <= 1e-6:
                raise _invalid_corners_error()

    cross_products: list[float] = []
    for index in range(4):
        first_edge = points[(index + 1) % 4] - points[index]
        second_edge = points[(index + 2) % 4] - points[(index + 1) % 4]
        cross_products.append(
            float((first_edge[0] * second_edge[1]) - (first_edge[1] * second_edge[0]))
        )
    if any(abs(value) <= 1e-8 for value in cross_products) or not (
        all(value > 0 for value in cross_products)
        or all(value < 0 for value in cross_products)
    ):
        raise _invalid_corners_error()

    if (
        image_width_px <= 1
        or image_height_px <= 1
        or np.any(points[:, 0] <= 0.0)
        or np.any(points[:, 1] <= 0.0)
        or np.any(points[:, 0] >= image_width_px - 1.0)
        or np.any(points[:, 1] >= image_height_px - 1.0)
    ):
        raise reference_error(
            code="REFERENCE_CROPPED",
            message="The reference marker touches or crosses the image boundary.",
            suggested_action="Retake the image with clear space around the complete marker.",
        )
    return points


def marker_edge_lengths(corners: NDArray[np.float64]) -> tuple[float, float, float, float]:
    """Return top, right, bottom, and left canonical edge lengths."""
    return tuple(
        float(np.linalg.norm(corners[(index + 1) % 4] - corners[index]))
        for index in range(4)
    )  # type: ignore[return-value]


def validate_marker_scale_and_perspective(
    corners: NDArray[np.float64],
    profile: MarkerProfileSpec,
) -> tuple[tuple[float, float, float, float], float]:
    """Reject markers that are too small or excessively perspective-distorted."""
    edge_lengths = marker_edge_lengths(corners)
    if not all(math.isfinite(length) and length > 0.0 for length in edge_lengths):
        raise _invalid_corners_error()
    minimum_edge = min(edge_lengths)
    maximum_edge = max(edge_lengths)
    if minimum_edge < profile.minimum_marker_side_px:
        raise reference_error(
            code="REFERENCE_TOO_SMALL",
            message="The reference marker is too small in the image.",
            suggested_action="Move closer and retake the image with a larger marker view.",
        )
    perspective_ratio = maximum_edge / minimum_edge
    if (
        not math.isfinite(perspective_ratio)
        or perspective_ratio > profile.maximum_perspective_ratio
    ):
        raise reference_error(
            code="EXCESSIVE_PERSPECTIVE",
            message="The reference marker has excessive perspective distortion.",
            suggested_action="Retake the image with the camera more parallel to the marker.",
        )
    return edge_lengths, perspective_ratio


def _as_grayscale(image: NDArray[np.uint8]) -> NDArray[np.uint8]:
    if image.dtype != np.uint8:
        raise _invalid_corners_error()
    if image.ndim == 2 and image.size:
        return image
    if image.ndim == 3 and image.shape[2] == 3 and image.size:
        return cast(NDArray[np.uint8], cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    raise _invalid_corners_error()


def reference_error(*, code: str, message: str, suggested_action: str) -> ApplicationError:
    """Build a path-free public calibration failure."""
    return ApplicationError(
        status_code=422,
        code=code,
        message=message,
        recoverable=True,
        suggested_action=suggested_action,
        field="image",
    )


def _invalid_corners_error() -> ApplicationError:
    return reference_error(
        code="REFERENCE_CORNERS_INVALID",
        message="The detected reference marker corners are invalid.",
        suggested_action="Retake the image with the complete marker flat and clearly visible.",
    )

