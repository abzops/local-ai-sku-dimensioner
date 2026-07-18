# Local API — Phases 0 through 3

All routes are local and use the `/api` prefix. JSON responses never contain a client filename,
absolute path, relative storage key, raw exception, or stack trace.

## Create a scan

`POST /api/scans`

```json
{
  "sku": "SKU-001",
  "barcode": "8901234567890",
  "product_name": "Example item"
}
```

`sku` is required. `barcode` and `product_name` are optional. The `201` response is a scan detail
with status `draft`, missing views `top`, `front`, and `side`, and an empty `images` list.

## Read and list scans

- `GET /api/scans/{scan_id}` returns one scan detail or structured `SCAN_NOT_FOUND`.
- `GET /api/scans?offset=0&limit=50` returns reverse-chronological summaries. `offset` is at least
  zero; `limit` is from 1 through 100.

## Upload scan images

`POST /api/scans/{scan_id}/images` accepts `multipart/form-data` fields:

- `top`: zero or one file
- `front`: zero or one file
- `side`: zero or one file
- `additional`: zero or more repeated files

At least one file is required. The default request limit is eight files, the default additional
limit is five per scan, and a scan can contain only one persisted top, front, and side view.
The server enforces the per-file byte ceiling while parsing multipart data, before a file can grow
past that limit in temporary storage.

The `201` response contains:

```json
{
  "scan": {
    "id": "server UUID",
    "sku": "SKU-001",
    "barcode": null,
    "product_name": null,
    "status": "images_uploaded",
    "missing_required_views": ["front", "side"],
    "created_at": "UTC timestamp",
    "updated_at": "UTC timestamp",
    "images": [
      {
        "id": "server image UUID",
        "view_type": "top",
        "media_type": "image/png",
        "size_bytes": 4096,
        "width_px": 1280,
        "height_px": 720,
        "created_at": "UTC timestamp"
      }
    ]
  },
  "uploaded_images": [
    {
      "id": "server image UUID",
      "view_type": "top",
      "media_type": "image/png",
      "size_bytes": 4096,
      "width_px": 1280,
      "height_px": 720,
      "created_at": "UTC timestamp"
    }
  ]
}
```

Each public image contains only `id`, `view_type`, canonical `media_type`, `size_bytes`, decoded
`width_px`, decoded `height_px`, and `created_at`.

## Structured request errors

```json
{
  "code": "IMAGE_TOO_SMALL",
  "message": "The image does not meet the minimum resolution.",
  "recoverable": true,
  "suggested_action": "Capture an image with a long edge of at least 1280 pixels and a short edge of at least 720 pixels.",
  "field": "top",
  "view": "top"
}
```

`field` and `view` are optional and omitted when not applicable. Health keeps its existing four-field
degraded error contract. See `docs/PHASE_1_CONTRACTS.md` for the frozen schema and error-code list.
Malformed multipart bodies return `MALFORMED_MULTIPART`; parser-level file/count limits return
`FILE_TOO_LARGE` or `UPLOAD_LIMIT_EXCEEDED` in the same shape.

## Batch behavior

All request files are validated before staging. If any file fails, no file or image metadata from
that request is kept. After staging, required-view and per-scan limits are rechecked; final files and
metadata are then coordinated with operation-owned compensation for normal failures. Existing files
from earlier successful requests are not deleted.

## Calibration options and profiles

The Phase 2 calibration routes are local, use `/api/calibration`, and never expose database or
filesystem details.

- `GET /api/calibration/options` returns the three approved dictionaries, marker ID range 0–49,
  fixed one-bit border, and profile defaults. It does not require a working database.
- `POST /api/calibration/profiles` creates an inactive immutable profile and returns `201`.
- `GET /api/calibration/profiles` returns `{items, total}`, active first and then newest first.
- `GET /api/calibration/profiles/{profile_id}` returns one profile.
- `POST /api/calibration/profiles/{profile_id}/activate` switches the single active profile in one
  transaction.

Profile creation accepts only `name`, `dictionary`, `marker_id`, `marker_size_mm`,
`minimum_marker_side_px`, `maximum_perspective_ratio`,
`maximum_homography_condition_number`, `maximum_marker_edge_residual_px`, and
`rectified_pixels_per_mm`. The accepted dictionaries are `DICT_4X4_50`, `DICT_5X5_50`, and
`DICT_6X6_50`. There is no update or delete endpoint in Phase 2.

## Exact-size marker SVG

`GET /api/calibration/profiles/{profile_id}/marker.svg` returns deterministic `image/svg+xml` with
the configured black-square side expressed in `mm`, a square `viewBox`, no script or external
resource, and a server-generated download name. Print at 100% / actual size with fit-to-page disabled
and physically verify the black square before use.

## Calibration test

`POST /api/calibration/profiles/{profile_id}/test` accepts `multipart/form-data` with exactly one
file field named `image`. The file passes the complete Phase 1 upload-validation chain before local
OpenCV analysis. The image and both previews remain in memory and are not persisted.

A successful response includes:

- profile ID, dictionary, marker ID, and physical marker side;
- four raw corners in canonical printed-marker order: top-left, top-right, bottom-right, bottom-left;
- orientation, four edge lengths, and longest/shortest perspective ratio;
- finite 3 × 3 image-pixel-to-marker-mm and inverse marker-plane matrices;
- normalized homography condition number and rectified pixel density;
- `marker_edge_localization_residual` evidence: RMS, maximum, sample count, per-edge RMS, threshold,
  and `valid: true`;
- bounded base64 PNG annotated and rectified previews.

The rectified preview dimensions exactly match `rectified_width_px` and `rectified_height_px`. If a
lossless PNG cannot fit the encoded-size ceiling without changing those dimensions, the request
fails with a sanitized structured calibration error.

This is marker-plane evidence only. The response contains no product contour or physical product
dimension. The edge residual is an image-local marker-border localization metric, not certified
camera reprojection error.

Structured failures include `CALIBRATION_PROFILE_NOT_FOUND`,
`CALIBRATION_PROFILE_NAME_CONFLICT`, `REFERENCE_NOT_DETECTED`, `REFERENCE_WRONG_ID`,
`REFERENCE_AMBIGUOUS`, `REFERENCE_CORNERS_INVALID`, `REFERENCE_CROPPED`, `REFERENCE_TOO_SMALL`,
`EXCESSIVE_PERSPECTIVE`, `HOMOGRAPHY_INVALID`, `HOMOGRAPHY_ILL_CONDITIONED`,
`REFERENCE_EDGE_EVIDENCE_INSUFFICIENT`, and `REFERENCE_EDGE_RESIDUAL_EXCESSIVE`. Existing safe
upload and `DATABASE_UNAVAILABLE` errors are reused. No response includes client filenames, local
paths, SQL, raw OpenCV exceptions, or stack traces.

## Measurement options

`GET /api/measurements/options` is database-independent and returns only safe configured policy:

- configured capture-setup ID, version, `orthogonal_rig` type, qualification state, and whether
  processing is enabled;
- the qualified object-size range, initial supported product domain, and physical requirements;
- required view order `top`, `front`, `side` and the fixed dimension-axis mapping;
- acceptable and warning disagreement thresholds; and
- the non-certified-metrology warning.

The default capture setup is `unconfigured` and unqualified, so processing is disabled. Clients
cannot create or select an arbitrary capture setup in Phase 3.

## Create or explicitly reprocess a measurement

`POST /api/scans/{scan_id}/measurements`

```json
{
  "request_id": "client UUID v4",
  "expected_calibration_profile_id": "active profile UUID",
  "expected_capture_setup_id": "configured server rig ID",
  "capture_contract_acknowledged": true,
  "reprocess_of_measurement_id": null
}
```

The operation is synchronous. A new request returns `201`; a replay of the same canonical request
returns the existing immutable attempt with `200`. `(scan_id, request_id)` is unique. Reusing the
request ID with changed fields returns `MEASUREMENT_REQUEST_CONFLICT`. Explicit reprocessing uses
this same endpoint with a new request UUID and the earlier attempt ID; it never overwrites the prior
result.

Processing is rejected before a claim when the scan is not ready, the capture setup is unqualified
or mismatched, no active profile exists, the expected profile is not active, acknowledgement is
missing, or the referenced reprocessing attempt does not belong to the scan. A claimed attempt is
persisted as `processing` and transitions once to `succeeded` or `failed`. Safe processing failures
are persisted as immutable failed attempts. An active non-expired lease is returned as processing;
an expired lease can be reclaimed atomically, and the stale worker cannot finalize it. The server
applies the configured lease to every claim and refuses startup configuration where that lease does
not exceed the synchronous processing deadline.

## Measurement history and evidence

- `GET /api/scans/{scan_id}/measurements?offset=0&limit=50` returns reverse-chronological immutable
  summaries.
- `GET /api/scans/{scan_id}/measurements/{measurement_id}` returns one processing, succeeded, or
  failed attempt.

A successful detail contains the frozen profile, capture-setup, and policy snapshots; source image
metadata and hashes; canonical top/front/side evidence; raw values for both contributing views;
reconciled length, width, and height; absolute and relative disagreement; reconciliation rule;
validation status; conservative uncertainty; engineering quality; warnings; and three preview
descriptors. Private source and preview storage keys are never public.

Staleness is computed on reads without changing the original result. Safe reasons include changed
active calibration profile, required source images, capture setup, processing version, algorithm
version, or measurement policy.

## Private measurement previews

`GET /api/scans/{scan_id}/measurements/{measurement_id}/previews/{view}` accepts only `top`,
`front`, or `side`. It returns the attempt-owned annotated `image/png` only for a succeeded attempt
after containment, ownership, media type, byte count, dimensions, and SHA-256 checks. Responses use
`Cache-Control: no-store`. A missing, changed, misplaced, or mismatched preview fails with a safe
structured response and never reveals the path or storage key.

## Measurement error boundary

Measurement failures use the existing structured shape: `code`, `message`, `recoverable`,
`suggested_action`, and optional safe `field`/`view`. The allowlisted Phase 3 codes and exact success
schemas are frozen in `docs/PHASE_3_CONTRACTS.md`. No measurement response exposes client
filenames, local paths, storage keys, SQL, tracebacks, OpenCV/Pillow exceptions, or internal model
data. A conservative uncertainty bound that reaches the associated positive dimension persists the
stable `MEASUREMENT_UNCERTAINTY_EXCESSIVE` failure. Phase 3 contains no AI model, queue, progress
stream, review, export, or LAN API.
