"""Integration tests for Phase 2 calibration options and profile APIs."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from typing import Any, Never, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.api import calibration_profiles as calibration_api
from backend.app.api.calibration_profiles import router as calibration_router
from backend.app.database import Database
from backend.app.errors import ApplicationError, register_error_handlers
from backend.app.models.calibration import CalibrationProfile
from backend.app.schemas.calibration import CalibrationProfileCreateRequest
from backend.app.services.calibration_profiles import (
    activate_calibration_profile,
    create_calibration_profile,
)

DATABASE_UNAVAILABLE_RESPONSE = {
    "code": "DATABASE_UNAVAILABLE",
    "message": "The local database is unavailable or has not been initialized.",
    "recoverable": True,
    "suggested_action": "Run scripts/setup_windows.ps1, then restart the application.",
}


def profile_payload(name: str, **changes: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "dictionary": "DICT_4X4_50",
        "marker_id": 0,
        "marker_size_mm": 100.0,
        "minimum_marker_side_px": 64,
        "maximum_perspective_ratio": 3.0,
        "maximum_homography_condition_number": 1_000_000.0,
        "maximum_marker_edge_residual_px": 2.0,
        "rectified_pixels_per_mm": 4.0,
    }
    payload.update(changes)
    return payload


@contextmanager
def profile_client(database_url: str | None) -> Iterator[TestClient]:
    app = FastAPI()
    database = Database(database_url) if database_url is not None else None
    app.state.database = database
    register_error_handlers(app)
    app.include_router(calibration_router, prefix="/api")
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if database is not None:
            database.dispose()


def test_options_are_available_without_a_database() -> None:
    with profile_client(None) as client:
        response = client.get("/api/calibration/options")

    assert response.status_code == 200
    assert response.json() == {
        "dictionaries": ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_50"],
        "marker_id_min": 0,
        "marker_id_max": 49,
        "border_bits": 1,
        "defaults": {
            "dictionary": "DICT_4X4_50",
            "marker_id": 0,
            "marker_size_mm": 100.0,
            "minimum_marker_side_px": 64,
            "maximum_perspective_ratio": 3.0,
            "maximum_homography_condition_number": 1_000_000.0,
            "maximum_marker_edge_residual_px": 2.0,
            "rectified_pixels_per_mm": 4.0,
        },
    }


def test_create_read_list_and_activate_profiles(migrated_database_url: str) -> None:
    with profile_client(migrated_database_url) as client:
        first_response = client.post(
            "/api/calibration/profiles",
            json=profile_payload("  First profile  "),
        )
        second_response = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Second profile", dictionary="DICT_5X5_50", marker_id=49),
        )
        first = first_response.json()
        second = second_response.json()
        activated = client.post(f"/api/calibration/profiles/{first['id']}/activate")
        read = client.get(f"/api/calibration/profiles/{first['id']}")
        listed = client.get("/api/calibration/profiles")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert UUID(first["id"]).version == 4
    assert first == {
        "id": first["id"],
        "name": "First profile",
        "dictionary": "DICT_4X4_50",
        "marker_id": 0,
        "marker_size_mm": 100.0,
        "border_bits": 1,
        "minimum_marker_side_px": 64,
        "maximum_perspective_ratio": 3.0,
        "maximum_homography_condition_number": 1_000_000.0,
        "maximum_marker_edge_residual_px": 2.0,
        "rectified_pixels_per_mm": 4.0,
        "is_active": False,
        "created_at": first["created_at"],
        "activated_at": None,
    }
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert activated.json()["activated_at"] is not None
    assert read.json() == activated.json()
    assert listed.json()["total"] == 2
    assert [item["id"] for item in listed.json()["items"]] == [first["id"], second["id"]]


def test_duplicate_name_and_missing_profile_use_structured_errors(
    migrated_database_url: str,
) -> None:
    missing_id = "0fbaddb9-54b9-4f34-9230-8c903fdbbe61"
    with profile_client(migrated_database_url) as client:
        first = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Unique name"),
        )
        duplicate = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Unique name"),
        )
        missing_read = client.get(f"/api/calibration/profiles/{missing_id}")
        missing_activation = client.post(
            f"/api/calibration/profiles/{missing_id}/activate"
        )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "code": "CALIBRATION_PROFILE_NAME_CONFLICT",
        "message": "A calibration profile with this name already exists.",
        "recoverable": True,
        "suggested_action": "Choose a unique calibration profile name and try again.",
        "field": "name",
    }
    for response in (missing_read, missing_activation):
        assert response.status_code == 404
        assert response.json()["code"] == "CALIBRATION_PROFILE_NOT_FOUND"
        assert "\\" not in response.text


def test_profile_request_rejects_unknown_and_out_of_range_fields(
    migrated_database_url: str,
) -> None:
    with profile_client(migrated_database_url) as client:
        unknown = client.post(
            "/api/calibration/profiles",
            json={**profile_payload("Unknown"), "make_active": True},
        )
        wrong_dictionary = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Wrong dictionary", dictionary="DICT_7X7_50"),
        )
        wrong_marker_id = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Wrong ID", marker_id=50),
        )

    for response in (unknown, wrong_dictionary, wrong_marker_id):
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_REQUEST"


def test_marker_svg_is_generated_from_server_profile_without_name_leakage(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    def fake_svg(spec: object) -> str:
        captured.append(spec)
        return '<svg width="100mm" height="100mm" viewBox="0 0 8 8"></svg>'

    monkeypatch.setattr(calibration_api, "_generate_marker_svg", fake_svg)
    with profile_client(migrated_database_url) as client:
        created = client.post(
            "/api/calibration/profiles",
            json=profile_payload("C:\\private\\profile name"),
        ).json()
        response = client.get(f"/api/calibration/profiles/{created['id']}/marker.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["content-disposition"] == 'attachment; filename="aruco-marker-0.svg"'
    assert response.text.startswith("<svg")
    assert "private" not in response.headers["content-disposition"]
    assert len(captured) == 1
    assert cast(Any, captured[0]).marker_id == 0


def database_failure() -> OperationalError:
    return OperationalError(
        "SELECT secret FROM C:\\private\\phase2.sqlite",
        {"password": "not-public"},
        RuntimeError("private database failure"),
    )


def assert_sanitized_database_failure(response: Response) -> None:
    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE
    assert "SELECT secret" not in response.text
    assert "private" not in response.text
    assert "phase2.sqlite" not in response.text
    assert "not-public" not in response.text


def fail_with_database_error(*_args: object, **_kwargs: object) -> Never:
    raise database_failure()


def test_create_read_list_and_activate_database_failures_are_sanitized(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with profile_client(migrated_database_url) as client:
        created = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Database failures"),
        ).json()

        monkeypatch.setattr(Session, "commit", fail_with_database_error)
        create_failure = client.post(
            "/api/calibration/profiles",
            json=profile_payload("Create failure"),
        )
        monkeypatch.undo()

        monkeypatch.setattr(Session, "scalar", fail_with_database_error)
        read_failure = client.get(f"/api/calibration/profiles/{created['id']}")
        monkeypatch.undo()

        monkeypatch.setattr(Session, "scalars", fail_with_database_error)
        list_failure = client.get("/api/calibration/profiles")
        monkeypatch.undo()

        monkeypatch.setattr(Session, "scalar", fail_with_database_error)
        activation_failure = client.post(f"/api/calibration/profiles/{created['id']}/activate")

    for response in (create_failure, read_failure, list_failure, activation_failure):
        assert_sanitized_database_failure(response)


def test_concurrent_activation_never_leaves_multiple_active_profiles(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    try:
        with database.session_factory() as session:
            first = create_calibration_profile(
                session,
                CalibrationProfileCreateRequest.model_validate(profile_payload("Concurrent one")),
            )
            second = create_calibration_profile(
                session,
                CalibrationProfileCreateRequest.model_validate(profile_payload("Concurrent two")),
            )

        barrier = Barrier(2)

        def activate(profile_id: str) -> str:
            barrier.wait(timeout=5)
            with database.session_factory() as session:
                try:
                    activate_calibration_profile(session, profile_id)
                    return "ok"
                except ApplicationError as error:
                    return error.payload.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(activate, (first.id, second.id)))

        assert all(result in {"ok", "DATABASE_UNAVAILABLE"} for result in results)
        assert "ok" in results
        with database.session_factory() as session:
            active_profiles = session.scalars(
                select(CalibrationProfile).where(CalibrationProfile.is_active.is_(True))
            ).all()
            assert len(active_profiles) == 1
            assert active_profiles[0].id in {first.id, second.id}
    finally:
        database.dispose()

