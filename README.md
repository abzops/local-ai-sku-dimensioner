# Local AI SKU Dimensioner

A Windows-first, fully local web application for building image-complete SKU scan records and
verifying printed ArUco calibration markers. The final product will derive external length, breadth,
and height from multiple mobile images using deterministic OpenCV geometry. Local AI may later
assist segmentation and broad shape classification, but it will not invent authoritative
measurements.

## Current scope

Phase 2 provides:

- The validated Phase 0 runtime and complete Phase 1 scan/image-upload workflow
- Immutable SQLite calibration profiles with explicit transaction-safe activation
- Three approved ArUco dictionaries with marker IDs 0 through 49
- Deterministic exact-physical-size SVG marker generation
- Bounded in-memory calibration uploads using all Phase 1 image-safety checks
- ArUco detection, canonical ordered corners, marker-plane homographies, inverse mapping,
  rectification, and bounded local previews
- A marker-edge localization residual with RMS, maximum, sample count, and per-edge evidence
- A mobile-friendly Calibration page for profiles, marker download, camera capture, and evidence
- Unit, synthetic, golden, integration, frontend, smoke, and regression tests

Phase 2 does **not** locate a product or calculate length, breadth, height, volume, or weight. It also
does not provide segmentation, AI, scan processing, background jobs, progress streams, review,
approval, exports, or LAN mode. Marker-plane coordinates are calibration evidence only.

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
8. Applies all SQLite migrations through the Phase 2 calibration-profile schema.
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
origin. `/scans/new`, `/scans`, `/scans/{id}`, `/calibration`, and `/status` support direct browser
navigation. Unknown `/api/*` paths remain JSON API `404` responses and are never replaced by the SPA
shell.

LAN binding is intentionally unavailable in Phase 2.

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

## Validation

Run the complete Phase 2 validation suite:

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
file.

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
| `APP_HOST` | `127.0.0.1` | Loopback-only host in Phase 2 |
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

The Phase 1 scan contract remains in `docs/PHASE_1_CONTRACTS.md`. Phase 2 routes are documented in
`docs/API.md`, and frozen calibration types are in `docs/PHASE_2_CONTRACTS.md`. Architectural
decisions are in `docs/DECISIONS.md`. Project-wide constraints are in `AGENTS.md`, and the phase plan
is in `PLAN.md`.

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
`0.0.0.0`; LAN mode is not part of Phase 2.

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
