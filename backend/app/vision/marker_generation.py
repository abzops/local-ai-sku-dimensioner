"""Deterministic, exact-physical-size SVG generation for calibration markers."""

from __future__ import annotations

import math

import cv2

from backend.app.calibration_contracts import (
    MARKER_BORDER_BITS,
    MARKER_ID_MAX,
    MARKER_ID_MIN,
    MarkerProfileSpec,
)
from backend.app.vision.aruco_dictionaries import (
    get_aruco_dictionary,
    marker_module_count,
)


def generate_marker_svg(profile: MarkerProfileSpec) -> str:
    """Generate a deterministic script-free SVG for the selected marker."""
    _validate_generation_profile(profile)
    module_count = marker_module_count(profile.dictionary, profile.border_bits)
    marker = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(profile.dictionary),
        profile.marker_id,
        module_count,
        borderBits=profile.border_bits,
    )

    physical_size = _format_number(profile.marker_size_mm)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{physical_size}mm" '
            f'height="{physical_size}mm" viewBox="0 0 {module_count} {module_count}" '
            'shape-rendering="crispEdges">'
        ),
        f'  <rect width="{module_count}" height="{module_count}" fill="#000"/>',
    ]
    for row in range(module_count):
        for column in range(module_count):
            if int(marker[row, column]) == 255:
                lines.append(
                    f'  <rect x="{column}" y="{row}" width="1" height="1" fill="#fff"/>'
                )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _validate_generation_profile(profile: MarkerProfileSpec) -> None:
    if not MARKER_ID_MIN <= profile.marker_id <= MARKER_ID_MAX:
        raise ValueError("Marker ID must be between 0 and 49")
    if profile.border_bits != MARKER_BORDER_BITS:
        raise ValueError("Phase 2 marker border must be one bit")
    if not math.isfinite(profile.marker_size_mm) or profile.marker_size_mm <= 0:
        raise ValueError("Marker size must be finite and positive")


def _format_number(value: float) -> str:
    return format(value, ".15g")

