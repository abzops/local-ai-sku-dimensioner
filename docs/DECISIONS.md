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

## D-019 — Keep calibration profiles immutable and activation explicit

**Status:** Accepted

Phase 2 stores marker configuration and numeric acceptance thresholds in immutable profiles. Only
activation can change after creation. Activation obtains a SQLite writer reservation, deactivates the
current row, flushes, activates the selected row, and commits once. A partial unique index on active
rows is the final invariant, so rollback or concurrent requests cannot leave multiple active profiles.

## D-020 — Restrict ArUco support and generate exact-size SVG locally

**Status:** Accepted

Phase 2 supports only `DICT_4X4_50`, `DICT_5X5_50`, and `DICT_6X6_50`, IDs 0 through 49, with a
one-bit marker border. The server generates deterministic script-free SVG whose black-square width
and height use the profile millimetres. Operators must print at actual size and physically verify the
black square; printer settings are outside software control.

## D-021 — Keep marker-plane geometry separate from product geometry

**Status:** Accepted

OpenCV returns canonical printed-marker corners, a pixel-to-marker-millimetre homography, its inverse,
and a marker-only rectification. These values establish reference-plane evidence only. Phase 2 does
not locate a product or apply the marker scale to length, breadth, height, volume, or any contour.

## D-022 — Name border residual as localization quality

**Status:** Accepted

The independent marker-border metric samples local image gradients around all four fitted edges and
reports RMS residual, maximum residual, total samples, and per-edge RMS. It is named
`marker_edge_localization_residual`; it is not represented as certified camera reprojection error.
Insufficient evidence or a maximum residual above the immutable profile threshold fails the test.

## D-023 — Keep calibration tests bounded and ephemeral

**Status:** Accepted

The calibration test accepts exactly one bounded multipart image, reuses the full Phase 1 content
validation chain, applies EXIF orientation, and analyzes it in memory. Test images and generated PNG
previews are not written to SQLite or the filesystem. Preview dimensions and encoded sizes are
bounded, and raw OpenCV errors and local paths remain behind the structured error boundary.
Rectified previews must retain the reported rectified dimensions. If lossless encoding cannot fit
the byte ceiling, the test fails safely rather than resizing the preview independently of geometry.

## D-024 — Resolve and capability-check headless OpenCV

**Status:** Accepted

Python dependencies remain declared by range in `pyproject.toml` and resolved through generated hash
locks. Phase 2 resolved NumPy 2.4.6 and `opencv-contrib-python-headless` 4.13.0.92 for Python 3.11.
Windows setup imports both and explicitly verifies `cv2.aruco`, `ArucoDetector`, marker generation,
and all three approved dictionaries after installation.

## D-025 — Bind calibration evidence to its immutable profile

**Status:** Accepted

The Calibration page displays the producing profile name and ID with every successful evidence set.
Changing the selected profile clears prior evidence, errors, and retry state, and stale asynchronous
results are not rendered for a different profile. Retrying the same image is available only while
the profile that originated the attempt remains selected.

## D-026 — Gate measurement on one configured qualified rig

**Status:** Accepted

Phase 3 has no capture-setup CRUD and does not accept a client-selected rig. The server owns one
configured `orthogonal_rig`, defaults it to `unconfigured` and unqualified, requires the request to
echo its exact safe ID, and snapshots the safe configuration into every attempt. Operator
acknowledgement is additional evidence and cannot replace physical qualification. A floor marker
never calibrates vertical height; each view requires a valid view-specific measurement plane.

## D-027 — Keep measurement attempts immutable and idempotent

**Status:** Accepted

Each scan/request UUID pair identifies one canonical immutable attempt. Exact replay returns that
attempt; changed fields conflict. Processing leases allow safe recovery after a bounded expiry, and
the lease token is compared when finalizing so a stale worker cannot write. Explicit reprocessing
creates a linked new attempt rather than changing prior values, evidence, failures, or previews.

## D-028 — Revalidate source images without mutating them

**Status:** Accepted

Only the persisted top, front, and side image records are used. Processing resolves storage beneath
the configured data root, rejects reparse points and containment violations, rechecks bytes and
metadata, applies EXIF orientation in memory, hashes original bytes and oriented pixels, and works
sequentially. It never renames, rewrites, normalizes, or deletes a Phase 1 source image and ignores
optional additional images.

## D-029 — Separate deterministic view geometry from reconciliation

**Status:** Accepted

Each view independently performs marker-plane rectification, deterministic multi-signal foreground
extraction, explicit candidate scoring, and oriented geometry. Top supplies length/width, front
supplies width/height, and side supplies length/height. Reconciliation retains both raw inputs and
uses both absolute and relative limits; invalid disagreement fails the whole attempt and no result
is silently averaged outside the acceptable range.

## D-030 — Describe quality and uncertainty as engineering evidence

**Status:** Accepted

Quality combines inspectable marker, homography, background, stability, uniqueness, and visibility
signals; it is not a probability. Uncertainty is a conservative additive engineering bound derived
from marker size/localization, raster resolution, foreground stability, and qualified rig terms; it
is not a statistical confidence interval and does not prove coplanarity or certified accuracy.

## D-031 — Coordinate preview persistence with result finalization

**Status:** Accepted

Three bounded annotated PNGs are staged beneath an operation-owned, same-volume directory and
atomically renamed into a new attempt-owned directory. Database finalization stores their hashes
and metadata with the terminal result. A normal failure compensates only files owned by that
operation. Reads verify attempt ownership, containment, type, size, dimensions, and hash and use
`Cache-Control: no-store`; storage keys and paths remain private. SQLite and NTFS still cannot form
one power-loss-atomic transaction.

## D-032 — Keep Phase 3 experimental pending physical qualification

**Status:** Accepted

Synthetic and golden fixtures prove deterministic software behavior, not physical accuracy. Until
the configured rig is qualified with repeated captures of traceable known-size rigid blocks, Phase
3 remains experimental and makes no real-world accuracy or certified-metrology claim. The capture
guide records the required study rather than fabricating measurements.

## D-033 — Fail closed at Phase 3 evidence and resource boundaries

**Status:** Accepted

The adaptive foreground mask is dependent evidence and cannot count toward the required two
independent signals. Shadow evidence is recorded before filtering, while selected-product clipped
neutral reflection at or above 5% is unsupported even if geometry variants appear stable. A
conservative uncertainty bound that reaches its positive dimension fails as
`MEASUREMENT_UNCERTAINTY_EXCESSIVE`. The configured processing lease must exceed the synchronous
deadline and is applied to the database claim. Heavy decoded and geometry arrays are retained for
only one view at a time; reconciliation receives array-free dimension evidence.
