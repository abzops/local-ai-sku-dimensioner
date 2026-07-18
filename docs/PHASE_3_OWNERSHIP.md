# Phase 3 Frozen Ownership

Phase 3 uses non-overlapping implementation ownership. Implementation agents work in isolated
temporary Git worktrees when available. They may read shared contracts from the lead worktree but
must not edit files outside their ownership. The lead integrates all work and owns every shared
change.

## Sub-agent A — persistence and measurement APIs

Owns:

```text
backend/app/measurement_contracts.py
backend/app/models/measurement.py
backend/app/schemas/measurements.py
backend/app/api/measurements.py
backend/app/services/measurement_results.py
backend/migrations/versions/0004_phase3_measurements.py
backend/tests/unit/test_measurement_results.py
backend/tests/integration/test_phase3_migration.py
backend/tests/integration/test_measurements_api.py
backend/tests/integration/test_measurement_previews_api.py
backend/tests/integration/test_measurement_concurrency.py
```

It must not edit geometry, orchestration/storage, frontend, lead-owned, or existing Phase 0–2 files.

## Sub-agent B — deterministic geometry engine

Owns:

```text
backend/app/vision/full_plane.py
backend/app/vision/foreground.py
backend/app/vision/product_contours.py
backend/app/vision/oriented_geometry.py
backend/app/vision/measurement_quality.py
backend/app/vision/reconciliation.py
backend/app/vision/geometry_previews.py
backend/tests/unit/test_full_plane.py
backend/tests/unit/test_foreground_extraction.py
backend/tests/unit/test_product_contours.py
backend/tests/unit/test_oriented_geometry.py
backend/tests/unit/test_measurement_quality.py
backend/tests/unit/test_measurement_reconciliation.py
backend/tests/unit/test_geometry_previews.py
backend/tests/synthetic/test_product_geometry_synthetic.py
backend/tests/golden/test_product_geometry_golden.py
backend/tests/fixtures/phase3_synthetic_factory.py
backend/tests/fixtures/generate_phase3_golden.py
backend/tests/fixtures/phase3/manifest.json
backend/tests/fixtures/phase3/nominal_top.png
backend/tests/fixtures/phase3/nominal_front.png
backend/tests/fixtures/phase3/nominal_side.png
backend/tests/fixtures/phase3/perspective_top.png
backend/tests/fixtures/phase3/perspective_front.png
backend/tests/fixtures/phase3/perspective_side.png
backend/tests/fixtures/phase3/ambiguous_top.png
```

It must not edit database, schemas, routes, services outside its geometry boundary, frontend, or
existing Phase 2 marker contracts.

## Sub-agent C — stored-image and processing orchestration

Owns:

```text
backend/app/services/stored_image_loader.py
backend/app/services/measurement_application.py
backend/app/services/measurement_storage.py
backend/tests/unit/test_stored_image_loader.py
backend/tests/unit/test_measurement_application.py
backend/tests/unit/test_measurement_storage.py
backend/tests/integration/test_measurement_atomicity.py
```

It must not edit Phase 1 images, Phase 2 public contracts, persistence-owned files, geometry files,
frontend, or lead-owned files.

## Sub-agent D — measurement frontend

Owns:

```text
frontend/src/types/measurements.ts
frontend/src/api/measurements.ts
frontend/src/api/measurements.test.ts
frontend/src/test/measurementFixtures.ts
frontend/src/components/MeasurementConfirmationDialog.tsx
frontend/src/components/MeasurementConfirmationDialog.test.tsx
frontend/src/components/MeasurementAttemptList.tsx
frontend/src/components/MeasurementEvidence.tsx
frontend/src/components/MeasurementEvidence.test.tsx
frontend/src/components/MeasurementPreview.tsx
frontend/src/components/MeasurementPreview.test.tsx
frontend/src/pages/MeasurementResultPage.tsx
frontend/src/pages/MeasurementResultPage.test.tsx
```

It uses only `docs/PHASE_3_CONTRACTS.md` and must not edit backend or lead-owned frontend files.

## Lead agent

Owns:

```text
backend/app/config.py
backend/app/models/__init__.py
backend/app/api/router.py
backend/tests/conftest.py
backend/tests/integration/test_phase3_workflow.py
frontend/src/pages/ScanDetailPage.tsx
frontend/src/pages/ScanDetailPage.test.tsx
frontend/src/app/router.tsx
frontend/src/app/App.test.tsx
frontend/src/pages/HomePage.tsx
frontend/src/styles/global.css
.env.example
README.md
CURRENT_STATUS.md
CHANGELOG.md
docs/API.md
docs/DECISIONS.md
docs/PHASE_3_CONTRACTS.md
docs/PHASE_3_OWNERSHIP.md
docs/GEOMETRY_CAPTURE_GUIDE.md
THIRD_PARTY_LICENSES.md
scripts/run_tests.ps1
scripts/smoke_test.ps1
```

The lead freezes contracts, integrates every worktree, resolves cross-layer issues without changing
the approved design, adds shared wiring and workflow tests, validates the complete project, runs the
independent review, and fixes blocking and major findings only.

## Integration rules

- No two implementation agents may edit the same file.
- Agents return uncommitted worktree changes; they do not commit, push, or merge.
- Shared contracts may be changed only by the lead and only before implementation begins.
- Existing Phase 0–2 public contracts remain untouched.
- Final integration and validation are not delegated.
- Phase 4 functionality is prohibited.

