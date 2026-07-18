"""Unit tests for Phase 3 measurement attempt persistence semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.calibration_contracts import ArucoDictionary
from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Database
from backend.app.errors import ApplicationError
from backend.app.measurement_contracts import (
    DIMENSION_VIEW_PAIRS,
    MEASUREMENT_VIEW_ORDER,
    VIEW_DIMENSION_PAIRS,
    DimensionName,
    DimensionValidationStatus,
    MeasurementFailurePersistenceInput,
    MeasurementStatus,
    MeasurementSuccessPersistenceInput,
    MeasurementView,
    PreviewKind,
    PreviewPersistenceInput,
    ReconciliationRule,
    SourceFingerprintUpdate,
    StaleReason,
)
from backend.app.models.calibration import CalibrationProfile
from backend.app.models.measurement import MeasurementAttempt, MeasurementSource
from backend.app.models.scan import Scan, ScanImage
from backend.app.schemas.measurements import (
    CaptureSetupSnapshotResponse,
    DimensionResultResponse,
    MeasurementFailure,
    MeasurementProcessRequest,
    PerViewMeasurementResponse,
    capture_setup_snapshot,
    measurement_options,
    measurement_policy_snapshot,
)
from backend.app.services.measurement_results import (
    canonical_json,
    claim_measurement_attempt,
    fail_measurement_attempt,
    get_measurement_detail,
    list_measurement_attempts,
    succeed_measurement_attempt,
)


class QualifiedCaptureSettings:
    capture_setup_id = "rig-test-1"
    capture_setup_version = "1"
    capture_setup_type = "orthogonal_rig"
    capture_setup_qualified = True
    capture_setup_min_object_mm = 75.0
    capture_setup_max_object_mm = 400.0
    capture_setup_marker_size_uncertainty_mm = 0.2
    capture_setup_plane_uncertainty_mm = 0.5
    capture_setup_orthogonality_uncertainty_deg = 0.5
    capture_setup_standoff_uncertainty_mm = 0.5
    capture_setup_max_off_plane_mm = 1.0
    measurement_acceptable_disagreement_mm = 5.0
    measurement_acceptable_disagreement_percent = 3.0
    measurement_warning_disagreement_mm = 10.0
    measurement_warning_disagreement_percent = 6.0
    measurement_usable_quality = 0.70
    measurement_weak_quality = 0.55
    measurement_stronger_source_quality_lead = 0.15
    measurement_weaker_source_uncertainty_ratio = 2.0
    measurement_max_rectified_edge_px = 4096
    measurement_max_rectified_pixels = 16_000_000
    measurement_max_physical_extent_mm = 1500.0
    measurement_max_components = 1024
    measurement_max_candidates = 64


CAPTURE = capture_setup_snapshot(QualifiedCaptureSettings())
POLICY = measurement_policy_snapshot(QualifiedCaptureSettings())


def test_capture_setup_snapshot_uses_frozen_version_boundary() -> None:
    exact_boundary = CaptureSetupSnapshotResponse(
        **{**CAPTURE.model_dump(), "version": "v" * 50}
    )

    assert exact_boundary.version == "v" * 50

    for invalid_version in ("v" * 51, "", "   "):
        with pytest.raises(ValidationError):
            CaptureSetupSnapshotResponse(
                **{**CAPTURE.model_dump(), "version": invalid_version}
            )


def seed_ready_scan(database: Database) -> tuple[str, str]:
    scan_id = str(uuid4())
    profile_id = str(uuid4())
    with database.session_factory() as session:
        session.add(
            CalibrationProfile(
                id=profile_id,
                name=f"Profile {profile_id[:8]}",
                dictionary=ArucoDictionary.DICT_4X4_50,
                marker_id=0,
                marker_size_mm=100.0,
                border_bits=1,
                minimum_marker_side_px=64,
                maximum_perspective_ratio=3.0,
                maximum_homography_condition_number=1_000_000.0,
                maximum_marker_edge_residual_px=2.0,
                rectified_pixels_per_mm=4.0,
                is_active=True,
                activated_at=datetime.now(UTC),
            )
        )
        scan = Scan(id=scan_id, sku=f"SKU-{scan_id[:8]}", status=ScanStatus.READY_FOR_PROCESSING)
        scan.images = [
            ScanImage(
                id=str(uuid4()),
                view_type=view,
                storage_key=f"scans/{scan_id}/original/{view.value}.png",
                media_type="image/png",
                file_extension=".png",
                size_bytes=2048,
                width_px=1600,
                height_px=1200,
            )
            for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
        ]
        session.add(scan)
        session.commit()
    return scan_id, profile_id


def process_request(
    profile_id: str,
    *,
    request_id: UUID | None = None,
    capture_id: str = CAPTURE.id,
    reprocess_of: UUID | None = None,
) -> MeasurementProcessRequest:
    return MeasurementProcessRequest(
        request_id=request_id or uuid4(),
        expected_calibration_profile_id=UUID(profile_id),
        expected_capture_setup_id=capture_id,
        capture_contract_acknowledged=True,
        reprocess_of_measurement_id=reprocess_of,
    )


def terminal_failure() -> MeasurementFailurePersistenceInput:
    failure = MeasurementFailure(
        code="PRODUCT_NOT_DETECTED",
        message="No supported product foreground was detected.",
        recoverable=True,
        suggested_action="Retake all three views with the product fully visible.",
    )
    return MeasurementFailurePersistenceInput(
        failure_json=canonical_json(failure.model_dump(mode="json", exclude_none=True))
    )


def test_policy_snapshot_and_options_use_active_configured_thresholds() -> None:
    settings = QualifiedCaptureSettings()
    settings.measurement_acceptable_disagreement_mm = 4.0
    settings.measurement_acceptable_disagreement_percent = 2.5
    settings.measurement_warning_disagreement_mm = 8.0
    settings.measurement_warning_disagreement_percent = 5.0
    settings.measurement_max_rectified_pixels = 12_000_000

    policy = measurement_policy_snapshot(settings)
    options = measurement_options(settings)

    assert policy.acceptable_absolute_mm == 4.0
    assert policy.acceptable_relative_percent == 2.5
    assert policy.warning_absolute_mm == 8.0
    assert policy.warning_relative_percent == 5.0
    assert policy.maximum_rectified_pixels == 12_000_000
    assert options.disagreement_thresholds.model_dump() == {
        "acceptable_absolute_mm": 4.0,
        "acceptable_relative_percent": 2.5,
        "warning_absolute_mm": 8.0,
        "warning_relative_percent": 5.0,
    }


def per_view_evidence(
    view: MeasurementView,
    source: MeasurementSource,
) -> PerViewMeasurementResponse:
    dimensions = {
        dimension: {
            DimensionName.LENGTH: 100.0,
            DimensionName.WIDTH: 80.0,
            DimensionName.HEIGHT: 60.0,
        }[dimension]
        for dimension in VIEW_DIMENSION_PAIRS[view]
    }
    return PerViewMeasurementResponse.model_validate(
        {
            "view": view,
            "source": {
                "view": view,
                "scan_image_id": source.scan_image_id,
                "original_sha256": "a" * 64,
                "oriented_pixel_sha256": "b" * 64,
                "media_type": source.media_type,
                "size_bytes": source.size_bytes,
                "width_px": source.width_px,
                "height_px": source.height_px,
            },
            "marker": {
                "dictionary": "DICT_4X4_50",
                "marker_id": 0,
                "marker_size_mm": 100.0,
                "ordered_corners": [
                    {"label": "top_left", "x_px": 0.0, "y_px": 0.0},
                    {"label": "top_right", "x_px": 100.0, "y_px": 0.0},
                    {"label": "bottom_right", "x_px": 100.0, "y_px": 100.0},
                    {"label": "bottom_left", "x_px": 0.0, "y_px": 100.0},
                ],
                "orientation_degrees": 0.0,
                "edge_lengths_px": {"top": 100, "right": 100, "bottom": 100, "left": 100},
                "perspective_ratio": 1.0,
                "image_to_plane_mm": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "plane_mm_to_image": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "homography_condition_number": 1.0,
                "marker_edge_quality": {
                    "metric_name": "marker_edge_localization_residual",
                    "description": "Sampled marker-border localization residual in image pixels.",
                    "rms_px": 0.2,
                    "maximum_px": 0.3,
                    "sample_count": 16,
                    "per_edge_rms_px": {"top": 0.2, "right": 0.2, "bottom": 0.2, "left": 0.2},
                    "threshold_px": 2.0,
                    "valid": True,
                },
            },
            "rectification": {
                "width_px": 800,
                "height_px": 600,
                "pixels_per_mm": 4.0,
                "physical_origin_mm": {"x_mm": 0.0, "y_mm": 0.0},
                "source_to_rectified": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "rectified_to_source": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "physical_width_mm": 200.0,
                "physical_height_mm": 150.0,
            },
            "foreground": {
                "background_lab_median": {"l": 90.0, "a": 0.0, "b": 0.0},
                "background_lab_mad": {"l": 1.0, "a": 1.0, "b": 1.0},
                "background_grayscale_median": 230.0,
                "foreground_grayscale_difference": 100.0,
                "supported_signals": ["lab_distance", "grayscale_difference"],
                "supported_signal_count": 2,
                "component_count": 1,
                "scored_candidate_count": 1,
                "selected_candidate_score": 0.9,
                "runner_up_candidate_score": None,
                "strong_core_coverage": 0.9,
                "mask_stability": 0.9,
                "shadow_fraction": 0.0,
                "reflection_fraction": 0.0,
                "marker_clearance_mm": 10.0,
                "border_clearance_mm": 10.0,
                "contour_area_mm2": 8000.0,
                "hull_area_mm2": 8100.0,
                "solidity": 0.98,
                "extent": 0.95,
                "oriented_box_corners_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 100.0, "y_mm": 0.0},
                    {"x_mm": 100.0, "y_mm": 80.0},
                    {"x_mm": 0.0, "y_mm": 80.0},
                ],
                "oriented_box_angle_degrees": 0.0,
                "threshold_variant_span_mm": 0.2,
                "morphology_variant_span_mm": 0.2,
            },
            "raw_dimensions_mm": dimensions,
            "quality": {
                "score": 0.9,
                "marker": 0.9,
                "homography": 0.9,
                "background": 0.9,
                "mask_stability": 0.9,
                "candidate_uniqueness": 0.9,
                "visibility": 0.9,
            },
            "uncertainty": {
                "marker_size_mm": 0.2,
                "marker_localization_mm": 0.2,
                "raster_mm": 0.2,
                "foreground_stability_mm": 0.2,
                "rig_plane_mm": 0.5,
                "rig_orthogonality_mm": 0.5,
                "mount_standoff_mm": 0.5,
                "off_plane_parallax_mm": 0.5,
                "total_mm": 2.0,
            },
            "warnings": [],
            "preview_available": True,
        }
    )


def success_result(attempt: MeasurementAttempt) -> MeasurementSuccessPersistenceInput:
    sources = {source.view: source for source in attempt.sources}
    per_view = [per_view_evidence(view, sources[view]) for view in MEASUREMENT_VIEW_ORDER]
    dimensions = []
    for dimension in DimensionName:
        views = DIMENSION_VIEW_PAIRS[dimension]
        value = {
            DimensionName.LENGTH: 100.0,
            DimensionName.WIDTH: 80.0,
            DimensionName.HEIGHT: 60.0,
        }[dimension]
        dimensions.append(
            DimensionResultResponse(
                dimension=dimension,
                contributing_views=views,
                raw_values_mm={views[0]: value, views[1]: value},
                value_mm=value,
                absolute_disagreement_mm=0.0,
                relative_disagreement_percent=0.0,
                quality_inputs={views[0]: 0.9, views[1]: 0.9},
                uncertainty_inputs_mm={views[0]: 2.0, views[1]: 2.0},
                uncertainty_mm=2.0,
                reconciliation_rule=ReconciliationRule.QUALITY_UNCERTAINTY_WEIGHTED,
                validation_status=DimensionValidationStatus.ACCEPTABLE,
                warnings=[],
            )
        )
    return MeasurementSuccessPersistenceInput(
        source_fingerprint="c" * 64,
        length_mm=100.0,
        width_mm=80.0,
        height_mm=60.0,
        per_view_evidence_json=canonical_json(
            [item.model_dump(mode="json") for item in per_view]
        ),
        reconciliation_evidence_json=canonical_json(
            [item.model_dump(mode="json") for item in dimensions]
        ),
        quality_evidence_json=canonical_json(
            {
                "score": 0.9,
                "minimum_view_score": 0.9,
                "view_scores": {"top": 0.9, "front": 0.9, "side": 0.9},
            }
        ),
        uncertainty_evidence_json="2.0",
        warnings_json="[]",
        source_updates=tuple(
            SourceFingerprintUpdate(source.id, "a" * 64, "b" * 64)
            for source in sources.values()
        ),
        previews=tuple(
            PreviewPersistenceInput(
                preview_id=str(uuid4()),
                view=view,
                kind=PreviewKind.ANNOTATED,
                storage_key=(
                    f"scans/{attempt.scan_id}/measurements/{attempt.id}/previews/"
                    f"{view.value}.png"
                ),
                sha256="d" * 64,
                media_type="image/png",
                size_bytes=1024,
                width_px=640,
                height_px=480,
            )
            for view in MEASUREMENT_VIEW_ORDER
        ),
    )


def test_success_persistence_writes_ordered_evidence_before_terminalizing(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    try:
        with database.session_factory() as session:
            claim = claim_measurement_attempt(
                session,
                scan_id,
                process_request(profile_id),
                CAPTURE,
                POLICY,
            )
            succeeded = succeed_measurement_attempt(
                session,
                claim.attempt.id,
                claim.attempt.lease_token,
                success_result(claim.attempt),
            )
            assert succeeded.status is MeasurementStatus.SUCCEEDED
            assert len(succeeded.previews) == 3

        with database.session_factory() as session:
            detail = get_measurement_detail(
                session,
                scan_id,
                claim.attempt.id,
                capture_snapshot=CAPTURE,
                policy_snapshot=POLICY,
            )
            assert detail.status is MeasurementStatus.SUCCEEDED
            assert detail.final_dimensions is not None
            assert detail.final_dimensions.model_dump() == {
                "length_mm": 100.0,
                "width_mm": 80.0,
                "height_mm": 60.0,
            }
            assert [item.view for item in detail.per_view_measurements] == list(
                MEASUREMENT_VIEW_ORDER
            )
            assert [item.dimension for item in detail.dimension_results] == list(
                DimensionName
            )
            assert [item.view for item in detail.previews] == list(MEASUREMENT_VIEW_ORDER)
            assert all("storage_key" not in item.model_dump() for item in detail.previews)
    finally:
        database.dispose()


def test_success_compare_and_set_rejects_active_profile_change(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    try:
        with database.session_factory() as session:
            claim = claim_measurement_attempt(
                session,
                scan_id,
                process_request(profile_id),
                CAPTURE,
                POLICY,
            )
            profile = session.get(CalibrationProfile, profile_id)
            assert profile is not None
            profile.is_active = False
            profile.activated_at = None
            session.commit()

            with pytest.raises(ApplicationError) as changed:
                succeed_measurement_attempt(
                    session,
                    claim.attempt.id,
                    claim.attempt.lease_token,
                    success_result(claim.attempt),
            )

            assert changed.value.payload.code == "ACTIVE_CALIBRATION_PROFILE_CHANGED"
            assert not session.in_transaction()
            session.expire_all()
            persisted = session.get(MeasurementAttempt, claim.attempt.id)
            assert persisted is not None
            assert persisted.status is MeasurementStatus.PROCESSING
            assert persisted.previews == []
    finally:
        database.dispose()


def test_claim_fail_and_same_request_terminal_replay(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    request = process_request(profile_id)
    try:
        with database.session_factory() as session:
            claim = claim_measurement_attempt(session, scan_id, request, CAPTURE, POLICY)
            assert not claim.replayed
            assert not claim.reclaimed
            assert claim.attempt.status is MeasurementStatus.PROCESSING
            assert len(claim.attempt.sources) == 3
            assert claim.attempt.lease_token

            failed = fail_measurement_attempt(
                session,
                claim.attempt.id,
                claim.attempt.lease_token,
                terminal_failure(),
            )
            assert failed.status is MeasurementStatus.FAILED

        with database.session_factory() as session:
            replay = claim_measurement_attempt(session, scan_id, request, CAPTURE, POLICY)
            assert replay.replayed
            assert not replay.reclaimed
            assert replay.attempt.id == claim.attempt.id

            detail = get_measurement_detail(
                session,
                scan_id,
                replay.attempt.id,
                capture_snapshot=CAPTURE,
                policy_snapshot=POLICY,
            )
            assert detail.status is MeasurementStatus.FAILED
            assert detail.failure is not None
            assert detail.failure.code == "PRODUCT_NOT_DETECTED"
            assert detail.final_dimensions is None
            assert detail.previews == []
    finally:
        database.dispose()


def test_same_request_id_with_changed_payload_is_rejected(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    request_id = uuid4()
    request = process_request(profile_id, request_id=request_id)
    try:
        with database.session_factory() as session:
            claim = claim_measurement_attempt(session, scan_id, request, CAPTURE, POLICY)
            fail_measurement_attempt(
                session,
                claim.attempt.id,
                claim.attempt.lease_token,
                terminal_failure(),
            )
            conflicting = process_request(
                profile_id,
                request_id=request_id,
                capture_id="other-rig",
            )
            with pytest.raises(ApplicationError) as caught:
                claim_measurement_attempt(session, scan_id, conflicting, CAPTURE, POLICY)
            assert caught.value.status_code == 409
            assert caught.value.payload.code == "MEASUREMENT_REQUEST_CONFLICT"
            assert not session.in_transaction()
    finally:
        database.dispose()


def test_new_attempt_after_terminal_requires_explicit_same_scan_reprocess(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    try:
        with database.session_factory() as session:
            first = claim_measurement_attempt(
                session,
                scan_id,
                process_request(profile_id),
                CAPTURE,
                POLICY,
            )
            fail_measurement_attempt(
                session,
                first.attempt.id,
                first.attempt.lease_token,
                terminal_failure(),
            )

            with pytest.raises(ApplicationError) as confirmation_required:
                claim_measurement_attempt(
                    session,
                    scan_id,
                    process_request(profile_id),
                    CAPTURE,
                    POLICY,
                )
            assert confirmation_required.value.payload.code == (
                "REPROCESS_CONFIRMATION_REQUIRED"
            )

            reprocess = process_request(
                profile_id,
                reprocess_of=UUID(first.attempt.id),
            )
            second = claim_measurement_attempt(
                session,
                scan_id,
                reprocess,
                CAPTURE,
                POLICY,
            )
            assert second.attempt.id != first.attempt.id
            assert second.attempt.reprocess_of_measurement_id == first.attempt.id
    finally:
        database.dispose()


def test_terminal_result_lists_as_stale_after_active_profile_changes(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    try:
        with database.session_factory() as session:
            claim = claim_measurement_attempt(
                session,
                scan_id,
                process_request(profile_id),
                CAPTURE,
                POLICY,
            )
            fail_measurement_attempt(
                session,
                claim.attempt.id,
                claim.attempt.lease_token,
                terminal_failure(),
            )

        with database.session_factory() as session:
            profile = session.get(CalibrationProfile, profile_id)
            assert profile is not None
            profile.is_active = False
            profile.activated_at = None
            session.commit()

        with database.session_factory() as session:
            history = list_measurement_attempts(
                session,
                scan_id,
                capture_snapshot=CAPTURE,
                policy_snapshot=POLICY,
                offset=0,
                limit=50,
            )
            assert history.total == 1
            assert history.items[0].is_stale
            assert history.items[0].stale_reasons == [
                StaleReason.ACTIVE_CALIBRATION_PROFILE_CHANGED
            ]
    finally:
        database.dispose()


def test_unqualified_capture_and_unready_scan_fail_before_attempt_creation(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    unqualified = CaptureSetupSnapshotResponse(**{**CAPTURE.model_dump(), "qualified": False})
    try:
        with database.session_factory() as session:
            with pytest.raises(ApplicationError) as caught:
                claim_measurement_attempt(
                    session,
                    scan_id,
                    process_request(profile_id),
                    unqualified,
                    POLICY,
                )
            assert caught.value.payload.code == "CAPTURE_SETUP_UNQUALIFIED"

            scan = session.get(Scan, scan_id)
            assert scan is not None
            scan.status = ScanStatus.DRAFT
            session.commit()
            with pytest.raises(ApplicationError) as not_ready:
                claim_measurement_attempt(
                    session,
                    scan_id,
                    process_request(profile_id),
                    CAPTURE,
                    POLICY,
                )
            assert not_ready.value.payload.code == "SCAN_NOT_READY"
    finally:
        database.dispose()
