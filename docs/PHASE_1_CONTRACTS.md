# Phase 1 Frozen Contracts

These contracts are frozen before parallel implementation. Sub-agents may implement against them
but must not independently change them.

## Domain values

- `ScanStatus`: `draft`, `images_uploaded`, `ready_for_processing` only.
- `ImageView`: `top`, `front`, `side`, `additional` only.
- Required views are ordered `top`, `front`, `side`.

## Database fields

- `scans`: `id`, `sku`, `barcode`, `product_name`, `status`, `created_at`, `updated_at`.
- `scan_images`: `id`, `scan_id`, `view_type`, `storage_key`, `media_type`,
  `file_extension`, `size_bytes`, `width_px`, `height_px`, `created_at`.
- IDs are server-generated UUIDv4 strings. Client filenames are not stored.
- Required views are unique per scan; multiple `additional` rows are allowed.

## Public schemas

- `ScanImageResponse`: image identity, view, canonical media type, byte size, decoded dimensions,
  and creation time. It never contains a filename or path.
- `ScanSummaryResponse`: scan metadata, status, image count, ordered missing required views, and
  timestamps.
- `ScanDetailResponse`: scan summary fields plus `images`, without `image_count`.
- `ScanListResponse`: `items`, `total`, `offset`, `limit`.
- `UploadBatchResponse`: the updated scan plus only the images inserted by that batch.

## Upload interface

- HTTP converts multipart fields into ordered `UploadInput` values.
- Validation produces `ValidatedUpload` values without writing files.
- Storage stages one operation into `StagedUploadBatch`, atomically finalizes it to
  `FinalizedUploadBatch`, and can remove only that operation's exact directory.
- Database persistence consumes `FinalizedImage` metadata in one SQLAlchemy transaction.
- Public image lists are rendered in top, front, side, then additional order. Additional images use
  stable creation-time and server-ID ordering.

## Errors

The existing health `ErrorResponse` remains exactly four fields. Phase 1 request errors extend it
with optional `field` and `view`; null optional fields are omitted. No error contains client
filenames, local paths, raw exceptions, or stack traces.

Expected request error codes include `INVALID_REQUEST`, `SCAN_NOT_FOUND`, `NO_FILES_PROVIDED`,
`UPLOAD_LIMIT_EXCEEDED`, `ADDITIONAL_IMAGE_LIMIT_EXCEEDED`, `DUPLICATE_VIEW`,
`UNSUPPORTED_FILE_EXTENSION`, `UNSUPPORTED_MEDIA_TYPE`, `IMAGE_FORMAT_MISMATCH`,
`FILE_TOO_LARGE`, `IMAGE_DECODE_FAILED`, `IMAGE_PIXEL_LIMIT_EXCEEDED`, `IMAGE_TOO_SMALL`,
`ANIMATED_IMAGE_NOT_SUPPORTED`, `STORAGE_UNAVAILABLE`, and `DATABASE_UNAVAILABLE`.
Parser-boundary errors additionally include `MALFORMED_MULTIPART` and `INVALID_UPLOAD_FIELD`.

## Frontend

`frontend/src/types/scans.ts` is the TypeScript mirror of the public schemas. Frontend code must
validate unknown JSON before treating it as these types.
