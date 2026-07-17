"""Integration tests for the Phase 1 Alembic schema."""

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


def test_phase1_migration_creates_expected_schema_and_can_downgrade(
    database_url: str,
) -> None:
    config = migration_config(database_url)
    command.upgrade(config, "0001_phase0")
    engine = create_engine(database_url)
    try:
        assert {"scans", "scan_images"}.isdisjoint(inspect(engine).get_table_names())

        command.upgrade(config, "head")
        inspector = inspect(engine)

        assert {"scans", "scan_images"}.issubset(inspector.get_table_names())
        assert {column["name"] for column in inspector.get_columns("scans")} == {
            "id", "sku", "barcode", "product_name", "status", "created_at", "updated_at",
        }
        assert {column["name"] for column in inspector.get_columns("scan_images")} == {
            "id", "scan_id", "view_type", "storage_key", "media_type", "file_extension",
            "size_bytes", "width_px", "height_px", "created_at",
        }
        indexes = {index["name"]: index for index in inspector.get_indexes("scan_images")}
        assert indexes["uq_scan_images_required_view"]["unique"] == 1
        assert indexes["ix_scan_images_scan_id"]["unique"] == 0
        foreign_keys = inspector.get_foreign_keys("scan_images")
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["constrained_columns"] == ["scan_id"]
        assert foreign_keys[0]["referred_table"] == "scans"
        assert foreign_keys[0]["referred_columns"] == ["id"]
        assert foreign_keys[0]["options"] == {"ondelete": "CASCADE"}

        command.downgrade(config, "0001_phase0")
        assert {"scans", "scan_images"}.isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_phase1_database_constraints_protect_status_and_required_views(
    database_url: str,
) -> None:
    command.upgrade(migration_config(database_url), "head")
    engine = create_engine(database_url)
    insert_scan = text("INSERT INTO scans (id, sku, status) VALUES (:id, :sku, :status)")
    insert_image = text(
        """
        INSERT INTO scan_images (
            id, scan_id, view_type, storage_key, media_type, file_extension,
            size_bytes, width_px, height_px
        ) VALUES (
            :id, :scan_id, :view_type, :storage_key, 'image/jpeg', '.jpg',
            100, 1280, 720
        )
        """
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                insert_scan,
                {"id": "scan-valid", "sku": "SKU", "status": "draft"},
            )
            connection.execute(
                insert_image,
                {
                    "id": "top-one",
                    "scan_id": "scan-valid",
                    "view_type": "top",
                    "storage_key": "top-one.jpg",
                },
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    insert_image,
                    {
                        "id": "top-two",
                        "scan_id": "scan-valid",
                        "view_type": "top",
                        "storage_key": "top-two.jpg",
                    },
                )

        with engine.begin() as connection:
            for number in (1, 2):
                connection.execute(
                    insert_image,
                    {
                        "id": f"additional-{number}",
                        "scan_id": "scan-valid",
                        "view_type": "additional",
                        "storage_key": f"additional-{number}.jpg",
                    },
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    insert_scan,
                    {"id": "scan-invalid", "sku": "SKU", "status": "processing"},
                )
    finally:
        engine.dispose()
