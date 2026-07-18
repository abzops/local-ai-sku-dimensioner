"""Explicit deterministic product-component and contour selection."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.errors import ApplicationError
from backend.app.vision.foreground import ForegroundResult
from backend.app.vision.full_plane import GeometryPolicy


@dataclass(frozen=True, slots=True)
class ProductContourResult:
    """One uniquely selected product contour with auditable candidate evidence."""

    foreground: ForegroundResult
    mask: NDArray[np.uint8]
    contour_px: NDArray[np.float64]
    component_count: int
    scored_candidate_count: int
    selected_score: float
    runner_up_score: float | None
    strong_core_coverage: float
    mask_stability: float
    marker_clearance_mm: float
    border_clearance_mm: float
    contour_area_mm2: float
    hull_area_mm2: float
    solidity: float
    extent: float
    centroid_px: tuple[float, float]


@dataclass(frozen=True, slots=True)
class _Candidate:
    label: int
    mask: NDArray[np.uint8]
    contour: NDArray[np.int32]
    score: float
    strong_core_coverage: float
    mask_stability: float
    marker_clearance_mm: float
    border_clearance_mm: float
    contour_area_mm2: float
    hull_area_mm2: float
    solidity: float
    extent: float
    centroid_px: tuple[float, float]


def select_product_contour(
    foreground: ForegroundResult,
    policy: GeometryPolicy,
) -> ProductContourResult:
    """Select by hard gates and explicit score, never by area alone."""
    mask = np.where(foreground.mask > 0, 1, 0).astype(np.uint8)
    if mask.shape != foreground.plane.image_bgr.shape[:2] or mask.size == 0:
        raise ValueError("Foreground mask dimensions are invalid")
    label_count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    component_count = max(0, int(label_count) - 1)
    if component_count > policy.maximum_connected_components:
        raise _contour_error(
            foreground,
            "MULTIPLE_OBJECTS_DETECTED",
            "The view contains too many foreground components.",
            "Clear the rig plane and retake the view with only one product.",
        )

    pixels_per_mm = foreground.plane.pixels_per_mm
    valid_area_mm2 = float(np.count_nonzero(foreground.plane.valid_mask)) / (
        pixels_per_mm**2
    )
    minimum_area = max(
        policy.minimum_candidate_area_mm2,
        valid_area_mm2 * policy.minimum_candidate_area_fraction,
    )
    maximum_area = valid_area_mm2 * policy.maximum_candidate_area_fraction
    candidates: list[_Candidate] = []
    saw_large_border_component = False
    saw_marker_contact = False

    for label in range(1, label_count):
        pixel_area = int(stats[label, cv2.CC_STAT_AREA])
        component_area_mm2 = pixel_area / (pixels_per_mm**2)
        if component_area_mm2 < minimum_area or component_area_mm2 > maximum_area:
            continue
        component = np.where(labels == label, 255, 0).astype(np.uint8)
        contours, _hierarchy = cv2.findContours(
            component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        if len(contours) != 1 or len(contours[0]) < 4:
            continue
        contour = np.asarray(contours[0], dtype=np.int32)
        contour_area_px = float(cv2.contourArea(contour))
        hull = cv2.convexHull(contour)
        hull_area_px = float(cv2.contourArea(hull))
        if contour_area_px <= 0.0 or hull_area_px <= 0.0:
            continue
        contour_area_mm2 = contour_area_px / (pixels_per_mm**2)
        hull_area_mm2 = hull_area_px / (pixels_per_mm**2)
        solidity = contour_area_px / hull_area_px
        x, y, width, height = cv2.boundingRect(contour)
        rectangle_area = float(width * height)
        extent = contour_area_px / rectangle_area if rectangle_area > 0.0 else 0.0
        border_clearance = _border_clearance_mm(
            contour,
            foreground.plane.valid_mask,
            pixels_per_mm,
        )
        marker_clearance = _marker_clearance_mm(
            contour,
            foreground.marker_guard_mask,
            pixels_per_mm,
            policy.marker_clearance_mm,
        )
        if border_clearance < policy.border_clearance_mm:
            saw_large_border_component = True
            continue
        if marker_clearance <= policy.marker_clearance_mm:
            saw_marker_contact = True
            continue
        if solidity < policy.minimum_solidity or extent < policy.minimum_extent:
            continue

        strong_coverage = _coverage(component, foreground.strong_core_mask)
        stability = _mask_stability(component, foreground)
        centroid = (float(centroids[label][0]), float(centroids[label][1]))
        expected_region_score = _expected_region_score(
            centroid, foreground.mask.shape[1], foreground.mask.shape[0]
        )
        solidity_score = _normalized_gate_score(solidity, policy.minimum_solidity)
        extent_score = _normalized_gate_score(extent, policy.minimum_extent)
        clearance_score = min(
            1.0,
            min(border_clearance, marker_clearance)
            / max(1.0, 3.0 * max(policy.border_clearance_mm, policy.marker_clearance_mm)),
        )
        score = _finite_score(
            (0.30 * stability)
            + (0.20 * strong_coverage)
            + (0.15 * solidity_score)
            + (0.10 * extent_score)
            + (0.15 * expected_region_score)
            + (0.10 * clearance_score)
        )
        candidates.append(
            _Candidate(
                label=label,
                mask=component,
                contour=contour,
                score=score,
                strong_core_coverage=strong_coverage,
                mask_stability=stability,
                marker_clearance_mm=marker_clearance,
                border_clearance_mm=border_clearance,
                contour_area_mm2=contour_area_mm2,
                hull_area_mm2=hull_area_mm2,
                solidity=solidity,
                extent=extent,
                centroid_px=centroid,
            )
        )

    if len(candidates) > policy.maximum_scored_candidates:
        raise _contour_error(
            foreground,
            "MULTIPLE_OBJECTS_DETECTED",
            "The view contains too many plausible product regions.",
            "Clear the rig plane and retake the view with only one product.",
        )
    if not candidates:
        if saw_marker_contact:
            raise _contour_error(
                foreground,
                "PRODUCT_MARKER_TOO_CLOSE",
                "The product foreground is too close to the reference marker.",
                "Separate the product from the marker and retake the view.",
            )
        if saw_large_border_component:
            raise _contour_error(
                foreground,
                "PRODUCT_CROPPED",
                "The product foreground touches the valid image boundary.",
                "Retake the view with clear space around the complete product.",
            )
        raise _contour_error(
            foreground,
            "PRODUCT_NOT_DETECTED",
            "No foreground region satisfies the product-selection rules.",
            "Retake the view with one opaque product on the qualified matte background.",
        )

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            -candidate.strong_core_coverage,
            -candidate.mask_stability,
            candidate.label,
        ),
    )
    selected = ranked[0]
    runner_score = ranked[1].score if len(ranked) > 1 else None
    if selected.score < policy.minimum_candidate_score:
        raise _contour_error(
            foreground,
            "PRODUCT_NOT_DETECTED",
            "The best foreground region has insufficient deterministic evidence.",
            "Improve contrast and lighting, then retake the view.",
        )
    if (
        runner_score is not None
        and selected.score - runner_score < policy.minimum_candidate_score_margin
    ):
        raise _contour_error(
            foreground,
            "MULTIPLE_OBJECTS_DETECTED",
            "More than one foreground region could be the product.",
            "Clear the rig plane and retake the view with only one product.",
        )

    contour_float = np.asarray(selected.contour, dtype=np.float64)
    if contour_float.ndim != 3 or contour_float.shape[1:] != (1, 2):
        raise _contour_error(
            foreground,
            "PRODUCT_CONTOUR_INVALID",
            "The selected product contour is invalid.",
            "Retake the view with a clearer product silhouette.",
        )
    selected_foreground = replace(
        foreground,
        reflection_fraction=_selected_reflection_fraction(
            foreground.plane.image_bgr,
            selected.mask,
        ),
    )
    return ProductContourResult(
        foreground=selected_foreground,
        mask=selected.mask.copy(),
        contour_px=contour_float.copy(),
        component_count=component_count,
        scored_candidate_count=len(candidates),
        selected_score=selected.score,
        runner_up_score=runner_score,
        strong_core_coverage=selected.strong_core_coverage,
        mask_stability=selected.mask_stability,
        marker_clearance_mm=selected.marker_clearance_mm,
        border_clearance_mm=selected.border_clearance_mm,
        contour_area_mm2=selected.contour_area_mm2,
        hull_area_mm2=selected.hull_area_mm2,
        solidity=selected.solidity,
        extent=selected.extent,
        centroid_px=selected.centroid_px,
    )


def _selected_reflection_fraction(
    image_bgr: NDArray[np.uint8],
    product_mask: NDArray[np.uint8],
) -> float:
    selector = product_mask > 0
    area = int(np.count_nonzero(selector))
    if area <= 0:
        return 0.0
    maximum_channel = np.max(image_bgr, axis=2)
    minimum_channel = np.min(image_bgr, axis=2)
    clipped_neutral = (maximum_channel >= 250) & (
        (maximum_channel - minimum_channel) <= 12
    )
    return float(np.count_nonzero(clipped_neutral & selector)) / area


def _coverage(component: NDArray[np.uint8], support: NDArray[np.uint8]) -> float:
    area = int(np.count_nonzero(component))
    if area <= 0:
        return 0.0
    return _finite_score(
        float(np.count_nonzero((component > 0) & (support > 0))) / area
    )


def _mask_stability(component: NDArray[np.uint8], foreground: ForegroundResult) -> float:
    component_bool = component > 0
    values: list[float] = []
    for signal in foreground.signal_masks:
        signal_bool = signal.mask > 0
        union = int(np.count_nonzero(component_bool | signal_bool))
        if union == 0:
            continue
        intersection = int(np.count_nonzero(component_bool & signal_bool))
        values.append(intersection / union)
    if not values:
        return 0.0
    values.sort(reverse=True)
    strongest = values[: min(3, len(values))]
    return _finite_score(float(np.mean(strongest)))


def _border_clearance_mm(
    contour: NDArray[np.int32], valid_mask: NDArray[np.uint8], pixels_per_mm: float
) -> float:
    points = contour.reshape(-1, 2)
    height, width = valid_mask.shape
    image_clearance = float(
        np.min(
            np.column_stack(
                (
                    points[:, 0],
                    points[:, 1],
                    (width - 1) - points[:, 0],
                    (height - 1) - points[:, 1],
                )
            )
        )
    )
    if np.any(valid_mask == 0):
        distance = cv2.distanceTransform(
            (valid_mask > 0).astype(np.uint8), cv2.DIST_L2, 5
        )
        valid_clearance = float(np.min(distance[points[:, 1], points[:, 0]]))
        image_clearance = min(image_clearance, valid_clearance)
    return max(0.0, image_clearance / pixels_per_mm)


def _marker_clearance_mm(
    contour: NDArray[np.int32],
    marker_guard_mask: NDArray[np.uint8],
    pixels_per_mm: float,
    guard_margin_mm: float,
) -> float:
    points = contour.reshape(-1, 2)
    outside = (marker_guard_mask == 0).astype(np.uint8)
    distance = cv2.distanceTransform(outside, cv2.DIST_L2, 5)
    clearance_from_guard = float(np.min(distance[points[:, 1], points[:, 0]]))
    if clearance_from_guard <= 1.5:
        return guard_margin_mm
    return guard_margin_mm + (clearance_from_guard / pixels_per_mm)


def _expected_region_score(
    centroid: tuple[float, float], width: int, height: int
) -> float:
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    distance = math.hypot(centroid[0] - center_x, centroid[1] - center_y)
    maximum = max(1.0, math.hypot(center_x, center_y))
    return _finite_score(1.0 - (distance / maximum))


def _normalized_gate_score(value: float, minimum: float) -> float:
    denominator = max(1e-9, 1.0 - minimum)
    return _finite_score((value - minimum) / denominator)


def _finite_score(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))


def _contour_error(
    foreground: ForegroundResult,
    code: str,
    message: str,
    suggested_action: str,
) -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code=code,
        message=message,
        recoverable=True,
        suggested_action=suggested_action,
        field=foreground.view.value,
        view=foreground.view,
    )
