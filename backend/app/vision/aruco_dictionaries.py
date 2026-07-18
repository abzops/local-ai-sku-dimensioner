"""Strict mapping between public dictionary names and OpenCV constants."""

from __future__ import annotations

from typing import Final

import cv2

from backend.app.calibration_contracts import ArucoDictionary

ARUCO_DICTIONARY_CONSTANTS: Final[dict[ArucoDictionary, int]] = {
    ArucoDictionary.DICT_4X4_50: cv2.aruco.DICT_4X4_50,
    ArucoDictionary.DICT_5X5_50: cv2.aruco.DICT_5X5_50,
    ArucoDictionary.DICT_6X6_50: cv2.aruco.DICT_6X6_50,
}


def get_aruco_dictionary(dictionary: ArucoDictionary) -> cv2.aruco.Dictionary:
    """Return the one approved OpenCV dictionary matching the public enum."""
    try:
        dictionary_constant = ARUCO_DICTIONARY_CONSTANTS[dictionary]
    except KeyError as error:
        raise ValueError("Unsupported ArUco dictionary") from error
    return cv2.aruco.getPredefinedDictionary(dictionary_constant)


def marker_module_count(dictionary: ArucoDictionary, border_bits: int) -> int:
    """Return the complete black-square grid size including the marker border."""
    if border_bits != 1:
        raise ValueError("Phase 2 marker border must be one bit")
    aruco_dictionary = get_aruco_dictionary(dictionary)
    return int(aruco_dictionary.markerSize + (2 * border_bits))

