# AGENTS.md

## Project Purpose

This repository contains a fully local, AI-assisted SKU dimensioning web application.

The system estimates:

- Length
- Breadth
- Height
- Bounding volume
- Broad external shape
- Measurement confidence

Inputs include:

- Top-view image
- Front-view image
- Side-view image
- Known physical reference marker or calibration card
- Optional manually entered weight

The application must run locally and must not require paid cloud APIs.

---

## Non-Negotiable Rules

1. Do not use paid or cloud AI APIs.
2. Do not use an LLM to guess physical dimensions.
3. Authoritative measurements must come from deterministic OpenCV geometry.
4. AI may assist with segmentation and shape classification only.
5. The application must support a geometry-only fallback.
6. Do not commit model weights, uploaded images, databases, or exports.
7. Do not change public API contracts without updating tests and documentation.
8. Validate file type, MIME type, file size, and image decoding before processing.
9. Never trust physical dimensions from image metadata.
10. Every measurement result must include:
   - Evidence
   - Confidence
   - Warnings
11. Missing calibration evidence must stop measurement.
12. Manual reviewer changes must preserve the original computed values.
13. Do not fabricate successful test results.
14. Do not expand the active phase without approval.
15. Target Windows 10/11 and PowerShell first.

---

## Required Reading

Before making changes, read:

- `PLAN.md`
- `AGENTS.md`
- `CURRENT_STATUS.md`, when present
- `docs/DECISIONS.md`, when present
- Existing tests relevant to the task

---

## Development Method

Work phase by phase.

Before modifying code:

1. Read the project documents.
2. Inspect the existing repository.
3. Summarize the current implementation.
4. List the exact files to add or modify.
5. Identify assumptions and risks.
6. Confirm the active phase.
7. Do not start implementation until the requested planning step is complete.

During implementation:

1. Implement the smallest complete vertical slice.
2. Keep measurement geometry separate from AI model code.
3. Keep backend, frontend, and storage responsibilities clearly separated.
4. Add tests with each feature.
5. Avoid unrelated refactoring.
6. Preserve backwards compatibility unless explicitly approved.

After implementation:

1. Run relevant unit tests.
2. Run integration tests.
3. Run linting.
4. Run type checks.
5. Build the frontend.
6. Update documentation.
7. Report all commands and results honestly.
8. State remaining limitations.

---

## Required Validation Commands

### Backend

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m mypy backend\app
```

### Frontend

```powershell
npm run lint
npm run test
npm run build
```

### Full Project

```powershell
.\scripts\run_tests.ps1
```

If a command does not yet exist in the current phase, document that clearly and add it when the phase requires it.

---

## Architecture Requirements

### Backend

Preferred stack:

- Python 3.11
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- OpenCV
- NumPy
- PyTorch only where required
- Local filesystem storage

### Frontend

Preferred stack:

- React
- TypeScript
- Vite
- Mobile-first responsive design

### Measurement Pipeline

The authoritative pipeline must follow:

```text
Image validation
→ Reference detection
→ Perspective correction
→ Product segmentation
→ Contour extraction
→ Pixel-to-millimetre conversion
→ Multi-view measurement fusion
→ Confidence scoring
→ Human review
```

### AI Boundary

AI can:

- Segment the product
- Detect likely shape class
- Detect capture-quality issues
- Assist manual review

AI cannot:

- Invent dimensions
- Override missing calibration
- Replace geometric calculations
- Return unverified physical measurements

---

## UI Requirements

The application must be:

- Mobile-friendly
- Accessible
- Usable over local Wi-Fi
- Clear about processing state
- Honest about failures and uncertainty

The UI must show actual stages, not a fake timer.

Required stages should include:

- Upload validation
- Reference detection
- Perspective correction
- Segmentation
- Top-view measurement
- Front-view measurement
- Side-view measurement
- Fusion
- Shape classification
- Confidence calculation
- Overlay generation
- Review ready

---

## Error Handling Requirements

Use structured errors.

Examples:

- `INVALID_FILE`
- `REFERENCE_NOT_DETECTED`
- `REFERENCE_AMBIGUOUS`
- `EXCESSIVE_PERSPECTIVE`
- `SEGMENTATION_FAILED`
- `PRODUCT_CROPPED`
- `MULTIPLE_OBJECTS_DETECTED`
- `MEASUREMENT_DISAGREEMENT`
- `MODEL_UNAVAILABLE`
- `PROCESSING_CANCELLED`

Do not expose:

- Full stack traces
- Local filesystem paths
- Secrets
- Internal model paths

---

## Security Requirements

Even though the app is local:

1. Bind to `127.0.0.1` by default.
2. Add LAN mode only when explicitly enabled.
3. Validate uploads by extension, MIME type, and decode result.
4. Generate server-side filenames.
5. Prevent path traversal.
6. Do not execute uploaded files.
7. Protect CSV export from formula injection.
8. Do not send telemetry by default.
9. Do not silently upload user images.
10. Do not expose model-download credentials.

---

## Testing Requirements

Every measurement-related feature must have tests.

Required categories:

- Unit tests
- Synthetic image tests
- Golden image tests
- Integration tests
- Regression tests

Important test cases:

- Correct marker
- Rotated marker
- Perspective-distorted marker
- Missing marker
- Wrong marker ID
- Blurred image
- Product cropped
- Multiple objects
- Rotated rectangular product
- Front and side height disagreement
- Model unavailable
- Manual mask correction
- Export correctness

Do not tune correction factors using the final validation set.

---

## Git Rules

1. Work on one phase branch at a time.
2. Keep `main` in a runnable state.
3. Commit only after validation.
4. Use clear commit messages.
5. Do not commit:
   - `.env`
   - Model weights
   - Uploaded images
   - SQLite database files
   - Generated reports
   - Temporary processing files

Suggested phase branches:

```text
phase-0-foundation
phase-1-upload
phase-2-marker-engine
phase-3-geometry
phase-4-ai-segmentation
phase-5-progress
phase-6-review
phase-7-confidence
phase-8-hardening
```

---

## Sub-Agent Rules

Use sub-agents only for independent analysis or review.

Good uses:

- Repository inspection
- Computer-vision review
- Test audit
- Security review
- UX review
- Licence research

Do not allow multiple agents to edit the same core files simultaneously.

Preferred pattern:

```text
One agent implements.
Another agent reviews.
The lead agent integrates.
```

Sub-agents should normally return findings only unless explicitly assigned an isolated non-overlapping implementation.

---

## Phase Control

Do not start a later phase automatically.

At the end of each phase, report:

- Files changed
- Tests added
- Commands run
- Results
- Known limitations
- Suggested next phase

Wait for approval before proceeding.

---

## Completion Standard

A task is complete only when:

- The requested scope is implemented.
- Relevant tests pass.
- Lint and type checks pass where configured.
- The frontend builds where applicable.
- Documentation is updated.
- Errors are handled.
- Limitations are stated honestly.
- No unrelated phase work was added.
