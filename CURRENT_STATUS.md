# Current Status

## Active phase

Phase 1 — Scan data and image upload workflow

## State

Implemented, independently reviewed, corrected, and validated on 2026-07-18. No commit or push has been created for the
Phase 1 branch.

## Implemented scope

- SQLite `scans` and `scan_images` records through Alembic revision `0002_phase1_scans`
- Draft scan creation, read, reverse-chronological history, and bounded pagination APIs
- Top, front, side, and repeatable optional additional image uploads
- Server-generated UUID storage keys beneath `DATA_ROOT\scans`
- Request limits plus extension, MIME, content decode, format, animation, decoded-pixel, file-size,
  and orientation-aware minimum-resolution validation
- Parser-level multipart byte/count bounds and structured malformed-parser failures
- All-or-nothing request validation, operation-owned staging/finalization, database transactions,
  and normal-failure compensation
- Duplicate required-view prevention and per-scan additional-image limits
- Safe structured errors without client filenames, local paths, raw exceptions, or stack traces
- Sanitized database-unavailable responses for readiness and late create, read, or list failures
- New Scan, History, and Scan Detail frontend pages
- Browser-local previews, mobile rear-camera inputs, and retry without duplicate scan creation
- Lost upload-response reconciliation and safe blocking of an unconfirmed create retry
- Production SPA serving, Phase 1 API/asset smoke coverage, and Windows process-tree shutdown support

## Explicitly not implemented

- OpenCV, ArUco, ChArUco, calibration, perspective correction, segmentation, or measurement
- AI dependencies, model downloads, dimension calculation, or weight integration
- Background processing, WebSocket or SSE progress, review, approval, or rejection
- Stored-image download or thumbnail API
- Exports, LAN mode, paid APIs, or cloud services

## Validation results

- Windows setup: passed with PowerShell 5.1, Python 3.11.9, Node.js 22.22.2, and npm 10.9.7.
- Backend: 75 tests passed.
- Ruff: passed with no findings.
- mypy strict checks: passed across 29 application source files.
- Frontend ESLint: passed with zero warnings.
- Frontend TypeScript check: passed.
- Frontend Vitest: 7 files and 27 tests passed.
- Python and frontend dependency consistency checks: passed.
- Frontend production build: passed with 102 transformed modules.
- Production smoke: passed for health, JS/CSS, create, three-view upload, read, and history.
- Development shutdown validation: backend/frontend process trees stopped and ports 8000/5173 were
  released.
- Rendered production browser validation: create/upload/detail/history passed, `/api/unknown`
  remained JSON, browser console had no errors, and 390 x 844 had no horizontal overflow.

## Known limitations

- SQLite and the filesystem cannot share a true cross-resource transaction. Normal failures are
  compensated, but abrupt power or process loss between file finalization and database commit can
  leave an unreferenced operation directory for later manual cleanup.
- File buffers are flushed but not explicitly forced to durable storage; abrupt power loss can still
  leave committed metadata whose file was not fully persisted.
- Equal byte length is rechecked between validation and storage, but the service boundary does not
  currently bind those bytes with a digest.
- The smoke test inherits custom upload limits, and `run_tests.ps1` does not include the separate
  development shutdown validator.
- Persisted images have no Phase 1 serving endpoint; scan detail intentionally exposes metadata only.
- FastAPI's current `TestClient` compatibility layer emits one upstream deprecation warning about
  its `httpx` fallback. Tests pass and application runtime is unaffected.
- Setup has been validated on the current Windows 11 machine, not yet on a second clean workstation.
- Backend coverage tooling is configured but no coverage threshold is enforced yet.

## Next gate

Do not commit or push Phase 1 until the user approves the completed implementation and validation.
Do not begin Phase 2 without separate explicit approval.
