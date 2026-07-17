# Current Status

## Active phase

Phase 2 — Reference marker and calibration engine

## State

Implemented, independently reviewed, corrected, and validated on 2026-07-18. The reviewer reported
no blockers and two major findings; both major findings now have regression coverage and are fixed.
No commit or push has been created for the Phase 2 branch.

## Implemented scope

- OpenCV contrib headless 4.13.0.92 and NumPy 2.4.6 resolved through the Python 3.11 lock workflow
- Setup verification for NumPy/OpenCV imports, `cv2.aruco`, `ArucoDetector`, marker generation, and
  `DICT_4X4_50`, `DICT_5X5_50`, and `DICT_6X6_50`
- Immutable SQLite calibration profiles through Alembic revision
  `0003_phase2_calibration_profiles`
- Explicit transaction-safe activation with one commit and a partial unique active-profile index
- Deterministic exact-size SVG markers for approved dictionaries and IDs 0 through 49
- Exactly-one-file calibration test uploads using existing Phase 1 extension, MIME, byte-size,
  decoded-format, animation, pixel-count, EXIF-orientation, and resolution validation
- Configured-marker detection, canonical ordered corners, marker-plane homography and inverse,
  normalized conditioning, and marker-only perspective rectification
- Marker-edge localization evidence with RMS, maximum, sample count, per-edge RMS, and threshold
- Bounded in-memory annotated and rectified PNG previews with no source/preview persistence
- Rectified preview dimensions preserved exactly, with safe structured failure when a lossless PNG
  cannot fit the encoded response ceiling
- Structured calibration failures without filenames, local paths, SQL, stack traces, or raw OpenCV
  exceptions
- Calibration options/profile/SVG/test APIs under `/api/calibration`
- Mobile-friendly Calibration page with profile creation/list/read/activation, SVG preview/download,
  print guidance, camera input, profile-bound retry, strict response validation, and complete
  profile-labelled evidence display
- Phase 0 and Phase 1 API, upload, health, production serving, and Windows shutdown behavior preserved

## Explicitly not implemented

- Product contours, product segmentation, or length, breadth, height, volume, weight, or confidence
- Applying marker-plane coordinates to a product
- AI models, SAM, YOLO, shape classification, or model downloads
- Scan processing, background jobs, WebSocket/SSE progress, review, approval, or rejection
- Exports, LAN mode, paid APIs, cloud services, or any Phase 3 behavior

## Automated validation results

- Windows setup: passed with PowerShell 5.1, Python 3.11.9, Node.js 22.22.2, NumPy 2.4.6, OpenCV
  4.13.0, and Alembic head `0003_phase2_calibration_profiles`.
- Backend: 149 tests passed; one upstream Starlette/httpx deprecation warning remains.
- Ruff: passed with no findings.
- mypy strict checks: passed across 44 application source files.
- Python dependency consistency: passed.
- Frontend ESLint and TypeScript checks: passed.
- Frontend Vitest: 9 files and 41 tests passed.
- Frontend production build: passed with 105 transformed modules.
- Frontend dependency consistency: passed.
- Production smoke: passed for Phase 0/1 behavior plus profile create/activate, SVG, marker analysis,
  bounded evidence/previews, ephemeral test behavior, `/calibration`, and API `404` isolation.
- Development shutdown: backend/frontend process trees stopped and ports 8000/5173 were released.
- `scripts/run_tests.ps1`: passed.
- `git diff --check`: passed; Git reported only expected Windows line-ending conversion warnings.
- Independent read-only review: no blockers, two majors fixed, and two minor findings deferred.
- Manual production validation: profile creation/activation, SVG rendering/download, valid marker
  evidence, wrong-ID and ambiguous-marker errors, non-persistence, direct `/calibration`, console,
  mobile overflow, API `404`, and port release checks passed. The in-app browser file-chooser bridge
  timed out, so its native picker interaction was covered by frontend tests while the same runtime
  image requests and responses were validated directly against the local API.

## Known limitations

- Browser/printer settings can change physical output scale. Software provides exact SVG millimetre
  attributes and instructions, but the operator must verify the printed black square with a ruler.
- Phase 2 uses planar marker homography and does not estimate camera intrinsics or lens distortion.
- The marker-edge residual is an image-local border-localization signal, not certified camera
  reprojection error or metrology accuracy.
- Test fixtures are deterministic synthetic/generated markers; controlled real-camera and physical
  printed-marker validation is still required before measurement work.
- The current golden regression regenerates its marker input through the locked OpenCV generator;
  it is deterministic but is not an independently stored binary camera-image golden.
- Frontend unknown-response validation checks the complete structural contract but does not decode
  PNG signatures/byte ceilings or fully parse UUID/timestamp semantics; the backend remains the
  authoritative strict contract boundary.
- Calibration tests intentionally return base64 previews in one response; dimensions and encoded
  bytes are bounded, but the response is not a streaming interface.
- Existing Phase 1 SQLite/filesystem power-loss, explicit fsync, and content re-hashing limitations
  remain unchanged.
- Backend coverage tooling exists, but no coverage threshold is enforced.
- FastAPI's current `TestClient` compatibility layer emits one upstream deprecation warning.
- Setup has been validated on the current Windows 11 machine, not a second clean workstation.

## Next gate

Wait for user approval before committing or pushing Phase 2. Do not begin Phase 3 without separate
explicit approval.
