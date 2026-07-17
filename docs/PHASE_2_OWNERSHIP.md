# Phase 2 Parallel Ownership

The lead froze these assignments before implementation. Agents work in isolated Git worktrees and
must not edit files outside their list. Shared contracts are lead-owned. Any newly discovered shared
change returns to the lead rather than creating overlapping edits.

## Lead agent

- `docs/PHASE_2_CONTRACTS.md`
- `docs/PHASE_2_OWNERSHIP.md`
- `backend/app/calibration_contracts.py`
- `backend/app/config.py`
- `backend/app/multipart.py`
- `backend/app/errors.py`
- `backend/app/schemas/errors.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/__init__.py`
- `backend/app/api/router.py`
- `backend/app/api/calibration_test.py`
- `backend/app/services/calibration_application.py`
- `backend/migrations/env.py`
- `backend/tests/conftest.py`
- `backend/tests/integration/test_calibration_test_api.py`
- `backend/tests/integration/test_phase0_phase1_regressions.py`
- `pyproject.toml`
- `requirements.lock`
- `requirements-dev.lock`
- `.env.example`
- `scripts/setup_windows.ps1`
- `scripts/smoke_test.ps1`
- `scripts/run_tests.ps1`
- `README.md`
- `CURRENT_STATUS.md`
- `CHANGELOG.md`
- `THIRD_PARTY_LICENSES.md`
- `docs/API.md`
- `docs/DECISIONS.md`

## Sub-agent A — calibration profile persistence and API

- `backend/app/models/calibration.py`
- `backend/app/schemas/calibration.py`
- `backend/app/services/calibration_profiles.py`
- `backend/app/api/calibration_profiles.py`
- `backend/migrations/versions/0003_phase2_calibration_profiles.py`
- `backend/tests/unit/test_calibration_profiles.py`
- `backend/tests/integration/test_phase2_migration.py`
- `backend/tests/integration/test_calibration_profiles_api.py`

Agent A implements migration, immutable profiles, transaction-safe activation, options, profile
routes, and the marker SVG route against the frozen generator interface. It does not edit OpenCV,
multipart, shared/router, scan/upload, frontend, dependency, or documentation files.

## Sub-agent B — deterministic marker vision engine

- `backend/app/vision/__init__.py`
- `backend/app/vision/aruco_dictionaries.py`
- `backend/app/vision/marker_generation.py`
- `backend/app/vision/marker_detection.py`
- `backend/app/vision/perspective.py`
- `backend/app/vision/marker_quality.py`
- `backend/app/vision/previews.py`
- `backend/app/vision/marker_engine.py`
- `backend/tests/unit/test_aruco_dictionaries.py`
- `backend/tests/unit/test_marker_generation.py`
- `backend/tests/unit/test_marker_detection.py`
- `backend/tests/unit/test_perspective.py`
- `backend/tests/unit/test_marker_quality.py`
- `backend/tests/unit/test_marker_previews.py`
- `backend/tests/synthetic/test_marker_engine_synthetic.py`
- `backend/tests/golden/test_marker_engine_golden.py`
- `backend/tests/fixtures/phase2_golden_marker.json`

Agent B implements deterministic marker generation/detection/geometry/evidence/previews and focused
unit, synthetic, and minimal deterministic golden tests. It does not edit database, API, multipart,
frontend, dependency, or documentation files. No generated binary fixture is committed.

## Sub-agent C — calibration frontend

- `frontend/src/types/calibration.ts`
- `frontend/src/api/calibration.ts`
- `frontend/src/api/calibration.test.ts`
- `frontend/src/pages/CalibrationPage.tsx`
- `frontend/src/pages/CalibrationPage.test.tsx`
- `frontend/src/components/CalibrationEvidence.tsx`
- `frontend/src/app/router.tsx`
- `frontend/src/components/AppNavigation.tsx`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/app/App.test.tsx`
- `frontend/src/styles/global.css`

Agent C implements only the frozen calibration UI/client/types and its tests. It does not edit
backend, dependency, script, or documentation files and does not add product measurement controls.

## Integration rule

The lead imports each worktree diff only after checking `git diff --name-only` against the assignment.
The lead owns all conflict resolution, cross-subsystem tests, final validation, documentation, and
post-integration fixes. The independent final reviewer is read-only.
