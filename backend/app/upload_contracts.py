"""Frozen interfaces between upload HTTP, validation, storage, and persistence."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from fastapi import UploadFile

from backend.app.contracts import ImageView

CanonicalExtension: TypeAlias = Literal[".jpg", ".png", ".webp"]
CanonicalMediaType: TypeAlias = Literal["image/jpeg", "image/png", "image/webp"]


@dataclass(frozen=True, slots=True)
class UploadInput:
    """One client upload with its server-assigned semantic view."""

    view_type: ImageView
    file: UploadFile


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """Decoded and validated metadata while the source upload remains open."""

    image_id: str
    view_type: ImageView
    canonical_extension: CanonicalExtension
    media_type: CanonicalMediaType
    size_bytes: int
    width_px: int
    height_px: int
    file: UploadFile


@dataclass(frozen=True, slots=True)
class StagedImage:
    """A validated image copied to a transaction-owned staging file."""

    image_id: str
    view_type: ImageView
    canonical_extension: CanonicalExtension
    media_type: CanonicalMediaType
    size_bytes: int
    width_px: int
    height_px: int
    staging_path: Path


@dataclass(frozen=True, slots=True)
class StagedUploadBatch:
    """All files owned by one not-yet-finalized upload operation."""

    scan_id: str
    operation_id: str
    staging_directory: Path
    final_directory: Path
    images: tuple[StagedImage, ...]


@dataclass(frozen=True, slots=True)
class FinalizedImage:
    """Final file metadata ready for insertion into the database."""

    image_id: str
    view_type: ImageView
    storage_key: str
    canonical_extension: CanonicalExtension
    media_type: CanonicalMediaType
    size_bytes: int
    width_px: int
    height_px: int
    absolute_path: Path


@dataclass(frozen=True, slots=True)
class FinalizedUploadBatch:
    """A finalized operation whose exact directory remains transaction-owned."""

    scan_id: str
    operation_id: str
    final_directory: Path
    images: tuple[FinalizedImage, ...]
