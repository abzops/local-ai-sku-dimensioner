# Changelog

All notable project changes will be documented in this file.

## [Unreleased]

### Added

- Phase 3 immutable measurement attempts, source snapshots, preview metadata, request idempotency,
  processing leases, explicit reprocessing relationships, and Alembic revision
  `0004_phase3_measurements`.
- A disabled-by-default configured orthogonal-rig contract with safe options API, qualification
  gate, physical size range, requirements, and uncertainty snapshot.
- Secure original-image revalidation, containment and reparse-point guards, original/oriented
  hashing, sequential view processing, private preview staging, atomic finalization, and
  operation-owned compensation.
- Deterministic full-plane rectification, multi-signal foreground evidence, marker exclusion,
  explicit product-candidate scoring, oriented geometry, fixed per-view axis mapping, conservative
  uncertainty, and cross-view reconciliation.
- Measurement options, create/reprocess, history, detail, and private annotated-preview APIs.
- Scan-detail measurement confirmation/history and direct immutable measurement-evidence pages.
- Frozen Phase 3 contracts, non-overlapping worktree ownership, capture guide, and unit, synthetic,
  golden, integration, frontend, smoke, atomicity, concurrency, and security tests.
- Phase 2 immutable calibration profiles with transaction-safe single-profile activation.
- Deterministic exact-size SVG generation for three approved ArUco dictionaries and IDs 0–49.
- OpenCV marker detection, canonical corners, marker-plane homographies and inverse mapping,
  rectification, bounded previews, and marker-edge localization evidence.
- Calibration options, profile, SVG, and in-memory test APIs under `/api/calibration`.
- Mobile-friendly Calibration page with profile management, marker download, camera capture, retry,
  and complete marker-only evidence.
- Focused unit, synthetic, minimal golden, integration, frontend, and production-smoke coverage.
- Frozen Phase 2 contracts and parallel-agent ownership record.
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

- Capture setup versions now use the frozen 50-character maximum consistently across environment
  validation, persistence snapshots, public response schemas, and frontend response validation.
- Measurement outcome recovery now keeps the canonical session request after network failures,
  malformed successes, and late `500/503` responses; the scan page offers exact-request retry,
  matching-history reconciliation, and explicit abandon actions.
- Alembic head advanced from `0003_phase2_calibration_profiles` to
  `0004_phase3_measurements`; the Phase 0 health contract still requires an exact head match.
- Production and local validation now cover the Phase 3 options boundary, direct measurement result
  navigation, persistence, geometry, reconciliation, private previews, and Phase 0-2 regressions.
- Alembic head advanced from `0002_phase1_scans` to `0003_phase2_calibration_profiles`; health still
  requires an exact match to the current single head.
- Python locks now include resolved NumPy 2.4.6 and `opencv-contrib-python-headless` 4.13.0.92.
- Windows setup verifies NumPy/OpenCV imports, ArUco detector and generator support, and all approved
  dictionaries after locked installation.
- Production smoke now covers calibration profile creation/activation, exact-size SVG, marker
  analysis evidence, ephemeral test behavior, `/calibration` SPA fallback, and API `404` isolation.
- Alembic head advanced from `0001_phase0` to `0002_phase1_scans`; health still requires an exact
  match to the current single migration head.
- Production smoke validation now exercises scan creation, a validated three-view upload, read, and
  history in addition to health and compiled assets.
- Local validation now includes Python and frontend dependency consistency checks.
- Upload retries now reconcile the persisted scan after an uncertain response; unconfirmed scan
  creation blocks automatic resubmission and directs the user to History.

### Fixed

- Measurement confirmation now requires fresh capture-contract acknowledgement after close,
  successful or failed submission, and scan, profile, capture-setup, or reprocess-source changes;
  stale dialog errors are reset without clearing a separately persisted uncertain request.
- A successful measurement POST response must carry the submitted request UUID before the frontend
  clears recovery state, preventing a mismatched response from discarding the canonical request.
- Phase 3 foreground consensus now counts only independently derived signals; the adaptive mask can
  refine a candidate but cannot satisfy the two-signal gate by duplicating its inputs.
- Shadow evidence now records the fraction removed before filtering, and selected-product glare at
  or above the unsupported reflection boundary fails with a structured error even when variants
  happen to remain stable.
- A conservative uncertainty that reaches a contributing raw dimension or reconciled value now
  fails immutably as `MEASUREMENT_UNCERTAINTY_EXCESSIVE` instead of returning a dimension or being
  rewritten as generic disagreement.
- The configured processing lease is passed into attempt claiming, configuration rejects leases
  that do not exceed the total deadline, and heavy per-view arrays are released before the next
  source is decoded.

- Rectified previews now preserve the reported rectified geometry; an incompressible PNG that
  exceeds the response ceiling fails through a sanitized structured calibration error instead of
  being silently resized or causing response validation to return a generic `500`.
- Calibration evidence and retry state are now bound to the selected profile, cleared on profile
  changes, and labelled with the producing profile name and ID.
- Root-level `scans/` runtime data is ignored if `DATA_ROOT` is accidentally configured inside the
  repository.
- Frontend health fixtures now identify the Phase 1 Alembic head as `0002_phase1_scans`.
- Late database failures during scan create, read, and list operations now return the existing
  sanitized structured `DATABASE_UNAVAILABLE` response.

### Security

- Measurement is rejected unless the server-configured rig is explicitly qualified and the client
  echoes the configured ID; arbitrary client capture-setup IDs are not accepted.
- Original scan images are resolved beneath the configured data root, reparse points and content
  changes are rejected, and successful or failed processing never mutates source image bytes.
- Private previews are attempt-owned, hash-checked, PNG-bounded, served with `no-store`, and never
  disclose storage keys or paths.
- Calibration tests accept exactly one bounded image, reuse the Phase 1 content-validation chain,
  and keep source bytes and generated previews in memory only.
- OpenCV failures, filenames, paths, SQL, and internal numeric diagnostics are excluded from public
  structured errors.
- Marker previews have explicit dimension and encoded-byte ceilings; generated SVG contains no
  script or external resource.
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
