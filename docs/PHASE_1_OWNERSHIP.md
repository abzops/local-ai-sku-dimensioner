# Phase 1 Parallel File Ownership

No implementation sub-agent may edit a file outside its list. Shared contracts and final
integration remain lead-owned.

## Sub-agent A — Database and scan API

```text
backend/app/models/__init__.py
backend/app/models/scan.py
backend/app/schemas/scans.py
backend/app/services/scans.py
backend/app/api/scans.py
backend/migrations/versions/0002_phase1_scans.py
backend/tests/unit/test_scan_status.py
backend/tests/integration/test_scans_api.py
backend/tests/integration/test_phase1_migration.py
```

## Sub-agent B — Upload validation and storage

```text
backend/app/services/__init__.py
backend/app/services/image_validation.py
backend/app/services/scan_storage.py
backend/app/services/uploads.py
backend/tests/unit/test_image_validation.py
backend/tests/unit/test_scan_storage.py
backend/tests/unit/test_upload_service.py
```

## Sub-agent C — Frontend

```text
frontend/src/api/scans.ts
frontend/src/api/scans.test.ts
frontend/src/components/AppNavigation.tsx
frontend/src/components/ImageCaptureField.tsx
frontend/src/components/ImageCaptureField.test.tsx
frontend/src/components/ScanStatusBadge.tsx
frontend/src/components/UploadErrorSummary.tsx
frontend/src/pages/NewScanPage.tsx
frontend/src/pages/NewScanPage.test.tsx
frontend/src/pages/HistoryPage.tsx
frontend/src/pages/HistoryPage.test.tsx
frontend/src/pages/ScanDetailPage.tsx
frontend/src/pages/ScanDetailPage.test.tsx
frontend/src/app/router.tsx
frontend/src/app/App.test.tsx
frontend/src/pages/HomePage.tsx
frontend/src/styles/global.css
```

## Lead agent — Shared contracts and integration

```text
.env.example
.gitignore
pyproject.toml
requirements.lock
requirements-dev.lock
THIRD_PARTY_LICENSES.md
backend/app/contracts.py
backend/app/upload_contracts.py
backend/app/errors.py
backend/app/schemas/errors.py
backend/app/config.py
backend/app/dependencies.py
backend/app/main.py
backend/app/multipart.py
backend/app/api/router.py
backend/app/api/uploads.py
backend/app/services/upload_application.py
backend/migrations/env.py
backend/tests/conftest.py
backend/tests/integration/test_health_api.py
backend/tests/integration/test_uploads_api.py
backend/tests/unit/test_config.py
backend/tests/unit/test_database.py
frontend/src/types/scans.ts
scripts/setup_windows.ps1
scripts/smoke_test.ps1
scripts/run_tests.ps1
README.md
CURRENT_STATUS.md
CHANGELOG.md
docs/API.md
docs/DECISIONS.md
docs/PHASE_1_CONTRACTS.md
docs/PHASE_1_OWNERSHIP.md
```
