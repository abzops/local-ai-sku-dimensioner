"""Tests for the frozen public/OpenCV ArUco dictionary mapping."""

import cv2
import pytest

from backend.app.calibration_contracts import ArucoDictionary
from backend.app.vision.aruco_dictionaries import (
    get_aruco_dictionary,
    marker_module_count,
)


@pytest.mark.parametrize(
    ("name", "marker_bits"),
    [
        (ArucoDictionary.DICT_4X4_50, 4),
        (ArucoDictionary.DICT_5X5_50, 5),
        (ArucoDictionary.DICT_6X6_50, 6),
    ],
)
def test_approved_dictionary_mapping(name: ArucoDictionary, marker_bits: int) -> None:
    dictionary = get_aruco_dictionary(name)

    assert isinstance(dictionary, cv2.aruco.Dictionary)
    assert dictionary.markerSize == marker_bits
    assert dictionary.bytesList.shape[0] == 50
    assert marker_module_count(name, 1) == marker_bits + 2


def test_marker_module_count_rejects_non_phase2_border() -> None:
    with pytest.raises(ValueError, match="one bit"):
        marker_module_count(ArucoDictionary.DICT_4X4_50, 2)

