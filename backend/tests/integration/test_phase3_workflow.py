"""Cross-subsystem Phase 3 workflow using real persistence, storage, and geometry."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import cv2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import measurements as measurements_api
from backend.app.calibration_contracts import ArucoDictionary
from backend.app.config import Settings
from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Database
from backend.app.errors import register_error_handlers
from backend.app.models.calibration import CalibrationProfile
from backend.app.models.scan import Scan, ScanImage
from backend.tests.fixtures.phase3_synthetic_factory import render_scene


@contextmanager
def phase3_client(settings: Settings) -> Iterator[TestClient]:
    app = FastAPI()
    database = Database(settings.database_url)
    app.state.database = database
    app.state.settings = settings
    register_error_handlers(app)
    app.include_router(measurements_api.router, prefix="/api")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        database.dispose()


def qualified_settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        data_root=tmp_path,
        database_url=database_url,
        frontend_dist_dir=tmp_path / "missing-dist",
        max_upload_mb=5,
        min_image_long_edge=12,
        min_image_short_edge=8,
        max_image_pixels=3_000_000,
        capture_setup_id="phase3-test-rig",
        capture_setup_version="1",
        capture_setup_qualified=True,
        capture_setup_min_object_mm=75.0,
        capture_setup_max_object_mm=400.0,
        capture_setup_marker_size_uncertainty_mm=0.2,
        capture_setup_plane_uncertainty_mm=0.5,
        capture_setup_orthogonality_uncertainty_deg=0.2,
        capture_setup_standoff_uncertainty_mm=0.4,
        capture_setup_max_off_plane_mm=0.5,
        measurement_processing_deadline_seconds=60.0,
    )


def seed_real_measurement_inputs(
    settings: Settings,
) -> tuple[str, str, dict[Path, bytes]]:
    database = Database(settings.database_url)
    scan_id = str(uuid4())
    profile_id = str(uuid4())
    originals: dict[Path, bytes] = {}
    try:
        with database.session_factory() as session:
            session.add(
                CalibrationProfile(
                    id=profile_id,
                    name="Phase 3 integration marker",
                    dictionary=ArucoDictionary.DICT_4X4_50,
                    marker_id=0,
                    marker_size_mm=100.0,
                    border_bits=1,
                    minimum_marker_side_px=64,
                    maximum_perspective_ratio=3.0,
                    maximum_homography_condition_number=1_000_000.0,
                    maximum_marker_edge_residual_px=2.0,
                    rectified_pixels_per_mm=2.0,
                    is_active=True,
                    activated_at=datetime.now(UTC),
                )
            )
            scan = Scan(
                id=scan_id,
                sku="PHASE3-INTEGRATION",
                status=ScanStatus.READY_FOR_PROCESSING,
            )
            images: list[ScanImage] = []
            for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE):
                scene = render_scene(view)
                encoded_ok, encoded = cv2.imencode(".png", scene.image_bgr)
                assert encoded_ok
                payload = encoded.tobytes()
                image_id = str(uuid4())
                storage_key = f"scans/{scan_id}/original/{image_id}.png"
                path = settings.data_root / Path(storage_key)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                originals[path] = payload
                height_px, width_px = scene.image_bgr.shape[:2]
                images.append(
                    ScanImage(
                        id=image_id,
                        view_type=view,
                        storage_key=storage_key,
                        media_type="image/png",
                        file_extension=".png",
                        size_bytes=len(payload),
                        width_px=width_px,
                        height_px=height_px,
                    )
                )
            scan.images = images
            session.add(scan)
            session.commit()
    finally:
        database.dispose()
    return scan_id, profile_id, originals


def measurement_request(
    profile_id: str,
    request_id: str,
    *,
    reprocess_of: str | None = None,
) -> dict[str, object]:
    return {
        "request_id": request_id,
        "expected_calibration_profile_id": profile_id,
        "expected_capture_setup_id": "phase3-test-rig",
        "capture_contract_acknowledged": True,
        "reprocess_of_measurement_id": reprocess_of,
    }


def test_real_phase3_workflow_is_idempotent_immutable_and_private(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    settings = qualified_settings(tmp_path, migrated_database_url)
    scan_id, profile_id, originals = seed_real_measurement_inputs(settings)
    request_id = str(uuid4())

    with phase3_client(settings) as client:
        options = client.get("/api/measurements/options")
        created = client.post(
            f"/api/scans/{scan_id}/measurements",
            json=measurement_request(profile_id, request_id),
        )
        replayed = client.post(
            f"/api/scans/{scan_id}/measurements",
            json=measurement_request(profile_id, request_id),
        )

        assert options.status_code == 200
        assert options.json()["capture_setup"]["processing_enabled"] is True
        assert created.status_code == 201, created.text
        assert replayed.status_code == 200
        assert replayed.json() == created.json()

        result = created.json()
        assert result["status"] == "succeeded"
        assert result["final_dimensions"]["length_mm"] == pytest.approx(240.0, abs=3.0)
        assert result["final_dimensions"]["width_mm"] == pytest.approx(140.0, abs=3.0)
        assert result["final_dimensions"]["height_mm"] == pytest.approx(120.0, abs=3.0)
        assert [item["view"] for item in result["per_view_measurements"]] == [
            "top",
            "front",
            "side",
        ]
        assert [item["dimension"] for item in result["dimension_results"]] == [
            "length",
            "width",
            "height",
        ]
        assert result["overall_uncertainty_mm"] > 0
        assert len(result["previews"]) == 3

        for preview in result["previews"]:
            response = client.get(preview["api_url"])
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert response.headers["cache-control"] == "no-store"
            assert response.content.startswith(b"\x89PNG\r\n\x1a\n")

        prior_detail = client.get(
            f"/api/scans/{scan_id}/measurements/{result['id']}"
        ).json()
        reprocessed = client.post(
            f"/api/scans/{scan_id}/measurements",
            json=measurement_request(
                profile_id,
                str(uuid4()),
                reprocess_of=result["id"],
            ),
        )
        history = client.get(f"/api/scans/{scan_id}/measurements")
        unchanged = client.get(
            f"/api/scans/{scan_id}/measurements/{result['id']}"
        )

    assert reprocessed.status_code == 201, reprocessed.text
    assert reprocessed.json()["id"] != result["id"]
    assert reprocessed.json()["reprocess_of_measurement_id"] == result["id"]
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert unchanged.json() == prior_detail
    assert all(path.read_bytes() == payload for path, payload in originals.items())
    for private_value in (str(tmp_path), "storage_key", "lease_token", "request_signature"):
        assert private_value not in created.text
        assert private_value not in reprocessed.text
