# Current Status

## Active phase

Phase 0 — Repository foundation

## State

Implemented and validated on 2026-07-17.

## Implemented scope

- Backend and frontend scaffolding
- Typed configuration and loopback-only default
- SQLite and Alembic baseline
- Structured health endpoint with exact Alembic-head verification and degraded startup handling
- Responsive health-status application shell
- SPA history fallback with a protected JSON API boundary
- Windows setup and process-tree-safe runtime scripts
- Local validation, shutdown validation, and production asset smoke-test harness

## Explicitly not implemented

- SKU or scan records
- Image upload or storage workflows
- OpenCV, calibration, markers, segmentation, or measurement
- Processing jobs or progress events
- Review, approval, history, or export workflows
- LAN mode or local access PIN
- AI models or model downloads

## Validation results

- Windows setup script: passed with PowerShell 5.1, Python 3.11.9, Node.js 22.22.2, and npm 10.9.7.
- Backend tests: 13 passed.
- Ruff: passed with no findings.
- mypy strict checks: passed across 13 application source files.
- Frontend ESLint: passed with zero warnings.
- Frontend TypeScript check: passed.
- Frontend Vitest: 2 files and 8 tests passed.
- Frontend production build: passed with Vite 7.3.6.
- Production smoke test: passed against an isolated migrated SQLite database.
- Development shutdown validation: backend/frontend process trees stopped and ports 8000/5173 were
  released.
- Rendered browser check: desktop and 390 × 844 mobile layouts passed; mobile horizontal overflow
  was absent and no browser console errors were recorded.

## Known limitations

- FastAPI's current `TestClient` compatibility layer emits one upstream deprecation warning about
  its `httpx` fallback. Tests pass and the application runtime is unaffected.
- Setup has been validated on the current Windows 11 machine, not yet on a second clean workstation.
- Backend coverage tooling is configured but no coverage threshold is enforced yet.
- The health endpoint establishes service and migration readiness only; it does not validate any
  future measurement capability.

## Next gate

Phase 1 must not begin without explicit approval after Phase 0 validation and review.
