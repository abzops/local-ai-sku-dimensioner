"""Create, read, and list Phase 1 scan records."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from backend.app.dependencies import SessionDependency
from backend.app.schemas.scans import CreateScanRequest, ScanDetail, ScanListResponse
from backend.app.services.scans import create_scan, get_scan, list_scans

router = APIRouter(prefix="/scans")


@router.post("", response_model=ScanDetail, status_code=status.HTTP_201_CREATED)
def create_scan_endpoint(
    request: CreateScanRequest,
    session: SessionDependency,
) -> ScanDetail:
    return create_scan(session, request)


@router.get("", response_model=ScanListResponse)
def list_scans_endpoint(
    session: SessionDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ScanListResponse:
    return list_scans(session, offset=offset, limit=limit)


@router.get("/{scan_id}", response_model=ScanDetail)
def read_scan_endpoint(
    session: SessionDependency,
    scan_id: Annotated[UUID, Path(description="Server-generated scan UUID")],
) -> ScanDetail:
    return get_scan(session, str(scan_id))
