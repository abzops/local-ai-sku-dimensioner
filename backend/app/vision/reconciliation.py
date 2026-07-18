"""Deterministic cross-view reconciliation without blind averaging."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from backend.app.contracts import ImageView
from backend.app.vision.full_plane import GeometryPolicy
from backend.app.vision.measurement_quality import (
    ViewQualityEvidence,
    ViewUncertaintyEvidence,
)
from backend.app.vision.oriented_geometry import DimensionName


class DimensionGeometry(Protocol):
    """Lightweight geometry required for cross-view reconciliation."""

    def value(self, dimension: DimensionName) -> float: ...


class DimensionValidationStatus(StrEnum):
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    INVALID = "invalid"


class ReconciliationRule(StrEnum):
    QUALITY_UNCERTAINTY_WEIGHTED = "quality_uncertainty_weighted"
    STRONGER_SOURCE = "stronger_source"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ViewMeasurementInput:
    view: ImageView
    geometry: DimensionGeometry
    quality: ViewQualityEvidence
    uncertainty: ViewUncertaintyEvidence


@dataclass(frozen=True, slots=True)
class _DimensionCommon:
    dimension: DimensionName
    contributing_views: tuple[ImageView, ImageView]
    raw_values_mm: tuple[tuple[ImageView, float], tuple[ImageView, float]]
    absolute_disagreement_mm: float
    relative_disagreement_percent: float
    quality_inputs: tuple[tuple[ImageView, float], tuple[ImageView, float]]
    uncertainty_inputs_mm: tuple[tuple[ImageView, float], tuple[ImageView, float]]


@dataclass(frozen=True, slots=True)
class DimensionReconciliation:
    dimension: DimensionName
    contributing_views: tuple[ImageView, ImageView]
    raw_values_mm: tuple[tuple[ImageView, float], tuple[ImageView, float]]
    value_mm: float | None
    absolute_disagreement_mm: float
    relative_disagreement_percent: float
    quality_inputs: tuple[tuple[ImageView, float], tuple[ImageView, float]]
    uncertainty_inputs_mm: tuple[tuple[ImageView, float], tuple[ImageView, float]]
    uncertainty_mm: float | None
    reconciliation_rule: ReconciliationRule
    validation_status: DimensionValidationStatus
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    dimensions: tuple[
        DimensionReconciliation,
        DimensionReconciliation,
        DimensionReconciliation,
    ]
    final_dimensions_mm: dict[DimensionName, float] | None
    overall_uncertainty_mm: float | None
    succeeded: bool
    failure_code: str | None


_DIMENSION_VIEWS = {
    DimensionName.LENGTH: (ImageView.TOP, ImageView.SIDE),
    DimensionName.WIDTH: (ImageView.TOP, ImageView.FRONT),
    DimensionName.HEIGHT: (ImageView.FRONT, ImageView.SIDE),
}


def reconcile_measurements(
    top: ViewMeasurementInput,
    front: ViewMeasurementInput,
    side: ViewMeasurementInput,
    policy: GeometryPolicy,
) -> ReconciliationResult:
    """Reconcile the frozen view pairs and fail the tuple if any axis is invalid."""
    inputs = {top.view: top, front.view: front, side.view: side}
    if set(inputs) != {ImageView.TOP, ImageView.FRONT, ImageView.SIDE}:
        raise ValueError("Reconciliation requires one top, front, and side input")
    results = tuple(
        _reconcile_dimension(dimension, inputs, policy)
        for dimension in (
            DimensionName.LENGTH,
            DimensionName.WIDTH,
            DimensionName.HEIGHT,
        )
    )
    if len(results) != 3:
        raise AssertionError("Three dimensions are required")
    succeeded = all(result.value_mm is not None for result in results)
    if not succeeded:
        return ReconciliationResult(
            dimensions=(results[0], results[1], results[2]),
            final_dimensions_mm=None,
            overall_uncertainty_mm=None,
            succeeded=False,
            failure_code=_failure_code(results),
        )
    final_dimensions = {
        result.dimension: float(result.value_mm)
        for result in results
        if result.value_mm is not None
    }
    overall_uncertainty = max(
        float(result.uncertainty_mm)
        for result in results
        if result.uncertainty_mm is not None
    )
    return ReconciliationResult(
        dimensions=(results[0], results[1], results[2]),
        final_dimensions_mm=final_dimensions,
        overall_uncertainty_mm=overall_uncertainty,
        succeeded=True,
        failure_code=None,
    )


def _reconcile_dimension(
    dimension: DimensionName,
    inputs: dict[ImageView, ViewMeasurementInput],
    policy: GeometryPolicy,
) -> DimensionReconciliation:
    views = _DIMENSION_VIEWS[dimension]
    first = inputs[views[0]]
    second = inputs[views[1]]
    first_value = _dimension_value(first.geometry, dimension)
    second_value = _dimension_value(second.geometry, dimension)
    values = (first_value, second_value)
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise ValueError("Raw dimension values must be finite and positive")
    absolute = abs(first_value - second_value)
    relative = 100.0 * absolute / max((first_value + second_value) / 2.0, 1.0)
    qualities = (first.quality.score, second.quality.score)
    uncertainties = (first.uncertainty.total_mm, second.uncertainty.total_mm)
    common = _DimensionCommon(
        dimension=dimension,
        contributing_views=views,
        raw_values_mm=((views[0], first_value), (views[1], second_value)),
        absolute_disagreement_mm=absolute,
        relative_disagreement_percent=relative,
        quality_inputs=((views[0], qualities[0]), (views[1], qualities[1])),
        uncertainty_inputs_mm=(
            (views[0], uncertainties[0]),
            (views[1], uncertainties[1]),
        ),
    )
    if any(
        not math.isfinite(uncertainty)
        or uncertainty < 0.0
        or uncertainty >= value
        for uncertainty, value in zip(uncertainties, values, strict=True)
    ):
        return _build_result(
            common,
            value_mm=None,
            uncertainty_mm=None,
            reconciliation_rule=ReconciliationRule.FAILED,
            validation_status=DimensionValidationStatus.INVALID,
            warnings=("MEASUREMENT_UNCERTAINTY_EXCESSIVE",),
        )
    if min(qualities) < policy.weak_quality:
        return _build_result(
            common,
            value_mm=None,
            uncertainty_mm=None,
            reconciliation_rule=ReconciliationRule.FAILED,
            validation_status=DimensionValidationStatus.INVALID,
            warnings=("MEASUREMENT_QUALITY_INSUFFICIENT",),
        )
    if (
        absolute > policy.warning_absolute_mm
        or relative > policy.warning_relative_percent
    ):
        return _build_result(
            common,
            value_mm=None,
            uncertainty_mm=None,
            reconciliation_rule=ReconciliationRule.FAILED,
            validation_status=DimensionValidationStatus.INVALID,
            warnings=("MEASUREMENT_DISAGREEMENT",),
        )

    acceptable = (
        absolute <= policy.acceptable_absolute_mm
        and relative <= policy.acceptable_relative_percent
    )
    stronger = _stronger_index(qualities, uncertainties, policy)
    final_uncertainty = max(uncertainties) + (absolute / 2.0)
    if acceptable:
        warnings: tuple[str, ...]
        if stronger is not None:
            value = values[stronger]
            rule = ReconciliationRule.STRONGER_SOURCE
            warnings = ("STRONGER_SOURCE_SELECTED",)
        else:
            first_weight = qualities[0] / max(uncertainties[0] ** 2, 1e-6)
            second_weight = qualities[1] / max(uncertainties[1] ** 2, 1e-6)
            total_weight = first_weight + second_weight
            if not math.isfinite(total_weight) or total_weight <= 0.0:
                return _build_result(
                    common,
                    value_mm=None,
                    uncertainty_mm=None,
                    reconciliation_rule=ReconciliationRule.FAILED,
                    validation_status=DimensionValidationStatus.INVALID,
                    warnings=("MEASUREMENT_UNCERTAINTY_EXCESSIVE",),
                )
            value = ((first_value * first_weight) + (second_value * second_weight)) / total_weight
            rule = ReconciliationRule.QUALITY_UNCERTAINTY_WEIGHTED
            warnings = ()
        if final_uncertainty >= value:
            return _build_result(
                common,
                value_mm=None,
                uncertainty_mm=None,
                reconciliation_rule=ReconciliationRule.FAILED,
                validation_status=DimensionValidationStatus.INVALID,
                warnings=("MEASUREMENT_UNCERTAINTY_EXCESSIVE",),
            )
        return _build_result(
            common,
            value_mm=float(value),
            uncertainty_mm=final_uncertainty,
            reconciliation_rule=rule,
            validation_status=DimensionValidationStatus.ACCEPTABLE,
            warnings=warnings,
        )

    warning_source = _warning_stronger_index(qualities, uncertainties, policy)
    if warning_source is None:
        return _build_result(
            common,
            value_mm=None,
            uncertainty_mm=None,
            reconciliation_rule=ReconciliationRule.FAILED,
            validation_status=DimensionValidationStatus.INVALID,
            warnings=("MEASUREMENT_DISAGREEMENT",),
        )
    if final_uncertainty >= values[warning_source]:
        return _build_result(
            common,
            value_mm=None,
            uncertainty_mm=None,
            reconciliation_rule=ReconciliationRule.FAILED,
            validation_status=DimensionValidationStatus.INVALID,
            warnings=("MEASUREMENT_UNCERTAINTY_EXCESSIVE",),
        )
    return _build_result(
        common,
        value_mm=values[warning_source],
        uncertainty_mm=final_uncertainty,
        reconciliation_rule=ReconciliationRule.STRONGER_SOURCE,
        validation_status=DimensionValidationStatus.WARNING,
        warnings=("CROSS_VIEW_DISAGREEMENT", "STRONGER_SOURCE_SELECTED"),
    )


def _dimension_value(geometry: DimensionGeometry, dimension: DimensionName) -> float:
    return geometry.value(dimension)


def _failure_code(results: tuple[DimensionReconciliation, ...]) -> str:
    codes = {
        warning
        for result in results
        for warning in result.warnings
        if warning.startswith("MEASUREMENT_")
    }
    for code in (
        "MEASUREMENT_UNCERTAINTY_EXCESSIVE",
        "MEASUREMENT_QUALITY_INSUFFICIENT",
        "MEASUREMENT_DISAGREEMENT",
    ):
        if code in codes:
            return code
    return "MEASUREMENT_DISAGREEMENT"


def _build_result(
    common: _DimensionCommon,
    *,
    value_mm: float | None,
    uncertainty_mm: float | None,
    reconciliation_rule: ReconciliationRule,
    validation_status: DimensionValidationStatus,
    warnings: tuple[str, ...],
) -> DimensionReconciliation:
    return DimensionReconciliation(
        dimension=common.dimension,
        contributing_views=common.contributing_views,
        raw_values_mm=common.raw_values_mm,
        value_mm=value_mm,
        absolute_disagreement_mm=common.absolute_disagreement_mm,
        relative_disagreement_percent=common.relative_disagreement_percent,
        quality_inputs=common.quality_inputs,
        uncertainty_inputs_mm=common.uncertainty_inputs_mm,
        uncertainty_mm=uncertainty_mm,
        reconciliation_rule=reconciliation_rule,
        validation_status=validation_status,
        warnings=warnings,
    )


def _stronger_index(
    qualities: tuple[float, float],
    uncertainties: tuple[float, float],
    policy: GeometryPolicy,
) -> int | None:
    quality_difference = abs(qualities[0] - qualities[1])
    if quality_difference >= policy.stronger_source_quality_lead:
        return 0 if qualities[0] > qualities[1] else 1
    lower_uncertainty = 0 if uncertainties[0] <= uncertainties[1] else 1
    higher_uncertainty = 1 - lower_uncertainty
    if uncertainties[higher_uncertainty] / max(uncertainties[lower_uncertainty], 1e-9) >= (
        policy.weaker_source_uncertainty_ratio
    ):
        return lower_uncertainty
    return None


def _warning_stronger_index(
    qualities: tuple[float, float],
    uncertainties: tuple[float, float],
    policy: GeometryPolicy,
) -> int | None:
    stronger = 0 if qualities[0] >= qualities[1] else 1
    weaker = 1 - stronger
    if (
        qualities[stronger] >= policy.usable_quality
        and qualities[stronger] - qualities[weaker]
        >= policy.stronger_source_quality_lead
        and uncertainties[stronger] < uncertainties[weaker]
    ):
        return stronger
    return None
