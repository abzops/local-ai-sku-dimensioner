"""Frozen shared Phase 1 domain contracts."""

from enum import StrEnum
from typing import Final


class ScanStatus(StrEnum):
    """The only scan lifecycle states available in Phase 1."""

    DRAFT = "draft"
    IMAGES_UPLOADED = "images_uploaded"
    READY_FOR_PROCESSING = "ready_for_processing"


class ImageView(StrEnum):
    """Image view labels accepted by the Phase 1 upload API."""

    TOP = "top"
    FRONT = "front"
    SIDE = "side"
    ADDITIONAL = "additional"


REQUIRED_IMAGE_VIEWS: Final[frozenset[ImageView]] = frozenset(
    {ImageView.TOP, ImageView.FRONT, ImageView.SIDE}
)
REQUIRED_IMAGE_VIEW_ORDER: Final[tuple[ImageView, ...]] = (
    ImageView.TOP,
    ImageView.FRONT,
    ImageView.SIDE,
)
