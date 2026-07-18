"""Top-level API router."""

from fastapi import APIRouter, HTTPException, status

from backend.app.api.calibration_profiles import router as calibration_profiles_router
from backend.app.api.calibration_test import router as calibration_test_router
from backend.app.api.health import router as health_router
from backend.app.api.measurements import router as measurements_router
from backend.app.api.scans import router as scans_router
from backend.app.api.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(measurements_router, tags=["measurements"])
api_router.include_router(calibration_test_router, tags=["calibration"])
api_router.include_router(calibration_profiles_router, tags=["calibration"])
api_router.include_router(uploads_router, tags=["scan-images"])
api_router.include_router(scans_router, tags=["scans"])


@api_router.api_route(
    "/{unmatched_path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def api_not_found(unmatched_path: str) -> None:
    """Keep unknown API requests inside the API JSON error boundary."""
    del unmatched_path
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
