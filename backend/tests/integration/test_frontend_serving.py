"""Production frontend routing integration tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def production_app(app_settings: Settings, tmp_path: Path) -> tuple[Settings, str]:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    marker = "phase-0-spa-shell"
    (dist_dir / "index.html").write_text(
        f"<!doctype html><html><body>{marker}</body></html>",
        encoding="utf-8",
    )
    settings = app_settings.model_copy(update={"frontend_dist_dir": dist_dir})
    return settings, marker


def test_frontend_route_falls_back_to_spa(
    app_settings: Settings,
    tmp_path: Path,
) -> None:
    settings, marker = production_app(app_settings, tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/status")

    assert response.status_code == 200
    assert marker in response.text


def test_unknown_api_route_returns_json_404(
    app_settings: Settings,
    tmp_path: Path,
) -> None:
    settings, marker = production_app(app_settings, tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert marker not in response.text


def test_missing_compiled_asset_does_not_fall_back_to_spa(
    app_settings: Settings,
    tmp_path: Path,
) -> None:
    settings, marker = production_app(app_settings, tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert marker not in response.text
