# Changelog

All notable project changes will be documented in this file.

## [Unreleased]

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
