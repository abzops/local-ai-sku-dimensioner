import type {
  ArucoDictionary,
  CalibrationApiErrorResponse,
  CalibrationDefaults,
  CalibrationOptionsResponse,
  CalibrationPreview,
  CalibrationProfileCreateRequest,
  CalibrationProfileListResponse,
  CalibrationProfileResponse,
  CalibrationTestResponse,
  EdgeValues,
  MarkerEdgeQuality,
  Matrix3x3,
  OrderedCorner,
} from "../types/calibration";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const dictionaries: ArucoDictionary[] = ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_50"];
const cornerLabels = ["top_left", "top_right", "bottom_right", "bottom_left"] as const;
const errorViews = ["top", "front", "side", "additional"] as const;

export class CalibrationApiRequestError extends Error {
  readonly status: number;
  readonly payload: CalibrationApiErrorResponse;

  constructor(status: number, payload: CalibrationApiErrorResponse) {
    super(payload.message);
    this.name = "CalibrationApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && actual.every((key) => keys.includes(key));
}

function hasOnlyKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[] = [],
): boolean {
  const actual = Object.keys(value);
  return required.every((key) => key in value) && actual.every((key) => required.includes(key) || optional.includes(key));
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNumberInRange(value: unknown, minimum: number, maximum: number): value is number {
  return isFiniteNumber(value) && value >= minimum && value <= maximum;
}

function isInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value);
}

function isPositiveInteger(value: unknown): value is number {
  return isInteger(value) && value > 0;
}

function isNonNegativeInteger(value: unknown): value is number {
  return isInteger(value) && value >= 0;
}

function isDictionary(value: unknown): value is ArucoDictionary {
  return typeof value === "string" && dictionaries.includes(value as ArucoDictionary);
}

const profileInputKeys = [
  "name",
  "dictionary",
  "marker_id",
  "marker_size_mm",
  "minimum_marker_side_px",
  "maximum_perspective_ratio",
  "maximum_homography_condition_number",
  "maximum_marker_edge_residual_px",
  "rectified_pixels_per_mm",
] as const;

function isProfileInputFields(value: Record<string, unknown>): boolean {
  return (
    typeof value.name === "string" &&
    isDictionary(value.dictionary) &&
    isInteger(value.marker_id) && value.marker_id >= 0 && value.marker_id <= 49 &&
    isNumberInRange(value.marker_size_mm, 10, 300) &&
    isInteger(value.minimum_marker_side_px) && value.minimum_marker_side_px >= 24 && value.minimum_marker_side_px <= 4096 &&
    isNumberInRange(value.maximum_perspective_ratio, 1, 10) &&
    isNumberInRange(value.maximum_homography_condition_number, 10, 1_000_000_000_000) &&
    isNumberInRange(value.maximum_marker_edge_residual_px, 0.1, 20) &&
    isNumberInRange(value.rectified_pixels_per_mm, 1, 6)
  );
}

function isDefaults(value: unknown): value is CalibrationDefaults {
  return isRecord(value) && hasExactKeys(value, profileInputKeys.filter((key) => key !== "name")) && isProfileInputFields({ name: "defaults", ...value });
}

function isOptions(value: unknown): value is CalibrationOptionsResponse {
  if (!isRecord(value) || !hasExactKeys(value, ["dictionaries", "marker_id_min", "marker_id_max", "border_bits", "defaults"])) return false;
  return Array.isArray(value.dictionaries) && value.dictionaries.length === dictionaries.length && value.dictionaries.every((entry, index) => entry === dictionaries[index]) && value.marker_id_min === 0 && value.marker_id_max === 49 && value.border_bits === 1 && isDefaults(value.defaults);
}

function isProfile(value: unknown): value is CalibrationProfileResponse {
  if (!isRecord(value) || !hasExactKeys(value, ["id", ...profileInputKeys, "border_bits", "is_active", "created_at", "activated_at"])) return false;
  return typeof value.id === "string" && isProfileInputFields(value) && value.border_bits === 1 && typeof value.is_active === "boolean" && typeof value.created_at === "string" && (typeof value.activated_at === "string" || value.activated_at === null);
}

function isProfileList(value: unknown): value is CalibrationProfileListResponse {
  return isRecord(value) && hasExactKeys(value, ["items", "total"]) && Array.isArray(value.items) && value.items.every(isProfile) && isNonNegativeInteger(value.total);
}

function isOrderedCorner(value: unknown, index: number): value is OrderedCorner {
  return isRecord(value) && hasExactKeys(value, ["label", "x_px", "y_px"]) && value.label === cornerLabels[index] && isFiniteNumber(value.x_px) && isFiniteNumber(value.y_px);
}

function isEdges(value: unknown): value is EdgeValues {
  return isRecord(value) && hasExactKeys(value, ["top", "right", "bottom", "left"]) && isNumberInRange(value.top, 0, Number.MAX_VALUE) && isNumberInRange(value.right, 0, Number.MAX_VALUE) && isNumberInRange(value.bottom, 0, Number.MAX_VALUE) && isNumberInRange(value.left, 0, Number.MAX_VALUE);
}

function isMatrix(value: unknown): value is Matrix3x3 {
  return Array.isArray(value) && value.length === 3 && value.every((row) => Array.isArray(row) && row.length === 3 && row.every(isFiniteNumber));
}

function isQuality(value: unknown): value is MarkerEdgeQuality {
  if (!isRecord(value) || !hasExactKeys(value, ["metric_name", "description", "rms_px", "maximum_px", "sample_count", "per_edge_rms_px", "threshold_px", "valid"])) return false;
  return value.metric_name === "marker_edge_localization_residual" && value.description === "Sampled marker-border localization residual in image pixels." && isNumberInRange(value.rms_px, 0, Number.MAX_VALUE) && isNumberInRange(value.maximum_px, value.rms_px, Number.MAX_VALUE) && isPositiveInteger(value.sample_count) && isEdges(value.per_edge_rms_px) && isNumberInRange(value.threshold_px, 0.1, 20) && value.valid === true;
}

function isBase64(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length % 4 === 0 && /^[A-Za-z0-9+/]*={0,2}$/.test(value);
}

function isPreview(value: unknown): value is CalibrationPreview {
  return isRecord(value) && hasExactKeys(value, ["media_type", "width_px", "height_px", "data_base64"]) && value.media_type === "image/png" && isPositiveInteger(value.width_px) && isPositiveInteger(value.height_px) && isBase64(value.data_base64);
}

function isCalibrationTest(value: unknown): value is CalibrationTestResponse {
  if (!isRecord(value) || !hasExactKeys(value, ["profile_id", "dictionary", "marker_id", "marker_size_mm", "ordered_corners", "orientation_degrees", "edge_lengths_px", "perspective_ratio", "image_to_marker_mm", "marker_mm_to_image", "homography_condition_number", "rectified_width_px", "rectified_height_px", "rectified_pixels_per_mm", "marker_edge_quality", "annotated_preview", "rectified_preview"])) return false;
  return typeof value.profile_id === "string" && isDictionary(value.dictionary) && isInteger(value.marker_id) && value.marker_id >= 0 && value.marker_id <= 49 && isNumberInRange(value.marker_size_mm, 10, 300) && Array.isArray(value.ordered_corners) && value.ordered_corners.length === 4 && value.ordered_corners.every((corner, index) => isOrderedCorner(corner, index)) && isFiniteNumber(value.orientation_degrees) && value.orientation_degrees >= -180 && value.orientation_degrees < 180 && isEdges(value.edge_lengths_px) && isNumberInRange(value.perspective_ratio, 1, 10) && isMatrix(value.image_to_marker_mm) && isMatrix(value.marker_mm_to_image) && isNumberInRange(value.homography_condition_number, 1, Number.MAX_VALUE) && isPositiveInteger(value.rectified_width_px) && value.rectified_width_px <= 1800 && isPositiveInteger(value.rectified_height_px) && value.rectified_height_px <= 1800 && isNumberInRange(value.rectified_pixels_per_mm, 1, 6) && isQuality(value.marker_edge_quality) && isPreview(value.annotated_preview) && value.annotated_preview.width_px <= 1280 && value.annotated_preview.height_px <= 1280 && isPreview(value.rectified_preview) && value.rectified_preview.width_px === value.rectified_width_px && value.rectified_preview.height_px === value.rectified_height_px;
}

function isApiError(value: unknown): value is CalibrationApiErrorResponse {
  if (!isRecord(value) || !hasOnlyKeys(value, ["code", "message", "recoverable", "suggested_action"], ["field", "view"])) return false;
  return typeof value.code === "string" && typeof value.message === "string" && typeof value.recoverable === "boolean" && typeof value.suggested_action === "string" && (value.field === undefined || typeof value.field === "string") && (value.view === undefined || errorViews.includes(value.view as (typeof errorViews)[number]));
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

function fallbackError(status: number): CalibrationApiErrorResponse {
  return { code: "REQUEST_FAILED", message: `The local API request failed with status ${status}.`, recoverable: status >= 500, suggested_action: "Check the local service and try again." };
}

async function requestJson<T>(path: string, init: RequestInit, validator: (value: unknown) => value is T): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers: { Accept: "application/json", ...init.headers } });
  const payload = await readJson(response);
  if (!response.ok) throw new CalibrationApiRequestError(response.status, isApiError(payload) ? payload : fallbackError(response.status));
  if (!validator(payload)) throw new CalibrationApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned an invalid calibration response.", recoverable: true, suggested_action: "Retry the request. If it continues to fail, restart the local service." });
  return payload;
}

function profilePath(profileId: string): string {
  return `/calibration/profiles/${encodeURIComponent(profileId)}`;
}

export function getCalibrationOptions(signal?: AbortSignal): Promise<CalibrationOptionsResponse> {
  return requestJson("/calibration/options", { method: "GET", signal }, isOptions);
}

export function createCalibrationProfile(request: CalibrationProfileCreateRequest, signal?: AbortSignal): Promise<CalibrationProfileResponse> {
  return requestJson("/calibration/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal }, isProfile);
}

export function listCalibrationProfiles(signal?: AbortSignal): Promise<CalibrationProfileListResponse> {
  return requestJson("/calibration/profiles", { method: "GET", signal }, isProfileList);
}

export function getCalibrationProfile(profileId: string, signal?: AbortSignal): Promise<CalibrationProfileResponse> {
  return requestJson(profilePath(profileId), { method: "GET", signal }, isProfile);
}

export function activateCalibrationProfile(profileId: string, signal?: AbortSignal): Promise<CalibrationProfileResponse> {
  return requestJson(`${profilePath(profileId)}/activate`, { method: "POST", signal }, isProfile);
}

export async function getCalibrationMarkerSvg(profileId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${apiBaseUrl}${profilePath(profileId)}/marker.svg`, { method: "GET", headers: { Accept: "image/svg+xml" }, signal });
  if (!response.ok) {
    const payload = await readJson(response);
    throw new CalibrationApiRequestError(response.status, isApiError(payload) ? payload : fallbackError(response.status));
  }
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "image/svg+xml") throw new CalibrationApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned an invalid marker document.", recoverable: true, suggested_action: "Retry the request. If it continues to fail, restart the local service." });
  return response.blob();
}

export function buildCalibrationTestFormData(image: File): FormData {
  const formData = new FormData();
  formData.append("image", image);
  return formData;
}

export function testCalibrationProfile(profileId: string, image: File, signal?: AbortSignal): Promise<CalibrationTestResponse> {
  return requestJson(`${profilePath(profileId)}/test`, { method: "POST", body: buildCalibrationTestFormData(image), signal }, isCalibrationTest);
}

export function asCalibrationApiError(error: unknown): CalibrationApiErrorResponse {
  if (error instanceof CalibrationApiRequestError) return error.payload;
  return { code: "NETWORK_ERROR", message: "The local service could not be reached.", recoverable: true, suggested_action: "Confirm the local service is running and try again." };
}
