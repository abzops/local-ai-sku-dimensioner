"""Tests for deterministic foreground signals and marker exclusion."""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.vision import foreground as foreground_module
from backend.app.vision.foreground import extract_foreground
from backend.app.vision.full_plane import GeometryPolicy, rectify_full_plane
from backend.app.vision.marker_engine import analyze_marker_image
from backend.tests.fixtures.phase3_synthetic_factory import marker_profile, render_scene


def _extract(**scene_options: bool):  # type: ignore[no-untyped-def]
    scene = render_scene(ImageView.TOP, **scene_options)
    marker = analyze_marker_image(scene.image_bgr, marker_profile())
    plane = rectify_full_plane(scene.image_bgr, marker, GeometryPolicy())
    return extract_foreground(
        plane, plane.marker_polygon_px, ImageView.TOP, GeometryPolicy()
    )


def test_multisignal_mask_excludes_marker_and_reports_channel_mad() -> None:
    result = _extract(noise_components=True)

    assert len(result.supported_signal_names) >= 3
    assert len(result.background_lab_mad) == 3
    assert all(value >= 0.0 for value in result.background_lab_mad)
    assert np.count_nonzero(
        (result.mask > 0) & (result.marker_guard_mask > 0)
    ) == 0
    assert result.component_count == 1
    assert 0.0 <= result.shadow_fraction <= 1.0
    assert 0.0 <= result.reflection_fraction <= 1.0


def test_low_contrast_fails_safely() -> None:
    with pytest.raises(ApplicationError) as captured:
        _extract(low_contrast=True)
    assert captured.value.payload.code == "FOREGROUND_LOW_CONTRAST"
    assert captured.value.payload.view is ImageView.TOP


def test_controlled_shadow_does_not_replace_the_product_core() -> None:
    result = _extract(shadow=True)

    assert np.count_nonzero(result.strong_core_mask) > 0
    assert result.component_count == 1
    assert result.shadow_fraction > 0.0


def test_dependent_adaptive_mask_cannot_satisfy_independent_signal_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_binary = foreground_module._binary
    binary_calls = 0

    def isolate_one_independent_signal(condition, usable):  # type: ignore[no-untyped-def]
        nonlocal binary_calls
        binary_calls += 1
        if binary_calls == 2:
            return np.zeros_like(usable)
        return original_binary(condition, usable)

    monkeypatch.setattr(foreground_module, "_binary", isolate_one_independent_signal)
    monkeypatch.setattr(
        foreground_module,
        "_edge_region_mask",
        lambda _gray, usable, _policy, _pixels_per_mm: np.zeros_like(usable),
    )

    with pytest.raises(ApplicationError) as captured:
        _extract()

    assert captured.value.payload.code == "FOREGROUND_LOW_CONTRAST"
