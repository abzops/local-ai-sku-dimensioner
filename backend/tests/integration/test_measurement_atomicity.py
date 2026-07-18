from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.errors import ApplicationError
from backend.app.services.measurement_storage import MeasurementStorage


def test_operation_owned_compensation_cannot_delete_another_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forged batch target is rejected before recursive cleanup."""
    storage = MeasurementStorage(tmp_path)
    scan_id = str(uuid4())
    first_attempt = str(uuid4())
    other_attempt = str(uuid4())
    other_directory = (
        tmp_path / "scans" / scan_id / "measurements" / other_attempt / "previews"
    )
    other_directory.mkdir(parents=True)
    sentinel = other_directory / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    forged = SimpleNamespace(
        scan_id=scan_id,
        attempt_id=first_attempt,
        operation_id=str(uuid4()),
        final_directory=other_directory,
    )
    monkeypatch.setattr(
        storage,
        "_final_directory",
        lambda _scan_id, _attempt_id: (
            tmp_path / "scans" / scan_id / "measurements" / first_attempt / "previews"
        ),
    )

    with pytest.raises(ApplicationError):
        storage.cleanup_finalized(forged)

    assert sentinel.read_text(encoding="utf-8") == "keep"
