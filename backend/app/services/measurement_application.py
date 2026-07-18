"""Synchronous Phase 3 orchestration across immutable sources, geometry, and persistence."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast
from uuid import uuid4

import cv2
from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.calibration_contracts import MarkerAnalysisResult, MarkerProfileSpec
from backend.app.contracts import REQUIRED_IMAGE_VIEW_ORDER, ImageView
from backend.app.errors import ApplicationError
from backend.app.models.scan import ScanImage
from backend.app.schemas.calibration import CalibrationProfileResponse
from backend.app.services.measurement_storage import (
    FinalizedMeasurementPreviewBatch,
    MeasurementStorage,
    PreviewWrite,
    StagedMeasurementPreviewBatch,
)
from backend.app.services.stored_image_loader import LoadedStoredImage, StoredImageLoader
from backend.app.vision.marker_engine import analyze_marker_image
from backend.app.vision.oriented_geometry import DimensionName

T = TypeVar("T")


class MeasurementSettings(Protocol):
    data_root: Path
    max_upload_bytes: int
    max_image_pixels: int
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
    measurement_processing_deadline_seconds: float
    measurement_processing_lease_seconds: int


class MeasurementRequest(Protocol):
    expected_capture_setup_id: str
    capture_contract_acknowledged: bool


class AttemptSource(Protocol):
    id: str
    view: Any
    scan_image_id: str
    storage_key_snapshot: str
    media_type: str
    size_bytes: int
    width_px: int
    height_px: int


class MeasurementAttempt(Protocol):
    id: str
    scan_id: str
    calibration_profile_id: str
    profile_snapshot_json: str
    lease_token: str
    sources: Sequence[AttemptSource]


class MeasurementClaim(Protocol):
    attempt: MeasurementAttempt
    replayed: bool
    reclaimed: bool


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """Array-free immutable source metadata retained across view processing."""

    scan_image_id: str
    view: ImageView
    original_sha256: str
    oriented_pixel_sha256: str
    media_type: str
    size_bytes: int
    width_px: int
    height_px: int


@dataclass(frozen=True, slots=True)
class ReconciliationGeometry:
    """Array-free dimension values required after one view completes."""

    view: ImageView
    values_mm: tuple[tuple[DimensionName, float], tuple[DimensionName, float]]

    def value(self, dimension: DimensionName) -> float:
        for name, value in self.values_mm:
            if name is dimension:
                return value
        raise KeyError(dimension)


@dataclass(frozen=True, slots=True)
class ViewWork:
    source: SourceEvidence
    geometry: ReconciliationGeometry
    quality: Any
    uncertainty: Any
    public_evidence: dict[str, object]
    preview: PreviewWrite


@dataclass(frozen=True, slots=True)
class ReconciliationBundle:
    succeeded: bool
    dimensions: tuple[dict[str, object], dict[str, object], dict[str, object]]
    final_dimensions: dict[str, float] | None
    overall_quality: dict[str, object] | None
    overall_uncertainty_mm: float | None
    warnings: tuple[str, ...]
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class SuccessEvidence:
    loaded_sources: tuple[SourceEvidence, SourceEvidence, SourceEvidence]
    source_fingerprint: str
    per_view: tuple[dict[str, object], dict[str, object], dict[str, object]]
    reconciliation: ReconciliationBundle
    previews: FinalizedMeasurementPreviewBatch


@dataclass(frozen=True, slots=True)
class FailureEvidence:
    error: ApplicationError
    loaded_sources: tuple[SourceEvidence, ...]
    source_fingerprint: str | None
    per_view: tuple[dict[str, object], ...]
    reconciliation: tuple[dict[str, object], ...] | None
    warnings: tuple[str, ...]


class PersistenceAdapter(Protocol):
    def snapshots(self, settings: MeasurementSettings) -> tuple[Any, Any]: ...

    def claim(
        self,
        session: Session,
        scan_id: str,
        request: MeasurementRequest,
        capture_snapshot: Any,
        policy_snapshot: Any,
    ) -> MeasurementClaim: ...

    def succeed(
        self,
        session: Session,
        attempt: MeasurementAttempt,
        evidence: SuccessEvidence,
    ) -> MeasurementAttempt: ...

    def fail(
        self,
        session: Session,
        attempt: MeasurementAttempt,
        evidence: FailureEvidence,
    ) -> MeasurementAttempt: ...


class GeometryAdapter(Protocol):
    def policy(self, policy_snapshot: Any, capture_snapshot: Any) -> Any: ...

    def rig(self, capture_snapshot: Any) -> Any: ...

    def marker(
        self,
        image_bgr: Any,
        profile: MarkerProfileSpec,
    ) -> MarkerAnalysisResult: ...

    def rectify(self, image_bgr: Any, marker: MarkerAnalysisResult, policy: Any) -> Any: ...

    def foreground(self, rectification: Any, view: ImageView, policy: Any) -> Any: ...

    def contour(self, foreground: Any, policy: Any) -> Any: ...

    def measure(self, contour: Any, view: ImageView, policy: Any) -> Any: ...

    def quality(
        self,
        marker: MarkerAnalysisResult,
        rectification: Any,
        contour: Any,
        geometry: Any,
        policy: Any,
    ) -> Any: ...

    def uncertainty(
        self,
        marker: MarkerAnalysisResult,
        rectification: Any,
        geometry: Any,
        rig: Any,
    ) -> Any: ...

    def require_quality(self, quality: Any, geometry: Any, policy: Any) -> None: ...

    def preview(self, rectification: Any, geometry: Any, policy: Any) -> Any: ...

    def view_evidence(
        self,
        loaded: LoadedStoredImage,
        profile: MarkerProfileSpec,
        marker: MarkerAnalysisResult,
        rectification: Any,
        foreground: Any,
        contour: Any,
        geometry: Any,
        quality: Any,
        uncertainty: Any,
        policy: Any,
    ) -> dict[str, object]: ...

    def reconcile(
        self,
        work: tuple[ViewWork, ViewWork, ViewWork],
        policy: Any,
    ) -> ReconciliationBundle: ...


class SourceResolver(Protocol):
    def resolve(
        self,
        session: Session,
        attempt: MeasurementAttempt,
    ) -> tuple[ScanImage, ScanImage, ScanImage]: ...


@dataclass(frozen=True, slots=True)
class StageDeadlines:
    total_seconds: float = 105.0
    source_seconds: float = 8.0
    marker_seconds: float = 15.0
    rectification_seconds: float = 15.0
    foreground_seconds: float = 20.0
    contour_seconds: float = 10.0
    geometry_seconds: float = 10.0
    quality_seconds: float = 5.0
    preview_seconds: float = 10.0
    reconciliation_seconds: float = 5.0
    storage_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value) and value > 0.0
            for value in (
                self.total_seconds,
                self.source_seconds,
                self.marker_seconds,
                self.rectification_seconds,
                self.foreground_seconds,
                self.contour_seconds,
                self.geometry_seconds,
                self.quality_seconds,
                self.preview_seconds,
                self.reconciliation_seconds,
                self.storage_seconds,
            )
        ):
            raise ValueError("Stage deadlines must be finite and positive")


class _StageTimer:
    def __init__(self, deadlines: StageDeadlines, clock: Callable[[], float]) -> None:
        self.deadlines = deadlines
        self.clock = clock
        self.started = clock()

    def run(
        self,
        name: str,
        limit_seconds: float,
        operation: Callable[[], T],
        *,
        view: ImageView | None = None,
    ) -> T:
        self._check_total()
        started = self.clock()
        result = operation()
        elapsed = self.clock() - started
        if not math.isfinite(elapsed) or elapsed > limit_seconds:
            raise _processing_interrupted_error(name, view)
        self._check_total()
        return result

    def _check_total(self) -> None:
        elapsed = self.clock() - self.started
        if not math.isfinite(elapsed) or elapsed > self.deadlines.total_seconds:
            raise _processing_interrupted_error("total", None)


class MeasurementApplicationService:
    """Process top, front, and side sequentially under one leased immutable attempt."""

    def __init__(
        self,
        settings: MeasurementSettings,
        *,
        persistence: PersistenceAdapter | None = None,
        geometry: GeometryAdapter | None = None,
        source_resolver: SourceResolver | None = None,
        image_loader: StoredImageLoader | None = None,
        storage: MeasurementStorage | None = None,
        deadlines: StageDeadlines | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.persistence = persistence or _DefaultPersistenceAdapter(
            settings.measurement_processing_lease_seconds
        )
        self.geometry = geometry or _DefaultGeometryAdapter()
        self.source_resolver = source_resolver or _DatabaseSourceResolver()
        self.image_loader = image_loader or StoredImageLoader(
            settings.data_root,
            max_file_size_bytes=settings.max_upload_bytes,
            max_decoded_pixels=settings.max_image_pixels,
        )
        self.storage = storage or MeasurementStorage(settings)
        self.deadlines = deadlines or StageDeadlines(
            total_seconds=settings.measurement_processing_deadline_seconds,
        )
        self.clock = clock

    def process(
        self,
        session: Session,
        scan_id: str,
        request: MeasurementRequest,
    ) -> tuple[MeasurementAttempt, bool]:
        """Claim/replay one request, then process and finalize it synchronously."""
        if not request.capture_contract_acknowledged:
            raise ApplicationError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="INVALID_REQUEST",
                message="The physical capture contract must be acknowledged.",
                recoverable=True,
                suggested_action="Review the configured rig requirements and confirm them.",
                field="capture_contract_acknowledged",
            )
        capture_snapshot, policy_snapshot = self.persistence.snapshots(self.settings)
        claim = self.persistence.claim(
            session,
            scan_id,
            request,
            capture_snapshot,
            policy_snapshot,
        )
        attempt = claim.attempt
        if claim.replayed:
            return attempt, True

        timer = _StageTimer(self.deadlines, self.clock)
        loaded: list[SourceEvidence] = []
        work: list[ViewWork] = []
        staged: StagedMeasurementPreviewBatch | None = None
        finalized: FinalizedMeasurementPreviewBatch | None = None
        reconciliation: ReconciliationBundle | None = None
        lease_owned = True
        failure_persist_started = False
        try:
            profile = _profile_spec(attempt.profile_snapshot_json)
            policy = self.geometry.policy(policy_snapshot, capture_snapshot)
            rig = self.geometry.rig(capture_snapshot)
            source_models = self.source_resolver.resolve(session, attempt)

            for source in source_models:
                view = source.view_type
                loaded_source = timer.run(
                    "source_validation",
                    self.deadlines.source_seconds,
                    partial(self.image_loader.load, source),
                    view=view,
                )
                source_evidence = _source_evidence(loaded_source)
                loaded.append(source_evidence)
                marker = timer.run(
                    "reference_detection",
                    self.deadlines.marker_seconds,
                    partial(
                        self.geometry.marker,
                        loaded_source.image_bgr,
                        profile,
                    ),
                    view=view,
                )
                rectification = timer.run(
                    "perspective_rectification",
                    self.deadlines.rectification_seconds,
                    partial(
                        self.geometry.rectify,
                        loaded_source.image_bgr,
                        marker,
                        policy,
                    ),
                    view=view,
                )
                foreground = timer.run(
                    "foreground_extraction",
                    self.deadlines.foreground_seconds,
                    partial(
                        self.geometry.foreground,
                        rectification,
                        view,
                        policy,
                    ),
                    view=view,
                )
                contour = timer.run(
                    "product_contour_selection",
                    self.deadlines.contour_seconds,
                    partial(self.geometry.contour, foreground, policy),
                    view=view,
                )
                geometry = timer.run(
                    "product_geometry",
                    self.deadlines.geometry_seconds,
                    partial(
                        self.geometry.measure,
                        contour,
                        view,
                        policy,
                    ),
                    view=view,
                )
                quality = timer.run(
                    "quality_evidence",
                    self.deadlines.quality_seconds,
                    partial(
                        self.geometry.quality,
                        marker,
                        rectification,
                        contour,
                        geometry,
                        policy,
                    ),
                    view=view,
                )
                uncertainty = timer.run(
                    "uncertainty_evidence",
                    self.deadlines.quality_seconds,
                    partial(
                        self.geometry.uncertainty,
                        marker,
                        rectification,
                        geometry,
                        rig,
                    ),
                    view=view,
                )
                self.geometry.require_quality(quality, geometry, policy)
                encoded = timer.run(
                    "annotated_preview",
                    self.deadlines.preview_seconds,
                    partial(
                        self.geometry.preview,
                        rectification,
                        geometry,
                        policy,
                    ),
                    view=view,
                )
                public_evidence = self.geometry.view_evidence(
                    loaded_source,
                    profile,
                    marker,
                    rectification,
                    foreground,
                    contour,
                    geometry,
                    quality,
                    uncertainty,
                    policy,
                )
                preview = _preview_write(view, encoded)
                reconciliation_geometry = _reconciliation_geometry(geometry)
                work.append(
                    ViewWork(
                        source=source_evidence,
                        geometry=reconciliation_geometry,
                        quality=quality,
                        uncertainty=uncertainty,
                        public_evidence=public_evidence,
                        preview=preview,
                    )
                )
                del loaded_source, marker, rectification, foreground, contour, geometry, encoded

            work_tuple = cast(tuple[ViewWork, ViewWork, ViewWork], tuple(work))
            reconciliation = timer.run(
                "cross_view_reconciliation",
                self.deadlines.reconciliation_seconds,
                lambda: self.geometry.reconcile(work_tuple, policy),
            )
            if not reconciliation.succeeded or reconciliation.final_dimensions is None:
                raise _reconciliation_error(reconciliation.failure_code)

            loaded_tuple = cast(
                tuple[SourceEvidence, SourceEvidence, SourceEvidence],
                tuple(loaded),
            )
            self._verify_sources_unchanged(timer, source_models, loaded_tuple)
            staged_batch = timer.run(
                "preview_staging",
                self.deadlines.storage_seconds,
                lambda: self.storage.stage(
                    attempt.scan_id,
                    attempt.id,
                    tuple(item.preview for item in work_tuple),
                ),
            )
            staged = staged_batch
            finalized = timer.run(
                "preview_finalization",
                self.deadlines.storage_seconds,
                partial(self.storage.finalize, staged_batch),
            )
            staged = None
            evidence = SuccessEvidence(
                loaded_sources=loaded_tuple,
                source_fingerprint=_source_fingerprint(loaded_tuple),
                per_view=(
                    work_tuple[0].public_evidence,
                    work_tuple[1].public_evidence,
                    work_tuple[2].public_evidence,
                ),
                reconciliation=reconciliation,
                previews=finalized,
            )
            try:
                terminal = self.persistence.succeed(session, attempt, evidence)
            except ApplicationError as error:
                self.storage.cleanup_finalized(finalized)
                finalized = None
                if error.payload.code == "PROCESSING_INTERRUPTED":
                    lease_owned = False
                    raise
                failure = _failure_evidence(
                    error,
                    loaded,
                    work,
                    reconciliation,
                )
                failure_persist_started = True
                return self.persistence.fail(session, attempt, failure), False
            finalized = None
            return terminal, False
        except ApplicationError as error:
            self._compensate(staged, finalized)
            if not lease_owned or failure_persist_started:
                raise
            failure = _failure_evidence(error, loaded, work, reconciliation)
            return self.persistence.fail(session, attempt, failure), False
        except (ArithmeticError, MemoryError, TypeError, ValueError, cv2.error) as error:
            self._compensate(staged, finalized)
            safe_error = _processing_interrupted_error("geometry", None)
            failure = _failure_evidence(safe_error, loaded, work, reconciliation)
            try:
                return self.persistence.fail(session, attempt, failure), False
            except ApplicationError:
                raise
            finally:
                del error

    def _verify_sources_unchanged(
        self,
        timer: _StageTimer,
        models: tuple[ScanImage, ScanImage, ScanImage],
        loaded: tuple[SourceEvidence, SourceEvidence, SourceEvidence],
    ) -> None:
        for model, previous in zip(models, loaded, strict=True):
            current = timer.run(
                "source_revalidation",
                self.deadlines.source_seconds,
                partial(self.image_loader.load, model),
                view=model.view_type,
            )
            if (
                current.scan_image_id != previous.scan_image_id
                or current.original_sha256 != previous.original_sha256
                or current.oriented_pixel_sha256 != previous.oriented_pixel_sha256
            ):
                raise _source_changed_error(model.view_type)
            del current

    def _compensate(
        self,
        staged: StagedMeasurementPreviewBatch | None,
        finalized: FinalizedMeasurementPreviewBatch | None,
    ) -> None:
        if finalized is not None:
            self.storage.cleanup_finalized(finalized)
        elif staged is not None:
            self.storage.cleanup_staged(staged)


class _DatabaseSourceResolver:
    def resolve(
        self,
        session: Session,
        attempt: MeasurementAttempt,
    ) -> tuple[ScanImage, ScanImage, ScanImage]:
        ordered_sources = _ordered_attempt_sources(attempt.sources)
        try:
            models = session.scalars(
                select(ScanImage).where(
                    ScanImage.id.in_(source.scan_image_id for source in ordered_sources)
                )
            ).all()
        except SQLAlchemyError as error:
            session.rollback()
            raise _database_unavailable_error() from error
        by_id = {model.id: model for model in models}
        ordered_models: list[ScanImage] = []
        for source in ordered_sources:
            model = by_id.get(source.scan_image_id)
            if model is None:
                raise _source_unavailable_error(ImageView(source.view.value))
            view = ImageView(source.view.value)
            if (
                model.view_type is not view
                or model.storage_key != source.storage_key_snapshot
                or model.media_type != source.media_type
                or model.size_bytes != source.size_bytes
                or model.width_px != source.width_px
                or model.height_px != source.height_px
            ):
                raise _source_changed_error(view)
            ordered_models.append(model)
        return cast(tuple[ScanImage, ScanImage, ScanImage], tuple(ordered_models))


class _DefaultGeometryAdapter:
    def __init__(self) -> None:
        self.full_plane = importlib.import_module("backend.app.vision.full_plane")
        self.foreground_module = importlib.import_module("backend.app.vision.foreground")
        self.contour_module = importlib.import_module("backend.app.vision.product_contours")
        self.geometry_module = importlib.import_module("backend.app.vision.oriented_geometry")
        self.quality_module = importlib.import_module("backend.app.vision.measurement_quality")
        self.reconciliation_module = importlib.import_module(
            "backend.app.vision.reconciliation"
        )
        self.preview_module = importlib.import_module("backend.app.vision.geometry_previews")

    def policy(self, policy_snapshot: Any, capture_snapshot: Any) -> Any:
        return self.full_plane.GeometryPolicy(
            acceptable_absolute_mm=policy_snapshot.acceptable_absolute_mm,
            acceptable_relative_percent=policy_snapshot.acceptable_relative_percent,
            warning_absolute_mm=policy_snapshot.warning_absolute_mm,
            warning_relative_percent=policy_snapshot.warning_relative_percent,
            usable_quality=policy_snapshot.usable_quality,
            weak_quality=policy_snapshot.weak_quality,
            stronger_source_quality_lead=policy_snapshot.stronger_source_quality_lead,
            weaker_source_uncertainty_ratio=policy_snapshot.weaker_source_uncertainty_ratio,
            maximum_rectified_edge_px=policy_snapshot.maximum_rectified_edge_px,
            maximum_rectified_pixels=policy_snapshot.maximum_rectified_pixels,
            maximum_physical_extent_mm=policy_snapshot.maximum_physical_extent_mm,
            maximum_connected_components=policy_snapshot.maximum_connected_components,
            maximum_scored_candidates=policy_snapshot.maximum_scored_candidates,
            maximum_preview_edge_px=policy_snapshot.maximum_preview_long_edge_px,
            maximum_preview_bytes=policy_snapshot.maximum_preview_encoded_size,
            minimum_object_mm=capture_snapshot.minimum_object_mm,
            maximum_object_mm=capture_snapshot.maximum_object_mm,
        )

    def rig(self, capture_snapshot: Any) -> Any:
        return self.quality_module.RigUncertaintySpec(
            marker_size_mm=capture_snapshot.marker_size_uncertainty_mm,
            plane_mm=capture_snapshot.plane_uncertainty_mm,
            orthogonality_degrees=capture_snapshot.orthogonality_uncertainty_deg,
            mount_standoff_mm=capture_snapshot.standoff_uncertainty_mm,
            maximum_off_plane_mm=capture_snapshot.maximum_off_plane_mm,
        )

    def marker(self, image_bgr: Any, profile: MarkerProfileSpec) -> MarkerAnalysisResult:
        return analyze_marker_image(image_bgr, profile)

    def rectify(self, image_bgr: Any, marker: MarkerAnalysisResult, policy: Any) -> Any:
        return self.full_plane.rectify_full_plane(image_bgr, marker, policy)

    def foreground(self, rectification: Any, view: ImageView, policy: Any) -> Any:
        return self.foreground_module.extract_foreground(
            rectification,
            rectification.marker_polygon_px,
            view,
            policy,
        )

    def contour(self, foreground: Any, policy: Any) -> Any:
        return self.contour_module.select_product_contour(foreground, policy)

    def measure(self, contour: Any, view: ImageView, policy: Any) -> Any:
        return self.geometry_module.measure_product_geometry(contour, view, policy)

    def quality(
        self,
        marker: MarkerAnalysisResult,
        rectification: Any,
        contour: Any,
        geometry: Any,
        policy: Any,
    ) -> Any:
        return self.quality_module.calculate_view_quality(
            marker,
            rectification,
            contour,
            geometry,
            policy,
        )

    def uncertainty(
        self,
        marker: MarkerAnalysisResult,
        rectification: Any,
        geometry: Any,
        rig: Any,
    ) -> Any:
        return self.quality_module.calculate_view_uncertainty(
            marker,
            rectification,
            geometry,
            rig,
        )

    def require_quality(self, quality: Any, geometry: Any, policy: Any) -> None:
        self.quality_module.require_minimum_view_quality(quality, geometry, policy)

    def preview(self, rectification: Any, geometry: Any, policy: Any) -> Any:
        return self.preview_module.create_geometry_preview(rectification, geometry, policy)

    def view_evidence(
        self,
        loaded: LoadedStoredImage,
        profile: MarkerProfileSpec,
        marker: MarkerAnalysisResult,
        rectification: Any,
        foreground: Any,
        contour: Any,
        geometry: Any,
        quality: Any,
        uncertainty: Any,
        policy: Any,
    ) -> dict[str, object]:
        warnings = [] if quality.score >= policy.usable_quality else ["VIEW_QUALITY_WEAK"]
        lab_mad = foreground.background_lab_mad
        return {
            "view": loaded.view.value,
            "source": _source_record(loaded),
            "marker": _marker_record(profile, marker),
            "rectification": {
                "width_px": rectification.width_px,
                "height_px": rectification.height_px,
                "pixels_per_mm": rectification.pixels_per_mm,
                "physical_origin_mm": {
                    "x_mm": rectification.origin_mm[0],
                    "y_mm": rectification.origin_mm[1],
                },
                "source_to_rectified": rectification.source_to_rectified,
                "rectified_to_source": rectification.rectified_to_source,
                "physical_width_mm": rectification.physical_width_mm,
                "physical_height_mm": rectification.physical_height_mm,
            },
            "foreground": {
                "background_lab_median": _lab_record(foreground.background_lab_median),
                "background_lab_mad": _lab_record(lab_mad),
                "background_grayscale_median": foreground.grayscale_background_median,
                "foreground_grayscale_difference": foreground.grayscale_foreground_difference,
                "supported_signals": list(foreground.supported_signal_names),
                "supported_signal_count": len(foreground.supported_signal_names),
                "component_count": contour.component_count,
                "scored_candidate_count": contour.scored_candidate_count,
                "selected_candidate_score": contour.selected_score,
                "runner_up_candidate_score": contour.runner_up_score,
                "strong_core_coverage": contour.strong_core_coverage,
                "mask_stability": contour.mask_stability,
                "shadow_fraction": foreground.shadow_fraction,
                "reflection_fraction": foreground.reflection_fraction,
                "marker_clearance_mm": contour.marker_clearance_mm,
                "border_clearance_mm": contour.border_clearance_mm,
                "contour_area_mm2": contour.contour_area_mm2,
                "hull_area_mm2": contour.hull_area_mm2,
                "solidity": contour.solidity,
                "extent": contour.extent,
                "oriented_box_corners_mm": [
                    {"x_mm": point[0], "y_mm": point[1]}
                    for point in geometry.oriented_box_corners_mm
                ],
                "oriented_box_angle_degrees": geometry.oriented_box_angle_degrees,
                "threshold_variant_span_mm": geometry.threshold_variant_span_mm,
                "morphology_variant_span_mm": geometry.morphology_variant_span_mm,
            },
            "raw_dimensions_mm": {
                item.dimension.value: item.value_mm for item in geometry.raw_dimensions
            },
            "quality": _public_dataclass_record(quality),
            "uncertainty": _public_dataclass_record(uncertainty),
            "warnings": warnings,
            "preview_available": True,
        }

    def reconcile(
        self,
        work: tuple[ViewWork, ViewWork, ViewWork],
        policy: Any,
    ) -> ReconciliationBundle:
        input_type = self.reconciliation_module.ViewMeasurementInput
        result = self.reconciliation_module.reconcile_measurements(
            input_type(work[0].source.view, work[0].geometry, work[0].quality, work[0].uncertainty),
            input_type(work[1].source.view, work[1].geometry, work[1].quality, work[1].uncertainty),
            input_type(work[2].source.view, work[2].geometry, work[2].quality, work[2].uncertainty),
            policy,
        )
        dimension_records = tuple(_dimension_record(item) for item in result.dimensions)
        qualities = [float(item.quality.score) for item in work]
        warnings = tuple(
            dict.fromkeys(
                warning
                for item in result.dimensions
                for warning in item.warnings
            )
        )
        finals = (
            {
                dimension.value: float(value)
                for dimension, value in result.final_dimensions_mm.items()
            }
            if result.final_dimensions_mm is not None
            else None
        )
        return ReconciliationBundle(
            succeeded=bool(result.succeeded),
            dimensions=cast(
                tuple[dict[str, object], dict[str, object], dict[str, object]],
                dimension_records,
            ),
            final_dimensions=finals,
            overall_quality=(
                {
                    "score": min(qualities),
                    "minimum_view_score": min(qualities),
                    "view_scores": {
                        "top": qualities[0],
                        "front": qualities[1],
                        "side": qualities[2],
                    },
                }
                if result.succeeded
                else None
            ),
            overall_uncertainty_mm=result.overall_uncertainty_mm,
            warnings=warnings,
            failure_code=result.failure_code,
        )


class _DefaultPersistenceAdapter:
    def __init__(self, lease_seconds: int) -> None:
        if lease_seconds <= 0:
            raise ValueError("Measurement lease duration must be positive")
        self.lease_seconds = lease_seconds
        self.schemas = importlib.import_module("backend.app.schemas.measurements")
        self.contracts = importlib.import_module("backend.app.measurement_contracts")
        self.results = importlib.import_module("backend.app.services.measurement_results")

    def snapshots(self, settings: MeasurementSettings) -> tuple[Any, Any]:
        return (
            self.schemas.capture_setup_snapshot(settings),
            self.schemas.measurement_policy_snapshot(settings),
        )

    def claim(
        self,
        session: Session,
        scan_id: str,
        request: MeasurementRequest,
        capture_snapshot: Any,
        policy_snapshot: Any,
    ) -> MeasurementClaim:
        return cast(
            MeasurementClaim,
            self.results.claim_measurement_attempt(
                session,
                scan_id,
                request,
                capture_snapshot,
                policy_snapshot,
                lease_seconds=self.lease_seconds,
            ),
        )

    def succeed(
        self,
        session: Session,
        attempt: MeasurementAttempt,
        evidence: SuccessEvidence,
    ) -> MeasurementAttempt:
        source_updates = self._source_updates(attempt, evidence.loaded_sources)
        preview_inputs = tuple(
            self.contracts.PreviewPersistenceInput(
                preview_id=str(uuid4()),
                view=self.contracts.MeasurementView(preview.view.value),
                kind=self.contracts.PreviewKind.ANNOTATED,
                storage_key=preview.storage_key,
                sha256=preview.sha256,
                media_type=preview.media_type,
                size_bytes=preview.size_bytes,
                width_px=preview.width_px,
                height_px=preview.height_px,
            )
            for preview in evidence.previews.previews
        )
        finals = evidence.reconciliation.final_dimensions
        if finals is None or evidence.reconciliation.overall_quality is None:
            raise ValueError("Successful evidence requires final dimensions and quality")
        result = self.contracts.MeasurementSuccessPersistenceInput(
            source_fingerprint=evidence.source_fingerprint,
            length_mm=finals["length"],
            width_mm=finals["width"],
            height_mm=finals["height"],
            per_view_evidence_json=_canonical_json(list(evidence.per_view)),
            reconciliation_evidence_json=_canonical_json(
                list(evidence.reconciliation.dimensions)
            ),
            quality_evidence_json=_canonical_json(
                evidence.reconciliation.overall_quality
            ),
            uncertainty_evidence_json=_canonical_json(
                evidence.reconciliation.overall_uncertainty_mm
            ),
            warnings_json=_canonical_json(list(evidence.reconciliation.warnings)),
            source_updates=source_updates,
            previews=preview_inputs,
        )
        return cast(
            MeasurementAttempt,
            self.results.succeed_measurement_attempt(
                session,
                attempt.id,
                attempt.lease_token,
                result,
            ),
        )

    def fail(
        self,
        session: Session,
        attempt: MeasurementAttempt,
        evidence: FailureEvidence,
    ) -> MeasurementAttempt:
        source_updates = self._source_updates(attempt, evidence.loaded_sources)
        payload = evidence.error.payload.model_dump(mode="json", exclude_none=True)
        result = self.contracts.MeasurementFailurePersistenceInput(
            failure_json=_canonical_json(payload),
            source_fingerprint=evidence.source_fingerprint,
            per_view_evidence_json=(
                _canonical_json(list(evidence.per_view)) if evidence.per_view else None
            ),
            reconciliation_evidence_json=(
                _canonical_json(list(evidence.reconciliation))
                if evidence.reconciliation is not None
                else None
            ),
            warnings_json=(
                _canonical_json(list(evidence.warnings)) if evidence.warnings else None
            ),
            source_updates=source_updates,
        )
        return cast(
            MeasurementAttempt,
            self.results.fail_measurement_attempt(
                session,
                attempt.id,
                attempt.lease_token,
                result,
            ),
        )

    def _source_updates(
        self,
        attempt: MeasurementAttempt,
        loaded: Sequence[SourceEvidence],
    ) -> tuple[Any, ...]:
        source_ids = {source.scan_image_id: source.id for source in attempt.sources}
        return tuple(
            self.contracts.SourceFingerprintUpdate(
                source_id=source_ids[item.scan_image_id],
                original_sha256=item.original_sha256,
                oriented_pixel_sha256=item.oriented_pixel_sha256,
            )
            for item in loaded
        )


def _ordered_attempt_sources(
    sources: Sequence[AttemptSource],
) -> tuple[AttemptSource, AttemptSource, AttemptSource]:
    by_view = {ImageView(source.view.value): source for source in sources}
    if set(by_view) != set(REQUIRED_IMAGE_VIEW_ORDER):
        raise ApplicationError(
            status_code=status.HTTP_409_CONFLICT,
            code="SOURCE_IMAGE_CHANGED",
            message="The saved measurement source set is invalid.",
            recoverable=True,
            suggested_action="Create a new measurement attempt from a complete scan.",
        )
    return (by_view[ImageView.TOP], by_view[ImageView.FRONT], by_view[ImageView.SIDE])


def _profile_spec(profile_snapshot_json: str) -> MarkerProfileSpec:
    try:
        profile = CalibrationProfileResponse.model_validate_json(profile_snapshot_json)
    except (TypeError, ValueError) as error:
        raise _processing_interrupted_error("profile_snapshot", None) from error
    return MarkerProfileSpec(
        dictionary=profile.dictionary,
        marker_id=profile.marker_id,
        marker_size_mm=profile.marker_size_mm,
        border_bits=profile.border_bits,
        minimum_marker_side_px=profile.minimum_marker_side_px,
        maximum_perspective_ratio=profile.maximum_perspective_ratio,
        maximum_homography_condition_number=profile.maximum_homography_condition_number,
        maximum_marker_edge_residual_px=profile.maximum_marker_edge_residual_px,
        rectified_pixels_per_mm=profile.rectified_pixels_per_mm,
    )


def _preview_write(view: ImageView, encoded: Any) -> PreviewWrite:
    return PreviewWrite(
        view=view,
        media_type="image/png",
        width_px=int(encoded.width_px),
        height_px=int(encoded.height_px),
        png_bytes=bytes(encoded.data),
    )


def _source_record(source: LoadedStoredImage) -> dict[str, object]:
    return {
        "view": source.view.value,
        "scan_image_id": source.scan_image_id,
        "original_sha256": source.original_sha256,
        "oriented_pixel_sha256": source.oriented_pixel_sha256,
        "media_type": source.media_type,
        "size_bytes": source.size_bytes,
        "width_px": source.width_px,
        "height_px": source.height_px,
    }


def _source_evidence(source: LoadedStoredImage) -> SourceEvidence:
    return SourceEvidence(
        scan_image_id=source.scan_image_id,
        view=source.view,
        original_sha256=source.original_sha256,
        oriented_pixel_sha256=source.oriented_pixel_sha256,
        media_type=source.media_type,
        size_bytes=source.size_bytes,
        width_px=source.width_px,
        height_px=source.height_px,
    )


def _reconciliation_geometry(geometry: Any) -> ReconciliationGeometry:
    values = tuple(
        (DimensionName(item.dimension.value), float(item.value_mm))
        for item in geometry.raw_dimensions
    )
    if len(values) != 2:
        raise ValueError("Each view must provide exactly two raw dimensions")
    return ReconciliationGeometry(
        view=ImageView(geometry.view.value),
        values_mm=(values[0], values[1]),
    )


def _marker_record(
    profile: MarkerProfileSpec,
    marker: MarkerAnalysisResult,
) -> dict[str, object]:
    return {
        "dictionary": marker.dictionary.value,
        "marker_id": marker.marker_id,
        "marker_size_mm": profile.marker_size_mm,
        "ordered_corners": [
            {"label": corner.label.value, "x_px": corner.x_px, "y_px": corner.y_px}
            for corner in marker.ordered_corners
        ],
        "orientation_degrees": marker.orientation_degrees,
        "edge_lengths_px": _public_dataclass_record(marker.edge_lengths_px),
        "perspective_ratio": marker.perspective_ratio,
        "image_to_plane_mm": marker.image_to_marker_mm,
        "plane_mm_to_image": marker.marker_mm_to_image,
        "homography_condition_number": marker.homography_condition_number,
        "marker_edge_quality": {
            **_public_dataclass_record(marker.marker_edge_quality),
            "per_edge_rms_px": _public_dataclass_record(
                marker.marker_edge_quality.per_edge_rms_px
            ),
        },
    }


def _lab_record(values: Sequence[float]) -> dict[str, float]:
    if len(values) != 3 or not all(math.isfinite(float(value)) for value in values):
        raise ValueError("LAB evidence must contain three finite channels")
    return {"l": float(values[0]), "a": float(values[1]), "b": float(values[2])}


def _public_dataclass_record(value: Any) -> dict[str, object]:
    fields = getattr(value, "__dataclass_fields__", None)
    if not isinstance(fields, dict):
        raise ValueError("Evidence must be a frozen dataclass")
    return {name: getattr(value, name) for name in fields}


def _dimension_record(item: Any) -> dict[str, object]:
    return {
        "dimension": item.dimension.value,
        "contributing_views": [view.value for view in item.contributing_views],
        "raw_values_mm": {view.value: value for view, value in item.raw_values_mm},
        "value_mm": item.value_mm,
        "absolute_disagreement_mm": item.absolute_disagreement_mm,
        "relative_disagreement_percent": item.relative_disagreement_percent,
        "quality_inputs": {view.value: value for view, value in item.quality_inputs},
        "uncertainty_inputs_mm": {
            view.value: value for view, value in item.uncertainty_inputs_mm
        },
        "uncertainty_mm": item.uncertainty_mm,
        "reconciliation_rule": item.reconciliation_rule.value,
        "validation_status": item.validation_status.value,
        "warnings": list(item.warnings),
    }


def _source_fingerprint(sources: Sequence[SourceEvidence]) -> str:
    evidence = [
        {
            "view": source.view.value,
            "scan_image_id": source.scan_image_id,
            "original_sha256": source.original_sha256,
            "oriented_pixel_sha256": source.oriented_pixel_sha256,
            "media_type": source.media_type,
            "size_bytes": source.size_bytes,
            "width_px": source.width_px,
            "height_px": source.height_px,
        }
        for source in sources
    ]
    return hashlib.sha256(_canonical_json(evidence).encode("ascii")).hexdigest()


def _failure_evidence(
    error: ApplicationError,
    loaded: Sequence[SourceEvidence],
    work: Sequence[ViewWork],
    reconciliation: ReconciliationBundle | None,
) -> FailureEvidence:
    fingerprint = _source_fingerprint(loaded) if loaded else None
    warnings = tuple(
        dict.fromkeys(
            warning
            for item in work
            for warning in cast(list[str], item.public_evidence.get("warnings", []))
        )
    )
    return FailureEvidence(
        error=error,
        loaded_sources=tuple(loaded),
        source_fingerprint=fingerprint,
        per_view=tuple(
            {**item.public_evidence, "preview_available": False} for item in work
        ),
        reconciliation=(reconciliation.dimensions if reconciliation is not None else None),
        warnings=warnings,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _processing_interrupted_error(stage: str, view: ImageView | None) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="PROCESSING_INTERRUPTED",
        message="Deterministic measurement did not complete within its safe processing limits.",
        recoverable=True,
        suggested_action="Retry processing. If it repeats, recapture the affected view.",
        field=stage,
        view=view,
    )


def _reconciliation_error(code: str | None) -> ApplicationError:
    if code == "MEASUREMENT_UNCERTAINTY_EXCESSIVE":
        return ApplicationError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=code,
            message="The conservative uncertainty is too large for a valid dimension.",
            recoverable=True,
            suggested_action="Improve capture stability and calibration, then recapture all views.",
        )
    return ApplicationError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="MEASUREMENT_DISAGREEMENT",
        message="The required views do not provide a safely reconcilable measurement.",
        recoverable=True,
        suggested_action="Review the evidence and recapture all required views in the rig.",
    )


def _source_unavailable_error(view: ImageView) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="SOURCE_IMAGE_UNAVAILABLE",
        message="A required stored image is unavailable for processing.",
        recoverable=True,
        suggested_action="Verify local storage access, then retry or upload a new scan.",
        field=view.value,
        view=view,
    )


def _source_changed_error(view: ImageView) -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="SOURCE_IMAGE_CHANGED",
        message="A required stored image changed during measurement processing.",
        recoverable=True,
        suggested_action="Create a new scan with the original unmodified image.",
        field=view.value,
        view=view,
    )


def _database_unavailable_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    )
