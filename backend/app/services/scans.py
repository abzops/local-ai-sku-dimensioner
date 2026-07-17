"""Persistence operations and deterministic scan status calculation."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Never

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.app.contracts import (
    REQUIRED_IMAGE_VIEW_ORDER,
    REQUIRED_IMAGE_VIEWS,
    ImageView,
    ScanStatus,
)
from backend.app.errors import ApplicationError
from backend.app.models.scan import Scan, ScanImage
from backend.app.schemas.scans import (
    CreateScanRequest,
    ScanDetail,
    ScanImageResponse,
    ScanListResponse,
    ScanSummary,
)

PUBLIC_IMAGE_VIEW_ORDER = {
    ImageView.TOP: 0,
    ImageView.FRONT: 1,
    ImageView.SIDE: 2,
    ImageView.ADDITIONAL: 3,
}


def timestamp_order(value: datetime) -> float:
    """Return a comparable UTC sort key for SQLite-naive and aware timestamps."""
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).timestamp()


def normalize_view(view: ImageView | str) -> ImageView:
    return view if isinstance(view, ImageView) else ImageView(view)


def missing_required_views(view_types: Iterable[ImageView | str]) -> list[ImageView]:
    """Return absent required views in the frozen top/front/side order."""
    present = {normalize_view(view) for view in view_types}
    return [view for view in REQUIRED_IMAGE_VIEW_ORDER if view not in present]


def calculate_scan_status(view_types: Iterable[ImageView | str]) -> ScanStatus:
    """Calculate the Phase 1 status solely from persisted image views."""
    present = {normalize_view(view) for view in view_types}
    if not present:
        return ScanStatus.DRAFT
    if REQUIRED_IMAGE_VIEWS.issubset(present):
        return ScanStatus.READY_FOR_PROCESSING
    return ScanStatus.IMAGES_UPLOADED


def image_response(image: ScanImage) -> ScanImageResponse:
    return ScanImageResponse.model_validate(image)


def scan_detail(scan: Scan) -> ScanDetail:
    missing = missing_required_views(image.view_type for image in scan.images)
    ordered_images = sorted(
        scan.images,
        key=lambda image: (
            PUBLIC_IMAGE_VIEW_ORDER[image.view_type],
            timestamp_order(image.created_at),
            image.id,
        ),
    )
    return ScanDetail(
        id=scan.id,
        sku=scan.sku,
        barcode=scan.barcode,
        product_name=scan.product_name,
        status=scan.status,
        missing_required_views=missing,
        created_at=scan.created_at,
        updated_at=scan.updated_at,
        images=[image_response(image) for image in ordered_images],
    )


def scan_summary(scan: Scan) -> ScanSummary:
    missing = missing_required_views(image.view_type for image in scan.images)
    return ScanSummary(
        id=scan.id,
        sku=scan.sku,
        barcode=scan.barcode,
        product_name=scan.product_name,
        status=scan.status,
        missing_required_views=missing,
        created_at=scan.created_at,
        updated_at=scan.updated_at,
        image_count=len(scan.images),
    )


def create_scan(session: Session, request: CreateScanRequest) -> ScanDetail:
    """Create and commit an empty draft scan."""
    try:
        scan = Scan(
            sku=request.sku,
            barcode=request.barcode,
            product_name=request.product_name,
            status=ScanStatus.DRAFT,
        )
        session.add(scan)
        session.commit()
        return scan_detail(scan)
    except SQLAlchemyError:
        _raise_database_unavailable(session)


def get_scan_model(session: Session, scan_id: str) -> Scan:
    """Load a scan and its images or raise the safe public not-found error."""
    try:
        scan = session.scalar(
            select(Scan).options(selectinload(Scan.images)).where(Scan.id == scan_id)
        )
    except SQLAlchemyError:
        _raise_database_unavailable(session)
    if scan is None:
        raise ApplicationError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SCAN_NOT_FOUND",
            message="The requested scan was not found.",
            recoverable=False,
            suggested_action="Return to scan history and select an existing scan.",
        )
    return scan


def get_scan(session: Session, scan_id: str) -> ScanDetail:
    return scan_detail(get_scan_model(session, scan_id))


def list_scans(session: Session, *, offset: int, limit: int) -> ScanListResponse:
    """Return a deterministic reverse-chronological page of scans."""
    try:
        total = session.scalar(select(func.count()).select_from(Scan)) or 0
        scans = session.scalars(
            select(Scan)
            .options(selectinload(Scan.images))
            .order_by(Scan.created_at.desc(), Scan.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return ScanListResponse(
            items=[scan_summary(scan) for scan in scans],
            total=total,
            offset=offset,
            limit=limit,
        )
    except SQLAlchemyError:
        _raise_database_unavailable(session)


def _raise_database_unavailable(session: Session) -> Never:
    """Roll back safely and expose only the established database error contract."""
    try:
        session.rollback()
    except SQLAlchemyError:
        pass
    raise ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    ) from None
