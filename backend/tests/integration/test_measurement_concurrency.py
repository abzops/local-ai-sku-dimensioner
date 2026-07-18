"""Integration tests for SQLite measurement leases and concurrent claims."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from backend.app.calibration_contracts import ArucoDictionary
from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Database
from backend.app.errors import ApplicationError
from backend.app.measurement_contracts import (
    MeasurementFailurePersistenceInput,
    MeasurementStatus,
)
from backend.app.models.calibration import CalibrationProfile
from backend.app.models.measurement import MeasurementAttempt
from backend.app.models.scan import Scan, ScanImage
from backend.app.schemas.measurements import (
    MeasurementFailure,
    MeasurementProcessRequest,
    capture_setup_snapshot,
    measurement_policy_snapshot,
)
from backend.app.services.measurement_results import (
    canonical_json,
    claim_measurement_attempt,
    fail_measurement_attempt,
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
        scan = Scan(
            id=scan_id,
            sku=f"SKU-{scan_id[:8]}",
            status=ScanStatus.READY_FOR_PROCESSING,
        )
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


def request(profile_id: str, *, request_id: UUID | None = None) -> MeasurementProcessRequest:
    return MeasurementProcessRequest(
        request_id=request_id or uuid4(),
        expected_calibration_profile_id=UUID(profile_id),
        expected_capture_setup_id=CAPTURE.id,
        capture_contract_acknowledged=True,
    )


def failure() -> MeasurementFailurePersistenceInput:
    payload = MeasurementFailure(
        code="PROCESSING_INTERRUPTED",
        message="Measurement processing was interrupted.",
        recoverable=True,
        suggested_action="Retry the confirmed measurement request.",
    )
    return MeasurementFailurePersistenceInput(
        failure_json=canonical_json(payload.model_dump(mode="json"))
    )


def test_concurrent_requests_create_only_one_processing_attempt(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    barrier = Barrier(2)

    def worker() -> tuple[str, str]:
        worker_request = request(profile_id)
        barrier.wait()
        with database.session_factory() as session:
            try:
                claim = claim_measurement_attempt(
                    session,
                    scan_id,
                    worker_request,
                    CAPTURE,
                    POLICY,
                )
                return "claimed", claim.attempt.id
            except ApplicationError as error:
                return "error", error.payload.code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (executor.submit(worker), executor.submit(worker))
            results = [future.result() for future in futures]

        assert sorted(result[0] for result in results) == ["claimed", "error"]
        assert next(value for kind, value in results if kind == "error") == (
            "MEASUREMENT_IN_PROGRESS"
        )
        with database.session_factory() as session:
            attempts = session.query(MeasurementAttempt).all()
            assert len(attempts) == 1
            assert attempts[0].status is MeasurementStatus.PROCESSING
    finally:
        database.dispose()


def test_expired_same_request_reclaims_lease_and_blocks_stale_worker(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    process_request = request(profile_id)
    try:
        with database.session_factory() as session:
            initial = claim_measurement_attempt(
                session,
                scan_id,
                process_request,
                CAPTURE,
                POLICY,
            )
            stale_token = initial.attempt.lease_token
            initial.attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()

        with database.session_factory() as session:
            reclaimed = claim_measurement_attempt(
                session,
                scan_id,
                process_request,
                CAPTURE,
                POLICY,
            )
            assert reclaimed.reclaimed
            assert not reclaimed.replayed
            assert reclaimed.attempt.lease_token != stale_token

            with pytest.raises(ApplicationError) as interrupted:
                fail_measurement_attempt(
                    session,
                    reclaimed.attempt.id,
                    stale_token,
                    failure(),
                )
            assert interrupted.value.payload.code == "PROCESSING_INTERRUPTED"

            terminal = fail_measurement_attempt(
                session,
                reclaimed.attempt.id,
                reclaimed.attempt.lease_token,
                failure(),
            )
            assert terminal.status is MeasurementStatus.FAILED
    finally:
        database.dispose()


def test_nonexpired_same_request_reports_in_progress(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    scan_id, profile_id = seed_ready_scan(database)
    process_request = request(profile_id)
    try:
        with database.session_factory() as session:
            claim_measurement_attempt(session, scan_id, process_request, CAPTURE, POLICY)
            with pytest.raises(ApplicationError) as caught:
                claim_measurement_attempt(
                    session,
                    scan_id,
                    process_request,
                    CAPTURE,
                    POLICY,
                )
            assert caught.value.payload.code == "MEASUREMENT_IN_PROGRESS"
            assert not session.in_transaction()
    finally:
        database.dispose()
