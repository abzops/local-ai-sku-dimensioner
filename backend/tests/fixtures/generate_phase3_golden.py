"""Explicit generator for the checked-in Phase 3 golden fixture set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2

from backend.app.contracts import ImageView
from backend.tests.fixtures.phase3_synthetic_factory import render_scene


def generate(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    specifications = {
        "nominal_top.png": (ImageView.TOP, False, False),
        "nominal_front.png": (ImageView.FRONT, False, False),
        "nominal_side.png": (ImageView.SIDE, False, False),
        "perspective_top.png": (ImageView.TOP, True, False),
        "perspective_front.png": (ImageView.FRONT, True, False),
        "perspective_side.png": (ImageView.SIDE, True, False),
        "ambiguous_top.png": (ImageView.TOP, False, True),
    }
    manifest: dict[str, object] = {
        "generator": "backend/tests/fixtures/generate_phase3_golden.py",
        "opencv_version": cv2.__version__,
        "physical_plane": "marker and product silhouette are generated in one plane",
        "files": {},
    }
    file_records: dict[str, object] = {}
    for filename, (view, perspective, ambiguous) in specifications.items():
        scene = render_scene(view, perspective=perspective, ambiguous=ambiguous)
        target = output_directory / filename
        success = cv2.imwrite(str(target), scene.image_bgr)
        if not success:
            raise RuntimeError(f"Could not generate {filename}")
        content = target.read_bytes()
        file_records[filename] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "view": view.value,
            "perspective": perspective,
            "ambiguous": ambiguous,
            "expected_dimensions_mm": scene.expected_dimensions_mm,
        }
    manifest["files"] = file_records
    (output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent / "phase3")
