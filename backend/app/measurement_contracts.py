"""Frozen Phase 3 measurement persistence and public domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from backend.app.models.measurement import MeasurementAttempt


class MeasurementStatus(StrEnum):
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DimensionName(StrEnum):
    LENGTH = "length"
    WIDTH = "width"
    HEIGHT = "height"


class MeasurementView(StrEnum):
    TOP = "top"
    FRONT = "front"
    SIDE = "side"


class DimensionValidationStatus(StrEnum):
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    INVALID = "invalid"


class ReconciliationRule(StrEnum):
    QUALITY_UNCERTAINTY_WEIGHTED = "quality_uncertainty_weighted"
    STRONGER_SOURCE = "stronger_source"
    FAILED = "failed"


class PreviewKind(StrEnum):
    ANNOTATED = "annotated"


class CaptureSetupType(StrEnum):
    ORTHOGONAL_RIG = "orthogonal_rig"


class StaleReason(StrEnum):
    ACTIVE_CALIBRATION_PROFILE_CHANGED = "active_calibration_profile_changed"
    SOURCE_IMAGES_CHANGED = "source_images_changed"
    CAPTURE_SETUP_CHANGED = "capture_setup_changed"
    PROCESSING_VERSION_CHANGED = "processing_version_changed"
    ALGORITHM_VERSION_CHANGED = "algorithm_version_changed"
    MEASUREMENT_POLICY_CHANGED = "measurement_policy_changed"


MEASUREMENT_VIEW_ORDER: Final[tuple[MeasurementView, ...]] = tuple(MeasurementView)
DIMENSION_ORDER: Final[tuple[DimensionName, ...]] = tuple(DimensionName)
DIMENSION_VIEW_PAIRS: Final[
    dict[DimensionName, tuple[MeasurementView, MeasurementView]]
] = {
    DimensionName.LENGTH: (MeasurementView.TOP, MeasurementView.SIDE),
    DimensionName.WIDTH: (MeasurementView.TOP, MeasurementView.FRONT),
    DimensionName.HEIGHT: (MeasurementView.FRONT, MeasurementView.SIDE),
}
VIEW_DIMENSION_PAIRS: Final[
    dict[MeasurementView, tuple[DimensionName, DimensionName]]
] = {
    MeasurementView.TOP: (DimensionName.LENGTH, DimensionName.WIDTH),
    MeasurementView.FRONT: (DimensionName.WIDTH, DimensionName.HEIGHT),
    MeasurementView.SIDE: (DimensionName.LENGTH, DimensionName.HEIGHT),
}

PROCESSING_VERSION: Final[str] = "phase3-v1"
ALGORITHM_VERSION: Final[str] = "deterministic-geometry-v1"
DEFAULT_LEASE_SECONDS: Final[int] = 120

ACCEPTABLE_DISAGREEMENT_ABSOLUTE_MM: Final[float] = 5.0
ACCEPTABLE_DISAGREEMENT_RELATIVE_PERCENT: Final[float] = 3.0
WARNING_DISAGREEMENT_ABSOLUTE_MM: Final[float] = 10.0
WARNING_DISAGREEMENT_RELATIVE_PERCENT: Final[float] = 6.0
USABLE_QUALITY_SCORE: Final[float] = 0.70
WEAK_QUALITY_SCORE: Final[float] = 0.55
STRONGER_SOURCE_QUALITY_LEAD: Final[float] = 0.15
WEAKER_SOURCE_UNCERTAINTY_RATIO: Final[float] = 2.0
MAXIMUM_RECTIFIED_EDGE_PX: Final[int] = 4096
MAXIMUM_RECTIFIED_PIXELS: Final[int] = 16_000_000
MAXIMUM_PHYSICAL_EXTENT_MM: Final[float] = 1500.0
MAXIMUM_CONNECTED_COMPONENTS: Final[int] = 1024
MAXIMUM_SCORED_CANDIDATES: Final[int] = 64
MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX: Final[int] = 1280
MAXIMUM_MEASUREMENT_PREVIEW_BYTES: Final[int] = 2 * 1024 * 1024

SUPPORTED_PRODUCT_DOMAIN: Final[tuple[str, ...]] = (
    "opaque",
    "rigid",
    "stable",
    "approximately_cuboidal",
    "fully_visible",
    "non_reflective_or_mildly_reflective",
    "configured_orthogonal_rig",
)
CAPTURE_REQUIREMENTS: Final[tuple[str, ...]] = (
    "Use the configured qualified orthogonal rig.",
    "Use a valid view-specific measurement plane for every required view.",
    "Register the product against the rig datums.",
    "Keep exactly one configured marker visible in each required image.",
)
NON_CERTIFIED_METROLOGY_WARNING: Final[str] = (
    "Measurements are deterministic engineering estimates from a physically qualified local "
    "rig, not certified metrology."
)


@dataclass(frozen=True, slots=True)
class SourceFingerprintUpdate:
    source_id: str
    original_sha256: str
    oriented_pixel_sha256: str


@dataclass(frozen=True, slots=True)
class PreviewPersistenceInput:
    preview_id: str
    view: MeasurementView
    kind: PreviewKind
    storage_key: str
    sha256: str
    media_type: str
    size_bytes: int
    width_px: int
    height_px: int


@dataclass(frozen=True, slots=True)
class MeasurementSuccessPersistenceInput:
    source_fingerprint: str
    length_mm: float
    width_mm: float
    height_mm: float
    per_view_evidence_json: str
    reconciliation_evidence_json: str
    quality_evidence_json: str
    uncertainty_evidence_json: str
    warnings_json: str
    source_updates: tuple[SourceFingerprintUpdate, ...]
    previews: tuple[PreviewPersistenceInput, ...]


@dataclass(frozen=True, slots=True)
class MeasurementFailurePersistenceInput:
    failure_json: str
    source_fingerprint: str | None = None
    per_view_evidence_json: str | None = None
    reconciliation_evidence_json: str | None = None
    quality_evidence_json: str | None = None
    uncertainty_evidence_json: str | None = None
    warnings_json: str | None = None
    source_updates: tuple[SourceFingerprintUpdate, ...] = ()


@dataclass(frozen=True, slots=True)
class MeasurementClaim:
    attempt: MeasurementAttempt
    replayed: bool
    reclaimed: bool
