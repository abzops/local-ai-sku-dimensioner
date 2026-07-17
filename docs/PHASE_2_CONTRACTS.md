# Phase 2 Frozen Contracts

These contracts were frozen before parallel implementation. Implementation agents may build against
them but must not independently add, remove, or rename public fields, routes, domain values, or error
codes.

## Phase boundary

Phase 2 calibrates and tests a printed ArUco reference marker. All returned geometry is restricted to
the marker plane. It does not locate a product, calculate product dimensions, process a scan, persist
test images or previews, or introduce AI, background work, progress streaming, review, export, or LAN
behavior.

## Domain values

- `ArucoDictionary`: `DICT_4X4_50`, `DICT_5X5_50`, or `DICT_6X6_50` only.
- `marker_id`: integer from 0 through 49 inclusive.
- `CornerLabel`, in canonical marker order: `top_left`, `top_right`, `bottom_right`,
  `bottom_left`. Labels describe the printed marker coordinate system, not the visually highest image
  point after rotation.
- `EdgeName`: `top`, `right`, `bottom`, `left`.
- `border_bits` is fixed at `1` in Phase 2.
- Marker size is the physical black-marker square side, in millimetres. Page margins are not included.

## Calibration profile persistence

Table `calibration_profiles` contains:

- `id`: server-generated UUIDv4 string, primary key.
- `name`: stripped string, 1 through 100 characters, unique.
- `dictionary`: approved `ArucoDictionary` value.
- `marker_id`: integer, 0 through 49.
- `marker_size_mm`: finite number, 10 through 300.
- `border_bits`: integer, fixed at 1.
- `minimum_marker_side_px`: integer, 24 through 4096.
- `maximum_perspective_ratio`: finite number, 1.0 through 10.0.
- `maximum_homography_condition_number`: finite number, 10 through 1e12.
- `maximum_marker_edge_residual_px`: finite number, 0.1 through 20.0.
- `rectified_pixels_per_mm`: finite number, 1.0 through 6.0.
- `is_active`: boolean, managed only by activation.
- `created_at`: UTC timestamp.
- `activated_at`: nullable UTC timestamp, managed only by activation.

User-configured profile fields are immutable after creation. There is no update or delete endpoint.
Activation is the only mutation. A SQLite partial unique index permits at most one row where
`is_active = 1`.

Activation uses one transaction: load and validate the selected row, deactivate the current active
row, flush, activate the selected row and set `activated_at`, then commit once. Any failure rolls the
whole switch back. Concurrent attempts may serialize or return the sanitized database-unavailable
error, but must never leave multiple active rows.

## Profile HTTP schemas

`CalibrationProfileCreateRequest` accepts exactly:

```json
{
  "name": "Warehouse 100 mm",
  "dictionary": "DICT_4X4_50",
  "marker_id": 0,
  "marker_size_mm": 100.0,
  "minimum_marker_side_px": 64,
  "maximum_perspective_ratio": 3.0,
  "maximum_homography_condition_number": 1000000.0,
  "maximum_marker_edge_residual_px": 2.0,
  "rectified_pixels_per_mm": 4.0
}
```

Unknown fields are rejected. `CalibrationProfileResponse` returns all persisted fields listed above.
`CalibrationProfileListResponse` is `{ "items": [...], "total": 0 }`, ordered active first and then
newest creation time and ID. Create returns `201`; read and activate return `200`.

`CalibrationOptionsResponse` is database-independent and returns:

```json
{
  "dictionaries": ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_50"],
  "marker_id_min": 0,
  "marker_id_max": 49,
  "border_bits": 1,
  "defaults": {
    "dictionary": "DICT_4X4_50",
    "marker_id": 0,
    "marker_size_mm": 100.0,
    "minimum_marker_side_px": 64,
    "maximum_perspective_ratio": 3.0,
    "maximum_homography_condition_number": 1000000.0,
    "maximum_marker_edge_residual_px": 2.0,
    "rectified_pixels_per_mm": 4.0
  }
}
```

## Routes

- `GET /api/calibration/options`
- `POST /api/calibration/profiles`
- `GET /api/calibration/profiles`
- `GET /api/calibration/profiles/{profile_id}`
- `POST /api/calibration/profiles/{profile_id}/activate`
- `GET /api/calibration/profiles/{profile_id}/marker.svg`
- `POST /api/calibration/profiles/{profile_id}/test`

The SVG route returns `image/svg+xml` with a server-generated attachment filename. The test route
accepts `multipart/form-data` with exactly one file field named `image`. Repeated `image`, any other
field, non-file fields, or an absent image are rejected. The route uses existing Phase 1 extension,
MIME, byte-size, decoded-format, animation, decoded-pixel, EXIF-orientation, and minimum-resolution
validation before OpenCV analysis.

## Marker SVG

The SVG is deterministic UTF-8 text. Its root contains `width="<marker_size_mm>mm"`,
`height="<marker_size_mm>mm"`, and a square `viewBox`. It uses only local SVG geometry, contains no
script, external reference, metadata-derived scale, or embedded path, and represents the selected
OpenCV dictionary, ID, and one-bit border exactly. Browsers may download or preview it; printing must
use 100% or actual size with fit-to-page scaling disabled. The operator must physically verify the
printed black-square side with a ruler.

## Detection and geometry interfaces

The deterministic vision entry point is conceptually:

```text
analyze_marker_image(oriented_image_bgr, MarkerProfileSpec) -> MarkerAnalysisResult
generate_marker_svg(MarkerProfileSpec) -> UTF-8 SVG text
```

The engine detects all recognized markers in the configured dictionary but accepts exactly one
occurrence of the configured ID and no additional recognized marker. It never accepts client-provided
corners. `MarkerAnalysisResult` contains:

- configured dictionary and detected marker ID;
- raw canonical ordered corners as four `{label, x_px, y_px}` records;
- clockwise orientation in image degrees from canonical top-left to top-right, normalized to
  `[-180, 180)`;
- edge lengths in pixels for top, right, bottom, and left;
- longest/shortest edge perspective ratio;
- `image_to_marker_mm` and `marker_mm_to_image` finite 3 by 3 matrices;
- normalized homography condition number;
- rectified output width, height, and pixels per millimetre;
- marker-edge localization evidence;
- bounded annotated and rectified PNG previews.

Marker millimetre coordinates are `(0,0)`, `(size,0)`, `(size,size)`, `(0,size)` in canonical corner
order. These planar coordinates and matrices must not be applied to any product dimensions in Phase 2.

## Marker-edge localization quality

The independent border metric is named `marker_edge_localization_residual`. It measures sampled image
edge evidence relative to the four fitted marker border edges. It is not described as certified camera
reprojection error and is not a camera-calibration result.

The evidence response is exactly:

```json
{
  "metric_name": "marker_edge_localization_residual",
  "description": "Sampled marker-border localization residual in image pixels.",
  "rms_px": 0.6,
  "maximum_px": 1.2,
  "sample_count": 64,
  "per_edge_rms_px": {"top": 0.5, "right": 0.7, "bottom": 0.6, "left": 0.6},
  "threshold_px": 2.0,
  "valid": true
}
```

All values are finite. Every edge must contribute evidence. Insufficient evidence fails; evidence
above the profile threshold fails and is never returned as valid.

## Calibration test response

`CalibrationTestResponse` is:

```json
{
  "profile_id": "UUID",
  "dictionary": "DICT_4X4_50",
  "marker_id": 0,
  "marker_size_mm": 100.0,
  "ordered_corners": [
    {"label": "top_left", "x_px": 10.0, "y_px": 10.0},
    {"label": "top_right", "x_px": 110.0, "y_px": 10.0},
    {"label": "bottom_right", "x_px": 110.0, "y_px": 110.0},
    {"label": "bottom_left", "x_px": 10.0, "y_px": 110.0}
  ],
  "orientation_degrees": 0.0,
  "edge_lengths_px": {"top": 100.0, "right": 100.0, "bottom": 100.0, "left": 100.0},
  "perspective_ratio": 1.0,
  "image_to_marker_mm": [[1.0, 0.0, -10.0], [0.0, 1.0, -10.0], [0.0, 0.0, 1.0]],
  "marker_mm_to_image": [[1.0, 0.0, 10.0], [0.0, 1.0, 10.0], [0.0, 0.0, 1.0]],
  "homography_condition_number": 1.0,
  "rectified_width_px": 400,
  "rectified_height_px": 400,
  "rectified_pixels_per_mm": 4.0,
  "marker_edge_quality": {},
  "annotated_preview": {
    "media_type": "image/png",
    "width_px": 1280,
    "height_px": 960,
    "data_base64": "..."
  },
  "rectified_preview": {
    "media_type": "image/png",
    "width_px": 400,
    "height_px": 400,
    "data_base64": "..."
  }
}
```

The abbreviated quality object above has the exact full shape in the preceding section. Preview
long edges are at most 1280 pixels, rectified edges at most 1800 pixels, and decoded PNG payloads at
most 2 MiB each. Test images and previews exist only in request memory and response memory and are
never written to the runtime filesystem or database. The rectified preview must preserve the
reported rectified geometry; if lossless encoding cannot fit the 2 MiB ceiling at those dimensions,
the request fails safely with `HOMOGRAPHY_INVALID` instead of rescaling the preview.

## Validation order and safe failures

1. Enforce bounded multipart request size, exactly one file, and the `image` field name.
2. Apply the complete Phase 1 image validation chain.
3. Decode the already validated, orientation-corrected bytes into OpenCV memory.
4. Detect all recognized markers in the configured dictionary.
5. Reject no marker, wrong ID, duplicate expected ID, or any additional recognized marker.
6. Reject non-finite, repeated, self-crossing, non-convex, cropped, or otherwise invalid corners.
7. Reject marker edges below `minimum_marker_side_px`.
8. Reject perspective ratio above the profile maximum.
9. Reject non-finite, singular, non-invertible, or over-threshold-conditioned homography.
10. Collect independent edge evidence; reject missing per-edge samples.
11. Reject marker-edge residual above its profile threshold.
12. Produce bounded previews and the success response.

Stable Phase 2 error codes are `CALIBRATION_PROFILE_NOT_FOUND`,
`CALIBRATION_PROFILE_NAME_CONFLICT`, `REFERENCE_NOT_DETECTED`, `REFERENCE_WRONG_ID`,
`REFERENCE_AMBIGUOUS`, `REFERENCE_CORNERS_INVALID`, `REFERENCE_CROPPED`, `REFERENCE_TOO_SMALL`,
`EXCESSIVE_PERSPECTIVE`, `HOMOGRAPHY_INVALID`, `HOMOGRAPHY_ILL_CONDITIONED`,
`REFERENCE_EDGE_EVIDENCE_INSUFFICIENT`, and `REFERENCE_EDGE_RESIDUAL_EXCESSIVE`. Existing upload,
request-validation, and `DATABASE_UNAVAILABLE` errors are reused.

All errors use the existing `RequestErrorResponse` fields: `code`, `message`, `recoverable`,
`suggested_action`, and optional `field`/`view`. Calibration failures may set `field="image"` but do
not set a scan image `view`. Responses never contain a client filename, local path, SQL, stack trace,
raw OpenCV exception text, or internal numeric diagnostics not named by the public contract.

## Frontend contract

`frontend/src/types/calibration.ts` mirrors every public request and response above. The API client
validates unknown JSON recursively, including enum values, finite numeric values, four corner labels
in exact order, 3 by 3 matrices, edge records, quality evidence, and PNG preview media type/base64.
The Calibration page supports profile create/list/read/activate, SVG preview/download, actual-size
printing instructions, a single `accept="image/jpeg,image/png,image/webp"` image input with
`capture="environment"`, retry of the same idempotent test request while its profile remains
selected, and complete profile-labelled evidence display. Selecting another profile clears prior
evidence, errors, and retry state.
It contains no product or measurement controls.
