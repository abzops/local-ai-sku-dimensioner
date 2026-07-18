# Current Status

## Active phase

Phase 3 - Geometry-only product measurement

## State

Implemented, independently reviewed, corrected, and fully validated on branch
`codex/phase-3-geometry` on 2026-07-19. Phase 3 remains experimental because physical rig
qualification with known-size rigid reference blocks has not been completed. Nothing has been
committed or pushed.

## Implemented scope

- All validated Phase 0 runtime/health/SPA behavior, Phase 1 scan/upload behavior, and Phase 2
  calibration behavior remain present.
- Alembic revision `0004_phase3_measurements` adds immutable measurement attempts, source snapshots,
  and private preview metadata without changing `ScanStatus`.
- One server-configured `orthogonal_rig` contract is unqualified and disabled by default. Clients
  must echo its exact safe ID; they cannot create or select capture setups.
- Safe `GET /api/measurements/options` exposes only qualification state, supported product domain,
  required views, fixed view-axis mapping, size range, disagreement policy, requirements, and the
  non-certified-metrology warning.
- Measurement create/reprocess, paginated history, immutable detail, and private annotated-preview
  APIs are available under `/api`.
- `(scan_id, request_id)` idempotency, canonical request signatures, expiring processing leases,
  stale-worker compare-and-set rejection, linked explicit reprocessing, and terminal immutability
  are enforced.
- Original top/front/side images are resolved beneath `DATA_ROOT`, checked for reparse points and
  containment, revalidated against stored metadata, decoded with EXIF orientation in memory, and
  hashed before sequential processing. Original files are never changed.
- Each view independently performs configured ArUco detection, full valid-plane rectification,
  marker exclusion, background sampling, independent multi-signal foreground consensus,
  morphology, connected components, explicit candidate scoring, oriented contour geometry,
  shadow/reflection rejection, quality evidence, and conservative uncertainty. Heavy arrays are
  released before the next view is decoded.
- Fixed mapping is top length/width, front width/height, and side length/height. Final length uses
  top/side, width uses top/front, and height uses front/side.
- Reconciliation requires both absolute and relative acceptable limits, permits only the frozen
  warning-range stronger-source rule, and fails the attempt for invalid disagreement, excessive
  uncertainty, or any invalid required view.
- Successful attempts retain all raw view evidence, final dimensions, disagreement, reconciliation
  rule, quality, uncertainty, warnings, and three bounded private annotated PNGs.
- Preview staging/finalization is same-volume and operation-owned; database failure triggers safe
  compensation, and reads recheck ownership, containment, PNG metadata, size, dimensions, and hash.
- The React UI provides qualification-aware measurement confirmation, immutable attempt history,
  explicit reprocessing, synchronous waiting/failure states, direct evidence routes, uncertainty,
  warnings, reconciliation evidence, per-view details, and local previews without fake progress.
- Capture setup versions are consistently bounded to 50 characters across configuration,
  persistence snapshots, public schemas, API response validation, and frontend validation.
- Measurement POST network failures, malformed successes, and late `500/503` responses preserve
  the canonical session request. The scan page can retry the identical UUID, reconcile it against
  refreshed attempt history, or abandon it explicitly without silently creating a new request.
- Measurement confirmation always resets acknowledgement and stale errors after close, completion,
  failure/reopen, or any scan, profile, capture-setup, or reprocess-source change. Closing the dialog
  does not discard a separately persisted uncertain request.
- Frozen contracts and ownership are recorded in `docs/PHASE_3_CONTRACTS.md` and
  `docs/PHASE_3_OWNERSHIP.md`; physical requirements are in `docs/GEOMETRY_CAPTURE_GUIDE.md`.

## Explicitly not implemented

- AI segmentation, SAM, YOLO, neural inference, model weights, or automatic shape classification
- Weight, volume, density, or certified-metrology calculations
- Background workers, queues, processing jobs, WebSocket/SSE progress, or fake stage percentages
- Review, approval, rejection, manual measurement editing, exports, or LAN mode
- Phase 4 or later functionality

## Validation status

- Integrated backend suite: 257 tests passed with one upstream Starlette/httpx deprecation warning.
- Ruff: passed with no findings.
- mypy strict checks: passed across 59 application source files.
- Python dependency consistency: passed with no broken requirements.
- Frontend ESLint and TypeScript checks: passed.
- Frontend Vitest: 14 files and 72 tests passed.
- Frontend production build: passed with 111 transformed modules.
- Phase 3 production smoke: passed for migrations, Phase 0-2 regressions, a qualified synthetic
  three-view measurement, replay, explicit reprocessing, immutable earlier evidence, all three
  private previews, source-file immutability, direct result routing, and JSON API 404 isolation.
- `setup_windows.ps1`: passed with Python 3.11.9, Node.js 22.22.2, NumPy 2.4.6, OpenCV 4.13.0,
  ArUco support, and Alembic head `0004_phase3_measurements`.
- Complete `run_tests.ps1`: passed, including backend, frontend, dependency, build, and production
  smoke validation.
- Development shutdown validation: passed; backend/frontend process trees ended and ports 8000 and
  5173 were released.
- Production/manual validation: direct `/scans`, `/scans/new`, `/calibration`, and measurement
  routes rendered; `/api/unknown` returned JSON `404`; the browser console was clean; the 390x844
  viewport had no horizontal overflow; and no listeners remained afterward.
- Final recovery validation used a local temporary late-response proxy outside the repository. Two
  byte-identical POST bodies reused request UUID `04e38eaf-b7bc-4d87-bba8-85709e26244b`; backend
  responses were initial `201` then idempotent `200`, history contained exactly one succeeded
  attempt, refresh removed the pending-recovery panel, and explicit reprocessing reopened without
  acknowledgement. Temporary validation processes were stopped and runtime data was moved to the
  Recycle Bin afterward.
- Independent read-only review: no blockers, five major findings corrected with regressions, and
  the three final low-risk findings corrected with focused regressions.

## Physical qualification status

Incomplete. Synthetic and golden tests validate deterministic software behavior only. No real-world
accuracy result is claimed. Before operational use, the configured rig must be qualified using
repeated captures of known-size rigid reference blocks and independent ground-truth measurements as
described in `docs/GEOMETRY_CAPTURE_GUIDE.md`.

## Known limitations

- A homography validates a numerical reference-plane mapping; software cannot independently prove
  that the product face, marker, and rig datum are physically coplanar.
- Phase 3 does not estimate camera intrinsics or correct lens distortion.
- Initial support is limited to opaque, rigid, stable, approximately cuboidal products with mild or
  no reflections, complete visibility, known plane registration, and axes within 75-400 mm by
  default.
- Quality values are engineering evidence, not probabilities. Uncertainty is a conservative
  additive engineering bound, not a statistical confidence interval.
- SQLite and NTFS cannot form one power-loss-atomic transaction. Operation-owned compensation
  handles normal failures, but abrupt power loss can leave an unreferenced preview directory.
- Explicit `fsync`, cryptographic source re-hashing after a successful immutable attempt, and a
  backend coverage threshold remain future hardening work.
- The FastAPI `TestClient` compatibility layer emits one upstream deprecation warning.
- Setup has been validated on the current Windows 11 machine, not a second clean workstation.

## Next gate

Wait for user approval before committing or pushing. Do not begin Phase 4.
