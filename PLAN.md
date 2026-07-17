# Local AI SKU Dimensioning System
## Codex Build Plan and Implementation Guide

**Project name:** Local AI SKU Dimensioning System  
**Suggested repository name:** `local-ai-sku-dimensioner`  
**Primary purpose:** Estimate product Length × Breadth × Height (L × B × H), external shape, and confidence from multiple mobile-phone images containing a known physical reference.  
**Runtime:** Fully local and offline after models and dependencies are downloaded.  
**Primary interface:** Mobile-friendly local web application.  
**Development agent:** OpenAI Codex.  
**Target operating system:** Windows 10/11 first, with Linux compatibility where practical.

---

# 1. Project Objective

Build a local web application that lets an operator:

1. Create or select an SKU.
2. Enter or scan its barcode.
3. Enter the exact dimensions of a known reference object or calibration marker.
4. Upload or capture:
   - Top image
   - Front image
   - Side image
   - Optional rear and angled images
5. Enter weight manually in version 1.
6. Process all images locally.
7. Detect the known reference.
8. Segment the product from the background.
9. Correct perspective and lens distortion.
10. Calculate:
    - Length in millimetres
    - Breadth in millimetres
    - Height in millimetres
    - Bounding-box volume
    - Basic external shape classification
11. Show real-time processing progress.
12. Display annotated images and measurement evidence.
13. Allow a human reviewer to approve, edit, reject, or reprocess the result.
14. Save scan history locally.
15. Export approved results as JSON and CSV.

The first release is not intended to replace a certified industrial DWS. It is an economical internal SKU master-data tool.

---

# 2. Core Engineering Principle

Do not ask an LLM or vision-language model to guess physical dimensions.

Use:

- **AI segmentation** to identify the SKU pixels.
- **OpenCV calibration and geometry** to calculate physical measurements.
- **A known reference object or marker** to establish scale.
- **Deterministic validation rules** to calculate confidence.
- **A human review screen** before accepting measurements.

The authoritative measurement engine must be deterministic and testable.

```text
Mobile images
    ↓
Input validation
    ↓
Reference detection
    ↓
Perspective correction
    ↓
Product segmentation
    ↓
Contour extraction
    ↓
Pixel-to-millimetre conversion
    ↓
Multi-view measurement fusion
    ↓
Shape classification
    ↓
Confidence scoring
    ↓
Human review
```

---

# 3. Version 1 Scope

## 3.1 Included

- Fully local runtime
- Mobile-friendly browser UI
- SKU and barcode text entry
- Top/front/side image upload
- Optional additional images
- Reference dimensions input
- ArUco reference-marker support
- Rectangular calibration-card support
- Image-quality checks
- Product segmentation
- Perspective correction
- Length, breadth, and height calculation
- Basic shape classification
- Bounding volume calculation
- Real-time progress
- Annotated review images
- Manual correction
- Approval/rejection workflow
- SQLite scan history
- JSON and CSV export
- Local model loading
- Automated tests
- Calibration utilities
- Windows setup scripts

## 3.2 Excluded from Version 1

- Certified legal-for-trade weighing
- Automatic weight capture
- Full photogrammetry
- Watertight 3D mesh generation
- Dense point-cloud generation
- Cloud deployment
- Multi-user authentication
- ERP or Supabase integration
- Conveyor scanning
- Automatic model training
- Transparent-object precision claims
- Guaranteed millimetre accuracy for every product type

These can be added later without blocking the measurement proof.

---

# 4. Recommended Technology Stack

## Backend

- Python 3.11
- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy
- SQLite
- OpenCV
- NumPy
- SciPy
- Pillow
- scikit-image
- scikit-learn
- PyTorch
- Segment Anything 2 or another locally licensed segmentation model
- python-multipart
- aiofiles
- pytest
- httpx

## Frontend

Use one of these approaches:

### Preferred for the first release

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- Native WebSocket API
- CSS Modules or a small custom design system

### Acceptable simplified alternative

- Server-rendered HTML
- Vanilla JavaScript
- CSS
- Jinja2

Use React when Codex can maintain the frontend cleanly. Do not introduce a large UI framework unless it clearly reduces implementation work.

## Storage

- SQLite for structured records
- Local filesystem for images, masks, overlays, and exports

## Local inference

- CPU must be supported.
- NVIDIA CUDA acceleration may be enabled when available.
- The application must not require a paid API.
- Model files must not be committed to Git.
- Provide a model-download script and checksum support.

---

# 5. Licensing Requirements

Before selecting or embedding any model:

1. Record the model name.
2. Record the source repository.
3. Record the licence.
4. Record whether commercial use is allowed.
5. Record whether model weights have separate terms.
6. Add the information to `THIRD_PARTY_LICENSES.md`.

Do not silently introduce dependencies that force the entire proprietary application to adopt an incompatible licence.

The application must still work in a geometry-only fallback mode if the AI model is unavailable.

---

# 6. Proposed Repository Structure

```text
local-ai-sku-dimensioner/
├── AGENTS.md
├── PLAN.md
├── README.md
├── CHANGELOG.md
├── THIRD_PARTY_LICENSES.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── package.json
├── scripts/
│   ├── setup_windows.ps1
│   ├── setup_linux.sh
│   ├── download_models.py
│   ├── run_dev.ps1
│   ├── run_prod.ps1
│   ├── run_tests.ps1
│   └── create_reference_markers.py
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── logging_config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── database_models.py
│   │   │   └── schemas.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── scans.py
│   │   │   ├── processing.py
│   │   │   ├── review.py
│   │   │   ├── calibration.py
│   │   │   └── exports.py
│   │   ├── services/
│   │   │   ├── job_manager.py
│   │   │   ├── storage_service.py
│   │   │   ├── export_service.py
│   │   │   └── model_manager.py
│   │   ├── vision/
│   │   │   ├── image_quality.py
│   │   │   ├── marker_detection.py
│   │   │   ├── perspective.py
│   │   │   ├── segmentation.py
│   │   │   ├── contour.py
│   │   │   ├── dimensions.py
│   │   │   ├── shape.py
│   │   │   ├── fusion.py
│   │   │   ├── confidence.py
│   │   │   └── overlays.py
│   │   └── workers/
│   │       └── scan_pipeline.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── fixtures/
│       └── golden/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── NewScan.tsx
│   │   │   ├── Processing.tsx
│   │   │   ├── Review.tsx
│   │   │   ├── History.tsx
│   │   │   └── Calibration.tsx
│   │   ├── api/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── styles/
│   └── tests/
├── data/
│   ├── database/
│   ├── scans/
│   ├── calibration/
│   ├── exports/
│   └── models/
├── docs/
│   ├── CAPTURE_GUIDE.md
│   ├── CALIBRATION_GUIDE.md
│   ├── VALIDATION_PLAN.md
│   ├── API.md
│   └── TROUBLESHOOTING.md
└── sample_data/
    ├── reference_blocks/
    └── example_scan/
```

---

# 7. AGENTS.md Instructions for Codex

Create an `AGENTS.md` file in the repository root containing the following operating rules:

```md
# AGENTS.md

## Project purpose

This project is a fully local SKU dimensioning web application. It estimates
Length × Breadth × Height from calibrated multi-view product images.

## Non-negotiable rules

1. Do not use paid or cloud APIs.
2. Do not estimate dimensions with an LLM.
3. Measurement calculations must be deterministic and covered by tests.
4. Keep AI segmentation behind a clean interface.
5. The app must have a geometry-only fallback.
6. Do not commit model weights, uploaded images, databases, or generated exports.
7. Do not change public API contracts without updating tests and documentation.
8. Validate file type, size, and image decoding before processing.
9. Never trust dimensions supplied by image metadata.
10. Every result must include evidence, confidence, and warnings.

## Supported development environment

Primary: Windows 10/11, PowerShell, Python 3.11, Node.js LTS.
Secondary: Linux.

## Required validation commands

Backend:
- python -m pytest backend/tests
- python -m ruff check backend
- python -m mypy backend/app

Frontend:
- npm run lint
- npm run test
- npm run build

## Development method

Work phase by phase.
Before modifying code:
1. Read PLAN.md.
2. Inspect existing tests.
3. State the files you will change.
4. Implement the smallest complete vertical slice.
5. Run the relevant tests.
6. Update documentation.
7. Summarize limitations honestly.

## UI requirements

The web UI must be mobile-friendly, accessible, and usable on local Wi-Fi.
Always show real processing stages, not a fake timer.
```

Clear repository instructions and a reliable test environment help Codex perform better on longer engineering work.

---

# 8. Data Model

## 8.1 Scan record

```json
{
  "id": "scan_uuid",
  "sku": "SNS-00125",
  "barcode": "8901234567890",
  "product_name": "Example Product",
  "status": "review_required",
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "reference_type": "aruco_marker",
  "reference_width_mm": 100.0,
  "reference_height_mm": 100.0,
  "manual_weight_g": 1245.0,
  "length_mm": 205.4,
  "breadth_mm": 94.6,
  "height_mm": 278.2,
  "bounding_volume_cm3": 5397.8,
  "shape_class": "bottle",
  "confidence": 0.91,
  "approved": false,
  "review_notes": null
}
```

## 8.2 Image record

```json
{
  "id": "image_uuid",
  "scan_id": "scan_uuid",
  "view_type": "top",
  "original_path": "data/scans/.../original/top.jpg",
  "mask_path": "data/scans/.../processed/top_mask.png",
  "overlay_path": "data/scans/.../processed/top_overlay.jpg",
  "width_px": 4032,
  "height_px": 3024,
  "quality_score": 0.94,
  "marker_detected": true,
  "warnings": []
}
```

## 8.3 Progress event

```json
{
  "scan_id": "scan_uuid",
  "stage": "segmenting_top_view",
  "progress": 42,
  "message": "Segmenting the product in the top image",
  "timestamp": "ISO-8601 timestamp"
}
```

## 8.4 Measurement evidence

```json
{
  "view": "top",
  "scale_mm_per_pixel_x": 0.192,
  "scale_mm_per_pixel_y": 0.191,
  "raw_major_axis_px": 1068.5,
  "raw_minor_axis_px": 493.2,
  "measured_major_axis_mm": 205.2,
  "measured_minor_axis_mm": 94.3,
  "reference_reprojection_error_px": 0.72
}
```

Store evidence so the reviewer can understand how the result was produced.

---

# 9. Image Capture Standard

The software cannot compensate for uncontrolled capture indefinitely. The UI must guide the operator.

## Required views

### Top

Used for:

- Length
- Breadth
- Rotation angle
- Top silhouette

### Front

Used for:

- Height
- Front silhouette
- Length cross-check

### Side

Used for:

- Height cross-check
- Breadth cross-check
- Side silhouette

## Capture rules

- Use the main rear camera.
- Do not use digital zoom.
- Keep the complete SKU visible.
- Keep the complete reference marker visible.
- Keep the phone approximately parallel to the measured face.
- Place the reference on the same measurement plane.
- Use diffuse lighting.
- Avoid heavy shadows.
- Do not move or deform the product between views.
- Do not resize or edit images before upload.
- Avoid portrait/landscape auto-rotation ambiguity.
- Use a matte background that contrasts with the SKU.

## Reference recommendation

Preferred:

- Printed ArUco marker on a rigid card
- Exact verified marker side length
- Separate horizontal and vertical reference placement

Acceptable fallback:

- Rigid rectangular card with exact measured width and height

Avoid:

- Coins
- Pens
- Phones
- Unverified packaging
- Flexible paper
- Objects with rounded or hidden edges

---

# 10. Measurement Method

## 10.1 Marker detection

For every required image:

1. Decode image.
2. Correct EXIF orientation.
3. Detect the configured ArUco marker.
4. Verify expected marker ID.
5. Reject duplicate or ambiguous marker detections.
6. Estimate marker corner locations.
7. Calculate homography.
8. Rectify the relevant measurement plane.
9. Compute reprojection error.
10. Reject results exceeding the configured threshold.

## 10.2 Segmentation

Create a `SegmentationProvider` interface.

```python
class SegmentationProvider(Protocol):
    def segment(
        self,
        image: np.ndarray,
        hints: SegmentationHints
    ) -> SegmentationResult:
        ...
```

Implement:

- `Sam2SegmentationProvider`
- `BackgroundSubtractionProvider`
- `ManualPolygonProvider`

The pipeline must allow the reviewer to correct a failed mask manually.

## 10.3 Top-view geometry

1. Rectify the platform plane.
2. Apply the product mask.
3. Remove the marker region.
4. Find the largest valid contour.
5. Remove small isolated regions.
6. Compute a minimum-area rotated rectangle.
7. Convert rectangle axes into millimetres.
8. Define:
   - Longer axis = length
   - Shorter axis = breadth
9. Save contour, corners, dimension lines, and values.

## 10.4 Front-view geometry

1. Rectify the vertical plane.
2. Identify the calibrated baseline.
3. Segment the product.
4. Find the maximum vertical extent.
5. Convert to millimetres.
6. Calculate front-derived height.
7. Calculate visible horizontal extent for cross-checking.

## 10.5 Side-view geometry

Repeat the front procedure using the side view.

Calculate:

- Side-derived height
- Breadth cross-check

## 10.6 Measurement fusion

Use deterministic fusion rules.

Example:

```text
Top length:             205.4 mm
Front length estimate:  207.1 mm
Difference:               1.7 mm
Accepted length:         205.9 mm

Front height:            278.0 mm
Side height:             279.2 mm
Difference:                1.2 mm
Accepted height:         278.6 mm
```

Suggested initial rules:

- Difference ≤ 5 mm: high agreement
- Difference > 5 mm and ≤ 10 mm: review recommended
- Difference > 10 mm: reject or require recapture

Do not average measurements blindly if one view has poor marker or segmentation quality. Use a weighted result based on evidence quality.

---

# 11. Shape Classification

Version 1 must classify only broad external categories:

- Cuboid
- Cylinder
- Bottle
- Can
- Pouch
- Packet
- Sphere-like
- Irregular rigid
- Unknown

Implement shape classification in layers:

## Layer 1: Geometry rules

Examples:

- Top rectangle + rectangular side profiles → cuboid
- Circular/elliptical top + rectangular side → cylinder/can
- Narrow neck detected in front profile → bottle
- Highly deformable/uneven silhouette → pouch or packet

## Layer 2: Optional local image classifier

Add a model only after the geometry pipeline works.

## Layer 3: Human review

The reviewer can change the shape category.

Do not use shape classification to change the authoritative dimensions without an explicit documented rule.

---

# 12. Confidence Scoring

Confidence must be explainable.

Suggested weighted inputs:

| Signal | Weight |
|---|---:|
| Reference marker quality | 25% |
| Perspective/reprojection quality | 15% |
| Segmentation quality | 20% |
| Front/side height agreement | 15% |
| Length/breadth cross-view agreement | 10% |
| Image sharpness and exposure | 10% |
| Product fully visible | 5% |

Example:

```text
Marker quality:          0.98
Perspective quality:     0.92
Segmentation quality:    0.89
Height agreement:        0.95
Cross-view agreement:    0.90
Image quality:           0.86
Visibility:              1.00
Final confidence:        0.93
```

Status rules:

- `confidence >= 0.90`: ready for review
- `0.75 <= confidence < 0.90`: review recommended
- `confidence < 0.75`: recapture recommended
- Missing required evidence: processing failed

Warnings must be saved separately from the score.

---

# 13. Image Quality Checks

Implement before expensive AI inference.

Check:

- Image decodes successfully
- Allowed file type
- Maximum file size
- Minimum resolution
- Blur using variance of Laplacian
- Overexposure
- Underexposure
- Marker visibility
- Product cropping at frame boundaries
- Multiple large foreground objects
- Extreme perspective
- Duplicated upload
- Wrong view selection where detectable

Do not reject automatically for every warning. Separate:

- Blocking errors
- Review warnings
- Informational notices

---

# 14. Real-Time Progress

Use WebSockets or Server-Sent Events.

Preferred endpoint:

```text
GET /api/scans/{scan_id}/events
```

Example stages:

```text
0%   Job created
5%   Validating files
12%  Inspecting image quality
20%  Detecting reference markers
30%  Correcting perspective
42%  Segmenting top view
52%  Measuring top view
62%  Segmenting front view
70%  Measuring height from front
78%  Processing side view
86%  Fusing measurements
92%  Classifying shape
96%  Generating overlays
100% Review result ready
```

Requirements:

- Progress must reflect actual pipeline stage changes.
- Do not use a fake timer.
- Failed stages must show the error.
- The client must reconnect safely.
- The latest event must be recoverable after page refresh.
- Processing must continue if the browser disconnects.
- A scan can be cancelled before finalization.

---

# 15. Web UI Requirements

## 15.1 Dashboard

Show:

- New Scan
- Total scans
- Approved scans
- Review required
- Failed scans
- Recent scans

## 15.2 New Scan page

Fields:

- SKU
- Barcode
- Product name
- Weight in grams, optional
- Reference type
- Reference dimensions
- Top image
- Front image
- Side image
- Optional additional images

Features:

- Mobile camera capture
- Drag-and-drop on desktop
- Image previews
- View labels
- Validation messages
- Clear capture instructions
- Start Processing button

## 15.3 Processing page

Show:

- Actual current stage
- Overall progress
- Per-view status
- Live messages
- Cancel button
- Automatically navigate to review when complete

## 15.4 Review page

Show:

- Top, front, and side annotated images
- Toggle between original, mask, and overlay
- Measured L × B × H
- Bounding volume
- Shape classification
- Confidence
- Evidence panel
- Warnings
- Editable final values
- Approval
- Rejection
- Reprocess
- Notes
- Export

Manual changes must preserve:

- Original computed value
- Final reviewed value
- Reviewer timestamp
- Reason for override

## 15.5 History page

Filters:

- SKU
- Barcode
- Status
- Date
- Confidence range
- Shape category

Actions:

- Open
- Reprocess
- Duplicate as new scan
- Export
- Delete with confirmation

## 15.6 Calibration page

Provide:

- Marker PDF generation
- Marker size configuration
- Test-image upload
- Detection preview
- Reprojection error
- Saved calibration profiles
- Active calibration profile
- Reference-block validation results

---

# 16. API Contract

Suggested endpoints:

```text
GET    /api/health
POST   /api/scans
POST   /api/scans/{id}/images
POST   /api/scans/{id}/process
GET    /api/scans/{id}
GET    /api/scans/{id}/events
POST   /api/scans/{id}/cancel
POST   /api/scans/{id}/approve
POST   /api/scans/{id}/reject
POST   /api/scans/{id}/reprocess
PATCH  /api/scans/{id}/review
GET    /api/scans
DELETE /api/scans/{id}
GET    /api/scans/{id}/export.json
GET    /api/scans/{id}/export.csv
POST   /api/calibration/test
GET    /api/calibration/profiles
POST   /api/calibration/profiles
```

Generate OpenAPI documentation automatically through FastAPI.

---

# 17. Error Handling

Use structured errors.

```json
{
  "code": "REFERENCE_NOT_DETECTED",
  "message": "The configured reference marker was not detected in the side image.",
  "view": "side",
  "recoverable": true,
  "suggested_action": "Retake the side image with the complete marker visible."
}
```

Required error categories:

- Invalid file
- Unsupported image
- File too large
- Marker missing
- Marker ambiguous
- Excessive perspective
- Segmentation failed
- Product cropped
- Multiple objects detected
- Measurement disagreement
- Model unavailable
- Processing cancelled
- Internal error

Never expose full local filesystem paths or raw stack traces in the UI.

---

# 18. Local Security and Privacy

Although the app is local:

- Bind to `127.0.0.1` by default.
- Add an explicit LAN mode for phone access.
- In LAN mode, show the actual local URL.
- Allow an optional local access PIN.
- Restrict uploads by extension, MIME type, decode validation, and size.
- Generate server-side filenames.
- Prevent path traversal.
- Do not execute uploaded content.
- Sanitize CSV exports against formula injection.
- Add configurable retention and deletion.
- Log administrative actions.
- Do not send telemetry by default.

---

# 19. Windows Setup Requirements

Codex must provide PowerShell scripts that work on Windows.

## Setup script responsibilities

1. Verify Python 3.11.
2. Verify Node.js.
3. Create `.venv`.
4. Install Python dependencies.
5. Install frontend dependencies.
6. Create data directories.
7. Copy `.env.example` to `.env` if missing.
8. Initialize SQLite.
9. Optionally download the local segmentation model.
10. Run health checks.

Avoid Linux-only instructions such as:

```text
cp
mkdir -p
nano
source .venv/bin/activate
```

Use PowerShell-compatible commands and scripts.

---

# 20. Environment Configuration

Example `.env.example`:

```env
APP_NAME=Local AI SKU Dimensioner
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
LAN_MODE=false
LAN_ACCESS_PIN=
DATABASE_URL=sqlite:///./data/database/app.db
MAX_UPLOAD_MB=25
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
MODEL_PROVIDER=sam2
MODEL_PATH=./data/models/sam2
DEVICE=auto
ENABLE_AI_SEGMENTATION=true
ENABLE_MANUAL_MASK=true
MIN_IMAGE_WIDTH=1280
MIN_IMAGE_HEIGHT=720
MAX_MARKER_REPROJECTION_ERROR_PX=2.0
HIGH_CONFIDENCE_THRESHOLD=0.90
REVIEW_CONFIDENCE_THRESHOLD=0.75
HEIGHT_WARNING_THRESHOLD_MM=5.0
HEIGHT_REJECT_THRESHOLD_MM=10.0
```

---

# 21. Testing Strategy

## 21.1 Unit tests

Test:

- Pixel-to-mm conversion
- Homography calculation
- Rotated bounding box
- Contour filtering
- Height extraction
- Measurement fusion
- Confidence calculation
- Shape rules
- Export formatting
- Error mapping

## 21.2 Synthetic image tests

Generate simple images with:

- Known rectangles
- Known circles
- Known perspective transformations
- Known marker placement
- Controlled noise
- Blur
- Cropping

The expected dimensions must be known exactly.

## 21.3 Golden-image tests

Maintain a small set of fixed test images and approved expected outputs.

Do not assert every pixel of an AI mask. Assert:

- Marker detection
- Approximate contour area
- Final dimension tolerance
- Warning set
- Output schema

## 21.4 Integration tests

Test the entire flow:

1. Create scan.
2. Upload three images.
3. Start processing.
4. Receive progress events.
5. Retrieve result.
6. Approve result.
7. Export JSON/CSV.

## 21.5 Manual reference-block validation

Use rigid blocks with verified dimensions:

```text
100 × 100 × 100 mm
200 × 150 × 75 mm
300 × 200 × 150 mm
400 × 300 × 200 mm
```

Test:

- Centre of platform
- Near each edge
- Rotated 0°, 15°, 30°, and 45°
- Multiple camera distances
- At least 20 repeats per block

Calculate:

- Mean absolute error
- Maximum absolute error
- Standard deviation
- Repeatability
- Failure rate

---

# 22. Accuracy Targets

These are prototype targets, not guarantees.

| Product type | Initial target |
|---|---:|
| Rectangular boxes | ±4–8 mm |
| Cans and cylinders | ±6–12 mm |
| Bottles | ±8–15 mm |
| Rigid irregular items | ±10–20 mm |
| Flexible pouches | ±15–30 mm |

Version 1 is accepted only after it demonstrates:

- Correct processing on reference blocks
- Repeatable results
- Visible evidence overlays
- Honest warnings on poor captures
- No fabricated result when reference detection fails

---

# 23. Development Phases for Codex

Do not ask Codex to implement the entire system in one prompt.

## Phase 0 — Repository foundation

Deliver:

- Repository structure
- `AGENTS.md`
- Backend and frontend scaffolding
- Configuration system
- Health endpoint
- SQLite initialization
- Windows scripts
- Basic CI-friendly commands
- README

Acceptance:

- Backend starts.
- Frontend starts.
- Health status is visible.
- Tests run.

## Phase 1 — Scan data and upload workflow

Deliver:

- Scan database model
- Create scan API
- Image upload API
- File validation
- Local storage
- New Scan UI
- Scan history shell

Acceptance:

- User can create a scan.
- User can upload top/front/side images.
- Records survive restart.
- Invalid files are rejected safely.

## Phase 2 — Reference marker engine

Deliver:

- ArUco marker generator
- Marker detection
- Plane rectification
- Reprojection error
- Calibration test UI
- Annotated marker preview

Acceptance:

- Known synthetic marker tests pass.
- User can see detected corners.
- Missing markers stop measurement.

## Phase 3 — Geometry-only product measurement

Deliver:

- Background-based segmentation fallback
- Contour extraction
- Top L/B measurement
- Front and side height measurement
- Fusion
- Annotated overlays
- JSON result

Acceptance:

- Reference blocks measure within agreed tolerance under controlled backgrounds.
- No AI dependency is required.

## Phase 4 — Local AI segmentation

Deliver:

- Segmentation provider interface
- Local model manager
- SAM 2 integration or approved alternative
- CPU mode
- GPU mode
- Manual mask correction
- AI fallback behavior

Acceptance:

- Unseen opaque products can be segmented.
- Model failure returns a recoverable error.
- Geometry pipeline remains separately testable.

## Phase 5 — Real-time processing

Deliver:

- Background job manager
- Real progress events
- WebSocket/SSE client
- Processing page
- Cancellation
- Page-refresh recovery

Acceptance:

- UI displays actual pipeline stages.
- Processing continues after browser disconnect.
- Failure stage is visible.

## Phase 6 — Review and approval

Deliver:

- Review page
- Original/mask/overlay viewer
- Evidence panel
- Warnings
- Editable final values
- Approval/rejection
- Audit history

Acceptance:

- Manual override preserves original result.
- Approved scans are clearly distinguished.
- Reviewer can reprocess.

## Phase 7 — Shape classification and confidence

Deliver:

- Geometry-based shape classifier
- Explainable confidence score
- Warning rules
- Unknown fallback

Acceptance:

- Shape result includes evidence.
- Low confidence does not appear as final truth.

## Phase 8 — Export and operational hardening

Deliver:

- JSON export
- CSV export
- Backup/restore guide
- Retention controls
- LAN mode
- Optional PIN
- Packaging/start scripts
- Final documentation

Acceptance:

- A non-developer can start the application locally.
- Phone can access it on the same Wi-Fi in LAN mode.
- Approved result exports correctly.

---

# 24. Codex Prompting Method

Use this structure for every implementation request:

```text
Read AGENTS.md and PLAN.md first.

Implement Phase [NUMBER]: [PHASE NAME].

Before coding:
1. Inspect the current repository and tests.
2. Summarize the current state.
3. List the files you will add or modify.
4. Identify any assumptions.

Implementation requirements:
[Paste only the relevant phase requirements.]

Validation:
- Run backend tests.
- Run frontend tests.
- Run lint/type checks.
- Build the frontend.
- Report every command and result.
- Do not claim success when a command failed.

Deliver:
- Working implementation
- Tests
- Documentation updates
- A concise summary of limitations
```

---

# 25. Master Prompt for Codex

Copy the following prompt into Codex after placing this file in the repository.

```text
You are the lead engineer for a fully local AI-assisted SKU dimensioning
application.

Read AGENTS.md and PLAN.md completely before making changes.

The product must let a user upload top, front, and side mobile-phone images of
an SKU. Every image includes a known physical reference marker. The system must
calculate Length × Breadth × Height using OpenCV calibration and geometry,
classify a broad external shape, calculate confidence, generate annotated
evidence images, show real processing progress, and require human review.

Critical constraints:
- The application must run locally.
- Do not call paid or cloud AI APIs.
- Do not use an LLM to guess measurements.
- Use deterministic geometry for authoritative dimensions.
- AI may segment and classify only.
- Support CPU execution.
- Keep a geometry-only fallback.
- Target Windows 10/11 first.
- Provide a mobile-friendly local web UI.
- Use FastAPI, React/TypeScript, SQLite, OpenCV, and a modular local
  segmentation provider.
- Do not commit model weights or user data.
- Write tests for all measurement calculations.

Begin with Phase 0 only.

Before implementation:
1. Inspect the repository.
2. Explain the intended Phase 0 architecture.
3. List all planned files.
4. Check for conflicting existing code.

Then implement Phase 0, run all available validation commands, fix failures,
and update README.md with exact Windows setup and run instructions.

Do not begin Phase 1 until Phase 0 is complete and validated.
```

---

# 26. Phase-by-Phase Prompts

## Prompt for Phase 1

```text
Read AGENTS.md and PLAN.md.

Implement Phase 1: Scan data and image upload workflow.

Build a complete vertical slice:
- SQLite scan and image records
- Create/list/read scan APIs
- Validated top/front/side image uploads
- Safe server-side filenames
- Local storage structure
- New Scan React page
- Basic History page
- Clear structured errors
- Automated unit and integration tests

Do not implement measurement or AI yet.

Run all backend tests, lint, typing, frontend tests, and frontend build.
Fix failures before reporting completion.
```

## Prompt for Phase 2

```text
Read AGENTS.md and PLAN.md.

Implement Phase 2: Reference marker engine.

Requirements:
- Generate printable ArUco markers
- Configure marker ID and physical side length
- Detect marker corners using OpenCV
- Calculate homography and rectify the measurement plane
- Calculate reprojection error
- Produce annotated detection images
- Add Calibration page and API
- Fail safely if the marker is absent or ambiguous
- Add synthetic and golden-image tests

Do not implement AI segmentation yet.
```

## Prompt for Phase 3

```text
Read AGENTS.md and PLAN.md.

Implement Phase 3: Geometry-only measurement.

Requirements:
- Background-based segmentation provider
- Largest valid product contour
- Minimum-area rotated rectangle for top L/B
- Front and side baseline-to-top height
- Cross-view validation and deterministic fusion
- Annotated measurement overlays
- Measurement evidence JSON
- Configurable warning and rejection thresholds
- Synthetic geometric tests and reference-block fixtures

The output must never contain dimensions when required calibration evidence is
missing.
```

## Prompt for Phase 4

```text
Read AGENTS.md and PLAN.md.

Implement Phase 4: Local AI segmentation.

First review the selected model licence and document it in
THIRD_PARTY_LICENSES.md.

Requirements:
- SegmentationProvider interface
- Local model manager
- CPU-compatible inference
- Optional CUDA inference
- No cloud calls
- Model weights stored under data/models and ignored by Git
- Download/setup script
- Graceful fallback to background subtraction
- Manual mask correction endpoint and UI
- Tests using mocked model outputs

Keep measurement geometry independent from model internals.
```

## Prompt for Phase 5

```text
Read AGENTS.md and PLAN.md.

Implement Phase 5: Real-time processing.

Requirements:
- Persistent local job state
- Background processing pipeline
- Actual stage-based progress
- WebSocket or SSE endpoint
- Reconnect after refresh
- Processing page
- Per-view status
- Cancellation
- Structured failure stage
- Integration tests for progress and completion

Do not simulate progress using timers.
```

## Prompt for Phase 6

```text
Read AGENTS.md and PLAN.md.

Implement Phase 6: Review and approval.

Requirements:
- Original/mask/overlay comparison
- Evidence and warning panels
- Computed versus reviewed measurements
- Shape editing
- Reviewer notes
- Approve/reject/reprocess
- Audit records
- Export controls
- Accessible mobile-friendly design

Manual edits must never overwrite the original computed result.
```

## Prompt for Phase 7

```text
Read AGENTS.md and PLAN.md.

Implement Phase 7: Shape and confidence.

Requirements:
- Broad geometry-based shape classes
- Unknown fallback
- Explainable weighted confidence
- Per-signal confidence breakdown
- Warning rules
- Unit tests for score calculation
- UI explanation for low-confidence scans

Do not add an LLM.
```

## Prompt for Phase 8

```text
Read AGENTS.md and PLAN.md.

Implement Phase 8: Operational hardening.

Requirements:
- JSON and CSV exports
- CSV formula-injection protection
- LAN mode
- Optional local access PIN
- Retention and delete controls
- Backup and restore instructions
- Windows production start script
- Complete README and troubleshooting guide
- Final end-to-end tests
- Performance measurements on CPU

Provide a release checklist and document remaining limitations honestly.
```

---

# 27. Local Model Strategy

## Version 1

- Geometry-first fallback
- Small local segmentation model
- No LLM
- No monocular depth as authoritative measurement

## Later optional additions

- Local lightweight image classifier
- Local vision-language model for product descriptions
- Photogrammetry for selected SKUs
- Learned measurement correction using validated reference-block data

Any learned correction model must:

- Preserve raw measurements
- Show corrected measurements separately
- Include training-data version
- Be tested against an untouched validation set
- Never hide the original geometric result

---

# 28. Manual Review Rules

Require review when:

- Confidence is below 0.90
- Product is transparent
- Product is reflective
- Product touches image boundary
- Marker reprojection error is high
- Front and side heights disagree
- Multiple objects are detected
- Product is flexible
- AI and fallback masks differ substantially
- Operator manually changes the mask

Require recapture when:

- Marker is missing
- Reference size is absent
- Required view is absent
- Product is heavily cropped
- Perspective cannot be rectified
- Height disagreement exceeds reject threshold
- Image is unreadable

---

# 29. Output Format

Approved JSON example:

```json
{
  "scan_id": "SCAN-00042",
  "sku": "SNS-00125",
  "barcode": "8901234567890",
  "product_name": "Example Bottle",
  "dimensions": {
    "length_mm": 205.4,
    "breadth_mm": 94.6,
    "height_mm": 278.2,
    "bounding_volume_cm3": 5397.8
  },
  "weight": {
    "value_g": 1245.0,
    "source": "manual"
  },
  "shape": {
    "class": "bottle",
    "confidence": 0.93
  },
  "measurement": {
    "confidence": 0.91,
    "status": "approved",
    "warnings": [],
    "method": "multi_view_reference_geometry"
  },
  "review": {
    "overridden": false,
    "notes": null,
    "approved_at": "ISO-8601 timestamp"
  }
}
```

---

# 30. Definition of Done

The initial project is complete only when:

- A Windows user can install it using documented scripts.
- The backend and frontend start locally.
- A phone can access the UI through LAN mode.
- Top/front/side images can be uploaded.
- Known markers are detected.
- Physical dimensions are calculated through deterministic geometry.
- Progress is shown from actual backend stages.
- Annotated evidence is visible.
- A reviewer can approve, correct, reject, and reprocess.
- History persists locally.
- JSON and CSV exports work.
- Tests cover the measurement core.
- The app fails safely when evidence is missing.
- No paid inference API is required.
- Limitations are clearly documented.

---

# 31. Immediate Next Steps

1. Create an empty repository named `local-ai-sku-dimensioner`.
2. Save this document as `PLAN.md`.
3. Create `AGENTS.md` using Section 7.
4. Open the repository in Codex.
5. Paste the Master Prompt from Section 25.
6. Allow Codex to implement only Phase 0.
7. Review all files and test results.
8. Commit Phase 0.
9. Continue one phase at a time.
10. Begin collecting controlled test photos and accurate reference blocks while development proceeds.

---

# 32. Final Product Positioning

The finished system should be described as:

> A local, AI-assisted SKU dimensioning and review application that derives
> external Length × Breadth × Height from calibrated multi-view mobile images
> and known physical references.

Do not describe it as:

- A certified trade dimensioner
- A certified weighing system
- A precision 3D scanner
- A replacement for industrial metrology
- A guaranteed millimetre-accurate system for all materials

The project succeeds by being economical, transparent, testable, and useful for controlled internal SKU master-data creation.
