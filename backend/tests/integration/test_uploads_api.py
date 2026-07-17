"""Cross-subsystem integration tests for Phase 1 image uploads."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.models.scan import ScanImage


def png_bytes(*, size: tuple[int, int] = (12, 8)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(38, 118, 184)).save(output, format="PNG")
    return output.getvalue()


def image_part(name: str, content: bytes | None = None) -> tuple[str, bytes, str]:
    return (name, content if content is not None else png_bytes(), "image/png")


def create_scan(client: TestClient, sku: str = "PHASE1-UPLOAD") -> dict[str, object]:
    response = client.post("/api/scans", json={"sku": sku})
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def stored_files(data_root: Path) -> list[Path]:
    scans_root = data_root / "scans"
    return sorted(path for path in scans_root.rglob("*") if path.is_file())


def test_upload_required_views_updates_status_and_safe_public_metadata(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan = create_scan(client)
        scan_id = str(scan["id"])
        response = client.post(
            f"/api/scans/{scan_id}/images",
            files=[
                ("side", image_part("customer-side.png")),
                ("top", image_part("customer-top.png")),
                ("front", image_part("customer-front.png")),
            ],
        )
        detail = client.get(f"/api/scans/{scan_id}")
        history = client.get("/api/scans")

    assert response.status_code == 201
    payload = response.json()
    assert [image["view_type"] for image in payload["uploaded_images"]] == [
        "top",
        "front",
        "side",
    ]
    assert payload["scan"]["status"] == "ready_for_processing"
    assert payload["scan"]["missing_required_views"] == []
    assert detail.json() == payload["scan"]
    assert history.json()["items"][0]["image_count"] == 3

    for image in payload["uploaded_images"]:
        assert set(image) == {
            "id",
            "view_type",
            "media_type",
            "size_bytes",
            "width_px",
            "height_px",
            "created_at",
        }
    assert "storage_key" not in response.text
    assert "customer-top" not in response.text
    assert str(app_settings.data_root) not in response.text

    files = stored_files(app_settings.data_root)
    assert len(files) == 3
    assert all(re.fullmatch(r"[0-9a-f-]{36}\.png", file.name) for file in files)
    assert not any("customer" in file.name for file in files)


def test_invalid_file_makes_the_complete_batch_fail_without_records_or_files(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan = create_scan(client, "ATOMIC-VALIDATION")
        scan_id = str(scan["id"])
        response = client.post(
            f"/api/scans/{scan_id}/images",
            files=[
                ("top", image_part("top.png")),
                ("side", image_part("side.png", b"not-an-image")),
            ],
        )
        detail = client.get(f"/api/scans/{scan_id}")

    assert response.status_code == 422
    assert response.json() == {
        "code": "IMAGE_DECODE_FAILED",
        "message": "The image content could not be decoded.",
        "recoverable": True,
        "suggested_action": "Choose a valid, unmodified image and retry.",
        "field": "side",
        "view": "side",
    }
    assert detail.json()["status"] == "draft"
    assert detail.json()["images"] == []
    assert stored_files(app_settings.data_root) == []


def test_duplicate_required_view_is_rejected_without_touching_owned_files(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "DUPLICATE-VIEW")["id"])
        first = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("top", image_part("first.png"))],
        )
        files_after_first = stored_files(app_settings.data_root)
        duplicate = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("top", image_part("second.png"))],
        )
        detail = client.get(f"/api/scans/{scan_id}")

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "DUPLICATE_VIEW"
    assert duplicate.json()["view"] == "top"
    assert stored_files(app_settings.data_root) == files_after_first
    assert detail.json()["status"] == "images_uploaded"
    assert len(detail.json()["images"]) == 1


def test_additional_images_are_repeatable_but_limited_per_scan(
    app_settings: Settings,
) -> None:
    settings = app_settings.model_copy(update={"max_additional_images": 3})
    app = create_app(settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "ADDITIONAL-LIMIT")["id"])
        accepted = client.post(
            f"/api/scans/{scan_id}/images",
            files=[
                ("additional", image_part("one.png")),
                ("additional", image_part("two.png")),
            ],
        )
        accepted_later = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("additional", image_part("three.png"))],
        )
        before_rejected = stored_files(settings.data_root)
        rejected = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("additional", image_part("four.png"))],
        )
        detail = client.get(f"/api/scans/{scan_id}")

    assert accepted.status_code == 201
    assert accepted_later.status_code == 201
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "ADDITIONAL_IMAGE_LIMIT_EXCEEDED"
    assert stored_files(settings.data_root) == before_rejected
    assert [image["view_type"] for image in detail.json()["images"]] == [
        "additional",
        "additional",
        "additional",
    ]


def test_database_failure_after_finalization_is_compensated(
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "DB-COMPENSATION")["id"])
        original_flush = Session.flush

        def fail_image_flush(
            session: Session,
            objects: object | None = None,
        ) -> None:
            if any(isinstance(value, ScanImage) for value in session.new):
                raise OperationalError("forced insert", {}, RuntimeError("forced"))
            original_flush(session, objects)

        monkeypatch.setattr(Session, "flush", fail_image_flush)
        response = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("top", image_part("top.png"))],
        )

        database = cast(Database, client.app.state.database)
        with database.session_factory() as session:
            image_count = session.scalar(select(func.count()).select_from(ScanImage))

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert image_count == 0
    assert stored_files(app_settings.data_root) == []


def test_storage_failure_is_structured_and_does_not_leak_local_paths(
    tmp_path: Path,
    migrated_database_url: str,
) -> None:
    conflicting_root = tmp_path / "data-root-is-a-file"
    conflicting_root.write_text("not a directory", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_root=conflicting_root,
        database_url=migrated_database_url,
        frontend_dist_dir=tmp_path / "missing-dist",
        min_image_long_edge=12,
        min_image_short_edge=8,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "STORAGE-FAILURE")["id"])
        response = client.post(
            f"/api/scans/{scan_id}/images",
            files=[("top", image_part("top.png"))],
        )
        detail = client.get(f"/api/scans/{scan_id}")

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert str(conflicting_root) not in response.text
    assert "Traceback" not in response.text
    assert detail.json()["images"] == []


def test_parser_rejects_oversized_file_before_application_validation(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "PARSER-SIZE-LIMIT")["id"])
        response = client.post(
            f"/api/scans/{scan_id}/images",
            files=[
                (
                    "top",
                    image_part("large.png", b"x" * (app_settings.max_upload_bytes + 1)),
                )
            ],
        )

    assert response.status_code == 413
    assert response.json() == {
        "code": "FILE_TOO_LARGE",
        "message": "The image exceeds the maximum upload size.",
        "recoverable": True,
        "suggested_action": "Choose an image no larger than 1 MiB.",
        "field": "top",
        "view": "top",
    }
    assert stored_files(app_settings.data_root) == []


def test_malformed_multipart_and_parser_file_count_errors_are_structured(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "PARSER-ERRORS")["id"])
        malformed = client.post(
            f"/api/scans/{scan_id}/images",
            content=b"not-a-valid-multipart-body",
            headers={"Content-Type": "multipart/form-data"},
        )
        too_many = client.post(
            f"/api/scans/{scan_id}/images",
            files=[
                ("additional", image_part(f"additional-{number}.png"))
                for number in range(app_settings.max_upload_files_per_request + 1)
            ],
        )

    assert malformed.status_code == 400
    assert malformed.json() == {
        "code": "MALFORMED_MULTIPART",
        "message": "The multipart upload could not be parsed.",
        "recoverable": True,
        "suggested_action": "Choose the images again and retry the upload.",
    }
    assert too_many.status_code == 400
    assert too_many.json()["code"] == "UPLOAD_LIMIT_EXCEEDED"
    assert "detail" not in malformed.json()
    assert "detail" not in too_many.json()
    assert stored_files(app_settings.data_root) == []


def test_empty_missing_and_invalid_scan_uploads_are_structured(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        scan_id = str(create_scan(client, "REQUEST-ERRORS")["id"])
        empty = client.post(f"/api/scans/{scan_id}/images")
        missing = client.post(
            "/api/scans/6ee1a334-044d-4641-8100-c6134bc2f5ce/images",
            files=[("top", image_part("top.png"))],
        )
        invalid = client.post(
            "/api/scans/not-a-uuid/images",
            files=[("top", image_part("top.png"))],
        )

    assert empty.status_code == 400
    assert empty.json()["code"] == "NO_FILES_PROVIDED"
    assert missing.status_code == 404
    assert missing.json()["code"] == "SCAN_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_REQUEST"
    assert invalid.json()["field"] == "scan_id"
    assert stored_files(app_settings.data_root) == []
