"""Explainable Phase 3 view quality and conservative uncertainty evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.app.calibration_contracts import MarkerAnalysisResult
from backend.app.errors import ApplicationError
from backend.app.vision.full_plane import GeometryPolicy, RectifiedPlane
from backend.app.vision.oriented_geometry import ViewGeometryResult
from backend.app.vision.product_contours import ProductContourResult


@dataclass(frozen=True, slots=True)
class ViewQualityEvidence:
    """Engineering evidence score; values are not probabilities."""

    score: float
    marker: float
    homography: float
    background: float
    mask_stability: float
    candidate_uniqueness: float
    visibility: float


@dataclass(frozen=True, slots=True)
class RigUncertaintySpec:
    """Physically qualified rig uncertainty bounds snapshotted by orchestration."""

    marker_size_mm: float
    plane_mm: float
    orthogonality_degrees: float
    mount_standoff_mm: float
    maximum_off_plane_mm: float

    def __post_init__(self) -> None:
        values = (
            self.marker_size_mm,
            self.plane_mm,
            self.orthogonality_degrees,
            self.mount_standoff_mm,
            self.maximum_off_plane_mm,
        )
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("Rig uncertainty bounds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ViewUncertaintyEvidence:
    """Conservative additive engineering bound in millimetres."""

    marker_size_mm: float
    marker_localization_mm: float
    raster_mm: float
    foreground_stability_mm: float
    rig_plane_mm: float
    rig_orthogonality_mm: float
    mount_standoff_mm: float
    off_plane_parallax_mm: float
    total_mm: float


def calculate_view_quality(
    marker: MarkerAnalysisResult,
    rectification: RectifiedPlane,
    contour: ProductContourResult,
    geometry: ViewGeometryResult,
    policy: GeometryPolicy,
) -> ViewQualityEvidence:
    """Calculate the frozen weighted quality evidence from named signals."""
    del rectification, geometry
    edge_quality = marker.marker_edge_quality
    marker_component = _score(
        1.0 - (edge_quality.maximum_px / max(edge_quality.threshold_px, 1e-9))
    )
    perspective_component = _score(
        1.0 - ((marker.perspective_ratio - 1.0) / 2.0)
    )
    condition_component = _score(
        1.0 - (math.log10(max(1.0, marker.homography_condition_number)) / 6.0)
    )
    homography_component = _score(
        (perspective_component + condition_component) / 2.0
    )
    uniformity_component = _score(
        1.0
        - (
            max(contour.foreground.background_lab_mad)
            / max(policy.background_lab_mad_maximum, 1e-9)
        )
    )
    contrast_component = _score(
        contour.foreground.grayscale_foreground_difference
        / max(policy.minimum_grayscale_difference * 2.0, 1e-9)
    )
    background_component = _score((uniformity_component + contrast_component) / 2.0)
    stability_component = _score(contour.mask_stability)
    if contour.runner_up_score is None:
        uniqueness_margin = 1.0
    else:
        uniqueness_margin = _score(
            (contour.selected_score - contour.runner_up_score)
            / max(policy.minimum_candidate_score_margin * 2.0, 1e-9)
        )
    candidate_component = _score(
        (contour.selected_score + uniqueness_margin) / 2.0
    )
    clearance = min(contour.border_clearance_mm, contour.marker_clearance_mm)
    clearance_component = _score(
        clearance
        / max(
            3.0 * max(policy.border_clearance_mm, policy.marker_clearance_mm),
            1e-9,
        )
    )
    interference_component = _score(
        1.0
        - min(
            1.0,
            contour.foreground.shadow_fraction + contour.foreground.reflection_fraction,
        )
    )
    visibility_component = _score(
        (clearance_component + interference_component) / 2.0
    )
    total = _score(
        (0.20 * marker_component)
        + (0.15 * homography_component)
        + (0.15 * background_component)
        + (0.20 * stability_component)
        + (0.15 * candidate_component)
        + (0.15 * visibility_component)
    )
    return ViewQualityEvidence(
        score=total,
        marker=marker_component,
        homography=homography_component,
        background=background_component,
        mask_stability=stability_component,
        candidate_uniqueness=candidate_component,
        visibility=visibility_component,
    )


def calculate_view_uncertainty(
    marker: MarkerAnalysisResult,
    rectification: RectifiedPlane,
    geometry: ViewGeometryResult,
    rig: RigUncertaintySpec,
) -> ViewUncertaintyEvidence:
    """Return a conservative sum; do not interpret it as a confidence interval."""
    minimum_marker_edge = min(
        marker.edge_lengths_px.top,
        marker.edge_lengths_px.right,
        marker.edge_lengths_px.bottom,
        marker.edge_lengths_px.left,
    )
    if not math.isfinite(minimum_marker_edge) or minimum_marker_edge <= 0.0:
        raise ValueError("Marker edge evidence must be finite and positive")
    marker_polygon = rectification.marker_polygon_px
    marker_plane_edges = tuple(
        math.hypot(
            float(marker_polygon[(index + 1) % 4, 0] - marker_polygon[index, 0]),
            float(marker_polygon[(index + 1) % 4, 1] - marker_polygon[index, 1]),
        )
        / rectification.pixels_per_mm
        for index in range(4)
    )
    marker_size_mm = float(sum(marker_plane_edges) / 4.0)
    marker_mm_per_pixel = marker_size_mm / minimum_marker_edge
    marker_localization = (
        marker.marker_edge_quality.maximum_px * marker_mm_per_pixel
    )
    raster = 1.0 / rectification.pixels_per_mm
    foreground_stability = max(
        geometry.threshold_variant_span_mm,
        geometry.morphology_variant_span_mm,
    ) / 2.0
    maximum_axis = max(
        measurement.value_mm for measurement in geometry.raw_dimensions
    )
    orthogonality = maximum_axis * math.tan(math.radians(rig.orthogonality_degrees))
    components = (
        rig.marker_size_mm,
        marker_localization,
        raster,
        foreground_stability,
        rig.plane_mm,
        orthogonality,
        rig.mount_standoff_mm,
        rig.maximum_off_plane_mm,
    )
    if not all(math.isfinite(value) and value >= 0.0 for value in components):
        raise ValueError("Uncertainty evidence must be finite and non-negative")
    total = float(sum(components))
    return ViewUncertaintyEvidence(
        marker_size_mm=rig.marker_size_mm,
        marker_localization_mm=marker_localization,
        raster_mm=raster,
        foreground_stability_mm=foreground_stability,
        rig_plane_mm=rig.plane_mm,
        rig_orthogonality_mm=orthogonality,
        mount_standoff_mm=rig.mount_standoff_mm,
        off_plane_parallax_mm=rig.maximum_off_plane_mm,
        total_mm=total,
    )


def require_minimum_view_quality(
    evidence: ViewQualityEvidence,
    geometry: ViewGeometryResult,
    policy: GeometryPolicy,
) -> None:
    """Reject evidence below the frozen weak-quality floor."""
    if evidence.score >= policy.weak_quality:
        return
    raise ApplicationError(
        status_code=422,
        code="MEASUREMENT_QUALITY_INSUFFICIENT",
        message="The deterministic evidence quality is insufficient for measurement.",
        recoverable=True,
        suggested_action="Improve alignment, contrast, and lighting, then retake the view.",
        field=geometry.view.value,
        view=geometry.view,
    )


def _score(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))
