"""Calibration profile persistence and transaction-safe activation."""

from typing import Never

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.calibration_contracts import MarkerProfileSpec
from backend.app.errors import ApplicationError
from backend.app.models.calibration import CalibrationProfile, utc_now
from backend.app.schemas.calibration import (
    CalibrationProfileCreateRequest,
    CalibrationProfileListResponse,
    CalibrationProfileResponse,
)


def profile_response(profile: CalibrationProfile) -> CalibrationProfileResponse:
    return CalibrationProfileResponse.model_validate(profile)


def profile_spec(profile: CalibrationProfile) -> MarkerProfileSpec:
    """Convert persisted values to the frozen vision-engine input."""

    return MarkerProfileSpec(
        dictionary=profile.dictionary,
        marker_id=profile.marker_id,
        marker_size_mm=profile.marker_size_mm,
        border_bits=profile.border_bits,
        minimum_marker_side_px=profile.minimum_marker_side_px,
        maximum_perspective_ratio=profile.maximum_perspective_ratio,
        maximum_homography_condition_number=profile.maximum_homography_condition_number,
        maximum_marker_edge_residual_px=profile.maximum_marker_edge_residual_px,
        rectified_pixels_per_mm=profile.rectified_pixels_per_mm,
    )


def create_calibration_profile(
    session: Session,
    request: CalibrationProfileCreateRequest,
) -> CalibrationProfileResponse:
    """Create one inactive immutable profile."""

    profile = CalibrationProfile(
        name=request.name,
        dictionary=request.dictionary,
        marker_id=request.marker_id,
        marker_size_mm=request.marker_size_mm,
        minimum_marker_side_px=request.minimum_marker_side_px,
        maximum_perspective_ratio=request.maximum_perspective_ratio,
        maximum_homography_condition_number=request.maximum_homography_condition_number,
        maximum_marker_edge_residual_px=request.maximum_marker_edge_residual_px,
        rectified_pixels_per_mm=request.rectified_pixels_per_mm,
    )
    session.add(profile)
    try:
        session.commit()
        return profile_response(profile)
    except IntegrityError:
        _rollback_quietly(session)
        raise ApplicationError(
            status_code=status.HTTP_409_CONFLICT,
            code="CALIBRATION_PROFILE_NAME_CONFLICT",
            message="A calibration profile with this name already exists.",
            recoverable=True,
            suggested_action="Choose a unique calibration profile name and try again.",
            field="name",
        ) from None
    except SQLAlchemyError:
        _raise_database_unavailable(session)


def get_profile_model(session: Session, profile_id: str) -> CalibrationProfile:
    """Load one profile or raise a sanitized public error."""

    try:
        profile = session.scalar(
            select(CalibrationProfile).where(CalibrationProfile.id == profile_id)
        )
    except SQLAlchemyError:
        _raise_database_unavailable(session)
    if profile is None:
        raise _profile_not_found()
    return profile


def get_calibration_profile(
    session: Session,
    profile_id: str,
) -> CalibrationProfileResponse:
    return profile_response(get_profile_model(session, profile_id))


def list_calibration_profiles(session: Session) -> CalibrationProfileListResponse:
    """List active first, followed by newest profiles in deterministic order."""

    try:
        total = session.scalar(select(func.count()).select_from(CalibrationProfile)) or 0
        profiles = session.scalars(
            select(CalibrationProfile).order_by(
                CalibrationProfile.is_active.desc(),
                CalibrationProfile.created_at.desc(),
                CalibrationProfile.id.desc(),
            )
        ).all()
        return CalibrationProfileListResponse(
            items=[profile_response(profile) for profile in profiles],
            total=total,
        )
    except SQLAlchemyError:
        _raise_database_unavailable(session)


def activate_calibration_profile(
    session: Session,
    profile_id: str,
) -> CalibrationProfileResponse:
    """Atomically switch the single active profile using one final commit."""

    try:
        # SQLite is the only supported database. Acquiring the writer reservation before
        # reading prevents two deferred transactions from making decisions on stale state.
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        target = session.scalar(
            select(CalibrationProfile).where(CalibrationProfile.id == profile_id)
        )
        if target is None:
            _rollback_quietly(session)
            raise _profile_not_found()

        active = session.scalar(
            select(CalibrationProfile).where(CalibrationProfile.is_active.is_(True))
        )
        if active is not None:
            active.is_active = False
        session.flush()

        target.is_active = True
        target.activated_at = utc_now()
        session.commit()
        return profile_response(target)
    except ApplicationError:
        raise
    except SQLAlchemyError:
        _raise_database_unavailable(session)


def _profile_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="CALIBRATION_PROFILE_NOT_FOUND",
        message="The requested calibration profile was not found.",
        recoverable=False,
        suggested_action="Select an existing calibration profile and try again.",
    )


def _rollback_quietly(session: Session) -> None:
    try:
        session.rollback()
    except SQLAlchemyError:
        pass


def _raise_database_unavailable(session: Session) -> Never:
    _rollback_quietly(session)
    raise ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    ) from None

