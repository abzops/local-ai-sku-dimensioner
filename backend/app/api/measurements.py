"""Phase 3 measurement options, processing, history, detail, and preview routes."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.dependencies import SessionDependency, SettingsDependency
from backend.app.measurement_contracts import MeasurementView
from backend.app.models.measurement import MeasurementAttempt, MeasurementPreview
from backend.app.schemas.measurements import (
    MeasurementAttemptDetailResponse,
    MeasurementAttemptListResponse,
    MeasurementOptionsResponse,
    MeasurementProcessRequest,
    MeasurementSettings,
    capture_setup_snapshot,
    measurement_options,
    measurement_policy_snapshot,
)
from backend.app.services.measurement_results import (
    get_measurement_detail,
    get_measurement_preview_model,
    list_measurement_attempts,
)

router = APIRouter()


class MeasurementProcessor(Protocol):
    """Narrow orchestration boundary owned by the Phase 3 application service."""

    def process(
        self,
        session: Session,
        scan_id: str,
        request: MeasurementProcessRequest,
    ) -> tuple[MeasurementAttempt, bool]: ...


class MeasurementPreviewStorage(Protocol):
    """Narrow read boundary owned by the Phase 3 storage service."""

    def read_preview(self, preview: MeasurementPreview) -> bytes: ...


@router.get("/measurements/options", response_model=MeasurementOptionsResponse)
def read_measurement_options(settings: SettingsDependency) -> MeasurementOptionsResponse:
    """Return database-independent capture and measurement policy options."""
    return measurement_options(cast(MeasurementSettings, settings))


@router.post(
    "/scans/{scan_id}/measurements",
    response_model=MeasurementAttemptDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def process_measurement_endpoint(
    request: MeasurementProcessRequest,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
) -> MeasurementAttemptDetailResponse:
    """Synchronously create or idempotently replay one measurement attempt."""
    scan_id_string = str(scan_id)
    attempt, replayed = _measurement_processor(settings).process(
        session,
        scan_id_string,
        request,
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
    return get_measurement_detail(
        session,
        scan_id_string,
        attempt.id,
        capture_snapshot=capture_setup_snapshot(cast(MeasurementSettings, settings)),
        policy_snapshot=measurement_policy_snapshot(cast(MeasurementSettings, settings)),
    )


@router.get(
    "/scans/{scan_id}/measurements",
    response_model=MeasurementAttemptListResponse,
)
def list_measurements_endpoint(
    session: SessionDependency,
    settings: SettingsDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MeasurementAttemptListResponse:
    """List immutable measurement attempts newest first."""
    return list_measurement_attempts(
        session,
        str(scan_id),
        capture_snapshot=capture_setup_snapshot(cast(MeasurementSettings, settings)),
        policy_snapshot=measurement_policy_snapshot(cast(MeasurementSettings, settings)),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/scans/{scan_id}/measurements/{measurement_id}",
    response_model=MeasurementAttemptDetailResponse,
)
def read_measurement_endpoint(
    session: SessionDependency,
    settings: SettingsDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
    measurement_id: Annotated[
        UUID,
        Path(description="Server-generated measurement-attempt UUID"),
    ],
) -> MeasurementAttemptDetailResponse:
    """Return one immutable attempt with safe, structured evidence."""
    return get_measurement_detail(
        session,
        str(scan_id),
        str(measurement_id),
        capture_snapshot=capture_setup_snapshot(cast(MeasurementSettings, settings)),
        policy_snapshot=measurement_policy_snapshot(cast(MeasurementSettings, settings)),
    )


@router.get("/scans/{scan_id}/measurements/{measurement_id}/previews/{view}")
def read_measurement_preview_endpoint(
    session: SessionDependency,
    settings: SettingsDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
    measurement_id: Annotated[
        UUID,
        Path(description="Server-generated measurement-attempt UUID"),
    ],
    view: Annotated[MeasurementView, Path(description="Required measurement view")],
) -> Response:
    """Return one verified local PNG without exposing its private storage key."""
    preview = get_measurement_preview_model(
        session,
        str(scan_id),
        str(measurement_id),
        view,
    )
    content = _measurement_preview_storage(settings).read_preview(preview)
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "Content-Length": str(len(content)),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _measurement_processor(settings: Settings) -> MeasurementProcessor:
    """Resolve orchestration lazily so API ownership remains non-overlapping."""
    module = import_module("backend.app.services.measurement_application")
    service_class = cast(
        Callable[[Settings], MeasurementProcessor],
        module.MeasurementApplicationService,
    )
    return service_class(settings)


def _measurement_preview_storage(settings: Settings) -> MeasurementPreviewStorage:
    """Resolve storage lazily so API ownership remains non-overlapping."""
    module = import_module("backend.app.services.measurement_storage")
    service_class = cast(
        Callable[[Settings], MeasurementPreviewStorage],
        module.MeasurementStorage,
    )
    return service_class(settings)
