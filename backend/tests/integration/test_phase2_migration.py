"""Integration tests for the Phase 2 calibration profile migration."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
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


def valid_profile_values(profile_id: str, name: str) -> dict[str, object]:
    return {
        "id": profile_id,
        "name": name,
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
    }


def test_phase2_migration_creates_expected_schema_and_can_downgrade(
    database_url: str,
) -> None:
    config = migration_config(database_url)
    command.upgrade(config, "0002_phase1_scans")
    engine = create_engine(database_url)
    try:
        assert "calibration_profiles" not in inspect(engine).get_table_names()

        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert "calibration_profiles" in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns("calibration_profiles")} == {
            "id",
            "name",
            "dictionary",
            "marker_id",
            "marker_size_mm",
            "border_bits",
            "minimum_marker_side_px",
            "maximum_perspective_ratio",
            "maximum_homography_condition_number",
            "maximum_marker_edge_residual_px",
            "rectified_pixels_per_mm",
            "is_active",
            "created_at",
            "activated_at",
        }
        indexes = {index["name"]: index for index in inspector.get_indexes("calibration_profiles")}
        assert indexes["uq_calibration_profiles_single_active"]["unique"] == 1
        assert indexes["ix_calibration_profiles_created_at"]["unique"] == 0

        command.downgrade(config, "0002_phase1_scans")
        assert "calibration_profiles" not in inspect(engine).get_table_names()
        assert {"scans", "scan_images"}.issubset(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_phase2_database_constraints_and_single_active_index(database_url: str) -> None:
    command.upgrade(migration_config(database_url), "head")
    engine = create_engine(database_url)
    insert_profile = text(
        """
        INSERT INTO calibration_profiles (
            id, name, dictionary, marker_id, marker_size_mm, border_bits,
            minimum_marker_side_px, maximum_perspective_ratio,
            maximum_homography_condition_number, maximum_marker_edge_residual_px,
            rectified_pixels_per_mm, is_active
        ) VALUES (
            :id, :name, :dictionary, :marker_id, :marker_size_mm, :border_bits,
            :minimum_marker_side_px, :maximum_perspective_ratio,
            :maximum_homography_condition_number, :maximum_marker_edge_residual_px,
            :rectified_pixels_per_mm, :is_active
        )
        """
    )
    try:
        with engine.begin() as connection:
            connection.execute(insert_profile, valid_profile_values("profile-one", "One"))
            connection.execute(insert_profile, valid_profile_values("profile-two", "Two"))

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE calibration_profiles SET is_active = 1 WHERE id = 'profile-one'")
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE calibration_profiles SET is_active = 1 WHERE id = 'profile-two'")
                )

        invalid_values = valid_profile_values("profile-invalid", "Invalid")
        invalid_values["marker_id"] = 50
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(insert_profile, invalid_values)

        duplicate_name = valid_profile_values("profile-duplicate", "One")
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(insert_profile, duplicate_name)
    finally:
        engine.dispose()

