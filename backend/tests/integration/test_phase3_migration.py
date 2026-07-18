"""Integration tests for the Phase 3 measurement persistence migration."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.app.config import REPOSITORY_ROOT


def migration_config(database_url: str) -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(REPOSITORY_ROOT / "backend" / "migrations"),
    )
    config.attributes["database_url"] = database_url
    return config


def test_phase3_migration_creates_exact_tables_and_can_downgrade(
    database_url: str,
) -> None:
    config = migration_config(database_url)
    command.upgrade(config, "0003_phase2_calibration_profiles")
    engine = create_engine(database_url)
    try:
        assert "measurement_attempts" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert {
            "measurement_attempts",
            "measurement_sources",
            "measurement_previews",
        }.issubset(inspector.get_table_names())
        assert {
            column["name"] for column in inspector.get_columns("measurement_attempts")
        } == {
            "id",
            "scan_id",
            "request_id",
            "request_signature",
            "reprocess_of_measurement_id",
            "calibration_profile_id",
            "status",
            "processing_version",
            "algorithm_version",
            "profile_snapshot_json",
            "capture_setup_snapshot_json",
            "measurement_policy_snapshot_json",
            "source_fingerprint",
            "length_mm",
            "width_mm",
            "height_mm",
            "per_view_evidence_json",
            "reconciliation_evidence_json",
            "quality_evidence_json",
            "uncertainty_evidence_json",
            "warnings_json",
            "failure_json",
            "lease_token",
            "lease_expires_at",
            "created_at",
            "started_at",
            "completed_at",
        }
        attempt_indexes = {
            item["name"]: item for item in inspector.get_indexes("measurement_attempts")
        }
        assert attempt_indexes["uq_measurement_attempts_processing_scan"]["unique"] == 1

        command.downgrade(config, "0003_phase2_calibration_profiles")
        tables = inspect(engine).get_table_names()
        assert "measurement_attempts" not in tables
        assert "measurement_sources" not in tables
        assert "measurement_previews" not in tables
        assert "calibration_profiles" in tables
    finally:
        engine.dispose()


def seed_dependencies(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO scans (id, sku, status) "
            "VALUES ('scan-one', 'SKU-ONE', 'ready_for_processing')"
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO calibration_profiles (
                id, name, dictionary, marker_id, marker_size_mm, border_bits,
                minimum_marker_side_px, maximum_perspective_ratio,
                maximum_homography_condition_number,
                maximum_marker_edge_residual_px, rectified_pixels_per_mm, is_active
            ) VALUES (
                'profile-one', 'Profile One', 'DICT_4X4_50', 0, 100, 1,
                64, 3, 1000000, 2, 4, 1
            )
            """
        )
    )


def insert_processing_attempt(
    connection: Connection,
    attempt_id: str,
    request_id: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO measurement_attempts (
                id, scan_id, request_id, request_signature, calibration_profile_id,
                status, processing_version, algorithm_version, profile_snapshot_json,
                capture_setup_snapshot_json, measurement_policy_snapshot_json,
                lease_token, lease_expires_at
            ) VALUES (
                :id, 'scan-one', :request_id, '{}', 'profile-one', 'processing',
                'phase3-v1', 'deterministic-geometry-v1', '{}', '{}', '{}',
                :lease_token, '2099-01-01 00:00:00'
            )
            """
        ),
        {"id": attempt_id, "request_id": request_id, "lease_token": request_id},
    )


def test_processing_uniqueness_and_terminal_immutability(
    database_url: str,
) -> None:
    command.upgrade(migration_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            seed_dependencies(connection)
            insert_processing_attempt(connection, "attempt-one", "request-one")

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                insert_processing_attempt(connection, "attempt-two", "request-two")

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO scan_images (
                        id, scan_id, view_type, storage_key, media_type, file_extension,
                        size_bytes, width_px, height_px
                    ) VALUES (
                        'image-one', 'scan-one', 'top', 'scans/scan-one/top.png',
                        'image/png', '.png', 2048, 1600, 1200
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO measurement_sources (
                        id, measurement_attempt_id, view, scan_image_id,
                        storage_key_snapshot, media_type, size_bytes, width_px, height_px
                    ) VALUES (
                        'source-one', 'attempt-one', 'top', 'image-one',
                        'private/source.png', 'image/png', 2048, 1600, 1200
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE measurement_attempts
                    SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                        failure_json = '{"code":"PRODUCT_NOT_DETECTED"}'
                    WHERE id = 'attempt-one'
                    """
                )
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE measurement_attempts SET algorithm_version = 'changed' ")
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE measurement_sources SET width_px = 1 "
                        "WHERE id = 'source-one'"
                    )
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM measurement_attempts WHERE id = 'attempt-one'")
                )
    finally:
        engine.dispose()
