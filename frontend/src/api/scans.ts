import type {
  ApiErrorResponse,
  ImageView,
  ScanCreateRequest,
  ScanDetailResponse,
  ScanImageResponse,
  ScanListResponse,
  ScanStatus,
  ScanSummaryResponse,
  UploadBatchResponse,
} from "../types/scans";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const scanStatuses: ScanStatus[] = ["draft", "images_uploaded", "ready_for_processing"];
const imageViews: ImageView[] = ["top", "front", "side", "additional"];
const mediaTypes: ScanImageResponse["media_type"][] = [
  "image/jpeg",
  "image/png",
  "image/webp",
];

export interface ScanListOptions {
  offset?: number;
  limit?: number;
}

export interface UploadScanImagesInput {
  top?: File;
  front?: File;
  side?: File;
  additional?: File[];
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly payload: ApiErrorResponse;

  constructor(status: number, payload: ApiErrorResponse) {
    super(payload.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isScanStatus(value: unknown): value is ScanStatus {
  return typeof value === "string" && scanStatuses.includes(value as ScanStatus);
}

function isImageView(value: unknown): value is ImageView {
  return typeof value === "string" && imageViews.includes(value as ImageView);
}

function isRequiredView(value: unknown): value is Exclude<ImageView, "additional"> {
  return value === "top" || value === "front" || value === "side";
}

function isScanImage(value: unknown): value is ScanImageResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    isImageView(value.view_type) &&
    typeof value.media_type === "string" &&
    mediaTypes.includes(value.media_type as ScanImageResponse["media_type"]) &&
    isPositiveInteger(value.size_bytes) &&
    isPositiveInteger(value.width_px) &&
    isPositiveInteger(value.height_px) &&
    typeof value.created_at === "string"
  );
}

function isScanBase(value: Record<string, unknown>): boolean {
  return (
    typeof value.id === "string" &&
    typeof value.sku === "string" &&
    isNullableString(value.barcode) &&
    isNullableString(value.product_name) &&
    isScanStatus(value.status) &&
    Array.isArray(value.missing_required_views) &&
    value.missing_required_views.every(isRequiredView) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isScanSummary(value: unknown): value is ScanSummaryResponse {
  return isRecord(value) && isScanBase(value) && isNonNegativeInteger(value.image_count);
}

function isScanDetail(value: unknown): value is ScanDetailResponse {
  return (
    isRecord(value) &&
    isScanBase(value) &&
    Array.isArray(value.images) &&
    value.images.every(isScanImage)
  );
}

function isScanList(value: unknown): value is ScanListResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isScanSummary) &&
    isNonNegativeInteger(value.total) &&
    isNonNegativeInteger(value.offset) &&
    isPositiveInteger(value.limit)
  );
}

function isUploadBatch(value: unknown): value is UploadBatchResponse {
  return (
    isRecord(value) &&
    isScanDetail(value.scan) &&
    Array.isArray(value.uploaded_images) &&
    value.uploaded_images.every(isScanImage)
  );
}

function isApiError(value: unknown): value is ApiErrorResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.recoverable === "boolean" &&
    typeof value.suggested_action === "string" &&
    (value.field === undefined || typeof value.field === "string") &&
    (value.view === undefined || isImageView(value.view))
  );
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

function fallbackError(status: number): ApiErrorResponse {
  return {
    code: "REQUEST_FAILED",
    message: `The local API request failed with status ${status}.`,
    recoverable: status >= 500,
    suggested_action: "Check the local service and try again.",
  };
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  validator: (value: unknown) => value is T,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
  });
  const payload = await readJson(response);

  if (!response.ok) {
    throw new ApiRequestError(response.status, isApiError(payload) ? payload : fallbackError(response.status));
  }
  if (!validator(payload)) {
    throw new ApiRequestError(502, {
      code: "INVALID_API_RESPONSE",
      message: "The local API returned an invalid response.",
      recoverable: true,
      suggested_action: "Retry the request. If it continues to fail, restart the local service.",
    });
  }
  return payload;
}

function scanPath(scanId: string): string {
  return `/scans/${encodeURIComponent(scanId)}`;
}

export function createScan(
  request: ScanCreateRequest,
  signal?: AbortSignal,
): Promise<ScanDetailResponse> {
  return requestJson(
    "/scans",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
    isScanDetail,
  );
}

export function getScan(scanId: string, signal?: AbortSignal): Promise<ScanDetailResponse> {
  return requestJson(scanPath(scanId), { method: "GET", signal }, isScanDetail);
}

export function listScans(
  options: ScanListOptions = {},
  signal?: AbortSignal,
): Promise<ScanListResponse> {
  const params = new URLSearchParams({
    offset: String(options.offset ?? 0),
    limit: String(options.limit ?? 50),
  });
  return requestJson(`/scans?${params.toString()}`, { method: "GET", signal }, isScanList);
}

export function buildUploadFormData(input: UploadScanImagesInput): FormData {
  const formData = new FormData();
  if (input.top) formData.append("top", input.top);
  if (input.front) formData.append("front", input.front);
  if (input.side) formData.append("side", input.side);
  input.additional?.forEach((file) => formData.append("additional", file));
  return formData;
}

export function uploadScanImages(
  scanId: string,
  input: UploadScanImagesInput,
  signal?: AbortSignal,
): Promise<UploadBatchResponse> {
  return requestJson(
    `${scanPath(scanId)}/images`,
    { method: "POST", body: buildUploadFormData(input), signal },
    isUploadBatch,
  );
}

export function asApiError(error: unknown): ApiErrorResponse {
  if (error instanceof ApiRequestError) {
    return error.payload;
  }
  return {
    code: "NETWORK_ERROR",
    message: "The local service could not be reached.",
    recoverable: true,
    suggested_action: "Confirm the local service is running and try again.",
  };
}
