from __future__ import annotations

import weakref
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from backend.app.calibration_contracts import ArucoDictionary
from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError
from backend.app.models.scan import ScanImage
from backend.app.schemas.calibration import CalibrationProfileResponse
from backend.app.services.measurement_application import (
    FailureEvidence,
    MeasurementApplicationService,
    ReconciliationBundle,
    StageDeadlines,
    SuccessEvidence,
)
from backend.app.services.measurement_storage import MeasurementStorage
from backend.app.services.stored_image_loader import LoadedStoredImage
from backend.app.vision.oriented_geometry import AxisMeasurement, DimensionName


@dataclass
class FakeSettings:
    data_root: Path
    max_upload_bytes: int = 1024 * 1024
    max_image_pixels: int = 1_000_000
    capture_setup_id: str = "rig-local-1"
    capture_setup_version: str = "1"
    capture_setup_type: str = "orthogonal_rig"
    capture_setup_qualified: bool = True
    capture_setup_min_object_mm: float = 75.0
    capture_setup_max_object_mm: float = 400.0
    capture_setup_marker_size_uncertainty_mm: float = 0.5
    capture_setup_plane_uncertainty_mm: float = 1.0
    capture_setup_orthogonality_uncertainty_deg: float = 0.5
    capture_setup_standoff_uncertainty_mm: float = 2.0
    capture_setup_max_off_plane_mm: float = 3.0
    measurement_acceptable_disagreement_mm: float = 5.0
    measurement_acceptable_disagreement_percent: float = 3.0
    measurement_warning_disagreement_mm: float = 10.0
    measurement_warning_disagreement_percent: float = 6.0
    measurement_usable_quality: float = 0.70
    measurement_weak_quality: float = 0.55
    measurement_stronger_source_quality_lead: float = 0.15
    measurement_weaker_source_uncertainty_ratio: float = 2.0
    measurement_max_rectified_edge_px: int = 4096
    measurement_max_rectified_pixels: int = 16_000_000
    measurement_max_physical_extent_mm: float = 1500.0
    measurement_max_components: int = 1024
    measurement_max_candidates: int = 64
    measurement_processing_deadline_seconds: float = 30.0
    measurement_processing_lease_seconds: int = 120


def _profile_json() -> str:
    return CalibrationProfileResponse(
        id=str(uuid4()),
        name="Qualified rig marker",
        dictionary=ArucoDictionary.DICT_4X4_50,
        marker_id=0,
        marker_size_mm=100.0,
        border_bits=1,
        minimum_marker_side_px=64,
        maximum_perspective_ratio=3.0,
        maximum_homography_condition_number=1_000_000.0,
        maximum_marker_edge_residual_px=2.0,
        rectified_pixels_per_mm=4.0,
        is_active=True,
        created_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
    ).model_dump_json()


def _attempt() -> SimpleNamespace:
    scan_id = str(uuid4())
    sources = [
        SimpleNamespace(
            id=str(uuid4()),
            view=SimpleNamespace(value=view.value),
            scan_image_id=str(uuid4()),
            storage_key_snapshot=f"scans/{scan_id}/original/op/{view.value}.png",
            media_type="image/png",
            size_bytes=100,
            width_px=40,
            height_px=20,
        )
        for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    ]
    profile_json = _profile_json()
    profile_id = CalibrationProfileResponse.model_validate_json(profile_json).id
    return SimpleNamespace(
        id=str(uuid4()),
        scan_id=scan_id,
        calibration_profile_id=profile_id,
        profile_snapshot_json=profile_json,
        lease_token=str(uuid4()),
        sources=sources,
    )


def _models(attempt: SimpleNamespace) -> tuple[ScanImage, ScanImage, ScanImage]:
    by_view = {source.view.value: source for source in attempt.sources}
    models = tuple(
        ScanImage(
            id=by_view[view.value].scan_image_id,
            scan_id=attempt.scan_id,
            view_type=view,
            storage_key=by_view[view.value].storage_key_snapshot,
            media_type="image/png",
            file_extension=".png",
            size_bytes=100,
            width_px=40,
            height_px=20,
        )
        for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    )
    return cast(tuple[ScanImage, ScanImage, ScanImage], models)


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 20), (100, 100, 100)).save(output, format="PNG")
    return output.getvalue()


class FakeLoader:
    def __init__(self, *, change_on_revalidation: bool = False) -> None:
        self.calls: dict[ImageView, int] = {}
        self.change_on_revalidation = change_on_revalidation

    def load(self, model: ScanImage) -> LoadedStoredImage:
        count = self.calls.get(model.view_type, 0) + 1
        self.calls[model.view_type] = count
        original = (model.view_type.value[0] * 64)[:64]
        if self.change_on_revalidation and count > 1 and model.view_type is ImageView.SIDE:
            original = "f" * 64
        return LoadedStoredImage(
            scan_image_id=model.id,
            view=model.view_type,
            storage_key=model.storage_key,
            original_sha256=original,
            oriented_pixel_sha256=(model.view_type.value[-1] * 64)[:64],
            media_type=model.media_type,
            size_bytes=model.size_bytes,
            width_px=model.width_px,
            height_px=model.height_px,
            image_bgr=np.zeros((20, 40, 3), dtype=np.uint8),
        )


class MemoryTrackingLoader(FakeLoader):
    def __init__(self) -> None:
        super().__init__()
        self.array_references: list[Any] = []

    def load(self, model: ScanImage) -> LoadedStoredImage:
        assert all(reference() is None for reference in self.array_references)
        loaded = super().load(model)
        self.array_references.append(weakref.ref(loaded.image_bgr))
        return loaded


class FakeSourceResolver:
    def __init__(self, models: tuple[ScanImage, ScanImage, ScanImage]) -> None:
        self.models = models
        self.called = 0

    def resolve(self, _session: Any, _attempt: Any) -> tuple[ScanImage, ScanImage, ScanImage]:
        self.called += 1
        return self.models


class FakePersistence:
    def __init__(self, attempt: SimpleNamespace, *, replayed: bool = False) -> None:
        self.attempt = attempt
        self.replayed = replayed
        self.success: SuccessEvidence | None = None
        self.failure: FailureEvidence | None = None
        self.success_error: ApplicationError | None = None

    def snapshots(self, _settings: Any) -> tuple[SimpleNamespace, SimpleNamespace]:
        return (
            SimpleNamespace(id="rig-local-1", qualified=True),
            SimpleNamespace(),
        )

    def claim(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            attempt=self.attempt,
            replayed=self.replayed,
            reclaimed=False,
        )

    def succeed(
        self,
        _session: Any,
        attempt: Any,
        evidence: SuccessEvidence,
    ) -> Any:
        self.success = evidence
        if self.success_error is not None:
            raise self.success_error
        attempt.terminal = "succeeded"
        return attempt

    def fail(
        self,
        _session: Any,
        attempt: Any,
        evidence: FailureEvidence,
    ) -> Any:
        self.failure = evidence
        attempt.terminal = "failed"
        return attempt


class FakeGeometry:
    def __init__(self, *, fail_stage: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_stage = fail_stage
        self.clock_state: list[float] | None = None

    def policy(self, _policy: Any, _capture: Any) -> SimpleNamespace:
        return SimpleNamespace(usable_quality=0.7)

    def rig(self, _capture: Any) -> object:
        return object()

    def _step(self, name: str, value: Any) -> Any:
        self.calls.append(name)
        if self.fail_stage == name:
            raise ApplicationError(
                status_code=422,
                code="PRODUCT_NOT_DETECTED",
                message="No stable product foreground was detected.",
                recoverable=True,
                suggested_action="Retake the affected view.",
            )
        if name == "marker" and self.clock_state is not None:
            self.clock_state[0] += 2.0
        return value

    def marker(self, *_args: Any) -> Any:
        return self._step("marker", SimpleNamespace())

    def rectify(self, *_args: Any) -> Any:
        return self._step("rectify", SimpleNamespace())

    def foreground(self, *_args: Any) -> Any:
        return self._step("foreground", SimpleNamespace())

    def contour(self, *_args: Any) -> Any:
        return self._step("contour", SimpleNamespace())

    def measure(self, _contour: Any, view: ImageView, _policy: Any) -> Any:
        names = {
            ImageView.TOP: (DimensionName.LENGTH, DimensionName.WIDTH),
            ImageView.FRONT: (DimensionName.WIDTH, DimensionName.HEIGHT),
            ImageView.SIDE: (DimensionName.LENGTH, DimensionName.HEIGHT),
        }[view]
        return self._step(
            "measure",
            SimpleNamespace(
                view=view,
                raw_dimensions=(
                    AxisMeasurement(names[0], 200.0),
                    AxisMeasurement(names[1], 100.0),
                ),
            ),
        )

    def quality(self, *_args: Any) -> Any:
        return self._step("quality", SimpleNamespace(score=0.9))

    def uncertainty(self, *_args: Any) -> Any:
        return self._step("uncertainty", SimpleNamespace(total_mm=2.0))

    def require_quality(self, *_args: Any) -> None:
        self._step("require_quality", None)

    def preview(self, *_args: Any) -> SimpleNamespace:
        return self._step(
            "preview",
            SimpleNamespace(width_px=40, height_px=20, data=_png()),
        )

    def view_evidence(self, loaded: LoadedStoredImage, *_args: Any) -> dict[str, object]:
        return {
            "view": loaded.view.value,
            "warnings": [],
            "preview_available": True,
        }

    def reconcile(self, _work: Any, _policy: Any) -> ReconciliationBundle:
        self.calls.append("reconcile")
        dimensions = tuple(
            {
                "dimension": name,
                "value_mm": value,
                "validation_status": "acceptable",
            }
            for name, value in (("length", 200.0), ("width", 100.0), ("height", 80.0))
        )
        if self.fail_stage == "reconcile":
            return ReconciliationBundle(
                succeeded=False,
                dimensions=cast(Any, dimensions),
                final_dimensions=None,
                overall_quality=None,
                overall_uncertainty_mm=None,
                warnings=("MEASUREMENT_DISAGREEMENT",),
                failure_code="MEASUREMENT_DISAGREEMENT",
            )
        return ReconciliationBundle(
            succeeded=True,
            dimensions=cast(Any, dimensions),
            final_dimensions={"length": 200.0, "width": 100.0, "height": 80.0},
            overall_quality={"score": 0.9},
            overall_uncertainty_mm=3.0,
            warnings=(),
            failure_code=None,
        )


class MemoryTrackingGeometry(FakeGeometry):
    def __init__(self) -> None:
        super().__init__()
        self.array_references: list[Any] = []

    def marker(self, *_args: Any) -> Any:
        assert all(reference() is None for reference in self.array_references)
        return super().marker(*_args)

    def _heavy(self, value: Any) -> Any:
        array = np.zeros((100, 100, 3), dtype=np.uint8)
        value.heavy_array = array
        self.array_references.append(weakref.ref(array))
        return value

    def rectify(self, *_args: Any) -> Any:
        return self._heavy(super().rectify(*_args))

    def foreground(self, *_args: Any) -> Any:
        return self._heavy(super().foreground(*_args))

    def contour(self, *_args: Any) -> Any:
        return self._heavy(super().contour(*_args))

    def measure(self, *args: Any) -> Any:
        return self._heavy(super().measure(*args))


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        expected_capture_setup_id="rig-local-1",
        capture_contract_acknowledged=True,
    )


def _service(
    tmp_path: Path,
    persistence: FakePersistence,
    geometry: FakeGeometry,
    loader: FakeLoader,
    resolver: FakeSourceResolver,
    *,
    deadlines: StageDeadlines | None = None,
    clock: Any = None,
) -> MeasurementApplicationService:
    arguments: dict[str, Any] = {}
    if clock is not None:
        arguments["clock"] = clock
    return MeasurementApplicationService(
        FakeSettings(tmp_path),
        persistence=cast(Any, persistence),
        geometry=cast(Any, geometry),
        source_resolver=cast(Any, resolver),
        image_loader=cast(Any, loader),
        storage=MeasurementStorage(tmp_path),
        deadlines=deadlines,
        **arguments,
    )


def test_default_deadline_uses_configured_processing_limit(tmp_path: Path) -> None:
    attempt = _attempt()
    settings = FakeSettings(tmp_path, measurement_processing_deadline_seconds=17.5)

    service = MeasurementApplicationService(
        settings,
        persistence=cast(Any, FakePersistence(attempt)),
        geometry=cast(Any, FakeGeometry()),
        source_resolver=cast(Any, FakeSourceResolver(_models(attempt))),
        image_loader=cast(Any, FakeLoader()),
        storage=MeasurementStorage(tmp_path),
    )

    assert service.deadlines.total_seconds == 17.5

    injected = StageDeadlines(total_seconds=9.0)
    injected_service = MeasurementApplicationService(
        settings,
        persistence=cast(Any, FakePersistence(attempt)),
        geometry=cast(Any, FakeGeometry()),
        source_resolver=cast(Any, FakeSourceResolver(_models(attempt))),
        image_loader=cast(Any, FakeLoader()),
        storage=MeasurementStorage(tmp_path),
        deadlines=injected,
    )

    assert injected_service.deadlines is injected


def test_configured_lease_reaches_default_persistence_claim(tmp_path: Path) -> None:
    attempt = _attempt()
    settings = FakeSettings(tmp_path, measurement_processing_lease_seconds=177)
    service = MeasurementApplicationService(
        settings,
        geometry=cast(Any, FakeGeometry()),
        source_resolver=cast(Any, FakeSourceResolver(_models(attempt))),
        image_loader=cast(Any, FakeLoader()),
        storage=MeasurementStorage(tmp_path),
    )
    persistence = cast(Any, service.persistence)
    captured: dict[str, Any] = {}

    def claim(*_args: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(attempt=attempt, replayed=False, reclaimed=False)

    persistence.results = SimpleNamespace(claim_measurement_attempt=claim)
    persistence.claim(object(), attempt.scan_id, _request(), object(), object())

    assert captured["lease_seconds"] == 177


def test_heavy_per_view_arrays_are_released_before_next_view(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    geometry = MemoryTrackingGeometry()
    loader = MemoryTrackingLoader()
    service = _service(
        tmp_path,
        persistence,
        geometry,
        loader,
        FakeSourceResolver(_models(attempt)),
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "succeeded"
    assert all(reference() is None for reference in loader.array_references)
    assert all(reference() is None for reference in geometry.array_references)


def test_process_runs_views_sequentially_revalidates_sources_and_finalizes(
    tmp_path: Path,
) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    geometry = FakeGeometry()
    loader = FakeLoader()
    resolver = FakeSourceResolver(_models(attempt))
    service = _service(tmp_path, persistence, geometry, loader, resolver)

    terminal, replayed = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert not replayed
    assert terminal.terminal == "succeeded"
    assert persistence.success is not None
    assert persistence.failure is None
    assert [
        loader.calls[view]
        for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)
    ] == [2, 2, 2]
    assert geometry.calls.count("reconcile") == 1
    assert persistence.success.previews.final_directory.is_dir()


def test_terminal_replay_skips_sources_geometry_and_storage(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt, replayed=True)
    geometry = FakeGeometry()
    resolver = FakeSourceResolver(_models(attempt))
    service = _service(tmp_path, persistence, geometry, FakeLoader(), resolver)

    terminal, replayed = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert replayed
    assert terminal is attempt
    assert resolver.called == 0
    assert not geometry.calls


def test_geometry_failure_is_persisted_without_previews(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    geometry = FakeGeometry(fail_stage="foreground")
    service = _service(
        tmp_path,
        persistence,
        geometry,
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
    )

    terminal, replayed = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert not replayed
    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "PRODUCT_NOT_DETECTED"
    assert not list(tmp_path.glob("scans/*/measurements/*/previews"))


def test_source_change_during_processing_fails_before_preview_storage(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    service = _service(
        tmp_path,
        persistence,
        FakeGeometry(),
        FakeLoader(change_on_revalidation=True),
        FakeSourceResolver(_models(attempt)),
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "SOURCE_IMAGE_CHANGED"


def test_reconciliation_failure_persists_evidence_without_previews(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    service = _service(
        tmp_path,
        persistence,
        FakeGeometry(fail_stage="reconcile"),
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "MEASUREMENT_DISAGREEMENT"
    assert persistence.failure.reconciliation is not None
    assert all(item["preview_available"] is False for item in persistence.failure.per_view)


def test_excessive_uncertainty_code_is_persisted_without_generic_rewrite(
    tmp_path: Path,
) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    geometry = FakeGeometry(fail_stage="reconcile")
    original_reconcile = geometry.reconcile

    def uncertainty_failure(_work: Any, _policy: Any) -> ReconciliationBundle:
        result = original_reconcile(_work, _policy)
        return ReconciliationBundle(
            succeeded=False,
            dimensions=result.dimensions,
            final_dimensions=None,
            overall_quality=None,
            overall_uncertainty_mm=None,
            warnings=("MEASUREMENT_UNCERTAINTY_EXCESSIVE",),
            failure_code="MEASUREMENT_UNCERTAINTY_EXCESSIVE",
        )

    geometry.reconcile = uncertainty_failure  # type: ignore[method-assign]
    service = _service(
        tmp_path,
        persistence,
        geometry,
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "MEASUREMENT_UNCERTAINTY_EXCESSIVE"


def test_stage_deadline_becomes_sanitized_persisted_failure(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    geometry = FakeGeometry()
    clock_state = [0.0]
    geometry.clock_state = clock_state
    deadlines = StageDeadlines(marker_seconds=1.0)
    service = _service(
        tmp_path,
        persistence,
        geometry,
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
        deadlines=deadlines,
        clock=lambda: clock_state[0],
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "PROCESSING_INTERRUPTED"
    assert persistence.failure.error.payload.field == "reference_detection"


def test_active_profile_change_compensates_finalized_previews_then_fails(
    tmp_path: Path,
) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    persistence.success_error = ApplicationError(
        status_code=409,
        code="ACTIVE_CALIBRATION_PROFILE_CHANGED",
        message="The active calibration profile changed before completion.",
        recoverable=True,
        suggested_action="Review the active profile and retry.",
    )
    service = _service(
        tmp_path,
        persistence,
        FakeGeometry(),
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
    )

    terminal, _ = service.process(cast(Any, object()), attempt.scan_id, _request())

    assert terminal.terminal == "failed"
    assert persistence.failure is not None
    assert persistence.failure.error.payload.code == "ACTIVE_CALIBRATION_PROFILE_CHANGED"
    assert persistence.success is not None
    assert not persistence.success.previews.final_directory.exists()


def test_stale_lease_compensates_previews_without_overwriting_attempt(tmp_path: Path) -> None:
    attempt = _attempt()
    persistence = FakePersistence(attempt)
    persistence.success_error = ApplicationError(
        status_code=409,
        code="PROCESSING_INTERRUPTED",
        message="The attempt is no longer owned by this request.",
        recoverable=True,
        suggested_action="Refresh measurement history.",
    )
    service = _service(
        tmp_path,
        persistence,
        FakeGeometry(),
        FakeLoader(),
        FakeSourceResolver(_models(attempt)),
    )

    with pytest.raises(ApplicationError) as caught:
        service.process(cast(Any, object()), attempt.scan_id, _request())

    assert caught.value.payload.code == "PROCESSING_INTERRUPTED"
    assert persistence.failure is None
    assert persistence.success is not None
    assert not persistence.success.previews.final_directory.exists()
