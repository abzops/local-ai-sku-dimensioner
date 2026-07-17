"""Health API integration tests."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.config import Settings
from backend.app.database import expected_alembic_head
from backend.app.main import create_app

DATABASE_UNAVAILABLE_RESPONSE = {
    "code": "DATABASE_UNAVAILABLE",
    "message": "The local database is unavailable or has not been initialized.",
    "recoverable": True,
    "suggested_action": "Run scripts/setup_windows.ps1, then restart the application.",
}


def replace_database_revision(database_url: str, revision: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": revision},
            )
    finally:
        engine.dispose()


def test_health_reports_readiness_at_correct_migration_head(app_settings: Settings) -> None:
    app = create_app(app_settings)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Local AI SKU Dimensioner",
        "version": "0.1.0",
        "database": {"status": "ok", "revision": expected_alembic_head()},
    }


def test_health_returns_structured_error_for_unmigrated_database(tmp_path: Path) -> None:
    database_path = tmp_path / "unmigrated" / "app.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+pysqlite:///{database_path.as_posix()}",
        frontend_dist_dir=tmp_path / "missing-dist",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE


def test_health_returns_structured_error_for_stale_revision(
    app_settings: Settings,
) -> None:
    assert app_settings.database_url is not None
    replace_database_revision(app_settings.database_url, "0001_phase0")
    app = create_app(app_settings)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE


def test_health_returns_structured_error_for_invalid_revision(
    app_settings: Settings,
) -> None:
    assert app_settings.database_url is not None
    replace_database_revision(app_settings.database_url, "not-a-real-revision")
    app = create_app(app_settings)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE


def test_health_starts_degraded_for_conflicting_data_root(tmp_path: Path) -> None:
    conflicting_root = tmp_path / "data-root-is-a-file"
    conflicting_root.write_text("not a directory", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_root=conflicting_root,
        frontend_dist_dir=tmp_path / "missing-dist",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert client.app.state.database is None
        assert client.app.state.database_initialization_error == (
            "DATABASE_INITIALIZATION_FAILED"
        )

    assert response.status_code == 503
    assert response.json() == DATABASE_UNAVAILABLE_RESPONSE
    assert str(conflicting_root) not in response.text
    assert "Traceback" not in response.text
