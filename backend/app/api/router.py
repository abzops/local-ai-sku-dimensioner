"""Top-level API router."""

from fastapi import APIRouter, HTTPException, status

from backend.app.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])


@api_router.api_route(
    "/{unmatched_path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def api_not_found(unmatched_path: str) -> None:
    """Keep unknown API requests inside the API JSON error boundary."""
    del unmatched_path
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
