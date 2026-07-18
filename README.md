# Local AI SKU Dimensioner

A Windows-first, fully local web application for building image-complete SKU scan records,
verifying printed ArUco calibration markers, and producing experimental deterministic external
dimensions from a physically qualified orthogonal rig. Local AI may later
assist segmentation and broad shape classification, but it will not invent authoritative
measurements.

## Current scope

Phase 3 provides:

- All validated Phase 0, Phase 1, and Phase 2 behavior
- An explicit local capture-rig contract that is unqualified and disabled by default
- Immutable, idempotent measurement attempts with processing leases and safe reprocessing links
- Secure revalidation of the original top, front, and side images without changing their bytes
- View-specific marker-plane rectification, multi-signal foreground evidence, explicit candidate
  scoring, oriented geometry, and fixed top/front/side axis mapping
- Cross-view reconciliation with absolute and relative disagreement gates
- Conservative engineering uncertainty, engineering-quality evidence, warnings, raw values, and
  three private annotated previews
- A mobile-friendly measurement confirmation, immutable history, and result-evidence workflow
- Unit, synthetic, golden, integration, frontend, smoke, and regression tests

Phase 3 is experimental and is not certified metrology. Physical qualification with known-size
rigid reference blocks remains incomplete, so no real-world accuracy claim is made. It supports
only opaque, rigid, stable, approximately cuboidal products captured in the configured qualified
orthogonal rig. It does **not** include AI segmentation, shape classification, weight or volume,
background jobs, progress streams, review, approval, exports, or LAN mode.

## Requirements

- Windows 10 or 11
- Windows PowerShell 5.1 or later
- Python 3.11 with the Windows `py` launcher
- Node.js 22.12+ or Node.js 24 LTS
- Internet access for the initial dependency installation

The application runtime is local after dependencies are installed. It does not call a cloud AI API
or send telemetry.

## Windows setup

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

The setup script:

1. Validates Python and Node.js versions.
2. Creates `.venv`.
3. Installs pinned Python tooling and packages from `requirements-dev.lock`.
4. Installs frontend packages from `frontend/package-lock.json`.
5. Creates `.env` from `.env.example` only when missing.
6. Creates local runtime directories.
7. Verifies NumPy, OpenCV, `cv2.aruco`, `ArucoDetector`, marker generation, and the three approved
   dictionaries.
8. Applies all SQLite migrations through the Phase 3 measurement schema.
9. Verifies database readiness.

The script does not require virtual-environment activation and does not change the system execution
policy. If `.venv` already exists, setup verifies that it uses Python 3.11. An incompatible or
incomplete environment is never deleted automatically; setup stops with an explicit remediation
message.

## Run in development

```powershell
.\scripts\run_dev.ps1
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` requests to FastAPI. Press `Ctrl+C` in the
PowerShell window to stop the backend and frontend wrapper processes and their tracked Python/Node
descendants. Cleanup is restricted to the two process trees launched by the script.

## Run the production build locally

```powershell
.\scripts\run_prod.ps1
```

Open <http://127.0.0.1:8000>. FastAPI serves both the API and compiled frontend from the same local
origin. `/scans/new`, `/scans`, `/scans/{id}`, `/scans/{id}/measurements/{measurementId}`,
`/calibration`, and `/status` support direct browser navigation. Unknown `/api/*` paths remain JSON
API `404` responses and are never replaced by the SPA shell.

LAN binding is intentionally unavailable in Phase 3.

## Phase 1 workflow

1. Open **New Scan** and enter a SKU plus optional barcode and product name.
2. Choose top, front, and side images. Optional additional images are supported up to the configured
   per-scan limit. Camera buttons use `capture="environment"` on compatible mobile browsers.
3. Review the browser-local previews, then create the scan and upload the selected files.
4. If upload fails, the created scan ID is retained. The page checks the saved scan before retrying,
   so a lost success response does not resend already-committed required views.
5. If scan creation itself cannot be confirmed, the form blocks an unsafe automatic retry and links
   to History so the user can check whether the record exists before starting another.
6. Open **History** or the scan detail page to inspect status, missing views, and safe image metadata.

Image bytes are not exposed by an API in Phase 1. Previews are available before upload from the
browser-selected files; persisted scan details intentionally show metadata only.

## Phase 2 calibration workflow

1. Open **Calibration** and create an immutable profile using one approved dictionary, marker ID,
   black-square side in millimetres, and explicit quality thresholds.
2. Activate the profile. The switch is one SQLite transaction, and the database enforces at most one
   active profile.
3. Preview or download its SVG. Print at **100% / actual size**, disable fit-to-page, and physically
   verify the black-square side with a ruler.
4. Capture or select exactly one JPEG, PNG, or WebP marker image. Phase 1 extension, MIME, size,
   decode, animation, pixel-count, EXIF-orientation, and resolution checks run before OpenCV.
5. Inspect canonical corners, orientation, edges, marker-plane matrices, normalized homography
   conditioning, edge-localization evidence, and annotated/rectified previews.

Calibration test images and previews are never written to disk or the database. The edge residual is
an image-local marker-border quality signal, not certified camera reprojection error. Missing, wrong,
duplicate, additional, cropped, undersized, excessively distorted, unstable, or weak-evidence
markers fail with a structured response.

Evidence is labelled with the immutable profile name and ID that produced it and is cleared when the
operator selects another profile. Rectified preview dimensions always match the reported geometry;
if a lossless PNG cannot fit the encoded response ceiling, the test fails with a sanitized
calibration error instead of silently changing the scale.

## Phase 3 measurement workflow

1. Build and physically qualify the orthogonal rig described in
   `docs/GEOMETRY_CAPTURE_GUIDE.md`. Configure a non-placeholder rig ID and version, its measured
   uncertainty bounds, and `CAPTURE_SETUP_QUALIFIED=true`. Qualification cannot be replaced by a UI
   acknowledgement.
2. Activate the correct marker calibration profile and create a scan with valid top, front, and side
   images. Each required view must contain exactly one configured marker on that view's valid
   measurement plane. A floor-plane marker never calibrates height.
3. Open the scan detail page, choose **Measure scan**, review the capture contract, and explicitly
   confirm that the opaque rigid cuboid and all three images satisfy it.
4. The request runs synchronously and processes one view at a time. Heavy decoded and geometry
   arrays are released before the next view; only bounded evidence and preview bytes are retained.
   The original image files are revalidated and hashed but are never renamed, normalized,
   overwritten, or deleted.
5. Inspect the immutable result: raw per-view axes, reconciled length/width/height, disagreement,
   conservative uncertainty, engineering quality, warnings, marker/foreground evidence, and the
   three private annotated previews.
6. Retrying an uncertain request reuses its request UUID. Explicit reprocessing uses a new UUID and
   links a new immutable attempt without changing earlier evidence.

Unsupported captures fail safely. This includes freehand images, unknown or unqualified rigs,
transparent/flexible/highly reflective products, unknown off-plane displacement, invalid marker or
homography evidence, ambiguous foreground candidates, cropping, insufficient quality, excessive
uncertainty, and invalid cross-view disagreement.

## Validation

Run the complete Phase 3 validation suite:

```powershell
.\scripts\run_tests.ps1
```

Individual commands:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m mypy backend\app
.\.venv\Scripts\python.exe -m pip check

npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend ls --depth=0

.\scripts\smoke_test.ps1
.\scripts\validate_dev_shutdown.ps1
```

The smoke test uses an isolated temporary SQLite database and data root, starts the production
server on an available loopback port, verifies health, the SPA shell, compiled JavaScript and CSS,
scan creation, a three-view upload, scan read, and history, then terminates the server and removes
its temporary files. It also creates and activates a calibration profile, validates the exact-size
SVG, analyzes a generated marker, checks marker evidence and previews, verifies direct
`/calibration` navigation and the JSON API `404` boundary, and confirms the test added no runtime
file. Phase 3 smoke coverage also checks the disabled-by-default measurement policy and the direct
measurement-result SPA route. A qualified synthetic smoke rig is test-only and is not evidence of
physical accuracy.

`validate_dev_shutdown.ps1` starts development mode, waits until both endpoints are reachable,
executes the same targeted cleanup path used after `Ctrl+C`, and confirms that the complete tracked
process trees are gone and both configured ports are released.

For a manual `Ctrl+C` check, run `run_dev.ps1`, open both URLs, press `Ctrl+C`, and then run:

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object LocalPort -In 8000,5173
Get-CimInstance Win32_Process |
    Where-Object CommandLine -Match 'backend\.app\.main:app|frontend\\node_modules\\vite'
```

Both commands should return no application-owned listeners or processes.

## Configuration

Configuration is read from `.env` and environment variables. See `.env.example`.

| Setting | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Local AI SKU Dimensioner` | Display and OpenAPI service name |
| `APP_ENV` | `development` | `development`, `production`, or `test` |
| `APP_HOST` | `127.0.0.1` | Loopback-only host in Phase 3 |
| `APP_PORT` | `8000` | Backend and production UI port |
| `LOG_LEVEL` | `INFO` | Local console log level |
| `DATA_ROOT` | `%LOCALAPPDATA%\LocalAISkuDimensioner` | Database and future runtime artifacts |
| `DATABASE_URL` | Derived from `DATA_ROOT` | Optional explicit local SQLite URL |
| `MAX_UPLOAD_MB` | `25` | Maximum bytes per uploaded image, expressed in MiB |
| `MIN_IMAGE_LONG_EDGE` | `1280` | Minimum decoded long-edge pixels after EXIF orientation |
| `MIN_IMAGE_SHORT_EDGE` | `720` | Minimum decoded short-edge pixels after EXIF orientation |
| `MAX_IMAGE_PIXELS` | `60000000` | Maximum decoded pixels accepted per image |
| `MAX_ADDITIONAL_IMAGES` | `5` | Maximum additional images stored per scan |
| `MAX_UPLOAD_FILES_PER_REQUEST` | `8` | Maximum multipart images in one request |
| `CAPTURE_SETUP_ID` | `unconfigured` | Safe configured rig identifier; clients cannot choose it |
| `CAPTURE_SETUP_VERSION` | `unconfigured` | Immutable operator-managed rig version label |
| `CAPTURE_SETUP_QUALIFIED` | `false` | Explicit physical-qualification gate for measurement |
| `CAPTURE_SETUP_TYPE` | `orthogonal_rig` | Only supported Phase 3 setup type |
| `CAPTURE_SETUP_MIN_OBJECT_MM` | `75` | Lower qualified object-axis bound |
| `CAPTURE_SETUP_MAX_OBJECT_MM` | `400` | Upper qualified object-axis bound |
| `CAPTURE_SETUP_MARKER_SIZE_UNCERTAINTY_MM` | `0.5` | Conservative marker-size uncertainty |
| `CAPTURE_SETUP_PLANE_UNCERTAINTY_MM` | `1.0` | Conservative measurement-plane uncertainty |
| `CAPTURE_SETUP_ORTHOGONALITY_UNCERTAINTY_DEG` | `0.5` | Qualified rig angular uncertainty |
| `CAPTURE_SETUP_STANDOFF_UNCERTAINTY_MM` | `2.0` | Conservative datum/standoff uncertainty |
| `CAPTURE_SETUP_MAX_OFF_PLANE_MM` | `0.0` | Qualified maximum off-plane displacement |
| `MEASUREMENT_PROCESSING_DEADLINE_SECONDS` | `30` | Synchronous processing deadline |
| `MEASUREMENT_PROCESSING_LEASE_SECONDS` | `120` | Attempt lease duration; must exceed the processing deadline |
| `VITE_API_BASE_URL` | `/api` | Frontend API prefix |

Runtime data is deliberately outside this OneDrive-hosted repository to avoid synchronizing user
images or a live SQLite database. Generated data, model weights, uploads, databases, exports, `.env`,
and build artifacts are excluded from Git.

The application can start in degraded mode when the database path cannot be initialized. Health
then returns the same sanitized `503` contract used for other database failures. A healthy response
requires the database revision to match the single Alembic head shipped with the application;
missing, stale, or invalid revisions are not reported as ready.

## Dependency management

`pyproject.toml` is the authoritative Python dependency declaration. `requirements.lock` and
`requirements-dev.lock` are generated lock files used for reproducible installation. The Phase 2
lock resolved NumPy 2.4.6 and `opencv-contrib-python-headless` 4.13.0.92 for Python 3.11. Setup checks
their required ArUco capabilities after installation rather than assuming a version is usable.

Regenerate them after an approved dependency change:

```powershell
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --output-file=requirements.lock pyproject.toml
.\.venv\Scripts\python.exe -m piptools compile --extra=dev --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --output-file=requirements-dev.lock pyproject.toml
```

Frontend dependencies are declared only in `frontend/package.json` and locked in
`frontend/package-lock.json`. There is no root npm workspace.

## Architecture

Development:

```text
Browser → Vite :5173 → /api proxy → FastAPI :8000 → SQLAlchemy → SQLite
```

Production:

```text
Browser → FastAPI :8000 ┬→ /api/*  API
                         └→ /*      compiled React application
```

The frozen Phase 1, Phase 2, and Phase 3 contracts are in `docs/PHASE_1_CONTRACTS.md`,
`docs/PHASE_2_CONTRACTS.md`, and `docs/PHASE_3_CONTRACTS.md`. Routes are documented in
`docs/API.md`, capture requirements are in `docs/GEOMETRY_CAPTURE_GUIDE.md`, and architectural
decisions are in `docs/DECISIONS.md`.

Backend coverage tooling is configured but is not yet enforced by `run_tests.ps1`; adding a measured
threshold remains a future quality improvement.

## Troubleshooting

### Python 3.11 not found

Verify the Windows launcher can find it:

```powershell
py -3.11 --version
```

### PowerShell blocks a script

Use the one-command, process-scoped form shown in the setup instructions. The scripts do not require
a permanent execution-policy change.

### Port already in use

Development uses ports 8000 and 5173. Stop the conflicting local process. Do not change the host to
`0.0.0.0`; LAN mode is not part of Phase 3.

### Health reports database unavailable

Run:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m backend.app.cli healthcheck
```

The health check remains unavailable until the database reaches the current Alembic head. Its HTTP
response does not include migration internals, filesystem paths, or stack traces.

### Marker is not detected or fails quality checks

Use only the SVG generated for the selected profile. Print at actual size, keep the complete black
square visible with clear surrounding space, avoid glare and blur, and hold the camera more parallel
to the marker. Do not loosen thresholds to turn poor evidence into a valid result.
