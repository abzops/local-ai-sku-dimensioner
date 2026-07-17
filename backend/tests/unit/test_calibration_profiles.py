"""Focused unit tests for immutable calibration profile contracts and services."""

from math import inf, nan
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from backend.app.calibration_contracts import ArucoDictionary
from backend.app.database import Database
from backend.app.errors import ApplicationError
from backend.app.models.calibration import CalibrationProfile
from backend.app.schemas.calibration import (
    CalibrationProfileCreateRequest,
    CalibrationTestResponse,
    calibration_options,
)
from backend.app.services.calibration_profiles import (
    activate_calibration_profile,
    create_calibration_profile,
    profile_spec,
)


def profile_request(name: str) -> CalibrationProfileCreateRequest:
    return CalibrationProfileCreateRequest(
        name=name,
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=0,
        marker_size_mm=100.0,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


def test_options_are_the_exact_database_independent_frozen_values() -> None:
    assert calibration_options().model_dump(mode="json") == {
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


@pytest.mark.parametrize(
    "changes",
    [
        {"dictionary": "DICT_7X7_50"},
        {"marker_id": -1},
        {"marker_id": 50},
        {"marker_size_mm": 9.9},
        {"minimum_marker_side_px": 23},
        {"maximum_perspective_ratio": 10.1},
        {"maximum_homography_condition_number": inf},
        {"maximum_marker_edge_residual_px": nan},
        {"rectified_pixels_per_mm": 6.1},
        {"unexpected": "field"},
    ],
)
def test_profile_request_rejects_out_of_contract_values(changes: dict[str, Any]) -> None:
    payload = profile_request("Validation profile").model_dump()
    payload.update(changes)

    with pytest.raises(ValidationError):
        CalibrationProfileCreateRequest.model_validate(payload)


def test_profile_request_is_stripped_and_immutable() -> None:
    request = profile_request("  Immutable profile  ")

    assert request.name == "Immutable profile"
    with pytest.raises(ValidationError):
        request.name = "Changed"


def marker_test_payload() -> dict[str, object]:
    preview = {
        "media_type": "image/png",
        "width_px": 100,
        "height_px": 100,
        "data_base64": (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/"
            "x8AAusB9WlX7Z8AAAAASUVORK5CYII="
        ),
    }
    return {
        "profile_id": "29779fdf-2fd0-4ff1-a86a-a783bda5f97c",
        "dictionary": "DICT_4X4_50",
        "marker_id": 0,
        "marker_size_mm": 100.0,
        "ordered_corners": [
            {"label": "top_left", "x_px": 10.0, "y_px": 10.0},
            {"label": "top_right", "x_px": 110.0, "y_px": 10.0},
            {"label": "bottom_right", "x_px": 110.0, "y_px": 110.0},
            {"label": "bottom_left", "x_px": 10.0, "y_px": 110.0},
        ],
        "orientation_degrees": 0.0,
        "edge_lengths_px": {
            "top": 100.0,
            "right": 100.0,
            "bottom": 100.0,
            "left": 100.0,
        },
        "perspective_ratio": 1.0,
        "image_to_marker_mm": [[1.0, 0.0, -10.0], [0.0, 1.0, -10.0], [0.0, 0.0, 1.0]],
        "marker_mm_to_image": [[1.0, 0.0, 10.0], [0.0, 1.0, 10.0], [0.0, 0.0, 1.0]],
        "homography_condition_number": 1.0,
        "rectified_width_px": 100,
        "rectified_height_px": 100,
        "rectified_pixels_per_mm": 4.0,
        "marker_edge_quality": {
            "metric_name": "marker_edge_localization_residual",
            "description": "Sampled marker-border localization residual in image pixels.",
            "rms_px": 0.5,
            "maximum_px": 1.0,
            "sample_count": 64,
            "per_edge_rms_px": {
                "top": 0.5,
                "right": 0.5,
                "bottom": 0.5,
                "left": 0.5,
            },
            "threshold_px": 2.0,
            "valid": True,
        },
        "annotated_preview": preview,
        "rectified_preview": preview,
    }


def test_calibration_test_response_enforces_nested_frozen_contract() -> None:
    validated = CalibrationTestResponse.model_validate(marker_test_payload())
    assert [corner.label.value for corner in validated.ordered_corners] == [
        "top_left",
        "top_right",
        "bottom_right",
        "bottom_left",
    ]

    invalid_order = marker_test_payload()
    ordered_corners = cast(list[dict[str, object]], invalid_order["ordered_corners"])
    ordered_corners[0]["label"] = "top_right"
    with pytest.raises(ValidationError):
        CalibrationTestResponse.model_validate(invalid_order)

    unknown_nested = marker_test_payload()
    quality = cast(dict[str, object], unknown_nested["marker_edge_quality"])
    quality["reprojection_error"] = 0.1
    with pytest.raises(ValidationError):
        CalibrationTestResponse.model_validate(unknown_nested)

    malformed_preview = marker_test_payload()
    preview = cast(dict[str, object], malformed_preview["annotated_preview"])
    preview["data_base64"] = "not-base64"
    with pytest.raises(ValidationError):
        CalibrationTestResponse.model_validate(malformed_preview)


def test_activation_switches_once_and_marker_spec_preserves_values(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    try:
        with database.session_factory() as session:
            first = create_calibration_profile(session, profile_request("First"))
            second = create_calibration_profile(
                session,
                CalibrationProfileCreateRequest(
                    **{
                        **profile_request("Second").model_dump(),
                        "dictionary": ArucoDictionary.DICT_6X6_50,
                        "marker_id": 49,
                    }
                ),
            )
            activated_first = activate_calibration_profile(session, first.id)
            activated_second = activate_calibration_profile(session, second.id)

            assert activated_first.is_active is True
            assert activated_second.is_active is True
            assert activated_second.activated_at is not None
            model = session.get(CalibrationProfile, second.id)
            assert model is not None
            spec = profile_spec(model)

        with database.session_factory() as session:
            persisted_first = session.get(CalibrationProfile, first.id)
            persisted_second = session.get(CalibrationProfile, second.id)
            assert persisted_first is not None and persisted_first.is_active is False
            assert persisted_second is not None and persisted_second.is_active is True

        assert spec.dictionary is ArucoDictionary.DICT_6X6_50
        assert spec.marker_id == 49
        assert spec.border_bits == 1
        assert spec.marker_size_mm == 100.0
    finally:
        database.dispose()


def test_activation_failure_rolls_back_deactivation(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(migrated_database_url)
    try:
        with database.session_factory() as session:
            first = create_calibration_profile(session, profile_request("Rollback active"))
            second = create_calibration_profile(session, profile_request("Rollback target"))
            activate_calibration_profile(session, first.id)

        with database.session_factory() as failing_session:
            def fail_flush(*_args: object, **_kwargs: object) -> None:
                raise OperationalError("private SQL", {}, RuntimeError("private path"))

            monkeypatch.setattr(failing_session, "flush", fail_flush)
            with pytest.raises(ApplicationError) as caught:
                activate_calibration_profile(failing_session, second.id)

        assert caught.value.status_code == 503
        assert caught.value.payload.code == "DATABASE_UNAVAILABLE"
        with database.session_factory() as verification_session:
            persisted_first = verification_session.get(CalibrationProfile, first.id)
            persisted_second = verification_session.get(CalibrationProfile, second.id)
            assert persisted_first is not None and persisted_first.is_active is True
            assert persisted_second is not None and persisted_second.is_active is False
    finally:
        database.dispose()

