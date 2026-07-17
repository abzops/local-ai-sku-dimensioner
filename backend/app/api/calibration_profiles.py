"""Calibration options, immutable profile, activation, and marker SVG routes."""

from importlib import import_module
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Path, Response, status

from backend.app.calibration_contracts import MarkerProfileSpec
from backend.app.dependencies import SessionDependency
from backend.app.schemas.calibration import (
    CalibrationOptionsResponse,
    CalibrationProfileCreateRequest,
    CalibrationProfileListResponse,
    CalibrationProfileResponse,
    calibration_options,
)
from backend.app.services.calibration_profiles import (
    activate_calibration_profile,
    create_calibration_profile,
    get_calibration_profile,
    get_profile_model,
    list_calibration_profiles,
    profile_spec,
)

router = APIRouter(prefix="/calibration")


class MarkerSvgGenerator(Protocol):
    def __call__(self, profile: MarkerProfileSpec) -> str: ...


@router.get("/options", response_model=CalibrationOptionsResponse)
def read_calibration_options() -> CalibrationOptionsResponse:
    return calibration_options()


@router.post(
    "/profiles",
    response_model=CalibrationProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_calibration_profile_endpoint(
    request: CalibrationProfileCreateRequest,
    session: SessionDependency,
) -> CalibrationProfileResponse:
    return create_calibration_profile(session, request)


@router.get("/profiles", response_model=CalibrationProfileListResponse)
def list_calibration_profiles_endpoint(
    session: SessionDependency,
) -> CalibrationProfileListResponse:
    return list_calibration_profiles(session)


@router.get("/profiles/{profile_id}", response_model=CalibrationProfileResponse)
def read_calibration_profile_endpoint(
    session: SessionDependency,
    profile_id: Annotated[UUID, Path(description="Server-generated profile UUID")],
) -> CalibrationProfileResponse:
    return get_calibration_profile(session, str(profile_id))


@router.post("/profiles/{profile_id}/activate", response_model=CalibrationProfileResponse)
def activate_calibration_profile_endpoint(
    session: SessionDependency,
    profile_id: Annotated[UUID, Path(description="Server-generated profile UUID")],
) -> CalibrationProfileResponse:
    return activate_calibration_profile(session, str(profile_id))


@router.get("/profiles/{profile_id}/marker.svg")
def download_calibration_marker(
    session: SessionDependency,
    profile_id: Annotated[UUID, Path(description="Server-generated profile UUID")],
) -> Response:
    profile = get_profile_model(session, str(profile_id))
    svg = _generate_marker_svg(profile_spec(profile))
    filename = f"aruco-marker-{profile.marker_id}.svg"
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _generate_marker_svg(profile: MarkerProfileSpec) -> str:
    """Resolve the deterministic generator lazily to keep API and vision ownership separate."""

    module = import_module("backend.app.vision.marker_generation")
    generator = cast(MarkerSvgGenerator, module.generate_marker_svg)
    return generator(profile)

