"""Independent image-edge evidence for fitted marker borders."""

from __future__ import annotations

import math
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.calibration_contracts import EdgeValues, MarkerEdgeQuality
from backend.app.vision.marker_detection import reference_error

SAMPLES_PER_EDGE: Final[int] = 16
MIN_SAMPLES_PER_EDGE: Final[int] = 8
MIN_GRADIENT_MAGNITUDE: Final[float] = 10.0
QUALITY_DESCRIPTION: Final[str] = (
    "Sampled marker-border localization residual in image pixels."
)


def calculate_marker_edge_quality(
    image_bgr: NDArray[np.uint8],
    corners: NDArray[np.float64],
    threshold_px: float,
) -> MarkerEdgeQuality:
    """Sample local gradients independently of the detector's fitted corners."""
    grayscale = _as_grayscale_float(image_bgr)
    gradient_x = cv2.Sobel(grayscale, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(grayscale, cv2.CV_32F, 0, 1, ksize=3)
    gradient_magnitude = np.asarray(
        cv2.magnitude(gradient_x, gradient_y), dtype=np.float32
    )

    edge_names = ("top", "right", "bottom", "left")
    edge_residuals: dict[str, list[float]] = {}
    minimum_edge = min(
        float(np.linalg.norm(corners[(index + 1) % 4] - corners[index]))
        for index in range(4)
    )
    search_radius = min(8.0, max(2.0, minimum_edge * 0.08))
    offsets = np.linspace(-search_radius, search_radius, num=65, dtype=np.float64)

    for index, edge_name in enumerate(edge_names):
        start = corners[index]
        end = corners[(index + 1) % 4]
        edge_vector = end - start
        edge_length = float(np.linalg.norm(edge_vector))
        if not math.isfinite(edge_length) or edge_length <= 0.0:
            raise _insufficient_evidence_error()
        normal = np.asarray([-edge_vector[1], edge_vector[0]], dtype=np.float64)
        normal /= edge_length
        residuals: list[float] = []
        for fraction in np.linspace(0.1, 0.9, num=SAMPLES_PER_EDGE):
            fitted_point = start + (float(fraction) * edge_vector)
            candidates = fitted_point + offsets[:, np.newaxis] * normal
            samples = _bilinear_samples(gradient_magnitude, candidates)
            if samples is None:
                continue
            best_index = int(np.argmax(samples))
            if float(samples[best_index]) < MIN_GRADIENT_MAGNITUDE:
                continue
            residuals.append(abs(float(offsets[best_index])))
        if len(residuals) < MIN_SAMPLES_PER_EDGE:
            raise _insufficient_evidence_error()
        edge_residuals[edge_name] = residuals

    all_residuals = [
        residual
        for edge_name in edge_names
        for residual in edge_residuals[edge_name]
    ]
    per_edge = {
        edge_name: _rms(edge_residuals[edge_name]) for edge_name in edge_names
    }
    rms_px = _rms(all_residuals)
    maximum_px = max(all_residuals)
    valid = (
        math.isfinite(threshold_px)
        and threshold_px > 0.0
        and maximum_px <= threshold_px
    )
    return MarkerEdgeQuality(
        metric_name="marker_edge_localization_residual",
        description=QUALITY_DESCRIPTION,
        rms_px=rms_px,
        maximum_px=maximum_px,
        sample_count=len(all_residuals),
        per_edge_rms_px=EdgeValues(
            top=per_edge["top"],
            right=per_edge["right"],
            bottom=per_edge["bottom"],
            left=per_edge["left"],
        ),
        threshold_px=threshold_px,
        valid=valid,
    )


def require_valid_marker_edge_quality(quality: MarkerEdgeQuality) -> None:
    """Reject evidence beyond the configured limit rather than marking it valid."""
    if not quality.valid:
        raise reference_error(
            code="REFERENCE_EDGE_RESIDUAL_EXCESSIVE",
            message="The marker border localization residual exceeds the allowed limit.",
            suggested_action="Retake a sharper image with less blur, glare, or perspective.",
        )


def _as_grayscale_float(image_bgr: NDArray[np.uint8]) -> NDArray[np.float32]:
    if image_bgr.dtype != np.uint8 or image_bgr.size == 0:
        raise _insufficient_evidence_error()
    if image_bgr.ndim == 2:
        return image_bgr.astype(np.float32)
    if image_bgr.ndim == 3 and image_bgr.shape[2] == 3:
        return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    raise _insufficient_evidence_error()


def _bilinear_samples(
    image: NDArray[np.float32], points: NDArray[np.float64]
) -> NDArray[np.float64] | None:
    height, width = image.shape
    x = points[:, 0]
    y = points[:, 1]
    if (
        np.any(x < 0.0)
        or np.any(y < 0.0)
        or np.any(x >= width - 1.0)
        or np.any(y >= height - 1.0)
    ):
        return None
    x0 = np.floor(x).astype(np.intp)
    y0 = np.floor(y).astype(np.intp)
    x1 = x0 + 1
    y1 = y0 + 1
    x_weight = x - x0
    y_weight = y - y0
    top = (1.0 - x_weight) * image[y0, x0] + x_weight * image[y0, x1]
    bottom = (1.0 - x_weight) * image[y1, x0] + x_weight * image[y1, x1]
    return np.asarray((1.0 - y_weight) * top + y_weight * bottom, dtype=np.float64)


def _rms(values: list[float]) -> float:
    if not values:
        raise _insufficient_evidence_error()
    result = math.sqrt(sum(value * value for value in values) / len(values))
    if not math.isfinite(result):
        raise _insufficient_evidence_error()
    return result


def _insufficient_evidence_error() -> Exception:
    return reference_error(
        code="REFERENCE_EDGE_EVIDENCE_INSUFFICIENT",
        message="The marker borders do not provide enough independent image evidence.",
        suggested_action="Retake a sharp, well-lit image with the complete marker visible.",
    )

