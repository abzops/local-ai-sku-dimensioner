"""Cross-subsystem integration tests for in-memory calibration analysis."""

from __future__ import annotations

import base64
from dataclasses import replace
from io import BytesIO
from typing import cast

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.vision.marker_engine import analyze_marker_image as real_analyze_marker_image

PROFILE_REQUEST = {
    "name": "Integration marker",
    "dictionary": "DICT_4X4_50",
    "marker_id": 0,
    "marker_size_mm": 100.0,
    "minimum_marker_side_px": 64,
    "maximum_perspective_ratio": 3.0,
    "maximum_homography_condition_number": 1_000_000.0,
    "maximum_marker_edge_residual_px": 2.0,
    "rectified_pixels_per_mm": 4.0,
}


def marker_png(
    marker_ids: tuple[int, ...] = (0,),
    *,
    dictionary_name: str = "DICT_4X4_50",
) -> bytes:
    """Return a deterministic Phase 2 test canvas with one or two sharp markers."""
    canvas = np.full((720, 1280), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, dictionary_name)
    )
    marker_edge = 360 if len(marker_ids) == 1 else 260
    x_positions = (460,) if len(marker_ids) == 1 else (250, 770)
    top = (canvas.shape[0] - marker_edge) // 2
    for marker_id, left in zip(marker_ids, x_positions, strict=True):
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_edge)
        canvas[top : top + marker_edge, left : left + marker_edge] = marker
    encoded, payload = cv2.imencode(".png", canvas)
    assert encoded
    return payload.tobytes()


def create_profile(client: TestClient, **updates: object) -> dict[str, object]:
    request = {**PROFILE_REQUEST, **updates}
    response = client.post("/api/calibration/profiles", json=request)
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_calibration_test_returns_complete_marker_plane_evidence_without_persistence(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile = create_profile(client)
        profile_id = str(profile["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("private-capture.png", marker_png(), "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_id"] == profile_id
    assert payload["dictionary"] == "DICT_4X4_50"
    assert payload["marker_id"] == 0
    assert [corner["label"] for corner in payload["ordered_corners"]] == [
        "top_left",
        "top_right",
        "bottom_right",
        "bottom_left",
    ]
    assert len(payload["image_to_marker_mm"]) == 3
    assert len(payload["marker_mm_to_image"]) == 3
    assert payload["marker_edge_quality"]["valid"] is True
    assert payload["marker_edge_quality"]["sample_count"] >= 32
    assert set(payload["marker_edge_quality"]["per_edge_rms_px"]) == {
        "top",
        "right",
        "bottom",
        "left",
    }
    for preview_name in ("annotated_preview", "rectified_preview"):
        preview = payload[preview_name]
        assert preview["media_type"] == "image/png"
        assert base64.b64decode(preview["data_base64"], validate=True).startswith(
            b"\x89PNG\r\n\x1a\n"
        )
    assert "private-capture" not in response.text
    assert str(app_settings.data_root) not in response.text
    assert not (app_settings.data_root / "calibration").exists()
    assert all(
        "private-capture" not in path.name
        for path in app_settings.data_root.rglob("*")
    )


def test_calibration_test_rejects_missing_repeated_and_unexpected_fields(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        endpoint = f"/api/calibration/profiles/{profile_id}/test"
        missing = client.post(endpoint)
        unexpected = client.post(
            endpoint,
            files={"top": ("marker.png", marker_png(), "image/png")},
        )
        repeated = client.post(
            endpoint,
            files=[
                ("image", ("first.png", marker_png(), "image/png")),
                ("image", ("second.png", marker_png(), "image/png")),
            ],
        )

    assert missing.status_code == 400
    assert missing.json()["code"] == "NO_FILES_PROVIDED"
    assert unexpected.status_code == 400
    assert unexpected.json()["code"] == "INVALID_UPLOAD_FIELD"
    assert repeated.status_code == 400
    assert repeated.json()["code"] == "UPLOAD_LIMIT_EXCEEDED"


def test_calibration_test_reuses_upload_validation_with_calibration_context(
    app_settings: Settings,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("invalid.png", b"not-an-image", "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_DECODE_FAILED"
    assert response.json()["field"] == "image"
    assert "view" not in response.json()


@pytest.mark.parametrize(
    ("ids", "expected_code"),
    [
        ((1,), "REFERENCE_WRONG_ID"),
        ((0, 1), "REFERENCE_AMBIGUOUS"),
    ],
)
def test_calibration_test_rejects_wrong_and_additional_markers(
    app_settings: Settings,
    ids: tuple[int, ...],
    expected_code: str,
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("marker.png", marker_png(ids), "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == expected_code
    assert "Traceback" not in response.text


def test_calibration_test_sanitizes_unexpected_opencv_failures(
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_analysis(_image: np.ndarray, _profile: object) -> None:
        raise cv2.error("C:\\private\\marker.png SQL secret internal failure")

    monkeypatch.setattr(
        "backend.app.services.calibration_application.analyze_marker_image",
        fail_analysis,
    )
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("marker.png", marker_png(), "image/png")},
        )

    assert response.status_code == 422
    assert response.json() == {
        "code": "CALIBRATION_TEST_FAILED",
        "message": "The marker image could not be analyzed safely.",
        "recoverable": True,
        "suggested_action": (
            "Retake the image with the complete marker clearly visible and retry."
        ),
        "field": "image",
    }
    assert "private" not in response.text
    assert "SQL" not in response.text
    assert "internal failure" not in response.text


def test_calibration_test_sanitizes_late_response_validation_failures(
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def inconsistent_analysis(image: np.ndarray, profile: object) -> object:
        result = real_analyze_marker_image(image, profile)  # type: ignore[arg-type]
        return replace(result, rectified_width_px=result.rectified_width_px + 1)

    monkeypatch.setattr(
        "backend.app.services.calibration_application.analyze_marker_image",
        inconsistent_analysis,
    )
    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("marker.png", marker_png(), "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "CALIBRATION_TEST_FAILED"
    assert "validation" not in response.text.lower()
    assert str(app_settings.data_root) not in response.text


def test_calibration_test_accepts_exif_oriented_validated_images(
    app_settings: Settings,
) -> None:
    """The application boundary must preserve Phase 1 EXIF orientation handling."""
    source = marker_png()
    image = cv2.imdecode(np.frombuffer(source, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert image is not None
    from PIL import Image

    output = BytesIO()
    pil_image = Image.fromarray(image)
    exif = pil_image.getexif()
    exif[274] = 6
    pil_image.save(output, format="JPEG", exif=exif, quality=100)

    app = create_app(app_settings)
    with TestClient(app) as client:
        profile_id = str(create_profile(client)["id"])
        response = client.post(
            f"/api/calibration/profiles/{profile_id}/test",
            files={"image": ("rotated.jpg", output.getvalue(), "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["marker_id"] == 0
