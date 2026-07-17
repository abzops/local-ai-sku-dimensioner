# Phase 1 API

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
