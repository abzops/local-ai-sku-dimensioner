# Changelog

All notable project changes will be documented in this file.

## [Unreleased]

### Added

- Phase 1 SQLite scan and image metadata schema with create, read, and paginated history APIs.
- Multipart top, front, side, and optional additional image uploads under `/api/scans/{id}/images`.
- Pillow-backed extension, MIME, byte-size, content decode, format, animation, pixel-count, and
  orientation-aware minimum-resolution validation.
- Operation-owned local staging, atomic same-volume finalization, transaction compensation, UUID
  storage names, duplicate-view prevention, and per-scan upload limits.
- New Scan, History, and Scan Detail pages with local previews, camera capture inputs, safe error
  rendering, and retry against the already-created scan.
- Phase 1 unit, integration, frontend, and production smoke coverage.
- Frozen cross-layer contracts and parallel-agent file-ownership record.
- Parser-level multipart byte/count bounds and sanitized malformed-multipart responses.

### Changed

- Alembic head advanced from `0001_phase0` to `0002_phase1_scans`; health still requires an exact
  match to the current single migration head.
- Production smoke validation now exercises scan creation, a validated three-view upload, read, and
  history in addition to health and compiled assets.
- Local validation now includes Python and frontend dependency consistency checks.
- Upload retries now reconcile the persisted scan after an uncertain response; unconfirmed scan
  creation blocks automatic resubmission and directs the user to History.

### Fixed

- Root-level `scans/` runtime data is ignored if `DATA_ROOT` is accidentally configured inside the
  repository.
- Frontend health fixtures now identify the Phase 1 Alembic head as `0002_phase1_scans`.
- Late database failures during scan create, read, and list operations now return the existing
  sanitized structured `DATABASE_UNAVAILABLE` response.

### Security

- Client filenames are used only to validate an allowed extension and are never stored or returned.
- Upload responses and failures omit filesystem paths, filenames, raw exceptions, and stack traces.
- Image bytes are bounded before decoding; decoded pixels are capped; animated images are rejected.
- Multipart file bytes and file counts are bounded while parsing, before temporary files can exceed
  configured limits.
- Filesystem deletion is restricted to the exact UUID operation directory owned by the request.

## [Phase 0]

### Added

- Phase 0 FastAPI application, typed settings, and structured health API.
- SQLite initialization and Alembic migration baseline.
- React, TypeScript, and Vite health-status application shell.
- Windows setup, development, production, validation, and smoke-test scripts.
- Backend and frontend unit and integration tests.
- Project instructions, current status, dependency records, and architecture decisions.
- Regression coverage for migration-head readiness, degraded database startup, SPA/API routing,
  frontend health failure states, production assets, and development shutdown.

### Fixed

- Health now rejects missing, stale, unknown, or invalid Alembic revisions instead of treating any
  non-empty revision as ready.
- Filesystem and database construction failures now start FastAPI in a sanitized degraded mode so
  `/api/health` can return a structured `503`.
- Development cleanup now targets the complete backend and frontend process trees and validates
  port release without terminating unrelated processes.
- Existing virtual environments are checked for Python 3.11 before dependency installation.
- Backend tests no longer inherit application configuration from the caller environment.
- Production SPA routes fall back to `index.html` without masking unknown `/api/*` requests or
  missing compiled assets.
- SQLite rollback journals and `sqlite`/`sqlite3` sidecars are excluded from Git.

### Security

- Default loopback-only binding.
- Runtime data stored outside the OneDrive repository by default.
- Local configuration, databases, uploads, exports, models, and generated artifacts excluded from
  Git.
