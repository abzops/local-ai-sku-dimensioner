"""Integration tests for safe measurement preview delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from backend.app.api import measurements as measurements_api
from backend.app.calibration_contracts import ArucoDictionary
from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Database
from backend.app.errors import ApplicationError, register_error_handlers
from backend.app.measurement_contracts import (
    MeasurementStatus,
    MeasurementView,
    PreviewKind,
)
from backend.app.models.calibration import CalibrationProfile
from backend.app.models.measurement import MeasurementPreview
from backend.app.models.scan import Scan, ScanImage
from backend.app.schemas.measurements import (
    MeasurementProcessRequest,
    capture_setup_snapshot,
    measurement_policy_snapshot,
)
from backend.app.services.measurement_results import claim_measurement_attempt

PNG_BYTES = b"\x89PNG\r\n\x1a\nverified-local-preview"


class StubSettings:
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

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root


class StubPreviewStorage:
    def __init__(self, expected_preview_id: str) -> None:
        self.expected_preview_id = expected_preview_id

    def read_preview(self, preview: MeasurementPreview) -> bytes:
        assert preview.id == self.expected_preview_id
        assert preview.storage_key.startswith("scans/")
        return PNG_BYTES


class FailingPreviewStorage:
    def read_preview(self, _preview: MeasurementPreview) -> bytes:
        raise ApplicationError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="STORAGE_UNAVAILABLE",
            message="Local image storage is unavailable.",
            recoverable=True,
            suggested_action="Check local storage access and retry.",
        )


@contextmanager
def preview_client(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage: object,
) -> Iterator[TestClient]:
    app = FastAPI()
    database = Database(database_url)
    app.state.database = database
    app.state.settings = StubSettings(tmp_path)
    register_error_handlers(app)
    app.include_router(measurements_api.router, prefix="/api")
    monkeypatch.setattr(
        measurements_api,
        "_measurement_preview_storage",
        lambda _settings: storage,
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        database.dispose()


def seed_succeeded_preview(database_url: str) -> tuple[str, str, str]:
    database = Database(database_url)
    scan_id = str(uuid4())
    profile_id = str(uuid4())
    preview_id = str(uuid4())
    try:
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

        settings = StubSettings(Path("unused"))
        with database.session_factory() as session:
            claim = claim_measurement_attempt(
                session,
                scan_id,
                MeasurementProcessRequest(
                    request_id=uuid4(),
                    expected_calibration_profile_id=UUID(profile_id),
                    expected_capture_setup_id=settings.capture_setup_id,
                    capture_contract_acknowledged=True,
                ),
                capture_setup_snapshot(settings),
                measurement_policy_snapshot(settings),
            )
            attempt = claim.attempt
            attempt.previews.append(
                MeasurementPreview(
                    id=preview_id,
                    view=MeasurementView.TOP,
                    kind=PreviewKind.ANNOTATED,
                    storage_key=(
                        f"scans/{scan_id}/measurements/{attempt.id}/previews/top.png"
                    ),
                    sha256="a" * 64,
                    media_type="image/png",
                    size_bytes=len(PNG_BYTES),
                    width_px=640,
                    height_px=480,
                )
            )
            session.flush()
            attempt.source_fingerprint = "b" * 64
            attempt.length_mm = 100.0
            attempt.width_mm = 80.0
            attempt.height_mm = 60.0
            attempt.per_view_evidence_json = "[]"
            attempt.reconciliation_evidence_json = "[]"
            attempt.quality_evidence_json = "{}"
            attempt.uncertainty_evidence_json = "0"
            attempt.warnings_json = "[]"
            attempt.completed_at = datetime.now(UTC)
            attempt.status = MeasurementStatus.SUCCEEDED
            session.commit()
            return scan_id, attempt.id, preview_id
    finally:
        database.dispose()


def test_preview_endpoint_returns_bytes_with_security_headers(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, attempt_id, preview_id = seed_succeeded_preview(migrated_database_url)
    with preview_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
        StubPreviewStorage(preview_id),
    ) as client:
        response = client.get(
            f"/api/scans/{scan_id}/measurements/{attempt_id}/previews/top"
        )

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-length"] == str(len(PNG_BYTES))
    assert "storage_key" not in response.text


def test_missing_preview_and_invalid_view_return_structured_errors(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, attempt_id, preview_id = seed_succeeded_preview(migrated_database_url)
    with preview_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
        StubPreviewStorage(preview_id),
    ) as client:
        missing = client.get(
            f"/api/scans/{scan_id}/measurements/{attempt_id}/previews/front"
        )
        invalid = client.get(
            f"/api/scans/{scan_id}/measurements/{attempt_id}/previews/additional"
        )

    assert missing.status_code == 404
    assert missing.json()["code"] == "MEASUREMENT_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_REQUEST"


def test_preview_storage_failure_remains_sanitized(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, attempt_id, _preview_id = seed_succeeded_preview(migrated_database_url)
    with preview_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
        FailingPreviewStorage(),
    ) as client:
        response = client.get(
            f"/api/scans/{scan_id}/measurements/{attempt_id}/previews/top"
        )

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert str(tmp_path) not in response.text
    assert "storage_key" not in response.text
