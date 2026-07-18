"""Strict public Phase 3 measurement request and response schemas."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol
from urllib.parse import quote
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.calibration_contracts import ArucoDictionary, CornerLabel
from backend.app.measurement_contracts import (
    ACCEPTABLE_DISAGREEMENT_ABSOLUTE_MM,
    ACCEPTABLE_DISAGREEMENT_RELATIVE_PERCENT,
    CAPTURE_REQUIREMENTS,
    DIMENSION_ORDER,
    DIMENSION_VIEW_PAIRS,
    MAXIMUM_CONNECTED_COMPONENTS,
    MAXIMUM_MEASUREMENT_PREVIEW_BYTES,
    MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX,
    MAXIMUM_PHYSICAL_EXTENT_MM,
    MAXIMUM_RECTIFIED_EDGE_PX,
    MAXIMUM_RECTIFIED_PIXELS,
    MAXIMUM_SCORED_CANDIDATES,
    MEASUREMENT_VIEW_ORDER,
    STRONGER_SOURCE_QUALITY_LEAD,
    SUPPORTED_PRODUCT_DOMAIN,
    USABLE_QUALITY_SCORE,
    VIEW_DIMENSION_PAIRS,
    WARNING_DISAGREEMENT_ABSOLUTE_MM,
    WARNING_DISAGREEMENT_RELATIVE_PERCENT,
    WEAK_QUALITY_SCORE,
    WEAKER_SOURCE_UNCERTAINTY_RATIO,
    CaptureSetupType,
    DimensionName,
    DimensionValidationStatus,
    MeasurementStatus,
    MeasurementView,
    PreviewKind,
    ReconciliationRule,
    StaleReason,
)
from backend.app.schemas.calibration import (
    CalibrationProfileResponse,
    EdgeValuesResponse,
    MarkerEdgeQualityResponse,
    Matrix3x3Response,
    OrderedCornerResponse,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
UnitScore = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
SafeText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
CaptureSetupVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]


class CaptureSettings(Protocol):
    capture_setup_id: str
    capture_setup_version: str
    capture_setup_type: str
    capture_setup_qualified: bool
    capture_setup_min_object_mm: float
    capture_setup_max_object_mm: float
    capture_setup_marker_size_uncertainty_mm: float
    capture_setup_plane_uncertainty_mm: float
    capture_setup_orthogonality_uncertainty_deg: float
    capture_setup_standoff_uncertainty_mm: float
    capture_setup_max_off_plane_mm: float


class MeasurementSettings(CaptureSettings, Protocol):
    measurement_acceptable_disagreement_mm: float
    measurement_acceptable_disagreement_percent: float
    measurement_warning_disagreement_mm: float
    measurement_warning_disagreement_percent: float
    measurement_usable_quality: float
    measurement_weak_quality: float
    measurement_stronger_source_quality_lead: float
    measurement_weaker_source_uncertainty_ratio: float
    measurement_max_rectified_edge_px: int
    measurement_max_rectified_pixels: int
    measurement_max_physical_extent_mm: float
    measurement_max_components: int
    measurement_max_candidates: int


class MeasurementProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    expected_calibration_profile_id: UUID
    expected_capture_setup_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    capture_contract_acknowledged: Literal[True]
    reprocess_of_measurement_id: UUID | None = None


class MeasurementFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SafeText
    message: SafeText
    recoverable: bool
    suggested_action: SafeText
    field: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    view: MeasurementView | None = None


class MeasurementSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    view: MeasurementView
    scan_image_id: str
    original_sha256: Sha256Hex
    oriented_pixel_sha256: Sha256Hex
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)

    @field_validator("scan_image_id")
    @classmethod
    def validate_image_uuid(cls, value: str) -> str:
        UUID(value)
        return value


class MarkerEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dictionary: ArucoDictionary
    marker_id: int = Field(ge=0, le=49)
    marker_size_mm: Annotated[float, Field(ge=10.0, le=300.0, allow_inf_nan=False)]
    ordered_corners: tuple[
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
    ]
    orientation_degrees: Annotated[float, Field(ge=-180.0, lt=180.0, allow_inf_nan=False)]
    edge_lengths_px: EdgeValuesResponse
    perspective_ratio: Annotated[float, Field(ge=1.0, le=10.0, allow_inf_nan=False)]
    image_to_plane_mm: Matrix3x3Response
    plane_mm_to_image: Matrix3x3Response
    homography_condition_number: Annotated[float, Field(ge=1.0, allow_inf_nan=False)]
    marker_edge_quality: MarkerEdgeQualityResponse

    @field_validator("ordered_corners")
    @classmethod
    def validate_corner_order(
        cls,
        value: tuple[
            OrderedCornerResponse,
            OrderedCornerResponse,
            OrderedCornerResponse,
            OrderedCornerResponse,
        ],
    ) -> tuple[
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
    ]:
        if tuple(corner.label for corner in value) != tuple(CornerLabel):
            raise ValueError("marker corners must use canonical order")
        return value


class PlanePointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x_mm: FiniteFloat
    y_mm: FiniteFloat


class RectificationEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width_px: int = Field(ge=1, le=MAXIMUM_RECTIFIED_EDGE_PX)
    height_px: int = Field(ge=1, le=MAXIMUM_RECTIFIED_EDGE_PX)
    pixels_per_mm: PositiveFloat
    physical_origin_mm: PlanePointResponse
    source_to_rectified: Matrix3x3Response
    rectified_to_source: Matrix3x3Response
    physical_width_mm: Annotated[
        float, Field(gt=0.0, le=MAXIMUM_PHYSICAL_EXTENT_MM, allow_inf_nan=False)
    ]
    physical_height_mm: Annotated[
        float, Field(gt=0.0, le=MAXIMUM_PHYSICAL_EXTENT_MM, allow_inf_nan=False)
    ]

    @model_validator(mode="after")
    def validate_pixel_bound(self) -> RectificationEvidenceResponse:
        if self.width_px * self.height_px > MAXIMUM_RECTIFIED_PIXELS:
            raise ValueError("rectified output exceeds pixel limit")
        return self


class LabValuesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    l: FiniteFloat  # noqa: E741 - LAB channel name is part of the public contract.
    a: FiniteFloat
    b: FiniteFloat


class ForegroundEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    background_lab_median: LabValuesResponse
    background_lab_mad: LabValuesResponse
    background_grayscale_median: FiniteFloat
    foreground_grayscale_difference: NonNegativeFloat
    supported_signals: list[Annotated[str, StringConstraints(min_length=1, max_length=50)]]
    supported_signal_count: int = Field(ge=1)
    component_count: int = Field(ge=0, le=MAXIMUM_CONNECTED_COMPONENTS)
    scored_candidate_count: int = Field(ge=0, le=MAXIMUM_SCORED_CANDIDATES)
    selected_candidate_score: UnitScore
    runner_up_candidate_score: UnitScore | None
    strong_core_coverage: UnitScore
    mask_stability: UnitScore
    shadow_fraction: UnitScore
    reflection_fraction: UnitScore
    marker_clearance_mm: NonNegativeFloat
    border_clearance_mm: NonNegativeFloat
    contour_area_mm2: PositiveFloat
    hull_area_mm2: PositiveFloat
    solidity: UnitScore
    extent: UnitScore
    oriented_box_corners_mm: tuple[
        PlanePointResponse,
        PlanePointResponse,
        PlanePointResponse,
        PlanePointResponse,
    ]
    oriented_box_angle_degrees: Annotated[
        float, Field(ge=-180.0, lt=180.0, allow_inf_nan=False)
    ]
    threshold_variant_span_mm: NonNegativeFloat
    morphology_variant_span_mm: NonNegativeFloat

    @model_validator(mode="after")
    def validate_signal_and_area_relationships(self) -> ForegroundEvidenceResponse:
        if self.supported_signal_count != len(self.supported_signals):
            raise ValueError("supported signal count does not match")
        if len(set(self.supported_signals)) != len(self.supported_signals):
            raise ValueError("supported signals must be unique")
        if self.hull_area_mm2 < self.contour_area_mm2:
            raise ValueError("hull area cannot be below contour area")
        return self


class ViewQualityEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: UnitScore
    marker: UnitScore
    homography: UnitScore
    background: UnitScore
    mask_stability: UnitScore
    candidate_uniqueness: UnitScore
    visibility: UnitScore


class ViewUncertaintyEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    marker_size_mm: NonNegativeFloat
    marker_localization_mm: NonNegativeFloat
    raster_mm: NonNegativeFloat
    foreground_stability_mm: NonNegativeFloat
    rig_plane_mm: NonNegativeFloat
    rig_orthogonality_mm: NonNegativeFloat
    mount_standoff_mm: NonNegativeFloat
    off_plane_parallax_mm: NonNegativeFloat
    total_mm: NonNegativeFloat

    @model_validator(mode="after")
    def total_covers_components(self) -> ViewUncertaintyEvidenceResponse:
        components = (
            self.marker_size_mm,
            self.marker_localization_mm,
            self.raster_mm,
            self.foreground_stability_mm,
            self.rig_plane_mm,
            self.rig_orthogonality_mm,
            self.mount_standoff_mm,
            self.off_plane_parallax_mm,
        )
        if self.total_mm < max(components):
            raise ValueError("total uncertainty must cover every component")
        return self


class PerViewMeasurementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    view: MeasurementView
    source: MeasurementSourceResponse
    marker: MarkerEvidenceResponse
    rectification: RectificationEvidenceResponse
    foreground: ForegroundEvidenceResponse
    raw_dimensions_mm: dict[DimensionName, PositiveFloat]
    quality: ViewQualityEvidenceResponse
    uncertainty: ViewUncertaintyEvidenceResponse
    warnings: list[SafeText]
    preview_available: bool

    @model_validator(mode="after")
    def validate_view_specific_fields(self) -> PerViewMeasurementResponse:
        if self.source.view is not self.view:
            raise ValueError("source view does not match evidence view")
        if set(self.raw_dimensions_mm) != set(VIEW_DIMENSION_PAIRS[self.view]):
            raise ValueError("raw dimensions do not match the view axis mapping")
        return self


class DimensionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: DimensionName
    contributing_views: tuple[MeasurementView, MeasurementView]
    raw_values_mm: dict[MeasurementView, PositiveFloat]
    value_mm: PositiveFloat | None
    absolute_disagreement_mm: NonNegativeFloat
    relative_disagreement_percent: NonNegativeFloat
    quality_inputs: dict[MeasurementView, UnitScore]
    uncertainty_inputs_mm: dict[MeasurementView, NonNegativeFloat]
    uncertainty_mm: NonNegativeFloat | None
    reconciliation_rule: ReconciliationRule
    validation_status: DimensionValidationStatus
    warnings: list[SafeText]

    @model_validator(mode="after")
    def validate_dimension_shape(self) -> DimensionResultResponse:
        expected = DIMENSION_VIEW_PAIRS[self.dimension]
        if self.contributing_views != expected:
            raise ValueError("contributing views do not match dimension")
        for values in (self.raw_values_mm, self.quality_inputs, self.uncertainty_inputs_mm):
            if set(values) != set(expected):
                raise ValueError("dimension evidence keys do not match contributing views")
        invalid = self.validation_status is DimensionValidationStatus.INVALID
        if invalid:
            if self.value_mm is not None or self.uncertainty_mm is not None:
                raise ValueError("invalid dimensions must omit value and uncertainty")
        elif self.value_mm is None or self.uncertainty_mm is None:
            raise ValueError("valid dimensions require value and uncertainty")
        if invalid != (self.reconciliation_rule is ReconciliationRule.FAILED):
            raise ValueError("invalid dimensions must use the failed rule")
        return self


class ViewScoresResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top: UnitScore
    front: UnitScore
    side: UnitScore


class OverallQualityEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: UnitScore
    minimum_view_score: UnitScore
    view_scores: ViewScoresResponse

    @model_validator(mode="after")
    def validate_minimum(self) -> OverallQualityEvidenceResponse:
        values = (
            self.view_scores.top,
            self.view_scores.front,
            self.view_scores.side,
        )
        if not math.isclose(self.minimum_view_score, min(values), abs_tol=1e-9):
            raise ValueError("minimum view score does not match")
        return self


class FinalDimensionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    length_mm: PositiveFloat
    width_mm: PositiveFloat
    height_mm: PositiveFloat


class PreviewDescriptorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    view: MeasurementView
    kind: Literal[PreviewKind.ANNOTATED]
    media_type: Literal["image/png"]
    width_px: int = Field(ge=1, le=MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX)
    height_px: int = Field(ge=1, le=MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX)
    size_bytes: int = Field(ge=1, le=MAXIMUM_MEASUREMENT_PREVIEW_BYTES)
    api_url: str

    @field_validator("api_url")
    @classmethod
    def validate_relative_api_url(cls, value: str) -> str:
        if not value.startswith("/api/scans/") or "://" in value or "\\" in value:
            raise ValueError("preview URL must be a server-relative API URL")
        return value


class CaptureSetupSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    version: CaptureSetupVersion
    type: Literal[CaptureSetupType.ORTHOGONAL_RIG]
    qualified: bool
    minimum_object_mm: PositiveFloat
    maximum_object_mm: PositiveFloat
    marker_size_uncertainty_mm: NonNegativeFloat
    plane_uncertainty_mm: NonNegativeFloat
    orthogonality_uncertainty_deg: NonNegativeFloat
    standoff_uncertainty_mm: NonNegativeFloat
    maximum_off_plane_mm: NonNegativeFloat

    @model_validator(mode="after")
    def validate_range(self) -> CaptureSetupSnapshotResponse:
        if self.minimum_object_mm >= self.maximum_object_mm:
            raise ValueError("capture setup minimum must be below maximum")
        return self


class MeasurementPolicySnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acceptable_absolute_mm: PositiveFloat = ACCEPTABLE_DISAGREEMENT_ABSOLUTE_MM
    acceptable_relative_percent: PositiveFloat = ACCEPTABLE_DISAGREEMENT_RELATIVE_PERCENT
    warning_absolute_mm: PositiveFloat = WARNING_DISAGREEMENT_ABSOLUTE_MM
    warning_relative_percent: PositiveFloat = WARNING_DISAGREEMENT_RELATIVE_PERCENT
    usable_quality: UnitScore = USABLE_QUALITY_SCORE
    weak_quality: UnitScore = WEAK_QUALITY_SCORE
    stronger_source_quality_lead: UnitScore = STRONGER_SOURCE_QUALITY_LEAD
    weaker_source_uncertainty_ratio: PositiveFloat = WEAKER_SOURCE_UNCERTAINTY_RATIO
    maximum_rectified_edge_px: int = MAXIMUM_RECTIFIED_EDGE_PX
    maximum_rectified_pixels: int = MAXIMUM_RECTIFIED_PIXELS
    maximum_physical_extent_mm: PositiveFloat = MAXIMUM_PHYSICAL_EXTENT_MM
    maximum_connected_components: int = MAXIMUM_CONNECTED_COMPONENTS
    maximum_scored_candidates: int = MAXIMUM_SCORED_CANDIDATES
    maximum_preview_long_edge_px: int = MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX
    maximum_preview_encoded_size: int = MAXIMUM_MEASUREMENT_PREVIEW_BYTES


class CaptureSetupOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: CaptureSetupVersion
    type: Literal[CaptureSetupType.ORTHOGONAL_RIG]
    qualified: bool
    processing_enabled: bool
    minimum_object_mm: PositiveFloat
    maximum_object_mm: PositiveFloat
    supported_product_domain: list[str]
    requirements: list[str]


class DisagreementThresholdsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acceptable_absolute_mm: float
    acceptable_relative_percent: float
    warning_absolute_mm: float
    warning_relative_percent: float


class DimensionAxisMappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top: tuple[Literal[DimensionName.LENGTH], Literal[DimensionName.WIDTH]]
    front: tuple[Literal[DimensionName.WIDTH], Literal[DimensionName.HEIGHT]]
    side: tuple[Literal[DimensionName.LENGTH], Literal[DimensionName.HEIGHT]]


class MeasurementOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capture_setup: CaptureSetupOptionsResponse
    required_views: tuple[
        Literal[MeasurementView.TOP],
        Literal[MeasurementView.FRONT],
        Literal[MeasurementView.SIDE],
    ]
    dimension_axis_mapping: DimensionAxisMappingResponse
    disagreement_thresholds: DisagreementThresholdsResponse
    non_certified_metrology_warning: Literal[
        "Measurements are deterministic engineering estimates from a physically qualified "
        "local rig, not certified metrology."
    ]


class MeasurementAttemptSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    scan_id: str
    request_id: str
    reprocess_of_measurement_id: str | None
    status: MeasurementStatus
    calibration_profile_id: str
    calibration_profile_name: str
    capture_setup_id: str
    capture_setup_version: CaptureSetupVersion
    processing_version: str
    algorithm_version: str
    length_mm: PositiveFloat | None
    width_mm: PositiveFloat | None
    height_mm: PositiveFloat | None
    failure_code: str | None
    is_stale: bool
    stale_reasons: list[StaleReason]
    created_at: datetime
    completed_at: datetime | None

    @field_validator(
        "id",
        "scan_id",
        "request_id",
        "reprocess_of_measurement_id",
        "calibration_profile_id",
    )
    @classmethod
    def validate_optional_uuid(cls, value: str | None) -> str | None:
        if value is not None:
            UUID(value)
        return value

    @field_validator("created_at", "completed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)

    @model_validator(mode="after")
    def validate_summary_state(self) -> MeasurementAttemptSummaryResponse:
        dimensions = (self.length_mm, self.width_mm, self.height_mm)
        if self.status is MeasurementStatus.PROCESSING:
            if (
                any(value is not None for value in dimensions)
                or self.failure_code
                or self.completed_at
            ):
                raise ValueError("processing summary contains terminal values")
        elif self.status is MeasurementStatus.SUCCEEDED:
            if (
                any(value is None for value in dimensions)
                or self.failure_code
                or not self.completed_at
            ):
                raise ValueError("succeeded summary is incomplete")
        elif (
            any(value is not None for value in dimensions)
            or not self.failure_code
            or not self.completed_at
        ):
            raise ValueError("failed summary is incomplete")
        if self.is_stale != bool(self.stale_reasons):
            raise ValueError("stale flag and reasons disagree")
        if len(set(self.stale_reasons)) != len(self.stale_reasons):
            raise ValueError("stale reasons must be unique")
        return self


class MeasurementAttemptListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[MeasurementAttemptSummaryResponse]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class MeasurementAttemptDetailResponse(MeasurementAttemptSummaryResponse):
    calibration_profile_snapshot: CalibrationProfileResponse
    capture_setup_snapshot: CaptureSetupSnapshotResponse
    measurement_policy_snapshot: MeasurementPolicySnapshotResponse
    source_fingerprint: Sha256Hex | None
    sources: list[MeasurementSourceResponse]
    per_view_measurements: list[PerViewMeasurementResponse]
    dimension_results: list[DimensionResultResponse]
    final_dimensions: FinalDimensionsResponse | None
    overall_quality: OverallQualityEvidenceResponse | None
    overall_uncertainty_mm: NonNegativeFloat | None
    warnings: list[SafeText]
    previews: list[PreviewDescriptorResponse]
    failure: MeasurementFailure | None
    started_at: datetime

    @field_validator("started_at")
    @classmethod
    def normalize_started_at(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @model_validator(mode="after")
    def validate_detail_state(self) -> MeasurementAttemptDetailResponse:
        if self.calibration_profile_snapshot.id != self.calibration_profile_id:
            raise ValueError("profile snapshot does not match producing profile")
        if (
            self.capture_setup_snapshot.id != self.capture_setup_id
            or self.capture_setup_snapshot.version != self.capture_setup_version
        ):
            raise ValueError("capture setup snapshot does not match summary")
        if self.status is MeasurementStatus.PROCESSING:
            if any(
                (
                    self.source_fingerprint,
                    self.sources,
                    self.per_view_measurements,
                    self.dimension_results,
                    self.final_dimensions,
                    self.overall_quality,
                    self.overall_uncertainty_mm,
                    self.warnings,
                    self.previews,
                    self.failure,
                )
            ):
                raise ValueError("processing detail contains terminal evidence")
        elif self.status is MeasurementStatus.SUCCEEDED:
            if (
                self.source_fingerprint is None
                or tuple(source.view for source in self.sources) != MEASUREMENT_VIEW_ORDER
                or tuple(item.view for item in self.per_view_measurements) != MEASUREMENT_VIEW_ORDER
                or tuple(item.dimension for item in self.dimension_results) != DIMENSION_ORDER
                or self.final_dimensions is None
                or self.overall_quality is None
                or self.overall_uncertainty_mm is None
                or tuple(preview.view for preview in self.previews) != MEASUREMENT_VIEW_ORDER
                or self.failure is not None
            ):
                raise ValueError("succeeded detail is incomplete")
        elif self.final_dimensions is not None or self.previews or self.failure is None:
            raise ValueError("failed detail has an invalid shape")

        for preview in self.previews:
            expected = (
                f"/api/scans/{quote(self.scan_id, safe='')}/measurements/"
                f"{quote(self.id, safe='')}/previews/{preview.view.value}"
            )
            if preview.api_url != expected:
                raise ValueError("preview URL does not match its owning attempt")
        return self


def capture_setup_snapshot(settings: CaptureSettings) -> CaptureSetupSnapshotResponse:
    return CaptureSetupSnapshotResponse(
        id=settings.capture_setup_id,
        version=settings.capture_setup_version,
        type=CaptureSetupType.ORTHOGONAL_RIG,
        qualified=settings.capture_setup_qualified,
        minimum_object_mm=settings.capture_setup_min_object_mm,
        maximum_object_mm=settings.capture_setup_max_object_mm,
        marker_size_uncertainty_mm=settings.capture_setup_marker_size_uncertainty_mm,
        plane_uncertainty_mm=settings.capture_setup_plane_uncertainty_mm,
        orthogonality_uncertainty_deg=settings.capture_setup_orthogonality_uncertainty_deg,
        standoff_uncertainty_mm=settings.capture_setup_standoff_uncertainty_mm,
        maximum_off_plane_mm=settings.capture_setup_max_off_plane_mm,
    )


def measurement_policy_snapshot(
    settings: MeasurementSettings,
) -> MeasurementPolicySnapshotResponse:
    return MeasurementPolicySnapshotResponse(
        acceptable_absolute_mm=settings.measurement_acceptable_disagreement_mm,
        acceptable_relative_percent=settings.measurement_acceptable_disagreement_percent,
        warning_absolute_mm=settings.measurement_warning_disagreement_mm,
        warning_relative_percent=settings.measurement_warning_disagreement_percent,
        usable_quality=settings.measurement_usable_quality,
        weak_quality=settings.measurement_weak_quality,
        stronger_source_quality_lead=settings.measurement_stronger_source_quality_lead,
        weaker_source_uncertainty_ratio=(
            settings.measurement_weaker_source_uncertainty_ratio
        ),
        maximum_rectified_edge_px=settings.measurement_max_rectified_edge_px,
        maximum_rectified_pixels=settings.measurement_max_rectified_pixels,
        maximum_physical_extent_mm=settings.measurement_max_physical_extent_mm,
        maximum_connected_components=settings.measurement_max_components,
        maximum_scored_candidates=settings.measurement_max_candidates,
    )


def measurement_options(settings: MeasurementSettings) -> MeasurementOptionsResponse:
    snapshot = capture_setup_snapshot(settings)
    return MeasurementOptionsResponse(
        capture_setup=CaptureSetupOptionsResponse(
            id=snapshot.id,
            version=snapshot.version,
            type=snapshot.type,
            qualified=snapshot.qualified,
            processing_enabled=snapshot.qualified,
            minimum_object_mm=snapshot.minimum_object_mm,
            maximum_object_mm=snapshot.maximum_object_mm,
            supported_product_domain=list(SUPPORTED_PRODUCT_DOMAIN),
            requirements=list(CAPTURE_REQUIREMENTS),
        ),
        required_views=(
            MeasurementView.TOP,
            MeasurementView.FRONT,
            MeasurementView.SIDE,
        ),
        dimension_axis_mapping=DimensionAxisMappingResponse(
            top=(DimensionName.LENGTH, DimensionName.WIDTH),
            front=(DimensionName.WIDTH, DimensionName.HEIGHT),
            side=(DimensionName.LENGTH, DimensionName.HEIGHT),
        ),
        disagreement_thresholds=DisagreementThresholdsResponse(
            acceptable_absolute_mm=settings.measurement_acceptable_disagreement_mm,
            acceptable_relative_percent=(
                settings.measurement_acceptable_disagreement_percent
            ),
            warning_absolute_mm=settings.measurement_warning_disagreement_mm,
            warning_relative_percent=settings.measurement_warning_disagreement_percent,
        ),
        non_certified_metrology_warning=(
            "Measurements are deterministic engineering estimates from a physically qualified "
            "local rig, not certified metrology."
        ),
    )
