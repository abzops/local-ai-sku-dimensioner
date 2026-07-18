"""Deterministic multi-signal foreground extraction for a qualified rig plane."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.full_plane import GeometryPolicy, RectifiedPlane


@dataclass(frozen=True, slots=True)
class SignalMask:
    """One independently derived foreground support mask."""

    name: str
    mask: NDArray[np.uint8]
    independent: bool = True


@dataclass(frozen=True, slots=True)
class ForegroundResult:
    """Owned masks and background evidence before product-candidate selection."""

    plane: RectifiedPlane
    view: ImageView
    mask: NDArray[np.uint8]
    strong_core_mask: NDArray[np.uint8]
    marker_guard_mask: NDArray[np.uint8]
    signal_masks: tuple[SignalMask, ...]
    background_lab_median: tuple[float, float, float]
    background_lab_mad: tuple[float, float, float]
    grayscale_background_median: float
    grayscale_foreground_difference: float
    supported_signal_names: tuple[str, ...]
    component_count: int
    shadow_fraction: float
    reflection_fraction: float


def extract_foreground(
    rectified_plane: RectifiedPlane,
    marker_polygon: NDArray[np.float64],
    view: ImageView,
    policy: GeometryPolicy,
) -> ForegroundResult:
    """Extract an inspectable consensus mask without AI or client geometry."""
    image = _validate_plane(rectified_plane)
    height, width = image.shape[:2]
    valid = np.where(rectified_plane.valid_mask > 0, 255, 0).astype(np.uint8)
    marker_guard = _marker_guard(
        marker_polygon,
        (height, width),
        rectified_plane.pixels_per_mm,
        policy.marker_clearance_mm,
    )
    usable = np.asarray(
        cv2.bitwise_and(valid, cv2.bitwise_not(marker_guard)), dtype=np.uint8
    )
    blurred = np.asarray(cv2.GaussianBlur(image, (5, 5), 0), dtype=np.uint8)
    lab = np.asarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB), dtype=np.uint8)
    gray = np.asarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
    background_sample = _background_sample_mask(usable, lab)
    if int(np.count_nonzero(background_sample)) < 100:
        raise _foreground_error(
            view,
            "BACKGROUND_INCONSISTENT",
            "The qualified rig background could not be sampled reliably.",
            "Retake the image with the complete matte rig background visible.",
        )

    sample_selector = background_sample > 0
    sample_lab = lab[sample_selector].astype(np.float64)
    lab_median_array = np.median(sample_lab, axis=0)
    lab_distances = np.linalg.norm(sample_lab - lab_median_array, axis=1)
    lab_mad_array = np.median(np.abs(sample_lab - lab_median_array), axis=0)
    lab_distance_mad = float(
        np.median(np.abs(lab_distances - np.median(lab_distances)))
    )
    if (
        not np.isfinite(lab_mad_array).all()
        or float(np.max(lab_mad_array)) > policy.background_lab_mad_maximum
    ):
        raise _foreground_error(
            view,
            "BACKGROUND_INCONSISTENT",
            "The qualified rig background is too uneven for deterministic extraction.",
            "Use a clean matte background with diffuse, even lighting.",
        )

    sample_gray = gray[sample_selector].astype(np.float64)
    gray_median = float(np.median(sample_gray))
    gray_mad = float(np.median(np.abs(sample_gray - gray_median)))
    lab_distance_image = np.linalg.norm(
        lab.astype(np.float64) - lab_median_array.reshape((1, 1, 3)), axis=2
    )
    gray_difference_image = np.abs(gray.astype(np.float64) - gray_median)
    lab_threshold = max(
        policy.minimum_lab_difference,
        float(np.median(lab_distances)) + (4.0 * max(lab_distance_mad, 0.5)),
    )
    gray_threshold = max(
        policy.minimum_grayscale_difference,
        float(np.median(np.abs(sample_gray - gray_median))) + (4.0 * max(gray_mad, 0.5)),
    )

    color_mask = _binary(lab_distance_image >= lab_threshold, usable)
    grayscale_mask = _binary(gray_difference_image >= gray_threshold, usable)
    edge_mask = _edge_region_mask(gray, usable, policy, rectified_plane.pixels_per_mm)
    adaptive_mask = _adaptive_support(gray, usable, color_mask, grayscale_mask, edge_mask)
    signals = (
        SignalMask("background_color_difference", color_mask),
        SignalMask("grayscale_difference", grayscale_mask),
        SignalMask("adaptive_threshold", adaptive_mask, independent=False),
        SignalMask("edge_detection", edge_mask),
    )
    support_count = np.zeros((height, width), dtype=np.uint8)
    for signal in signals:
        if signal.independent:
            support_count += (signal.mask > 0).astype(np.uint8)

    strong_core = _binary(support_count >= 2, usable)
    if int(np.count_nonzero(strong_core)) == 0:
        raise _foreground_error(
            view,
            "FOREGROUND_LOW_CONTRAST",
            "The product does not have enough deterministic contrast from the rig background.",
            "Use a matte contrasting background and diffuse lighting, then recapture the view.",
        )

    inclusive = _binary(support_count >= 1, usable)
    expansion_radius = _kernel_radius(2.0, rectified_plane.pixels_per_mm)
    expanded_core = cv2.dilate(
        strong_core,
        _elliptical_kernel(expansion_radius),
        iterations=1,
    )
    candidate = np.asarray(
        cv2.bitwise_and(inclusive, expanded_core), dtype=np.uint8
    )

    shadow_mask = _shadow_mask(
        lab,
        lab_median_array,
        usable,
        policy.minimum_grayscale_difference,
    )
    pre_shadow_candidate = candidate.copy()
    pre_shadow_area = max(1, int(np.count_nonzero(pre_shadow_candidate)))
    removed_shadow_fraction = float(
        np.count_nonzero((shadow_mask > 0) & (pre_shadow_candidate > 0))
    ) / pre_shadow_area
    candidate = np.asarray(
        cv2.bitwise_and(candidate, cv2.bitwise_not(shadow_mask)), dtype=np.uint8
    )
    candidate = _apply_morphology(candidate, rectified_plane.pixels_per_mm, policy)
    candidate = np.asarray(cv2.bitwise_and(candidate, usable), dtype=np.uint8)
    candidate[marker_guard > 0] = 0
    candidate = _remove_small_components(
        candidate,
        max(
            4,
            int(round(policy.minimum_candidate_area_mm2 * rectified_plane.pixels_per_mm**2)),
        ),
    )

    component_count, _labels = cv2.connectedComponents(
        (candidate > 0).astype(np.uint8), connectivity=8
    )
    foreground_components = max(0, int(component_count) - 1)
    if foreground_components > policy.maximum_connected_components:
        raise _foreground_error(
            view,
            "MULTIPLE_OBJECTS_DETECTED",
            "The view contains too many foreground regions to select a product safely.",
            "Clear the rig surface and retake the image with only one product.",
        )
    if int(np.count_nonzero(candidate)) == 0:
        raise _foreground_error(
            view,
            "PRODUCT_NOT_DETECTED",
            "No stable product foreground was detected.",
            "Retake the image with the product fully visible on a contrasting matte background.",
        )

    foreground_selector = candidate > 0
    grayscale_difference = float(np.median(gray_difference_image[foreground_selector]))
    if not math.isfinite(grayscale_difference):
        raise _foreground_error(
            view,
            "FOREGROUND_LOW_CONTRAST",
            "The product contrast evidence is invalid.",
            "Retake the image with diffuse lighting and a contrasting background.",
        )
    reflection_mask = _reflection_mask(image, candidate)
    area = max(1, int(np.count_nonzero(candidate)))
    shadow_fraction = removed_shadow_fraction
    reflection_fraction = float(np.count_nonzero(reflection_mask)) / area
    supported_names = tuple(
        signal.name for signal in signals if int(np.count_nonzero(signal.mask)) > 0
    )

    return ForegroundResult(
        plane=rectified_plane,
        view=view,
        mask=np.asarray(candidate, dtype=np.uint8).copy(),
        strong_core_mask=np.asarray(strong_core, dtype=np.uint8).copy(),
        marker_guard_mask=marker_guard.copy(),
        signal_masks=tuple(
            SignalMask(signal.name, signal.mask.copy(), signal.independent)
            for signal in signals
        ),
        background_lab_median=(
            float(lab_median_array[0]),
            float(lab_median_array[1]),
            float(lab_median_array[2]),
        ),
        background_lab_mad=(
            float(lab_mad_array[0]),
            float(lab_mad_array[1]),
            float(lab_mad_array[2]),
        ),
        grayscale_background_median=gray_median,
        grayscale_foreground_difference=grayscale_difference,
        supported_signal_names=supported_names,
        component_count=foreground_components,
        shadow_fraction=shadow_fraction,
        reflection_fraction=reflection_fraction,
    )


def _validate_plane(plane: RectifiedPlane) -> NDArray[np.uint8]:
    image = np.asarray(plane.image_bgr)
    mask = np.asarray(plane.valid_mask)
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or mask.dtype != np.uint8
        or mask.shape != image.shape[:2]
        or not math.isfinite(plane.pixels_per_mm)
        or plane.pixels_per_mm <= 0.0
    ):
        raise ValueError("Rectified plane arrays are invalid")
    return image


def _marker_guard(
    polygon: NDArray[np.float64],
    shape: tuple[int, int],
    pixels_per_mm: float,
    clearance_mm: float,
) -> NDArray[np.uint8]:
    points = np.asarray(polygon, dtype=np.float64)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError("Marker polygon must be a finite 4 by 2 array")
    guard = np.zeros(shape, dtype=np.uint8)
    cv2.fillConvexPoly(guard, np.rint(points).astype(np.int32), 255)
    radius = _kernel_radius(clearance_mm, pixels_per_mm)
    if radius > 0:
        guard = np.asarray(
            cv2.dilate(guard, _elliptical_kernel(radius), iterations=1),
            dtype=np.uint8,
        )
    return np.asarray(guard, dtype=np.uint8)


def _background_sample_mask(
    usable: NDArray[np.uint8], lab: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    """Select the dominant matte rig colour, not a warp/letterbox border."""
    selector = usable > 0
    samples = lab[selector]
    if samples.size == 0:
        return np.zeros_like(usable)
    quantized = samples.astype(np.int32) // 8
    codes = (quantized[:, 0] * 1024) + (quantized[:, 1] * 32) + quantized[:, 2]
    counts = np.bincount(codes, minlength=32 * 32 * 32)
    dominant_code = int(np.argmax(counts))
    dominant = np.asarray(
        [
            ((dominant_code // 1024) * 8) + 3.5,
            (((dominant_code // 32) % 32) * 8) + 3.5,
            ((dominant_code % 32) * 8) + 3.5,
        ],
        dtype=np.float64,
    )
    distance = np.linalg.norm(lab.astype(np.float64) - dominant, axis=2)
    return np.where((distance <= 12.0) & selector, 255, 0).astype(np.uint8)


def _binary(condition: NDArray[np.bool_], usable: NDArray[np.uint8]) -> NDArray[np.uint8]:
    mask = np.where(condition, 255, 0).astype(np.uint8)
    return np.asarray(cv2.bitwise_and(mask, usable), dtype=np.uint8)


def _edge_region_mask(
    gray: NDArray[np.uint8],
    usable: NDArray[np.uint8],
    policy: GeometryPolicy,
    pixels_per_mm: float,
) -> NDArray[np.uint8]:
    valid_values = gray[usable > 0]
    median = float(np.median(valid_values)) if valid_values.size else 128.0
    low = int(max(0.0, 0.66 * median))
    high = int(min(255.0, max(float(low + 1), 1.33 * median)))
    edges = cv2.Canny(gray, low, high)
    close_radius = max(1, _kernel_radius(policy.morphology_close_mm, pixels_per_mm))
    closed = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        _elliptical_kernel(close_radius),
        iterations=1,
    )
    contours, _hierarchy = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    filled = np.zeros_like(gray)
    minimum_area_px = max(4.0, policy.minimum_candidate_area_mm2 * pixels_per_mm**2)
    for contour in contours:
        if cv2.contourArea(contour) >= minimum_area_px:
            cv2.drawContours(filled, [contour], -1, 255, thickness=cv2.FILLED)
    return np.asarray(cv2.bitwise_and(filled, usable), dtype=np.uint8)


def _adaptive_support(
    gray: NDArray[np.uint8],
    usable: NDArray[np.uint8],
    color_mask: NDArray[np.uint8],
    grayscale_mask: NDArray[np.uint8],
    edge_mask: NDArray[np.uint8],
) -> NDArray[np.uint8]:
    minimum_edge = min(gray.shape)
    block_size = min(51, max(11, ((minimum_edge // 16) | 1)))
    if block_size % 2 == 0:
        block_size += 1
    dark = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        5,
    )
    light = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        -5,
    )
    independent_support = cv2.bitwise_or(
        cv2.bitwise_or(color_mask, grayscale_mask), edge_mask
    )
    adaptive = cv2.bitwise_or(dark, light)
    return np.asarray(
        cv2.bitwise_and(cv2.bitwise_and(adaptive, independent_support), usable),
        dtype=np.uint8,
    )


def _shadow_mask(
    lab: NDArray[np.uint8],
    background_lab: NDArray[np.float64],
    usable: NDArray[np.uint8],
    minimum_luminance_difference: float,
) -> NDArray[np.uint8]:
    lab_float = lab.astype(np.float64)
    luminance_drop = background_lab[0] - lab_float[:, :, 0]
    chroma_difference = np.linalg.norm(
        lab_float[:, :, 1:3] - background_lab[1:3].reshape((1, 1, 2)), axis=2
    )
    luminance_edges = cv2.Canny(lab[:, :, 0], 40, 100)
    shadow_only = (
        (luminance_drop >= max(8.0, minimum_luminance_difference * 0.5))
        & (chroma_difference <= 8.0)
        & (luminance_edges == 0)
        & (usable > 0)
    )
    return np.where(shadow_only, 255, 0).astype(np.uint8)


def _reflection_mask(
    image_bgr: NDArray[np.uint8], candidate: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    maximum_channel = np.max(image_bgr, axis=2)
    minimum_channel = np.min(image_bgr, axis=2)
    clipped_neutral = (maximum_channel >= 250) & ((maximum_channel - minimum_channel) <= 12)
    return np.where(clipped_neutral & (candidate > 0), 255, 0).astype(np.uint8)


def _apply_morphology(
    mask: NDArray[np.uint8], pixels_per_mm: float, policy: GeometryPolicy
) -> NDArray[np.uint8]:
    opened = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        _elliptical_kernel(_kernel_radius(policy.morphology_open_mm, pixels_per_mm)),
        iterations=1,
    )
    return np.asarray(
        cv2.morphologyEx(
            opened,
            cv2.MORPH_CLOSE,
            _elliptical_kernel(_kernel_radius(policy.morphology_close_mm, pixels_per_mm)),
            iterations=1,
        ),
        dtype=np.uint8,
    )


def _remove_small_components(
    mask: NDArray[np.uint8], minimum_area_px: int
) -> NDArray[np.uint8]:
    label_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8
    )
    cleaned = np.zeros_like(mask)
    for label in range(1, label_count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= minimum_area_px:
            cleaned[labels == label] = 255
    return cleaned


def _kernel_radius(millimetres: float, pixels_per_mm: float) -> int:
    return min(31, max(0, int(round(millimetres * pixels_per_mm))))


def _elliptical_kernel(radius: int) -> NDArray[np.uint8]:
    safe_radius = max(0, radius)
    edge = (2 * safe_radius) + 1
    return np.asarray(
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (edge, edge)), dtype=np.uint8
    )


def _foreground_error(
    view: ImageView,
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
        field=view.value,
        view=view,
    )
