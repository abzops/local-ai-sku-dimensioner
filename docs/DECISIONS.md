# Architecture Decisions

## D-001 — Deterministic geometry owns measurements

**Status:** Accepted

Physical measurements will come from calibrated, testable OpenCV geometry. AI may later provide
segmentation or broad classification but cannot invent or override dimensions.

## D-002 — Keep Phase 0 infrastructure-only

**Status:** Accepted

Phase 0 contains the runtime, health contract, database lifecycle, UI shell, scripts, and validation
harness only. Scan, upload, calibration, vision, processing, review, and export behavior belongs to
later approved phases.

## D-003 — Store runtime data outside the repository

**Status:** Accepted

The repository resides inside OneDrive. Runtime data therefore defaults to
`%LOCALAPPDATA%\LocalAISkuDimensioner` to avoid cloud synchronization of user images and locking or
copy conflicts on a live SQLite database. `DATA_ROOT` remains configurable.

## D-004 — Establish Alembic before domain tables

**Status:** Accepted

Phase 0 creates an empty Alembic baseline. Phase 1 can add scan tables through an explicit migration
without retrofitting schema history after data exists.

## D-005 — Use same-origin production serving

**Status:** Accepted

Vite proxies API calls during development. In production, FastAPI serves both `/api/*` and the
compiled React application. This avoids permissive CORS configuration and provides one local start
command.

## D-006 — Keep package management authoritative and scoped

**Status:** Accepted

`pyproject.toml` is authoritative for Python dependencies; generated lock files provide reproducible
installation. Frontend dependencies exist only in `frontend/package.json` and
`frontend/package-lock.json`; no root npm workspace is used.

## D-007 — Validate locally with PowerShell in Phase 0

**Status:** Accepted

Phase 0 uses `scripts/run_tests.ps1` and `scripts/smoke_test.ps1`. No hosted CI workflow is added.

## D-008 — Keep network access loopback-only

**Status:** Accepted

Phase 0 accepts only `127.0.0.1` or `localhost` as the configured host. LAN mode is deferred until its
security controls are implemented in Phase 8.

## D-009 — Treat migration head as database readiness

**Status:** Accepted

Database readiness requires both a working SQLite connection and an exact match with the single
Alembic head shipped by the application. Missing, stale, unknown, or invalid revisions return the
same sanitized `503`. Filesystem or engine construction failures are captured as sanitized
application state so FastAPI can start in degraded mode and expose the health response.

## D-010 — Preserve the API boundary during SPA fallback

**Status:** Accepted

Production serves `index.html` for route-like, non-file frontend paths so direct navigation works.
Unknown `/api/*` paths are handled before the static mount and retain FastAPI's JSON `404` contract;
missing asset paths continue to return `404` rather than the SPA shell.

## D-011 — Terminate only development-owned process trees

**Status:** Accepted

Development startup records the backend and frontend wrapper processes and discovers their
descendants. Shutdown uses Windows' targeted process-tree termination for those roots, validates
captured process identity before fallback termination, and never searches for or kills unrelated
Python or Node processes by name.
