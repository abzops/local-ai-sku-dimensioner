"""Integration tests for Phase 1 scan creation, reads, and history."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.api.scans import router as scans_router
from backend.app.database import Database
from backend.app.errors import ApplicationError

DATABASE_UNAVAILABLE_RESPONSE = {
    "code": "DATABASE_UNAVAILABLE",
    "message": "The local database is unavailable or has not been initialized.",
    "recoverable": True,
    "suggested_action": "Run scripts/setup_windows.ps1, then restart the application.",
}


@contextmanager
def scan_client(database_url: str) -> Iterator[TestClient]:
    app = FastAPI()
    database = Database(database_url)
    app.state.database = database

    @app.exception_handler(ApplicationError)
    def handle_application_error(
        _request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=error.payload.model_dump(mode="json", exclude_none=True),
        )

    app.include_router(scans_router, prefix="/api")
    try:
        with TestClient(app) as client:
            yield client
    finally:
        database.dispose()


def test_create_and_read_scan_persists_across_database_instances(
    migrated_database_url: str,
) -> None:
    with scan_client(migrated_database_url) as client:
        response = client.post(
            "/api/scans",
            json={
                "sku": "  SNS-00125  ",
                "barcode": "  8901234567890  ",
                "product_name": "  Example Product  ",
            },
        )

    assert response.status_code == 201
    created = response.json()
    assert UUID(created["id"]).version == 4
    assert created == {
        "id": created["id"],
        "sku": "SNS-00125",
        "barcode": "8901234567890",
        "product_name": "Example Product",
        "status": "draft",
        "missing_required_views": ["top", "front", "side"],
        "created_at": created["created_at"],
        "updated_at": created["updated_at"],
        "images": [],
    }

    with scan_client(migrated_database_url) as restarted_client:
        read_response = restarted_client.get(f"/api/scans/{created['id']}")

    assert read_response.status_code == 200
    assert read_response.json() == created


def test_create_normalizes_empty_optional_values_to_null(
    migrated_database_url: str,
) -> None:
    with scan_client(migrated_database_url) as client:
        response = client.post(
            "/api/scans",
            json={"sku": "SKU-EMPTY-OPTIONALS", "barcode": " ", "product_name": ""},
        )

    assert response.status_code == 201
    assert response.json()["barcode"] is None
    assert response.json()["product_name"] is None


def test_list_scans_is_reverse_chronological_and_paginated(
    migrated_database_url: str,
) -> None:
    with scan_client(migrated_database_url) as client:
        first = client.post("/api/scans", json={"sku": "FIRST"}).json()
        second = client.post("/api/scans", json={"sku": "SECOND"}).json()

        first_page = client.get("/api/scans", params={"offset": 0, "limit": 1})
        second_page = client.get("/api/scans", params={"offset": 1, "limit": 1})

    assert first_page.status_code == 200
    assert first_page.json() == {
        "items": [
            {
                "id": second["id"],
                "sku": "SECOND",
                "barcode": None,
                "product_name": None,
                "status": "draft",
                "missing_required_views": ["top", "front", "side"],
                "created_at": second["created_at"],
                "updated_at": second["updated_at"],
                "image_count": 0,
            }
        ],
        "total": 2,
        "offset": 0,
        "limit": 1,
    }
    assert second_page.json()["items"][0]["id"] == first["id"]
    assert second_page.json()["total"] == 2


def test_read_missing_scan_returns_safe_structured_error(
    migrated_database_url: str,
) -> None:
    missing_id = "d8de2af4-cd83-41e0-a5d9-00963fb72865"

    with scan_client(migrated_database_url) as client:
        response = client.get(f"/api/scans/{missing_id}")

    assert response.status_code == 404
    assert response.json() == {
        "code": "SCAN_NOT_FOUND",
        "message": "The requested scan was not found.",
        "recoverable": False,
        "suggested_action": "Return to scan history and select an existing scan.",
    }
    assert "\\" not in response.text


def test_scan_inputs_and_pagination_are_bounded(migrated_database_url: str) -> None:
    with scan_client(migrated_database_url) as client:
        blank_sku = client.post("/api/scans", json={"sku": "   "})
        unknown_field = client.post(
            "/api/scans",
            json={"sku": "SKU", "status": "ready_for_processing"},
        )
        oversized_page = client.get("/api/scans", params={"limit": 101})

    assert blank_sku.status_code == 422
    assert unknown_field.status_code == 422
    assert oversized_page.status_code == 422


def test_public_detail_and_summary_do_not_expose_storage_fields(
    migrated_database_url: str,
) -> None:
    with scan_client(migrated_database_url) as client:
        created = client.post("/api/scans", json={"sku": "SAFE-PUBLIC-SCHEMA"}).json()
        database = cast(Database, client.app.state.database)
        from backend.app.contracts import ImageView
        from backend.app.models.scan import ScanImage

        with database.session_factory() as session:
            session.add(
                ScanImage(
                    scan_id=created["id"],
                    view_type=ImageView.TOP,
                    storage_key=f"scans/{created['id']}/original/operation/image.jpg",
                    media_type="image/jpeg",
                    file_extension=".jpg",
                    size_bytes=2048,
                    width_px=1920,
                    height_px=1080,
                )
            )
            session.commit()

        detail = client.get(f"/api/scans/{created['id']}")
        history = client.get("/api/scans")

    assert detail.status_code == 200
    image = detail.json()["images"][0]
    assert set(image) == {
        "id",
        "view_type",
        "media_type",
        "size_bytes",
        "width_px",
        "height_px",
        "created_at",
    }
    assert detail.json()["missing_required_views"] == ["front", "side"]
    assert history.json()["items"][0]["image_count"] == 1
    assert "storage_key" not in detail.text
    assert "original/operation" not in detail.text


def database_failure() -> OperationalError:
    return OperationalError(
        "SELECT secret FROM C:\\private\\database.sqlite",
        {"password": "not-public"},
        RuntimeError("private database failure"),
    )


def assert_sanitized_database_failure(response: Response) -> None:
    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE
    assert "SELECT secret" not in response.text
    assert "private" not in response.text
    assert "database.sqlite" not in response.text
    assert "not-public" not in response.text


def test_create_late_database_failure_returns_sanitized_structured_error(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit(_session: Session) -> None:
        raise database_failure()

    monkeypatch.setattr(Session, "commit", fail_commit)
    with scan_client(migrated_database_url) as client:
        response = client.post("/api/scans", json={"sku": "CREATE-DB-FAILURE"})

    assert_sanitized_database_failure(response)


def test_read_late_database_failure_returns_sanitized_structured_error(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with scan_client(migrated_database_url) as client:
        created = client.post("/api/scans", json={"sku": "READ-DB-FAILURE"}).json()

        def fail_scalar(_session: Session, *_args: object, **_kwargs: object) -> None:
            raise database_failure()

        monkeypatch.setattr(Session, "scalar", fail_scalar)
        response = client.get(f"/api/scans/{created['id']}")

    assert_sanitized_database_failure(response)


def test_list_late_database_failure_returns_sanitized_structured_error(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with scan_client(migrated_database_url) as client:
        client.post("/api/scans", json={"sku": "LIST-DB-FAILURE"})

        def fail_scalars(_session: Session, *_args: object, **_kwargs: object) -> None:
            raise database_failure()

        monkeypatch.setattr(Session, "scalars", fail_scalars)
        response = client.get("/api/scans")

    assert_sanitized_database_failure(response)
