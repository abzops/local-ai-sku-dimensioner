"""Unit tests for the frozen Phase 1 scan status rules."""

import pytest

from backend.app.contracts import ImageView, ScanStatus
from backend.app.services.scans import calculate_scan_status, missing_required_views


@pytest.mark.parametrize(
    ("views", "expected"),
    [
        ([], ScanStatus.DRAFT),
        ([ImageView.ADDITIONAL], ScanStatus.IMAGES_UPLOADED),
        ([ImageView.TOP], ScanStatus.IMAGES_UPLOADED),
        ([ImageView.TOP, ImageView.FRONT], ScanStatus.IMAGES_UPLOADED),
        (
            [ImageView.TOP, ImageView.FRONT, ImageView.SIDE],
            ScanStatus.READY_FOR_PROCESSING,
        ),
        (
            ["additional", "side", "front", "top", "additional"],
            ScanStatus.READY_FOR_PROCESSING,
        ),
    ],
)
def test_calculate_scan_status(
    views: list[ImageView | str],
    expected: ScanStatus,
) -> None:
    assert calculate_scan_status(views) is expected


def test_missing_required_views_preserves_public_order() -> None:
    assert missing_required_views([ImageView.FRONT, ImageView.ADDITIONAL]) == [
        ImageView.TOP,
        ImageView.SIDE,
    ]
