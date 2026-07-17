"""Tests for deterministic exact-size marker SVG generation."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from dataclasses import replace

import cv2
import pytest

from backend.app.calibration_contracts import ArucoDictionary, MarkerProfileSpec
from backend.app.vision.aruco_dictionaries import (
    get_aruco_dictionary,
    marker_module_count,
)
from backend.app.vision.marker_generation import generate_marker_svg


def _profile(
    dictionary: ArucoDictionary = ArucoDictionary.DICT_4X4_50,
    marker_id: int = 0,
) -> MarkerProfileSpec:
    return MarkerProfileSpec(
        dictionary=dictionary,
        marker_id=marker_id,
        marker_size_mm=100.0,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
    )


@pytest.mark.parametrize("dictionary", list(ArucoDictionary))
@pytest.mark.parametrize("marker_id", [0, 49])
def test_svg_matches_opencv_marker_bits(
    dictionary: ArucoDictionary, marker_id: int
) -> None:
    profile = _profile(dictionary, marker_id)
    svg = generate_marker_svg(profile)
    root = element_tree.fromstring(svg)
    module_count = marker_module_count(dictionary, 1)
    expected = cv2.aruco.generateImageMarker(
        get_aruco_dictionary(dictionary), marker_id, module_count, borderBits=1
    )
    white_cells = {
        (int(node.attrib["y"]), int(node.attrib["x"]))
        for node in root
        if node.attrib.get("fill") == "#fff"
    }

    assert root.attrib["width"] == "100mm"
    assert root.attrib["height"] == "100mm"
    assert root.attrib["viewBox"] == f"0 0 {module_count} {module_count}"
    assert white_cells == {
        (row, column)
        for row in range(module_count)
        for column in range(module_count)
        if int(expected[row, column]) == 255
    }
    assert svg == generate_marker_svg(profile)
    assert "<script" not in svg.lower()
    assert "href=" not in svg.lower()
    assert "path" not in svg.lower()


def test_svg_uses_configured_physical_black_square_size() -> None:
    svg = generate_marker_svg(replace(_profile(), marker_size_mm=37.5))

    assert 'width="37.5mm"' in svg
    assert 'height="37.5mm"' in svg


@pytest.mark.parametrize(
    "profile",
    [
        replace(_profile(), marker_id=-1),
        replace(_profile(), marker_id=50),
        replace(_profile(), border_bits=2),
        replace(_profile(), marker_size_mm=float("nan")),
    ],
)
def test_svg_rejects_invalid_internal_profile(profile: MarkerProfileSpec) -> None:
    with pytest.raises(ValueError):
        generate_marker_svg(profile)

