"""Production frontend mounting."""

from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """Serve the SPA shell for route-like paths without masking missing assets or APIs."""

    @staticmethod
    def _is_frontend_route(path: str, scope: Scope) -> bool:
        normalized_path = path.strip("/")
        return (
            scope["method"] in {"GET", "HEAD"}
            and normalized_path != "api"
            and not normalized_path.startswith("api/")
            and not PurePosixPath(normalized_path).suffix
        )

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or not self._is_frontend_route(path, scope):
                raise
        return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, dist_dir: Path) -> bool:
    """Mount an existing Vite build and report whether it was available."""
    if not (dist_dir / "index.html").is_file():
        return False
    app.mount("/", SPAStaticFiles(directory=dist_dir, html=True), name="frontend")
    return True
