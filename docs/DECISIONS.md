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

## D-012 — Keep the Phase 1 scan lifecycle derived and minimal

**Status:** Accepted

The only Phase 1 statuses are `draft`, `images_uploaded`, and `ready_for_processing`. Status is
derived from persisted image views: no images is draft, any incomplete set is images uploaded, and
top plus front plus side is ready for later processing. Processing, review, approved, and rejected
states are not introduced early.

## D-013 — Validate decoded content before storage

**Status:** Accepted

An upload must pass extension and MIME checks, a bounded byte read, full Pillow decode, decoded
format matching, animated-image rejection, a decoded-pixel ceiling, EXIF-aware orientation, and
minimum long/short edges. Every file in a request is validated before any request file is written.
This validation establishes safe image input only; it performs no measurement or correction.

## D-014 — Coordinate SQLite and filesystem changes with owned compensation

**Status:** Accepted

Validated batches are written to a UUID operation directory under the scan's same-volume staging
area, then moved atomically to its final operation directory immediately before metadata insertion.
Metadata rows and scan status are committed in one database transaction. Normal failures remove
only that request's exact staged or finalized operation directory. Existing files are never deleted
unless the current transaction owns them. A true atomic commit across SQLite and NTFS is not
available, so abrupt process or power loss can still leave an unreferenced final directory.

## D-015 — Treat client filenames and storage paths as private input

**Status:** Accepted

The client filename is consulted only for its final extension. Image and operation names are
server-generated UUIDs, storage keys are relative to `DATA_ROOT`, and neither names nor keys are
present in public Pydantic schemas. Errors use stable codes and safe field/view context without
paths, filenames, raw exceptions, or stack traces.

## D-016 — Keep Phase 1 images local and private

**Status:** Accepted

Original validated images are stored beneath `%LOCALAPPDATA%\LocalAISkuDimensioner\scans` by
default. Phase 1 does not provide an image download or thumbnail endpoint. The browser displays
object-URL previews only for files selected in the current form; persisted details display safe
metadata.

## D-017 — Retry uploads against the created scan

**Status:** Accepted

The New Scan page creates the scan once and retains its server ID if upload fails. Before presenting
or completing a retry, it reads the scan to reconcile a success response that may have been lost. If
scan creation itself has an unknown outcome and no server ID was received, automatic resubmission is
blocked and the user is directed to History; this avoids creating a second draft on an uncertain
create result.

## D-018 — Bound multipart files during parsing

**Status:** Accepted

The upload route owns multipart parsing instead of allowing framework parameter injection to spool
the complete request first. File count and each file's bytes are bounded while the parser receives
the body, malformed parser failures use the public structured error shape, and parsed temporary
files are always closed after orchestration. Pillow validation remains the second content-safety
boundary after parser-level resource limits.
