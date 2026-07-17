"""Database initialization tests."""

from pathlib import Path

from backend.app.database import Database


def test_migration_initializes_sqlite(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    database = Database(migrated_database_url)
    try:
        database.check_connection()
        assert database.current_revision() == "0001_phase0"
    finally:
        database.dispose()

    assert (tmp_path / "database" / "test.db").is_file()

