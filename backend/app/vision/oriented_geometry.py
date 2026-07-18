"""Oriented product geometry and frozen per-view axis mapping."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision.full_plane import GeometryPolicy, rectified_pixels_to_mm
from backend.app.vision.product_contours import ProductContourResult


class DimensionName(StrEnum):
    LENGTH = "length"
    WIDTH = "width"
    HEIGHT = "height"


@dataclass(frozen=True, slots=True)
class AxisMeasurement:
    dimension: DimensionName
    value_mm: float


@dataclass(frozen=True, slots=True)
class AxisVariantSpan:
    dimension: DimensionName
    minimum_mm: float
    maximum_mm: float
    span_mm: float


@dataclass(frozen=True, slots=True)
class ViewGeometryResult:
    """Raw view measurements and canonical oriented bounding evidence."""

    view: ImageView
    raw_dimensions: tuple[AxisMeasurement, AxisMeasurement]
    oriented_box_corners_mm: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]
    oriented_box_corners_px: NDArray[np.float64]
    oriented_box_angle_degrees: float
    axis_misalignment_degrees: float
    variant_spans: tuple[AxisVariantSpan, AxisVariantSpan]
    threshold_variant_span_mm: float
    morphology_variant_span_mm: float
    contour_px: NDArray[np.float64]
    contour_result: ProductContourResult

    def value(self, dimension: DimensionName) -> float:
        for measurement in self.raw_dimensions:
            if measurement.dimension is dimension:
                return measurement.value_mm
        raise KeyError(dimension)

    def span(self, dimension: DimensionName) -> float:
        for evidence in self.variant_spans:
            if evidence.dimension is dimension:
                return evidence.span_mm
        raise KeyError(dimension)


def measure_product_geometry(
    product: ProductContourResult,
    view: ImageView,
    policy: GeometryPolicy,
) -> ViewGeometryResult:
    """Measure the selected contour in marker-plane millimetres."""
    if product.foreground.view is not view:
        raise ValueError("Product contour view does not match the requested view")
    contour_px_points = product.contour_px.reshape(-1, 2)
    contour_mm = rectified_pixels_to_mm(contour_px_points, product.foreground.plane)
    if len(contour_mm) < 4 or not np.isfinite(contour_mm).all():
        raise _geometry_error(
            product,
            "PRODUCT_CONTOUR_INVALID",
            "The product contour cannot be converted into finite plane geometry.",
            "Retake the view with a clear, complete product silhouette.",
        )
    try:
        rectangle = cv2.minAreaRect(contour_mm.astype(np.float32).reshape((-1, 1, 2)))
        raw_box_mm = np.asarray(cv2.boxPoints(rectangle), dtype=np.float64)
    except cv2.error as error:
        raise _geometry_error(
            product,
            "PRODUCT_CONTOUR_INVALID",
            "The product bounding geometry could not be calculated safely.",
            "Retake the view with a clear, complete product silhouette.",
        ) from error
    box_mm = _canonical_box(raw_box_mm)
    assignments, angle, misalignment = _assign_dimensions(box_mm, view)
    if view in (ImageView.FRONT, ImageView.SIDE) and (
        misalignment > policy.maximum_axis_misalignment_degrees
    ):
        raise _geometry_error(
            product,
            "PRODUCT_AXIS_MISALIGNED",
            "The product is not aligned with the qualified rig axes.",
            "Register the product against the rig datums and retake the view.",
        )
    for measurement in assignments:
        if (
            not math.isfinite(measurement.value_mm)
            or measurement.value_mm < policy.minimum_object_mm
            or measurement.value_mm > policy.maximum_object_mm
        ):
            raise _geometry_error(
                product,
                "UNSUPPORTED_PRODUCT_DOMAIN",
                "The measured product extent is outside the qualified rig range.",
                "Use a qualified rig that supports the complete product size.",
            )

    threshold_values: dict[DimensionName, list[float]] = {
        measurement.dimension: [measurement.value_mm] for measurement in assignments
    }
    for signal_contour in _variant_contours(product):
        signal_mm = rectified_pixels_to_mm(
            signal_contour.reshape(-1, 2), product.foreground.plane
        )
        if len(signal_mm) < 4 or not np.isfinite(signal_mm).all():
            continue
        try:
            signal_box = _canonical_box(
                np.asarray(
                    cv2.boxPoints(
                        cv2.minAreaRect(signal_mm.astype(np.float32).reshape((-1, 1, 2)))
                    ),
                    dtype=np.float64,
                )
            )
            variant_assignments, _variant_angle, variant_misalignment = _assign_dimensions(
                signal_box, view
            )
        except (cv2.error, ValueError):
            continue
        if view in (ImageView.FRONT, ImageView.SIDE) and (
            variant_misalignment > policy.maximum_axis_misalignment_degrees * 2.0
        ):
            continue
        for measurement in variant_assignments:
            if math.isfinite(measurement.value_mm) and measurement.value_mm > 0.0:
                threshold_values[measurement.dimension].append(measurement.value_mm)

    morphology_values: dict[DimensionName, list[float]] = {
        measurement.dimension: [measurement.value_mm] for measurement in assignments
    }
    for morphology_contour in _morphology_variant_contours(product, policy):
        morphology_mm = rectified_pixels_to_mm(
            morphology_contour.reshape(-1, 2), product.foreground.plane
        )
        if len(morphology_mm) < 4 or not np.isfinite(morphology_mm).all():
            continue
        try:
            morphology_box = _canonical_box(
                np.asarray(
                    cv2.boxPoints(
                        cv2.minAreaRect(
                            morphology_mm.astype(np.float32).reshape((-1, 1, 2))
                        )
                    ),
                    dtype=np.float64,
                )
            )
            morphology_assignments, _morphology_angle, morphology_misalignment = (
                _assign_dimensions(morphology_box, view)
            )
        except (cv2.error, ValueError):
            continue
        if view in (ImageView.FRONT, ImageView.SIDE) and (
            morphology_misalignment > policy.maximum_axis_misalignment_degrees * 2.0
        ):
            continue
        for measurement in morphology_assignments:
            if math.isfinite(measurement.value_mm) and measurement.value_mm > 0.0:
                morphology_values[measurement.dimension].append(measurement.value_mm)

    threshold_spans = (
        _variant_span(
            assignments[0].dimension,
            threshold_values[assignments[0].dimension],
        ),
        _variant_span(
            assignments[1].dimension,
            threshold_values[assignments[1].dimension],
        ),
    )
    morphology_spans = (
        _variant_span(
            assignments[0].dimension,
            morphology_values[assignments[0].dimension],
        ),
        _variant_span(
            assignments[1].dimension,
            morphology_values[assignments[1].dimension],
        ),
    )
    spans = (
        _merge_spans(threshold_spans[0], morphology_spans[0]),
        _merge_spans(threshold_spans[1], morphology_spans[1]),
    )
    threshold_variant_span = max(span.span_mm for span in threshold_spans)
    morphology_variant_span = max(span.span_mm for span in morphology_spans)
    _reject_unstable_shadow_or_reflection(product, assignments, spans, policy)
    box_px = np.column_stack(
        (
            (box_mm[:, 0] - product.foreground.plane.origin_mm[0])
            * product.foreground.plane.pixels_per_mm,
            (box_mm[:, 1] - product.foreground.plane.origin_mm[1])
            * product.foreground.plane.pixels_per_mm,
        )
    )
    return ViewGeometryResult(
        view=view,
        raw_dimensions=(assignments[0], assignments[1]),
        oriented_box_corners_mm=(
            (float(box_mm[0, 0]), float(box_mm[0, 1])),
            (float(box_mm[1, 0]), float(box_mm[1, 1])),
            (float(box_mm[2, 0]), float(box_mm[2, 1])),
            (float(box_mm[3, 0]), float(box_mm[3, 1])),
        ),
        oriented_box_corners_px=box_px.astype(np.float64),
        oriented_box_angle_degrees=angle,
        axis_misalignment_degrees=misalignment,
        variant_spans=(spans[0], spans[1]),
        threshold_variant_span_mm=threshold_variant_span,
        morphology_variant_span_mm=morphology_variant_span,
        contour_px=product.contour_px.copy(),
        contour_result=product,
    )


def _assign_dimensions(
    box_mm: NDArray[np.float64], view: ImageView
) -> tuple[tuple[AxisMeasurement, AxisMeasurement], float, float]:
    edges = (
        box_mm[1] - box_mm[0],
        box_mm[2] - box_mm[1],
    )
    lengths = tuple(float(np.linalg.norm(edge)) for edge in edges)
    if not all(math.isfinite(length) and length > 0.0 for length in lengths):
        raise ValueError("Oriented box sides must be finite and positive")
    angles = tuple(_normalized_axis_angle(edge) for edge in edges)

    if view is ImageView.TOP:
        long_index = 0 if lengths[0] >= lengths[1] else 1
        short_index = 1 - long_index
        result = (
            AxisMeasurement(DimensionName.LENGTH, lengths[long_index]),
            AxisMeasurement(DimensionName.WIDTH, lengths[short_index]),
        )
        return result, angles[long_index], 0.0

    horizontal_index = (
        0
        if _horizontal_deviation(angles[0]) <= _horizontal_deviation(angles[1])
        else 1
    )
    vertical_index = 1 - horizontal_index
    horizontal_name = (
        DimensionName.WIDTH if view is ImageView.FRONT else DimensionName.LENGTH
    )
    result = (
        AxisMeasurement(horizontal_name, lengths[horizontal_index]),
        AxisMeasurement(DimensionName.HEIGHT, lengths[vertical_index]),
    )
    deviation = max(
        _horizontal_deviation(angles[horizontal_index]),
        _vertical_deviation(angles[vertical_index]),
    )
    return result, angles[horizontal_index], deviation


def _canonical_box(box: NDArray[np.float64]) -> NDArray[np.float64]:
    points = np.asarray(box, dtype=np.float64)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError("Oriented box must be a finite 4 by 2 array")
    center = np.mean(points, axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    signed_area = 0.5 * float(
        np.sum(
            (ordered[:, 0] * np.roll(ordered[:, 1], -1))
            - (ordered[:, 1] * np.roll(ordered[:, 0], -1))
        )
    )
    if signed_area < 0.0:
        ordered = ordered[::-1]
    start = int(np.argmin(ordered[:, 0] + ordered[:, 1]))
    ordered = np.roll(ordered, -start, axis=0)
    if not np.isfinite(ordered).all():
        raise ValueError("Oriented box must be finite")
    return ordered


def _normalized_axis_angle(edge: NDArray[np.float64]) -> float:
    angle = math.degrees(math.atan2(float(edge[1]), float(edge[0])))
    normalized = ((angle + 90.0) % 180.0) - 90.0
    return float(normalized)


def _horizontal_deviation(angle: float) -> float:
    return abs(angle)


def _vertical_deviation(angle: float) -> float:
    return abs(90.0 - abs(angle))


def _variant_contours(product: ProductContourResult) -> tuple[NDArray[np.float64], ...]:
    radius = max(1, int(round(2.0 * product.foreground.plane.pixels_per_mm)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, ((2 * radius) + 1,) * 2)
    region = cv2.dilate(product.mask, kernel, iterations=1)
    selected_area = max(1, int(np.count_nonzero(product.mask)))
    variants: list[NDArray[np.float64]] = []
    for signal in product.foreground.signal_masks:
        if signal.name not in {
            "background_color_difference",
            "grayscale_difference",
            "adaptive_threshold",
        }:
            continue
        restricted = cv2.bitwise_and(signal.mask, region)
        label_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            (restricted > 0).astype(np.uint8), connectivity=8
        )
        best_label: int | None = None
        best_overlap = 0
        for label in range(1, label_count):
            component = labels == label
            overlap = int(np.count_nonzero(component & (product.mask > 0)))
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = label
        if best_label is None or best_overlap / selected_area < 0.50:
            continue
        component_mask = np.where(labels == best_label, 255, 0).astype(np.uint8)
        contours, _hierarchy = cv2.findContours(
            component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        if len(contours) == 1 and len(contours[0]) >= 4:
            variants.append(np.asarray(contours[0], dtype=np.float64))
    return tuple(variants)


def _morphology_variant_contours(
    product: ProductContourResult, policy: GeometryPolicy
) -> tuple[NDArray[np.float64], ...]:
    pixels_per_mm = product.foreground.plane.pixels_per_mm
    variants: list[NDArray[np.float64]] = []
    for scale in (0.5, 1.5):
        open_radius = max(
            0, int(round(policy.morphology_open_mm * pixels_per_mm * scale))
        )
        close_radius = max(
            0, int(round(policy.morphology_close_mm * pixels_per_mm * scale))
        )
        opened = cv2.morphologyEx(
            product.foreground.mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                ((2 * open_radius) + 1, (2 * open_radius) + 1),
            ),
        )
        varied = cv2.morphologyEx(
            opened,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                ((2 * close_radius) + 1, (2 * close_radius) + 1),
            ),
        )
        contour = _best_overlap_contour(
            np.asarray(varied, dtype=np.uint8), product
        )
        if contour is not None:
            variants.append(contour)
    return tuple(variants)


def _best_overlap_contour(
    candidate_mask: NDArray[np.uint8], product: ProductContourResult
) -> NDArray[np.float64] | None:
    label_count, labels, _stats, _centroids = cv2.connectedComponentsWithStats(
        (candidate_mask > 0).astype(np.uint8), connectivity=8
    )
    best_label: int | None = None
    best_overlap = 0
    for label in range(1, label_count):
        overlap = int(np.count_nonzero((labels == label) & (product.mask > 0)))
        if overlap > best_overlap:
            best_label = label
            best_overlap = overlap
    if best_label is None or best_overlap <= 0:
        return None
    component = np.where(labels == best_label, 255, 0).astype(np.uint8)
    contours, _hierarchy = cv2.findContours(
        component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if len(contours) != 1 or len(contours[0]) < 4:
        return None
    return np.asarray(contours[0], dtype=np.float64)


def _variant_span(
    dimension: DimensionName, values: list[float]
) -> AxisVariantSpan:
    minimum = float(min(values))
    maximum = float(max(values))
    return AxisVariantSpan(
        dimension=dimension,
        minimum_mm=minimum,
        maximum_mm=maximum,
        span_mm=maximum - minimum,
    )


def _merge_spans(
    threshold: AxisVariantSpan, morphology: AxisVariantSpan
) -> AxisVariantSpan:
    if threshold.dimension is not morphology.dimension:
        raise ValueError("Variant spans must describe the same dimension")
    minimum = min(threshold.minimum_mm, morphology.minimum_mm)
    maximum = max(threshold.maximum_mm, morphology.maximum_mm)
    return AxisVariantSpan(
        dimension=threshold.dimension,
        minimum_mm=minimum,
        maximum_mm=maximum,
        span_mm=maximum - minimum,
    )


def _reject_unstable_shadow_or_reflection(
    product: ProductContourResult,
    measurements: tuple[AxisMeasurement, AxisMeasurement],
    spans: tuple[AxisVariantSpan, AxisVariantSpan],
    policy: GeometryPolicy,
) -> None:
    if product.foreground.reflection_fraction >= 0.05:
        raise _geometry_error(
            product,
            "REFLECTION_INTERFERENCE",
            "Reflections make the product boundary unsupported for measurement.",
            "Use diffuse lighting and remove glare before retaking the view.",
        )
    unstable = any(
        span.span_mm
        > max(
            policy.maximum_shadow_geometry_change_mm,
            measurement.value_mm * policy.maximum_shadow_geometry_change_percent / 100.0,
        )
        for measurement, span in zip(measurements, spans, strict=True)
    )
    if not unstable:
        return
    if product.foreground.shadow_fraction >= 0.05:
        raise _geometry_error(
            product,
            "SHADOW_INTERFERENCE",
            "Shadows make the product boundary unstable.",
            "Use diffuse lighting from multiple directions and retake the view.",
        )
    raise _geometry_error(
        product,
        "MEASUREMENT_QUALITY_INSUFFICIENT",
        "The product dimensions are unstable across deterministic foreground variants.",
        "Improve contrast and lighting, then retake the view.",
    )


def _geometry_error(
    product: ProductContourResult,
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
        field=product.foreground.view.value,
        view=product.foreground.view,
    )
