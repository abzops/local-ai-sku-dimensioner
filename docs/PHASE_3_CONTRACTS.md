# Phase 3 Frozen Contracts

These contracts are frozen before implementation. Implementation agents must build against them
and must not independently add, remove, or rename public routes, fields, enum values, database
columns, error codes, or cross-layer interfaces.

## Phase boundary

Phase 3 synchronously measures an opaque, rigid, stable, approximately cuboidal product captured in
one explicitly configured and physically qualified orthogonal rig. It uses deterministic OpenCV
geometry only. It does not add AI, shape classification, weight or volumetric-weight calculation,
background work, queues, progress streaming, review, export, LAN mode, or Phase 4 behavior.

A marker calibrates only its valid physical plane. A floor-plane marker does not calibrate height,
marker residual does not prove product coplanarity, lens distortion is not claimed as corrected,
and outputs are not certified metrology. Unknown off-plane displacement is blocking.

## Domain values

- `MeasurementStatus`: `processing`, `succeeded`, `failed`.
- `DimensionName`: `length`, `width`, `height`.
- `MeasurementView`: `top`, `front`, `side`, in that order.
- `DimensionValidationStatus`: `acceptable`, `warning`, `invalid`.
- `ReconciliationRule`: `quality_uncertainty_weighted`, `stronger_source`, `failed`.
- `PreviewKind`: `annotated` only.
- `CaptureSetupType`: `orthogonal_rig` only.
- Existing `ScanStatus` remains exactly `draft`, `images_uploaded`, and
  `ready_for_processing`.

Axis mapping is fixed:

- top: `length`, `width`
- front: `width`, `height`
- side: `length`, `height`
- final length: top plus side
- final width: top plus front
- final height: front plus side

All physical values use finite millimetres. Quality scores are engineering evidence, not
probabilities. Uncertainty is a conservative engineering bound, not a statistical confidence
interval.

## Configured capture setup

The server owns one configuration-only capture contract. Phase 3 provides no capture-setup CRUD.

Settings are:

- `CAPTURE_SETUP_ID`: non-empty safe display identifier, at most 100 characters.
- `CAPTURE_SETUP_VERSION`: non-empty safe display version, at most 50 characters.
- `CAPTURE_SETUP_QUALIFIED`: boolean, default `false`.
- `CAPTURE_SETUP_TYPE`: fixed `orthogonal_rig`.
- `CAPTURE_SETUP_MIN_OBJECT_MM`: finite positive minimum supported axis, default 75.
- `CAPTURE_SETUP_MAX_OBJECT_MM`: finite maximum supported axis, default 400.
- `CAPTURE_SETUP_MARKER_SIZE_UNCERTAINTY_MM`: finite non-negative bound.
- `CAPTURE_SETUP_PLANE_UNCERTAINTY_MM`: finite non-negative bound.
- `CAPTURE_SETUP_ORTHOGONALITY_UNCERTAINTY_DEG`: finite non-negative bound.
- `CAPTURE_SETUP_STANDOFF_UNCERTAINTY_MM`: finite non-negative bound.
- `CAPTURE_SETUP_MAX_OFF_PLANE_MM`: finite non-negative bound.

Qualification is disabled by default. A qualified configuration must have an ID, version, the fixed
type, a valid minimum/maximum relationship, and finite uncertainty bounds. Software cannot verify
physical qualification or coplanarity; qualification is an explicit operator/admin responsibility.

The server snapshots every safe value above into each attempt. The client sends only
`expected_capture_setup_id`, which must equal the configured ID. Operator acknowledgement is
required but never substitutes for `CAPTURE_SETUP_QUALIFIED=true`.

## Measurement policy

The server owns and snapshots these initial policy values:

- acceptable disagreement: absolute <= 5 mm and relative <= 3%.
- warning ceiling: absolute <= 10 mm and relative <= 6%.
- invalid: absolute > 10 mm or relative > 6%.
- usable quality: >= 0.70.
- weak quality: >= 0.55 and < 0.70.
- stronger-source quality lead: >= 0.15.
- weaker-source uncertainty ratio: >= 2.0.
- a per-view or reconciled uncertainty bound must remain below its corresponding positive physical
  dimension; otherwise the attempt fails as `MEASUREMENT_UNCERTAINTY_EXCESSIVE`.
- maximum rectified edge: 4096 pixels.
- maximum rectified pixels: 16,000,000.
- maximum physical extent: 1500 mm per axis.
- maximum connected components: 1024.
- maximum scored candidates: 64.
- maximum preview long edge: 1280 pixels.
- maximum preview encoded size: 2 MiB.

Both acceptable limits must pass. Warning-range values are never blended. Invalid disagreement or
one invalid required view fails the entire attempt.

## Public options API

`GET /api/measurements/options` is database-independent and returns:

```json
{
  "capture_setup": {
    "id": "rig-local-1",
    "version": "1",
    "type": "orthogonal_rig",
    "qualified": false,
    "processing_enabled": false,
    "minimum_object_mm": 75.0,
    "maximum_object_mm": 400.0,
    "supported_product_domain": [
      "opaque",
      "rigid",
      "stable",
      "approximately_cuboidal",
      "fully_visible",
      "non_reflective_or_mildly_reflective",
      "configured_orthogonal_rig"
    ],
    "requirements": [
      "Use the configured qualified orthogonal rig.",
      "Use a valid view-specific measurement plane for every required view.",
      "Register the product against the rig datums.",
      "Keep exactly one configured marker visible in each required image."
    ]
  },
  "required_views": ["top", "front", "side"],
  "dimension_axis_mapping": {
    "top": ["length", "width"],
    "front": ["width", "height"],
    "side": ["length", "height"]
  },
  "disagreement_thresholds": {
    "acceptable_absolute_mm": 5.0,
    "acceptable_relative_percent": 3.0,
    "warning_absolute_mm": 10.0,
    "warning_relative_percent": 6.0
  },
  "non_certified_metrology_warning": "Measurements are deterministic engineering estimates from a physically qualified local rig, not certified metrology."
}
```

`processing_enabled` is true only when the configured capture contract passes validation and is
qualified. The response contains no paths, secrets, environment-variable names, or internal
configuration.

## Processing request

`POST /api/scans/{scan_id}/measurements` accepts exactly:

```json
{
  "request_id": "UUID",
  "expected_calibration_profile_id": "UUID",
  "expected_capture_setup_id": "rig-local-1",
  "capture_contract_acknowledged": true,
  "reprocess_of_measurement_id": null
}
```

Unknown fields are rejected. The request accepts no source IDs, paths, filenames, hashes, corners,
contours, masks, matrices, dimensions, or physical scale. Reprocessing supplies a new `request_id`
and the prior terminal attempt ID in `reprocess_of_measurement_id`.

## Public safe records

`MeasurementFailure` contains exactly:

- `code`
- `message`
- `recoverable`
- `suggested_action`
- optional `field`
- optional `view`, restricted to top/front/side

`MeasurementSourceResponse` contains:

- `view`
- `scan_image_id`
- `original_sha256`: lowercase 64-character hexadecimal digest
- `oriented_pixel_sha256`: lowercase 64-character hexadecimal digest
- `media_type`
- `size_bytes`
- `width_px`
- `height_px`

It never contains a filename, storage key, or path.

`MarkerEvidenceResponse` contains the server-derived Phase 2 marker evidence required for audit:

- dictionary, marker ID, and physical marker side
- canonical ordered corners
- orientation and edge lengths
- perspective ratio
- finite image-to-plane and plane-to-image 3 by 3 matrices
- homography condition number
- marker-edge localization evidence

`RectificationEvidenceResponse` contains:

- width and height in pixels
- pixels per millimetre
- physical origin in millimetres
- finite source-to-rectified and rectified-to-source 3 by 3 matrices
- physical width and height in millimetres

`ForegroundEvidenceResponse` contains:

- background Lab median and MAD
- grayscale background median and foreground difference
- supported signal names and count
- component and scored-candidate counts
- selected and runner-up scores
- strong-core coverage and mask stability
- shadow and reflection fractions
- marker and border clearance in millimetres
- contour area, hull area, solidity, and extent
- canonically ordered oriented-box corners in millimetres
- oriented-box angle
- threshold/morphology variant spans

`ViewQualityEvidenceResponse` contains a finite `score` from 0 through 1 and these finite components:
marker, homography, background, mask stability, candidate uniqueness, and visibility.

`ViewUncertaintyEvidenceResponse` contains finite non-negative millimetre components for marker
size, marker localization, raster, foreground stability, rig plane, rig orthogonality, mount/standoff,
off-plane/parallax, and `total_mm`.

`PerViewMeasurementResponse` contains:

- `view`
- the safe source record
- marker evidence
- rectification evidence
- foreground evidence
- raw dimensions valid for that view only
- quality evidence
- uncertainty evidence
- warnings
- preview availability

`DimensionResultResponse` contains exactly:

- `dimension`: length, width, or height
- `contributing_views`: the frozen pair for that dimension
- `raw_values_mm`: both named view values
- `value_mm`: finite positive value when acceptable or warning, otherwise null
- `absolute_disagreement_mm`
- `relative_disagreement_percent`
- `quality_inputs`: both named view scores
- `uncertainty_inputs_mm`: both named view uncertainty values
- `uncertainty_mm`: conservative final bound or null
- `reconciliation_rule`
- `validation_status`
- `warnings`

`PreviewDescriptorResponse` contains only `view`, `kind`, `media_type`, `width_px`, `height_px`,
`size_bytes`, and a server-relative API URL. The URL must match the owning scan, attempt, and view;
it is never a storage path.

## Attempt responses

`MeasurementAttemptSummaryResponse` contains:

- identity, scan, request, and optional reprocess IDs
- status
- producing calibration-profile ID and name
- safe capture-setup ID and version
- processing and algorithm versions
- nullable final length/width/height
- nullable safe failure code
- `is_stale` and allowlisted `stale_reasons`
- created and nullable completed timestamps

`MeasurementAttemptListResponse` contains `items`, `total`, `offset`, and `limit`, newest first.

`MeasurementAttemptDetailResponse` contains the summary fields plus:

- complete safe calibration-profile snapshot
- complete safe capture-setup snapshot
- measurement-policy snapshot
- source fingerprint
- ordered source records
- ordered per-view evidence
- ordered length/width/height dimension results
- nullable final-dimensions object
- overall quality evidence
- nullable overall uncertainty in millimetres
- warnings
- preview descriptors
- nullable structured failure
- started timestamp

State invariants:

- processing: no final dimensions, no preview descriptors, no terminal evidence, no failure, no
  completed timestamp.
- succeeded: three sources, three views, three valid dimension records, final dimensions, three
  previews, no failure, and a completed timestamp.
- failed: no final dimensions or previews, a structured safe failure, and a completed timestamp;
  safe partial sources/view evidence may be retained.

A newly created terminal attempt returns 201. A same-key replay of an existing terminal attempt
returns 200. Preconditions that prevent attempt creation return the existing structured request
error shape. Persisted deterministic failures are resources and are returned as failed attempt
details rather than fabricated successes.

## Routes

- `GET /api/measurements/options`
- `POST /api/scans/{scan_id}/measurements`
- `GET /api/scans/{scan_id}/measurements`
- `GET /api/scans/{scan_id}/measurements/{measurement_id}`
- `GET /api/scans/{scan_id}/measurements/{measurement_id}/previews/{view}`

No process or reprocess alias route is allowed.

## Database fields

Migration `0004_phase3_measurements` adds exactly three tables.

`measurement_attempts`:

- `id`, `scan_id`, `request_id`, `request_signature`
- nullable `reprocess_of_measurement_id`
- `calibration_profile_id`, `status`
- `processing_version`, `algorithm_version`
- `profile_snapshot_json`, `capture_setup_snapshot_json`, `measurement_policy_snapshot_json`
- nullable `source_fingerprint`
- nullable `length_mm`, `width_mm`, `height_mm`
- nullable `per_view_evidence_json`, `reconciliation_evidence_json`, `quality_evidence_json`,
  `uncertainty_evidence_json`, `warnings_json`, `failure_json`
- `lease_token`, `lease_expires_at`
- `created_at`, `started_at`, nullable `completed_at`

`measurement_sources`:

- `id`, `measurement_attempt_id`, `view`, `scan_image_id`
- private `storage_key_snapshot`
- nullable `original_sha256`, nullable `oriented_pixel_sha256`
- `media_type`, `size_bytes`, `width_px`, `height_px`

`measurement_previews`:

- `id`, `measurement_attempt_id`, `view`, `kind`
- private `storage_key`, `sha256`
- `media_type`, `size_bytes`, `width_px`, `height_px`, `created_at`

IDs are server UUIDv4 strings. A unique constraint covers `(scan_id, request_id)`. A partial unique
index permits one processing attempt per scan. Sources are unique per attempt/view; previews are
unique per attempt/view/kind. Terminal attempts and their evidence are immutable. Existing ScanStatus
columns and constraints are unchanged.

## Idempotency, leases, and reprocessing

- The request signature is canonical JSON over all public request fields except no server state.
- Same scan/request ID plus the same signature returns the existing attempt.
- Same key with a different signature returns `MEASUREMENT_REQUEST_CONFLICT`.
- A non-expired processing lease returns `MEASUREMENT_IN_PROGRESS`.
- The same request may atomically reclaim an expired lease with a new private token.
- Every terminal update uses a compare-and-set on attempt ID, processing status, and lease token.
- The configured lease duration must exceed the configured total processing deadline and is passed
  to every claim operation.
- A stale worker cannot finalize after reclamation.
- A different request cannot supersede an active processing attempt.
- After a terminal attempt exists, a new request requires a same-scan terminal
  `reprocess_of_measurement_id`.
- Reprocessing creates a new immutable attempt and never overwrites earlier evidence or previews.

## Internal service interfaces

The deterministic geometry entry points are frozen conceptually as:

```text
rectify_full_plane(image_bgr, marker_evidence, policy) -> RectifiedPlane
extract_foreground(rectified_plane, marker_polygon, view, policy) -> ForegroundResult
measure_product_geometry(foreground_result, view, policy) -> ViewGeometryResult
reconcile_measurements(top, front, side, policy) -> ReconciliationResult
create_geometry_preview(rectified_plane, view_geometry, policy) -> EncodedPreview
```

All arrays are owned NumPy arrays with validated dtype, shape, finite values, and configured size
bounds. Geometry functions perform no database or filesystem writes and raise only allowlisted safe
application errors at their public boundary.

Foreground strong-core consensus requires at least two independently derived signals. Adaptive
threshold support is derived from the base masks and may refine candidates, but it never counts as
an additional independent vote. Shadow evidence is measured before shadow pixels are removed.
Selected-product clipped neutral reflection at or above 5% is outside the supported domain.

Decoded source images, rectified planes, masks, contours, and other heavy arrays are owned by one
view at a time and released before the next required view is decoded. Only array-free source and
geometry evidence plus bounded preview bytes survive to reconciliation and persistence.

The application interface is conceptually:

```text
MeasurementApplicationService.process(session, scan_id, request) -> (attempt, replayed)
```

The persistence service owns claim/reclaim/finalize/fail compare-and-set operations. The stored-image
loader returns original and oriented hashes plus an owned BGR array without changing the source. The
measurement storage service stages and finalizes only attempt-owned preview directories and can
compensate only those exact directories.

## Reconciliation

For values `a` and `b`:

```text
absolute_mm = abs(a - b)
relative_percent = 100 * absolute_mm / max((a + b) / 2, 1 mm)
```

- Acceptable requires absolute <= 5 mm and relative <= 3%.
- Warning is outside acceptable but absolute <= 10 mm and relative <= 6%.
- Invalid is absolute > 10 mm or relative > 6%.
- Acceptable and comparable evidence may use `quality / uncertainty^2` weighting.
- Within acceptable, select a stronger source when quality leads by at least 0.15 or the weaker
  uncertainty is at least twice the stronger uncertainty.
- Warning never blends. It may select the stronger source only when quality is at least 0.70,
  quality leads by at least 0.15, and uncertainty is lower.
- Otherwise the dimension and entire attempt fail.
- One invalid required view or any invalid final dimension fails the entire attempt.

Final uncertainty is the greater per-view conservative bound plus half the absolute disagreement.
It must remain below the selected positive dimension so the conservative lower bound stays
physically meaningful.

## Storage and preview contract

Original images are read-only. Optional additional images are ignored.

Preview staging is beneath:

```text
DATA_ROOT/scans/{scan_id}/.staging/measurements/{attempt_id}/{operation_id}/
```

Successful final previews are beneath:

```text
DATA_ROOT/scans/{scan_id}/measurements/{attempt_id}/previews/
```

All names are server-controlled. Staging and final locations are on the same volume. Finalization is
an atomic directory rename followed by one short database transaction. Normal failure removes only
the current operation-owned directory. Original images, earlier attempts, and earlier previews are
never renamed, normalized, overwritten, or deleted.

The preview endpoint verifies database ownership, containment, reparse-point safety, metadata, SHA-256,
PNG media type/signature, and byte bounds. It returns `Cache-Control: no-store` and never returns a
path or storage key.

## Stable error codes

Phase 3 adds:

- `CAPTURE_SETUP_UNQUALIFIED`
- `CAPTURE_SETUP_MISMATCH`
- `UNSUPPORTED_PRODUCT_DOMAIN`
- `SCAN_NOT_READY`
- `ACTIVE_CALIBRATION_PROFILE_REQUIRED`
- `ACTIVE_CALIBRATION_PROFILE_CHANGED`
- `SOURCE_IMAGE_UNAVAILABLE`
- `SOURCE_IMAGE_CHANGED`
- `RECTIFICATION_INVALID`
- `RECTIFICATION_LIMIT_EXCEEDED`
- `PHYSICAL_EXTENT_EXCEEDED`
- `BACKGROUND_INCONSISTENT`
- `FOREGROUND_LOW_CONTRAST`
- `SHADOW_INTERFERENCE`
- `REFLECTION_INTERFERENCE`
- `PRODUCT_NOT_DETECTED`
- `MULTIPLE_OBJECTS_DETECTED`
- `PRODUCT_CROPPED`
- `PRODUCT_MARKER_TOO_CLOSE`
- `PRODUCT_CONTOUR_INVALID`
- `PRODUCT_AXIS_MISALIGNED`
- `MEASUREMENT_QUALITY_INSUFFICIENT`
- `MEASUREMENT_UNCERTAINTY_EXCESSIVE`
- `MEASUREMENT_DISAGREEMENT`
- `MEASUREMENT_NOT_FOUND`
- `MEASUREMENT_REQUEST_CONFLICT`
- `MEASUREMENT_IN_PROGRESS`
- `REPROCESS_CONFIRMATION_REQUIRED`
- `PROCESSING_INTERRUPTED`

Existing safe upload, marker, `STORAGE_UNAVAILABLE`, and `DATABASE_UNAVAILABLE` codes are reused.
No failure exposes filenames, storage keys, paths, SQL, raw OpenCV/Pillow exceptions, stack traces,
or client-supplied display text.

## Frontend TypeScript contract

`frontend/src/types/measurements.ts` mirrors every public enum, request, options, summary, detail,
evidence, failure, and preview record above. The API client validates unknown JSON recursively with
exact keys, finite values, UUIDs, lowercase SHA-256 values, canonical view/dimension order, status
invariants, correct contribution pairs, server-relative preview URLs, and safe error fields.

The frontend never accepts a filesystem-looking preview value, silently generates a new request ID
after an uncertain outcome, displays fake progress, or treats engineering quality as probability.
