"""Phase 3 attempt claiming, immutable terminal persistence, and safe reads."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Never
from urllib.parse import quote
from uuid import uuid4

from fastapi import status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.app.contracts import ImageView, ScanStatus
from backend.app.errors import ApplicationError
from backend.app.measurement_contracts import (
    ALGORITHM_VERSION,
    DEFAULT_LEASE_SECONDS,
    DIMENSION_ORDER,
    MAXIMUM_MEASUREMENT_PREVIEW_BYTES,
    MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX,
    MEASUREMENT_VIEW_ORDER,
    PROCESSING_VERSION,
    DimensionName,
    MeasurementClaim,
    MeasurementFailurePersistenceInput,
    MeasurementStatus,
    MeasurementSuccessPersistenceInput,
    MeasurementView,
    PreviewKind,
    PreviewPersistenceInput,
    SourceFingerprintUpdate,
    StaleReason,
)
from backend.app.models.calibration import CalibrationProfile
from backend.app.models.measurement import (
    MeasurementAttempt,
    MeasurementPreview,
    MeasurementSource,
)
from backend.app.models.scan import Scan, ScanImage
from backend.app.schemas.calibration import CalibrationProfileResponse
from backend.app.schemas.measurements import (
    CaptureSetupSnapshotResponse,
    DimensionResultResponse,
    FinalDimensionsResponse,
    MeasurementAttemptDetailResponse,
    MeasurementAttemptListResponse,
    MeasurementAttemptSummaryResponse,
    MeasurementFailure,
    MeasurementPolicySnapshotResponse,
    MeasurementProcessRequest,
    MeasurementSourceResponse,
    OverallQualityEvidenceResponse,
    PerViewMeasurementResponse,
    PreviewDescriptorResponse,
    SafeText,
)

_PER_VIEW_ADAPTER = TypeAdapter(list[PerViewMeasurementResponse])
_DIMENSION_ADAPTER = TypeAdapter(list[DimensionResultResponse])
_WARNINGS_ADAPTER = TypeAdapter(list[SafeText])
_FLOAT_ADAPTER = TypeAdapter(float)


def canonical_json(value: object) -> str:
    """Return stable compact JSON for signatures and immutable snapshots."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def request_signature(request: MeasurementProcessRequest) -> str:
    return canonical_json(request.model_dump(mode="json"))


def claim_measurement_attempt(
    session: Session,
    scan_id: str,
    request: MeasurementProcessRequest,
    capture_snapshot: CaptureSetupSnapshotResponse,
    policy_snapshot: MeasurementPolicySnapshotResponse,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> MeasurementClaim:
    """Atomically replay, reclaim, or create one processing attempt."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    signature = request_signature(request)
    now = datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    new_lease_token = str(uuid4())
    try:
        _begin_immediate(session)
        existing = session.scalar(
            select(MeasurementAttempt)
            .options(
                selectinload(MeasurementAttempt.sources),
                selectinload(MeasurementAttempt.previews),
            )
            .where(
                MeasurementAttempt.scan_id == scan_id,
                MeasurementAttempt.request_id == str(request.request_id),
            )
        )
        if existing is not None:
            if existing.request_signature != signature:
                _rollback_quietly(session)
                raise _request_conflict()
            if existing.status is not MeasurementStatus.PROCESSING:
                session.commit()
                return MeasurementClaim(existing, replayed=True, reclaimed=False)
            if _as_utc(existing.lease_expires_at) > now:
                _rollback_quietly(session)
                raise _measurement_in_progress()
            existing.lease_token = new_lease_token
            existing.lease_expires_at = lease_expires_at
            session.commit()
            return MeasurementClaim(existing, replayed=False, reclaimed=True)

        active_processing = session.scalar(
            select(MeasurementAttempt).where(
                MeasurementAttempt.scan_id == scan_id,
                MeasurementAttempt.status == MeasurementStatus.PROCESSING,
            )
        )
        if active_processing is not None:
            _rollback_quietly(session)
            raise _measurement_in_progress()

        scan = session.scalar(
            select(Scan).options(selectinload(Scan.images)).where(Scan.id == scan_id)
        )
        if scan is None:
            _rollback_quietly(session)
            raise _scan_not_found()
        required_images = _required_images(scan)
        if scan.status is not ScanStatus.READY_FOR_PROCESSING or required_images is None:
            _rollback_quietly(session)
            raise _scan_not_ready()

        if not capture_snapshot.qualified:
            _rollback_quietly(session)
            raise _capture_setup_unqualified()
        if request.expected_capture_setup_id != capture_snapshot.id:
            _rollback_quietly(session)
            raise _capture_setup_mismatch()

        profile = session.scalar(
            select(CalibrationProfile).where(CalibrationProfile.is_active.is_(True))
        )
        if profile is None:
            _rollback_quietly(session)
            raise _active_profile_required()
        if profile.id != str(request.expected_calibration_profile_id):
            _rollback_quietly(session)
            raise _active_profile_changed()

        terminal_attempts = session.scalars(
            select(MeasurementAttempt).where(
                MeasurementAttempt.scan_id == scan_id,
                MeasurementAttempt.status.in_(
                    (MeasurementStatus.SUCCEEDED, MeasurementStatus.FAILED)
                ),
            )
        ).all()
        reprocess_id = (
            str(request.reprocess_of_measurement_id)
            if request.reprocess_of_measurement_id is not None
            else None
        )
        if terminal_attempts and reprocess_id is None:
            _rollback_quietly(session)
            raise _reprocess_confirmation_required()
        if reprocess_id is not None and not any(
            attempt.id == reprocess_id for attempt in terminal_attempts
        ):
            _rollback_quietly(session)
            raise _measurement_not_found()

        profile_snapshot = CalibrationProfileResponse.model_validate(profile)
        attempt = MeasurementAttempt(
            id=str(uuid4()),
            scan_id=scan.id,
            request_id=str(request.request_id),
            request_signature=signature,
            reprocess_of_measurement_id=reprocess_id,
            calibration_profile_id=profile.id,
            status=MeasurementStatus.PROCESSING,
            processing_version=PROCESSING_VERSION,
            algorithm_version=ALGORITHM_VERSION,
            profile_snapshot_json=canonical_json(profile_snapshot.model_dump(mode="json")),
            capture_setup_snapshot_json=canonical_json(
                capture_snapshot.model_dump(mode="json")
            ),
            measurement_policy_snapshot_json=canonical_json(
                policy_snapshot.model_dump(mode="json")
            ),
            lease_token=new_lease_token,
            lease_expires_at=lease_expires_at,
            created_at=now,
            started_at=now,
        )
        attempt.sources = [
            MeasurementSource(
                id=str(uuid4()),
                view=view,
                scan_image_id=image.id,
                storage_key_snapshot=image.storage_key,
                media_type=image.media_type,
                size_bytes=image.size_bytes,
                width_px=image.width_px,
                height_px=image.height_px,
            )
            for view, image in zip(MEASUREMENT_VIEW_ORDER, required_images, strict=True)
        ]
        session.add(attempt)
        session.commit()
        return MeasurementClaim(attempt, replayed=False, reclaimed=False)
    except ApplicationError:
        raise
    except IntegrityError:
        _raise_database_unavailable(session)
    except (SQLAlchemyError, ValidationError, ValueError, TypeError):
        _raise_database_unavailable(session)


def succeed_measurement_attempt(
    session: Session,
    attempt_id: str,
    lease_token: str,
    result: MeasurementSuccessPersistenceInput,
) -> MeasurementAttempt:
    """Compare-and-set one leased processing attempt to immutable succeeded."""
    per_view = _PER_VIEW_ADAPTER.validate_json(result.per_view_evidence_json)
    dimensions = _DIMENSION_ADAPTER.validate_json(result.reconciliation_evidence_json)
    quality = OverallQualityEvidenceResponse.model_validate_json(result.quality_evidence_json)
    overall_uncertainty = _FLOAT_ADAPTER.validate_json(result.uncertainty_evidence_json)
    warnings = _WARNINGS_ADAPTER.validate_json(result.warnings_json)
    final_values = {
        DimensionName.LENGTH: result.length_mm,
        DimensionName.WIDTH: result.width_mm,
        DimensionName.HEIGHT: result.height_mm,
    }
    if (
        tuple(item.view for item in per_view) != MEASUREMENT_VIEW_ORDER
        or tuple(item.dimension for item in dimensions) != DIMENSION_ORDER
        or len(result.source_updates) != 3
        or tuple(preview.view for preview in result.previews) != MEASUREMENT_VIEW_ORDER
        or not math_is_finite_nonnegative(overall_uncertainty)
        or any(
            not math.isfinite(value)
            or value <= 0.0
            or dimension.value_mm is None
            or not math.isclose(value, dimension.value_mm, abs_tol=1e-9)
            for value, dimension in zip(
                final_values.values(),
                dimensions,
                strict=True,
            )
        )
        or any(not _valid_preview_input(preview) for preview in result.previews)
    ):
        raise ValueError("success evidence does not match the frozen order")
    del quality, warnings
    _validate_sha256(result.source_fingerprint)
    try:
        _begin_immediate(session)
        attempt = _leased_attempt(session, attempt_id, lease_token)
        active_profile_id = session.scalar(
            select(CalibrationProfile.id).where(CalibrationProfile.is_active.is_(True))
        )
        if active_profile_id != attempt.calibration_profile_id:
            _rollback_quietly(session)
            raise _active_profile_changed()
        _apply_source_updates(attempt, result.source_updates)
        attempt.previews.extend(
            MeasurementPreview(
                id=preview.preview_id,
                view=preview.view,
                kind=preview.kind,
                storage_key=preview.storage_key,
                sha256=_validated_sha256(preview.sha256),
                media_type=preview.media_type,
                size_bytes=preview.size_bytes,
                width_px=preview.width_px,
                height_px=preview.height_px,
            )
            for preview in result.previews
        )
        # Child evidence must be written while its parent is still processing;
        # database triggers make all child rows immutable after terminalization.
        session.flush()
        attempt.source_fingerprint = result.source_fingerprint
        attempt.length_mm = result.length_mm
        attempt.width_mm = result.width_mm
        attempt.height_mm = result.height_mm
        attempt.per_view_evidence_json = canonical_json(
            [item.model_dump(mode="json") for item in per_view]
        )
        attempt.reconciliation_evidence_json = canonical_json(
            [item.model_dump(mode="json") for item in dimensions]
        )
        attempt.quality_evidence_json = canonical_json(
            OverallQualityEvidenceResponse.model_validate_json(
                result.quality_evidence_json
            ).model_dump(mode="json")
        )
        attempt.uncertainty_evidence_json = canonical_json(overall_uncertainty)
        attempt.warnings_json = canonical_json(
            _WARNINGS_ADAPTER.validate_json(result.warnings_json)
        )
        attempt.failure_json = None
        attempt.completed_at = datetime.now(UTC)
        attempt.status = MeasurementStatus.SUCCEEDED
        session.commit()
        return attempt
    except ApplicationError:
        raise
    except (IntegrityError, SQLAlchemyError, ValidationError):
        _raise_database_unavailable(session)


def fail_measurement_attempt(
    session: Session,
    attempt_id: str,
    lease_token: str,
    result: MeasurementFailurePersistenceInput,
) -> MeasurementAttempt:
    """Compare-and-set one leased processing attempt to immutable failed."""
    failure = MeasurementFailure.model_validate_json(result.failure_json)
    per_view_json = _validate_optional_per_view_json(result.per_view_evidence_json)
    dimensions_json = _validate_optional_dimensions_json(
        result.reconciliation_evidence_json
    )
    quality_json = _validate_optional_quality_json(result.quality_evidence_json)
    uncertainty_json = _validate_optional_uncertainty_json(
        result.uncertainty_evidence_json
    )
    warnings_json = _validate_optional_warnings_json(result.warnings_json)
    if result.source_fingerprint is not None:
        _validate_sha256(result.source_fingerprint)
    try:
        _begin_immediate(session)
        attempt = _leased_attempt(session, attempt_id, lease_token)
        _apply_source_updates(attempt, result.source_updates)
        # Persist safe partial source evidence before terminalization for the
        # same trigger-ordering reason as successful attempts.
        session.flush()
        attempt.source_fingerprint = result.source_fingerprint
        attempt.per_view_evidence_json = per_view_json
        attempt.reconciliation_evidence_json = dimensions_json
        attempt.quality_evidence_json = quality_json
        attempt.uncertainty_evidence_json = uncertainty_json
        attempt.warnings_json = warnings_json
        attempt.failure_json = canonical_json(failure.model_dump(mode="json", exclude_none=True))
        attempt.completed_at = datetime.now(UTC)
        attempt.status = MeasurementStatus.FAILED
        session.commit()
        return attempt
    except ApplicationError:
        raise
    except (IntegrityError, SQLAlchemyError, ValidationError):
        _raise_database_unavailable(session)


def get_measurement_attempt_model(
    session: Session, scan_id: str, measurement_id: str
) -> MeasurementAttempt:
    try:
        attempt = session.scalar(
            select(MeasurementAttempt)
            .options(
                selectinload(MeasurementAttempt.sources),
                selectinload(MeasurementAttempt.previews),
            )
            .where(
                MeasurementAttempt.id == measurement_id,
                MeasurementAttempt.scan_id == scan_id,
            )
        )
    except SQLAlchemyError:
        _raise_database_unavailable(session)
    if attempt is None:
        raise _measurement_not_found()
    return attempt


def get_measurement_preview_model(
    session: Session,
    scan_id: str,
    measurement_id: str,
    view: MeasurementView,
) -> MeasurementPreview:
    attempt = get_measurement_attempt_model(session, scan_id, measurement_id)
    preview = next(
        (
            item
            for item in attempt.previews
            if item.view is view and item.kind is PreviewKind.ANNOTATED
        ),
        None,
    )
    if preview is None:
        raise _measurement_not_found()
    return preview


def list_measurement_attempts(
    session: Session,
    scan_id: str,
    *,
    capture_snapshot: CaptureSetupSnapshotResponse,
    policy_snapshot: MeasurementPolicySnapshotResponse,
    offset: int,
    limit: int,
) -> MeasurementAttemptListResponse:
    try:
        if session.scalar(select(Scan.id).where(Scan.id == scan_id)) is None:
            raise _scan_not_found()
        total = session.scalar(
            select(func.count())
            .select_from(MeasurementAttempt)
            .where(MeasurementAttempt.scan_id == scan_id)
        ) or 0
        attempts = session.scalars(
            select(MeasurementAttempt)
            .options(
                selectinload(MeasurementAttempt.sources),
                selectinload(MeasurementAttempt.previews),
            )
            .where(MeasurementAttempt.scan_id == scan_id)
            .order_by(MeasurementAttempt.created_at.desc(), MeasurementAttempt.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return MeasurementAttemptListResponse(
            items=[
                _summary(session, attempt, capture_snapshot, policy_snapshot)
                for attempt in attempts
            ],
            total=total,
            offset=offset,
            limit=limit,
        )
    except ApplicationError:
        raise
    except (SQLAlchemyError, ValidationError, ValueError, TypeError, json.JSONDecodeError):
        _raise_database_unavailable(session)


def get_measurement_detail(
    session: Session,
    scan_id: str,
    measurement_id: str,
    *,
    capture_snapshot: CaptureSetupSnapshotResponse,
    policy_snapshot: MeasurementPolicySnapshotResponse,
) -> MeasurementAttemptDetailResponse:
    attempt = get_measurement_attempt_model(session, scan_id, measurement_id)
    try:
        summary = _summary(session, attempt, capture_snapshot, policy_snapshot)
        profile = CalibrationProfileResponse.model_validate_json(
            attempt.profile_snapshot_json
        )
        stored_capture = CaptureSetupSnapshotResponse.model_validate_json(
            attempt.capture_setup_snapshot_json
        )
        stored_policy = MeasurementPolicySnapshotResponse.model_validate_json(
            attempt.measurement_policy_snapshot_json
        )
        sources = [
            MeasurementSourceResponse.model_validate(source)
            for source in sorted(
                attempt.sources,
                key=lambda item: MEASUREMENT_VIEW_ORDER.index(item.view),
            )
            if source.original_sha256 is not None
            and source.oriented_pixel_sha256 is not None
        ]
        per_view = (
            _PER_VIEW_ADAPTER.validate_json(attempt.per_view_evidence_json)
            if attempt.per_view_evidence_json is not None
            else []
        )
        dimensions = (
            _DIMENSION_ADAPTER.validate_json(attempt.reconciliation_evidence_json)
            if attempt.reconciliation_evidence_json is not None
            else []
        )
        overall_quality = (
            OverallQualityEvidenceResponse.model_validate_json(attempt.quality_evidence_json)
            if attempt.quality_evidence_json is not None
            else None
        )
        overall_uncertainty = (
            _FLOAT_ADAPTER.validate_json(attempt.uncertainty_evidence_json)
            if attempt.uncertainty_evidence_json is not None
            else None
        )
        warnings = (
            _WARNINGS_ADAPTER.validate_json(attempt.warnings_json)
            if attempt.warnings_json is not None
            else []
        )
        failure = (
            MeasurementFailure.model_validate_json(attempt.failure_json)
            if attempt.failure_json is not None
            else None
        )
        previews = [
            _preview_descriptor(scan_id, attempt.id, preview)
            for preview in sorted(
                attempt.previews, key=lambda item: MEASUREMENT_VIEW_ORDER.index(item.view)
            )
        ]
        final_dimensions = (
            FinalDimensionsResponse(
                length_mm=_required_dimension(attempt.length_mm),
                width_mm=_required_dimension(attempt.width_mm),
                height_mm=_required_dimension(attempt.height_mm),
            )
            if attempt.status is MeasurementStatus.SUCCEEDED
            else None
        )
        return MeasurementAttemptDetailResponse(
            **summary.model_dump(),
            calibration_profile_snapshot=profile,
            capture_setup_snapshot=stored_capture,
            measurement_policy_snapshot=stored_policy,
            source_fingerprint=attempt.source_fingerprint,
            sources=sources,
            per_view_measurements=per_view,
            dimension_results=dimensions,
            final_dimensions=final_dimensions,
            overall_quality=overall_quality,
            overall_uncertainty_mm=overall_uncertainty,
            warnings=warnings,
            previews=previews,
            failure=failure,
            started_at=attempt.started_at,
        )
    except (
        SQLAlchemyError,
        ValidationError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        _raise_database_unavailable(session)


def _summary(
    session: Session,
    attempt: MeasurementAttempt,
    capture_snapshot: CaptureSetupSnapshotResponse,
    policy_snapshot: MeasurementPolicySnapshotResponse,
) -> MeasurementAttemptSummaryResponse:
    profile = CalibrationProfileResponse.model_validate_json(attempt.profile_snapshot_json)
    stored_capture = CaptureSetupSnapshotResponse.model_validate_json(
        attempt.capture_setup_snapshot_json
    )
    failure = (
        MeasurementFailure.model_validate_json(attempt.failure_json)
        if attempt.failure_json is not None
        else None
    )
    stale_reasons = _stale_reasons(
        session, attempt, capture_snapshot, policy_snapshot
    )
    return MeasurementAttemptSummaryResponse(
        id=attempt.id,
        scan_id=attempt.scan_id,
        request_id=attempt.request_id,
        reprocess_of_measurement_id=attempt.reprocess_of_measurement_id,
        status=attempt.status,
        calibration_profile_id=attempt.calibration_profile_id,
        calibration_profile_name=profile.name,
        capture_setup_id=stored_capture.id,
        capture_setup_version=stored_capture.version,
        processing_version=attempt.processing_version,
        algorithm_version=attempt.algorithm_version,
        length_mm=attempt.length_mm,
        width_mm=attempt.width_mm,
        height_mm=attempt.height_mm,
        failure_code=failure.code if failure is not None else None,
        is_stale=bool(stale_reasons),
        stale_reasons=stale_reasons,
        created_at=attempt.created_at,
        completed_at=attempt.completed_at,
    )


def _stale_reasons(
    session: Session,
    attempt: MeasurementAttempt,
    capture_snapshot: CaptureSetupSnapshotResponse,
    policy_snapshot: MeasurementPolicySnapshotResponse,
) -> list[StaleReason]:
    reasons: list[StaleReason] = []
    active_profile_id = session.scalar(
        select(CalibrationProfile.id).where(CalibrationProfile.is_active.is_(True))
    )
    if active_profile_id != attempt.calibration_profile_id:
        reasons.append(StaleReason.ACTIVE_CALIBRATION_PROFILE_CHANGED)
    current_images = session.scalars(
        select(ScanImage).where(
            ScanImage.scan_id == attempt.scan_id,
            ScanImage.view_type.in_((ImageView.TOP, ImageView.FRONT, ImageView.SIDE)),
        )
    ).all()
    current_ids = {
        MeasurementView(image.view_type.value): image.id for image in current_images
    }
    stored_ids = {source.view: source.scan_image_id for source in attempt.sources}
    if current_ids != stored_ids:
        reasons.append(StaleReason.SOURCE_IMAGES_CHANGED)
    if attempt.capture_setup_snapshot_json != canonical_json(
        capture_snapshot.model_dump(mode="json")
    ):
        reasons.append(StaleReason.CAPTURE_SETUP_CHANGED)
    if attempt.processing_version != PROCESSING_VERSION:
        reasons.append(StaleReason.PROCESSING_VERSION_CHANGED)
    if attempt.algorithm_version != ALGORITHM_VERSION:
        reasons.append(StaleReason.ALGORITHM_VERSION_CHANGED)
    if attempt.measurement_policy_snapshot_json != canonical_json(
        policy_snapshot.model_dump(mode="json")
    ):
        reasons.append(StaleReason.MEASUREMENT_POLICY_CHANGED)
    return reasons


def _preview_descriptor(
    scan_id: str, attempt_id: str, preview: MeasurementPreview
) -> PreviewDescriptorResponse:
    api_url = (
        f"/api/scans/{quote(scan_id, safe='')}/measurements/"
        f"{quote(attempt_id, safe='')}/previews/{preview.view.value}"
    )
    return PreviewDescriptorResponse(
        view=preview.view,
        kind=PreviewKind.ANNOTATED,
        media_type="image/png",
        width_px=preview.width_px,
        height_px=preview.height_px,
        size_bytes=preview.size_bytes,
        api_url=api_url,
    )


def _required_images(scan: Scan) -> tuple[ScanImage, ScanImage, ScanImage] | None:
    by_view = {
        MeasurementView(image.view_type.value): image
        for image in scan.images
        if image.view_type in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    }
    if tuple(by_view) != MEASUREMENT_VIEW_ORDER:
        if set(by_view) != set(MEASUREMENT_VIEW_ORDER):
            return None
    try:
        return (
            by_view[MeasurementView.TOP],
            by_view[MeasurementView.FRONT],
            by_view[MeasurementView.SIDE],
        )
    except KeyError:
        return None


def _leased_attempt(session: Session, attempt_id: str, lease_token: str) -> MeasurementAttempt:
    attempt = session.scalar(
        select(MeasurementAttempt)
        .options(
            selectinload(MeasurementAttempt.sources),
            selectinload(MeasurementAttempt.previews),
        )
        .where(
            MeasurementAttempt.id == attempt_id,
            MeasurementAttempt.status == MeasurementStatus.PROCESSING,
            MeasurementAttempt.lease_token == lease_token,
        )
    )
    if attempt is None:
        _rollback_quietly(session)
        raise ApplicationError(
            status_code=status.HTTP_409_CONFLICT,
            code="PROCESSING_INTERRUPTED",
            message="The measurement attempt is no longer owned by this processing request.",
            recoverable=True,
            suggested_action="Refresh measurement history before retrying.",
        )
    return attempt


def _apply_source_updates(
    attempt: MeasurementAttempt,
    updates: tuple[SourceFingerprintUpdate, ...],
) -> None:
    by_id = {source.id: source for source in attempt.sources}
    seen: set[str] = set()
    for update in updates:
        source_id = update.source_id
        if source_id in seen or source_id not in by_id:
            raise ValueError("source fingerprint update does not belong to attempt")
        original = _validated_sha256(update.original_sha256)
        oriented = _validated_sha256(update.oriented_pixel_sha256)
        by_id[source_id].original_sha256 = original
        by_id[source_id].oriented_pixel_sha256 = oriented
        seen.add(source_id)


def _validate_optional_per_view_json(value: str | None) -> str | None:
    if value is None:
        return None
    items = _PER_VIEW_ADAPTER.validate_json(value)
    views = tuple(item.view for item in items)
    if len(set(views)) != len(views) or views != tuple(
        view for view in MEASUREMENT_VIEW_ORDER if view in views
    ):
        raise ValueError("partial per-view evidence must use frozen order")
    return canonical_json(
        [item.model_dump(mode="json") for item in items]
    )


def _validate_optional_dimensions_json(value: str | None) -> str | None:
    if value is None:
        return None
    items = _DIMENSION_ADAPTER.validate_json(value)
    dimensions = tuple(item.dimension for item in items)
    if len(set(dimensions)) != len(dimensions) or dimensions != tuple(
        dimension for dimension in DIMENSION_ORDER if dimension in dimensions
    ):
        raise ValueError("partial dimension evidence must use frozen order")
    return canonical_json(
        [item.model_dump(mode="json") for item in items]
    )


def _validate_optional_quality_json(value: str | None) -> str | None:
    if value is None:
        return None
    return canonical_json(
        OverallQualityEvidenceResponse.model_validate_json(value).model_dump(mode="json")
    )


def _validate_optional_uncertainty_json(value: str | None) -> str | None:
    if value is None:
        return None
    uncertainty = _FLOAT_ADAPTER.validate_json(value)
    if not math_is_finite_nonnegative(uncertainty):
        raise ValueError("overall uncertainty must be finite and non-negative")
    return canonical_json(uncertainty)


def _validate_optional_warnings_json(value: str | None) -> str | None:
    if value is None:
        return None
    return canonical_json(_WARNINGS_ADAPTER.validate_json(value))


def math_is_finite_nonnegative(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0.0


def _required_dimension(value: float | None) -> float:
    if value is None:
        raise ValueError("succeeded attempt is missing a dimension")
    return value


def _valid_preview_input(preview: object) -> bool:
    if not isinstance(preview, PreviewPersistenceInput):
        return False
    key = PurePosixPath(preview.storage_key)
    return (
        preview.kind is PreviewKind.ANNOTATED
        and preview.media_type == "image/png"
        and 1 <= preview.size_bytes <= MAXIMUM_MEASUREMENT_PREVIEW_BYTES
        and 1 <= preview.width_px <= MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX
        and 1 <= preview.height_px <= MAXIMUM_MEASUREMENT_PREVIEW_EDGE_PX
        and not key.is_absolute()
        and "\\" not in preview.storage_key
        and all(part not in {"", ".", ".."} for part in key.parts)
    )


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid SHA-256")


def _validated_sha256(value: str) -> str:
    _validate_sha256(value)
    return value


def _begin_immediate(session: Session) -> None:
    _rollback_quietly(session)
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _rollback_quietly(session: Session) -> None:
    try:
        session.rollback()
    except SQLAlchemyError:
        pass


def _raise_database_unavailable(session: Session) -> Never:
    _rollback_quietly(session)
    raise ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    ) from None


def _scan_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="SCAN_NOT_FOUND",
        message="The requested scan was not found.",
        recoverable=False,
        suggested_action="Return to scan history and select an existing scan.",
    )


def _scan_not_ready() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="SCAN_NOT_READY",
        message="The scan is not ready for deterministic measurement.",
        recoverable=True,
        suggested_action="Upload valid top, front, and side images before processing.",
    )


def _capture_setup_unqualified() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="CAPTURE_SETUP_UNQUALIFIED",
        message="The configured physical capture setup is not qualified.",
        recoverable=False,
        suggested_action="Qualify the configured orthogonal rig before processing scans.",
    )


def _capture_setup_mismatch() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="CAPTURE_SETUP_MISMATCH",
        message="The configured capture setup changed before processing began.",
        recoverable=True,
        suggested_action="Review the active capture setup and confirm the measurement again.",
        field="expected_capture_setup_id",
    )


def _active_profile_required() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="ACTIVE_CALIBRATION_PROFILE_REQUIRED",
        message="An active calibration profile is required.",
        recoverable=True,
        suggested_action="Activate a qualified calibration profile and try again.",
    )


def _active_profile_changed() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="ACTIVE_CALIBRATION_PROFILE_CHANGED",
        message="The active calibration profile changed before processing began.",
        recoverable=True,
        suggested_action="Review the active calibration profile and confirm again.",
        field="expected_calibration_profile_id",
    )


def _measurement_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="MEASUREMENT_NOT_FOUND",
        message="The requested measurement attempt was not found.",
        recoverable=False,
        suggested_action="Refresh the scan measurement history.",
    )


def _request_conflict() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="MEASUREMENT_REQUEST_CONFLICT",
        message="The request ID was already used with different measurement inputs.",
        recoverable=False,
        suggested_action="Refresh history before starting a separately confirmed attempt.",
        field="request_id",
    )


def _measurement_in_progress() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="MEASUREMENT_IN_PROGRESS",
        message="A measurement attempt is already processing for this scan.",
        recoverable=True,
        suggested_action="Wait for the current request or refresh measurement history.",
    )


def _reprocess_confirmation_required() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_409_CONFLICT,
        code="REPROCESS_CONFIRMATION_REQUIRED",
        message="A prior terminal measurement exists for this scan.",
        recoverable=True,
        suggested_action="Confirm reprocessing from an existing terminal attempt.",
        field="reprocess_of_measurement_id",
    )
