"""Integration tests for Phase 3 measurement options and attempt APIs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.api import measurements as measurements_api
from backend.app.calibration_contracts import ArucoDictionary
from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Database
from backend.app.errors import register_error_handlers
from backend.app.measurement_contracts import MeasurementFailurePersistenceInput
from backend.app.models.calibration import CalibrationProfile
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


class FailingMeasurementProcessor:
    def __init__(self, settings: StubSettings) -> None:
        self.capture_settings = settings
        self.capture = capture_setup_snapshot(settings)

    def process(
        self,
        session: Session,
        scan_id: str,
        request: MeasurementProcessRequest,
    ) -> tuple[object, bool]:
        claim = claim_measurement_attempt(
            session,
            scan_id,
            request,
            self.capture,
            measurement_policy_snapshot(self.capture_settings),
        )
        if claim.replayed:
            return claim.attempt, True
        failure = MeasurementFailure(
            code="PRODUCT_NOT_DETECTED",
            message="No supported product foreground was detected.",
            recoverable=True,
            suggested_action="Retake all three views with the product fully visible.",
        )
        failed = fail_measurement_attempt(
            session,
            claim.attempt.id,
            claim.attempt.lease_token,
            MeasurementFailurePersistenceInput(
                failure_json=canonical_json(
                    failure.model_dump(mode="json", exclude_none=True)
                )
            ),
        )
        return failed, False


@contextmanager
def measurement_client(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_database: bool = True,
) -> Iterator[TestClient]:
    app = FastAPI()
    database = Database(database_url) if with_database else None
    app.state.database = database
    app.state.settings = StubSettings(tmp_path)
    register_error_handlers(app)
    app.include_router(measurements_api.router, prefix="/api")
    monkeypatch.setattr(
        measurements_api,
        "_measurement_processor",
        lambda settings: FailingMeasurementProcessor(cast(StubSettings, settings)),
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        if database is not None:
            database.dispose()


def seed_ready_scan(database_url: str) -> tuple[str, str]:
    database = Database(database_url)
    scan_id = str(uuid4())
    profile_id = str(uuid4())
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
    finally:
        database.dispose()
    return scan_id, profile_id


def request_payload(profile_id: str, request_id: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "expected_calibration_profile_id": profile_id,
        "expected_capture_setup_id": "rig-test-1",
        "capture_contract_acknowledged": True,
        "reprocess_of_measurement_id": None,
    }


def test_options_are_database_independent_and_do_not_expose_configuration_paths(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with measurement_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
        with_database=False,
    ) as client:
        response = client.get("/api/measurements/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["capture_setup"]["qualified"] is True
    assert payload["capture_setup"]["processing_enabled"] is True
    assert payload["required_views"] == ["top", "front", "side"]
    assert payload["dimension_axis_mapping"] == {
        "top": ["length", "width"],
        "front": ["width", "height"],
        "side": ["length", "height"],
    }
    assert "data_root" not in response.text
    assert str(tmp_path) not in response.text


def test_process_replays_terminal_attempt_and_history_is_safe(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, profile_id = seed_ready_scan(migrated_database_url)
    request_id = str(uuid4())
    with measurement_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
    ) as client:
        created = client.post(
            f"/api/scans/{scan_id}/measurements",
            json=request_payload(profile_id, request_id),
        )
        replayed = client.post(
            f"/api/scans/{scan_id}/measurements",
            json=request_payload(profile_id, request_id),
        )
        history = client.get(f"/api/scans/{scan_id}/measurements")
        detail = client.get(
            f"/api/scans/{scan_id}/measurements/{created.json()['id']}"
        )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json() == created.json()
    assert created.json()["status"] == "failed"
    assert created.json()["failure"]["code"] == "PRODUCT_NOT_DETECTED"
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert detail.json() == created.json()
    for private_field in ("storage_key", "lease_token", "request_signature"):
        assert private_field not in created.text
        assert private_field not in history.text


def test_processing_request_rejects_unknown_fields_and_missing_acknowledgement(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, profile_id = seed_ready_scan(migrated_database_url)
    payload = request_payload(profile_id, str(uuid4()))
    with measurement_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
    ) as client:
        unknown = client.post(
            f"/api/scans/{scan_id}/measurements",
            json={**payload, "length_mm": 100},
        )
        missing_ack = client.post(
            f"/api/scans/{scan_id}/measurements",
            json={
                key: value
                for key, value in payload.items()
                if key != "capture_contract_acknowledged"
            },
        )

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "INVALID_REQUEST"
    assert missing_ack.status_code == 422
    assert missing_ack.json()["code"] == "INVALID_REQUEST"


def test_late_database_failure_is_sanitized(
    migrated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_id, _profile_id = seed_ready_scan(migrated_database_url)

    def fail_scalar(_session: Session, *_args: object, **_kwargs: object) -> None:
        raise OperationalError(
            "SELECT secret FROM C:\\private\\measurement.sqlite",
            {"password": "not-public"},
            RuntimeError("private database failure"),
        )

    monkeypatch.setattr(Session, "scalar", fail_scalar)
    with measurement_client(
        migrated_database_url,
        tmp_path,
        monkeypatch,
    ) as client:
        response = client.get(f"/api/scans/{scan_id}/measurements")

    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "The local database is unavailable or has not been initialized.",
        "recoverable": True,
        "suggested_action": "Run scripts/setup_windows.ps1, then restart the application.",
    }
    assert "SELECT secret" not in response.text
    assert "measurement.sqlite" not in response.text
    assert "not-public" not in response.text
