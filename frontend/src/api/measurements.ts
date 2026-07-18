import type {
  DimensionName,
  DimensionResultResponse,
  ForegroundEvidenceResponse,
  MarkerEvidenceResponse,
  MeasurementApiErrorResponse,
  MeasurementAttemptDetailResponse,
  MeasurementAttemptListResponse,
  MeasurementAttemptSummaryResponse,
  MeasurementFailure,
  MeasurementOptionsResponse,
  MeasurementPolicySnapshotResponse,
  MeasurementProcessRequest,
  MeasurementSourceResponse,
  MeasurementStaleReason,
  MeasurementView,
  PerViewMeasurementResponse,
  PreviewDescriptorResponse,
  RectificationEvidenceResponse,
  ViewQualityEvidenceResponse,
  ViewUncertaintyEvidenceResponse,
} from "../types/measurements";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const views = ["top", "front", "side"] as const;
const dimensions = ["length", "width", "height"] as const;
const staleReasons: MeasurementStaleReason[] = [
  "active_calibration_profile_changed", "source_images_changed", "capture_setup_changed",
  "processing_version_changed", "algorithm_version_changed", "measurement_policy_changed",
];
const dictionaries = ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_50"] as const;
const cornerLabels = ["top_left", "top_right", "bottom_right", "bottom_left"] as const;
const pairs: Record<DimensionName, [MeasurementView, MeasurementView]> = {
  length: ["top", "side"], width: ["top", "front"], height: ["front", "side"],
};
const viewDimensions: Record<MeasurementView, [DimensionName, DimensionName]> = {
  top: ["length", "width"], front: ["width", "height"], side: ["length", "height"],
};
const summaryKeys = [
  "id", "scan_id", "request_id", "reprocess_of_measurement_id", "status",
  "calibration_profile_id", "calibration_profile_name", "capture_setup_id",
  "capture_setup_version", "processing_version", "algorithm_version", "length_mm",
  "width_mm", "height_mm", "failure_code", "is_stale", "stale_reasons", "created_at",
  "completed_at",
] as const;

export class MeasurementApiRequestError extends Error {
  readonly status: number;
  readonly payload: MeasurementApiErrorResponse;
  readonly outcomeUncertain: boolean;

  constructor(status: number, payload: MeasurementApiErrorResponse, outcomeUncertain = false) {
    super(payload.message);
    this.name = "MeasurementApiRequestError";
    this.status = status;
    this.payload = payload;
    this.outcomeUncertain = outcomeUncertain;
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function exact(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && actual.every((key) => keys.includes(key));
}
function only(value: Record<string, unknown>, required: readonly string[], optional: readonly string[] = []): boolean {
  const actual = Object.keys(value);
  return required.every((key) => key in value) && actual.every((key) => required.includes(key) || optional.includes(key));
}
function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function positive(value: unknown): value is number { return finite(value) && value > 0; }
function nonnegative(value: unknown): value is number { return finite(value) && value >= 0; }
function integer(value: unknown): value is number { return finite(value) && Number.isInteger(value); }
function unit(value: unknown): value is number { return finite(value) && value >= 0 && value <= 1; }
function safeText(value: unknown, maximum = 500): value is string { return typeof value === "string" && value.length > 0 && value.length <= maximum; }
function captureSetupVersion(value: unknown): value is string {
  return safeText(value, 50) && value.trim() === value;
}
function uuid4(value: unknown): value is string { return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value); }
function timestamp(value: unknown): value is string { return typeof value === "string" && Number.isFinite(Date.parse(value)); }
function sha(value: unknown): value is string { return typeof value === "string" && /^[0-9a-f]{64}$/.test(value); }
function isView(value: unknown): value is MeasurementView { return typeof value === "string" && views.includes(value as MeasurementView); }
function ordered<T extends string>(value: unknown, expected: readonly T[]): value is T[] {
  return Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index]);
}
function safeStrings(value: unknown): value is string[] { return Array.isArray(value) && value.every((item) => safeText(item)); }
function matrix(value: unknown): boolean { return Array.isArray(value) && value.length === 3 && value.every((row) => Array.isArray(row) && row.length === 3 && row.every(finite)); }
function keyedNumbers(value: unknown, keys: readonly string[], validator: (item: unknown) => boolean): boolean {
  return record(value) && exact(value, keys) && keys.every((key) => validator(value[key]));
}

function isError(value: unknown): value is MeasurementApiErrorResponse {
  return record(value) && only(value, ["code", "message", "recoverable", "suggested_action"], ["field", "view"])
    && safeText(value.code, 100) && safeText(value.message) && typeof value.recoverable === "boolean"
    && safeText(value.suggested_action) && (value.field === undefined || safeText(value.field, 100))
    && (value.view === undefined || isView(value.view));
}

function isOptions(value: unknown): value is MeasurementOptionsResponse {
  if (!record(value) || !exact(value, ["capture_setup", "required_views", "dimension_axis_mapping", "disagreement_thresholds", "non_certified_metrology_warning"])) return false;
  const capture = value.capture_setup;
  const mapping = value.dimension_axis_mapping;
  const thresholds = value.disagreement_thresholds;
  return record(capture) && exact(capture, ["id", "version", "type", "qualified", "processing_enabled", "minimum_object_mm", "maximum_object_mm", "supported_product_domain", "requirements"])
    && safeText(capture.id, 100) && captureSetupVersion(capture.version) && capture.type === "orthogonal_rig"
    && typeof capture.qualified === "boolean" && typeof capture.processing_enabled === "boolean"
    && capture.processing_enabled === capture.qualified && positive(capture.minimum_object_mm)
    && positive(capture.maximum_object_mm) && capture.minimum_object_mm < capture.maximum_object_mm
    && safeStrings(capture.supported_product_domain) && safeStrings(capture.requirements)
    && ordered(value.required_views, views) && record(mapping) && exact(mapping, views)
    && ordered(mapping.top, ["length", "width"]) && ordered(mapping.front, ["width", "height"])
    && ordered(mapping.side, ["length", "height"]) && record(thresholds)
    && exact(thresholds, ["acceptable_absolute_mm", "acceptable_relative_percent", "warning_absolute_mm", "warning_relative_percent"])
    && positive(thresholds.acceptable_absolute_mm) && positive(thresholds.acceptable_relative_percent)
    && positive(thresholds.warning_absolute_mm) && positive(thresholds.warning_relative_percent)
    && thresholds.acceptable_absolute_mm <= thresholds.warning_absolute_mm
    && thresholds.acceptable_relative_percent <= thresholds.warning_relative_percent
    && value.non_certified_metrology_warning === "Measurements are deterministic engineering estimates from a physically qualified local rig, not certified metrology.";
}

function isProfile(value: unknown): boolean {
  const keys = ["id", "name", "dictionary", "marker_id", "marker_size_mm", "border_bits", "minimum_marker_side_px", "maximum_perspective_ratio", "maximum_homography_condition_number", "maximum_marker_edge_residual_px", "rectified_pixels_per_mm", "is_active", "created_at", "activated_at"];
  return record(value) && exact(value, keys) && uuid4(value.id) && safeText(value.name, 100)
    && dictionaries.includes(value.dictionary as (typeof dictionaries)[number]) && integer(value.marker_id) && value.marker_id >= 0 && value.marker_id <= 49
    && finite(value.marker_size_mm) && value.marker_size_mm >= 10 && value.marker_size_mm <= 300 && value.border_bits === 1
    && integer(value.minimum_marker_side_px) && value.minimum_marker_side_px >= 24 && value.minimum_marker_side_px <= 4096
    && finite(value.maximum_perspective_ratio) && value.maximum_perspective_ratio >= 1 && value.maximum_perspective_ratio <= 10
    && finite(value.maximum_homography_condition_number) && value.maximum_homography_condition_number >= 10
    && finite(value.maximum_marker_edge_residual_px) && value.maximum_marker_edge_residual_px >= 0.1 && value.maximum_marker_edge_residual_px <= 20
    && finite(value.rectified_pixels_per_mm) && value.rectified_pixels_per_mm >= 1 && value.rectified_pixels_per_mm <= 6
    && typeof value.is_active === "boolean" && timestamp(value.created_at) && (value.activated_at === null || timestamp(value.activated_at));
}

function isSource(value: unknown, expectedView?: MeasurementView): value is MeasurementSourceResponse {
  return record(value) && exact(value, ["view", "scan_image_id", "original_sha256", "oriented_pixel_sha256", "media_type", "size_bytes", "width_px", "height_px"])
    && isView(value.view) && (expectedView === undefined || value.view === expectedView) && uuid4(value.scan_image_id)
    && sha(value.original_sha256) && sha(value.oriented_pixel_sha256)
    && ["image/jpeg", "image/png", "image/webp"].includes(String(value.media_type))
    && integer(value.size_bytes) && value.size_bytes > 0 && integer(value.width_px) && value.width_px > 0 && integer(value.height_px) && value.height_px > 0;
}

function isEdges(value: unknown): boolean { return keyedNumbers(value, ["top", "right", "bottom", "left"], nonnegative); }
function isMarker(value: unknown): value is MarkerEvidenceResponse {
  if (!record(value) || !exact(value, ["dictionary", "marker_id", "marker_size_mm", "ordered_corners", "orientation_degrees", "edge_lengths_px", "perspective_ratio", "image_to_plane_mm", "plane_mm_to_image", "homography_condition_number", "marker_edge_quality"])) return false;
  const quality = value.marker_edge_quality;
  return dictionaries.includes(value.dictionary as (typeof dictionaries)[number]) && integer(value.marker_id) && value.marker_id >= 0 && value.marker_id <= 49
    && finite(value.marker_size_mm) && value.marker_size_mm >= 10 && value.marker_size_mm <= 300
    && Array.isArray(value.ordered_corners) && value.ordered_corners.length === 4 && value.ordered_corners.every((corner, index) => record(corner) && exact(corner, ["label", "x_px", "y_px"]) && corner.label === cornerLabels[index] && finite(corner.x_px) && finite(corner.y_px))
    && finite(value.orientation_degrees) && value.orientation_degrees >= -180 && value.orientation_degrees < 180
    && isEdges(value.edge_lengths_px) && finite(value.perspective_ratio) && value.perspective_ratio >= 1 && value.perspective_ratio <= 10
    && matrix(value.image_to_plane_mm) && matrix(value.plane_mm_to_image) && finite(value.homography_condition_number) && value.homography_condition_number >= 1
    && record(quality) && exact(quality, ["metric_name", "description", "rms_px", "maximum_px", "sample_count", "per_edge_rms_px", "threshold_px", "valid"])
    && quality.metric_name === "marker_edge_localization_residual" && quality.description === "Sampled marker-border localization residual in image pixels."
    && nonnegative(quality.rms_px) && finite(quality.maximum_px) && quality.maximum_px >= quality.rms_px
    && integer(quality.sample_count) && quality.sample_count > 0 && isEdges(quality.per_edge_rms_px) && positive(quality.threshold_px) && quality.valid === true;
}

function isPoint(value: unknown): boolean { return record(value) && exact(value, ["x_mm", "y_mm"]) && finite(value.x_mm) && finite(value.y_mm); }
function isRectification(value: unknown): value is RectificationEvidenceResponse {
  return record(value) && exact(value, ["width_px", "height_px", "pixels_per_mm", "physical_origin_mm", "source_to_rectified", "rectified_to_source", "physical_width_mm", "physical_height_mm"])
    && integer(value.width_px) && value.width_px > 0 && value.width_px <= 4096 && integer(value.height_px) && value.height_px > 0 && value.height_px <= 4096
    && value.width_px * value.height_px <= 16_000_000 && positive(value.pixels_per_mm) && isPoint(value.physical_origin_mm)
    && matrix(value.source_to_rectified) && matrix(value.rectified_to_source) && positive(value.physical_width_mm) && value.physical_width_mm <= 1500
    && positive(value.physical_height_mm) && value.physical_height_mm <= 1500;
}

function lab(value: unknown): boolean { return keyedNumbers(value, ["l", "a", "b"], finite); }
function isForeground(value: unknown): value is ForegroundEvidenceResponse {
  const keys = ["background_lab_median", "background_lab_mad", "background_grayscale_median", "foreground_grayscale_difference", "supported_signals", "supported_signal_count", "component_count", "scored_candidate_count", "selected_candidate_score", "runner_up_candidate_score", "strong_core_coverage", "mask_stability", "shadow_fraction", "reflection_fraction", "marker_clearance_mm", "border_clearance_mm", "contour_area_mm2", "hull_area_mm2", "solidity", "extent", "oriented_box_corners_mm", "oriented_box_angle_degrees", "threshold_variant_span_mm", "morphology_variant_span_mm"];
  return record(value) && exact(value, keys) && lab(value.background_lab_median) && lab(value.background_lab_mad)
    && finite(value.background_grayscale_median) && nonnegative(value.foreground_grayscale_difference)
    && safeStrings(value.supported_signals) && value.supported_signals.length > 0 && new Set(value.supported_signals).size === value.supported_signals.length
    && value.supported_signal_count === value.supported_signals.length && integer(value.component_count) && value.component_count >= 0 && value.component_count <= 1024
    && integer(value.scored_candidate_count) && value.scored_candidate_count >= 0 && value.scored_candidate_count <= 64
    && unit(value.selected_candidate_score) && (value.runner_up_candidate_score === null || unit(value.runner_up_candidate_score))
    && unit(value.strong_core_coverage) && unit(value.mask_stability) && unit(value.shadow_fraction) && unit(value.reflection_fraction)
    && nonnegative(value.marker_clearance_mm) && nonnegative(value.border_clearance_mm) && positive(value.contour_area_mm2)
    && finite(value.hull_area_mm2) && value.hull_area_mm2 >= value.contour_area_mm2 && unit(value.solidity) && unit(value.extent)
    && Array.isArray(value.oriented_box_corners_mm) && value.oriented_box_corners_mm.length === 4 && value.oriented_box_corners_mm.every(isPoint)
    && finite(value.oriented_box_angle_degrees) && value.oriented_box_angle_degrees >= -180 && value.oriented_box_angle_degrees < 180
    && nonnegative(value.threshold_variant_span_mm) && nonnegative(value.morphology_variant_span_mm);
}

function isQuality(value: unknown): value is ViewQualityEvidenceResponse { return keyedNumbers(value, ["score", "marker", "homography", "background", "mask_stability", "candidate_uniqueness", "visibility"], unit); }
function isUncertainty(value: unknown): value is ViewUncertaintyEvidenceResponse {
  const keys = ["marker_size_mm", "marker_localization_mm", "raster_mm", "foreground_stability_mm", "rig_plane_mm", "rig_orthogonality_mm", "mount_standoff_mm", "off_plane_parallax_mm", "total_mm"];
  return keyedNumbers(value, keys, nonnegative) && record(value) && nonnegative(value.total_mm) && Math.max(...keys.slice(0, -1).map((key) => value[key] as number)) <= value.total_mm;
}
function isPerView(value: unknown, expectedView: MeasurementView): value is PerViewMeasurementResponse {
  return record(value) && exact(value, ["view", "source", "marker", "rectification", "foreground", "raw_dimensions_mm", "quality", "uncertainty", "warnings", "preview_available"])
    && value.view === expectedView && isSource(value.source, expectedView) && isMarker(value.marker) && isRectification(value.rectification)
    && isForeground(value.foreground) && keyedNumbers(value.raw_dimensions_mm, viewDimensions[expectedView], positive)
    && isQuality(value.quality) && isUncertainty(value.uncertainty) && safeStrings(value.warnings) && typeof value.preview_available === "boolean";
}

function isDimensionResult(value: unknown, expected: DimensionName): value is DimensionResultResponse {
  if (!record(value) || !exact(value, ["dimension", "contributing_views", "raw_values_mm", "value_mm", "absolute_disagreement_mm", "relative_disagreement_percent", "quality_inputs", "uncertainty_inputs_mm", "uncertainty_mm", "reconciliation_rule", "validation_status", "warnings"])) return false;
  const invalid = value.validation_status === "invalid";
  return value.dimension === expected && ordered(value.contributing_views, pairs[expected])
    && keyedNumbers(value.raw_values_mm, pairs[expected], positive) && keyedNumbers(value.quality_inputs, pairs[expected], unit)
    && keyedNumbers(value.uncertainty_inputs_mm, pairs[expected], nonnegative) && nonnegative(value.absolute_disagreement_mm)
    && nonnegative(value.relative_disagreement_percent) && ["acceptable", "warning", "invalid"].includes(String(value.validation_status))
    && ["quality_uncertainty_weighted", "stronger_source", "failed"].includes(String(value.reconciliation_rule))
    && (invalid ? value.value_mm === null && value.uncertainty_mm === null && value.reconciliation_rule === "failed"
      : positive(value.value_mm) && nonnegative(value.uncertainty_mm) && value.reconciliation_rule !== "failed")
    && safeStrings(value.warnings);
}

function isFailure(value: unknown): value is MeasurementFailure { return isError(value); }
function isSummary(value: unknown): value is MeasurementAttemptSummaryResponse {
  if (!record(value) || !exact(value, summaryKeys)) return false;
  const status = value.status;
  const stale = value.stale_reasons;
  const base = uuid4(value.id) && uuid4(value.scan_id) && uuid4(value.request_id)
    && (value.reprocess_of_measurement_id === null || uuid4(value.reprocess_of_measurement_id))
    && ["processing", "succeeded", "failed"].includes(String(status)) && uuid4(value.calibration_profile_id)
    && safeText(value.calibration_profile_name, 100) && safeText(value.capture_setup_id, 100) && captureSetupVersion(value.capture_setup_version)
    && safeText(value.processing_version, 64) && safeText(value.algorithm_version, 64) && typeof value.is_stale === "boolean"
    && Array.isArray(stale) && stale.every((item) => staleReasons.includes(item as MeasurementStaleReason))
    && new Set(stale).size === stale.length && value.is_stale === (stale.length > 0) && timestamp(value.created_at)
    && (value.completed_at === null || timestamp(value.completed_at));
  if (!base) return false;
  if (status === "processing") return value.length_mm === null && value.width_mm === null && value.height_mm === null && value.failure_code === null && value.completed_at === null;
  if (status === "succeeded") return positive(value.length_mm) && positive(value.width_mm) && positive(value.height_mm) && value.failure_code === null && value.completed_at !== null;
  return value.length_mm === null && value.width_mm === null && value.height_mm === null && safeText(value.failure_code, 100) && value.completed_at !== null;
}

function isCaptureSnapshot(value: unknown): boolean {
  return record(value) && exact(value, ["id", "version", "type", "qualified", "minimum_object_mm", "maximum_object_mm", "marker_size_uncertainty_mm", "plane_uncertainty_mm", "orthogonality_uncertainty_deg", "standoff_uncertainty_mm", "maximum_off_plane_mm"])
    && safeText(value.id, 100) && captureSetupVersion(value.version) && value.type === "orthogonal_rig" && typeof value.qualified === "boolean"
    && positive(value.minimum_object_mm) && positive(value.maximum_object_mm) && value.minimum_object_mm < value.maximum_object_mm
    && nonnegative(value.marker_size_uncertainty_mm) && nonnegative(value.plane_uncertainty_mm) && nonnegative(value.orthogonality_uncertainty_deg)
    && nonnegative(value.standoff_uncertainty_mm) && nonnegative(value.maximum_off_plane_mm);
}
function isPolicy(value: unknown): value is MeasurementPolicySnapshotResponse {
  const keys = ["acceptable_absolute_mm", "acceptable_relative_percent", "warning_absolute_mm", "warning_relative_percent", "usable_quality", "weak_quality", "stronger_source_quality_lead", "weaker_source_uncertainty_ratio", "maximum_rectified_edge_px", "maximum_rectified_pixels", "maximum_physical_extent_mm", "maximum_connected_components", "maximum_scored_candidates", "maximum_preview_long_edge_px", "maximum_preview_encoded_size"];
  return record(value) && exact(value, keys) && positive(value.acceptable_absolute_mm) && positive(value.acceptable_relative_percent)
    && positive(value.warning_absolute_mm) && positive(value.warning_relative_percent) && unit(value.usable_quality) && unit(value.weak_quality)
    && unit(value.stronger_source_quality_lead) && positive(value.weaker_source_uncertainty_ratio)
    && keys.slice(8).every((key) => positive(value[key]));
}
function isPreview(value: unknown, scanId: string, measurementId: string, expectedView: MeasurementView): value is PreviewDescriptorResponse {
  const expected = `/api/scans/${encodeURIComponent(scanId)}/measurements/${encodeURIComponent(measurementId)}/previews/${expectedView}`;
  return record(value) && exact(value, ["view", "kind", "media_type", "width_px", "height_px", "size_bytes", "api_url"])
    && value.view === expectedView && value.kind === "annotated" && value.media_type === "image/png"
    && integer(value.width_px) && value.width_px > 0 && value.width_px <= 1280 && integer(value.height_px) && value.height_px > 0 && value.height_px <= 1280
    && integer(value.size_bytes) && value.size_bytes > 0 && value.size_bytes <= 2 * 1024 * 1024 && value.api_url === expected
    && !expected.includes("\\") && !expected.includes("://");
}

function isDetail(value: unknown): value is MeasurementAttemptDetailResponse {
  const detailKeys = [...summaryKeys, "calibration_profile_snapshot", "capture_setup_snapshot", "measurement_policy_snapshot", "source_fingerprint", "sources", "per_view_measurements", "dimension_results", "final_dimensions", "overall_quality", "overall_uncertainty_mm", "warnings", "previews", "failure", "started_at"];
  if (!record(value) || !exact(value, detailKeys)) return false;
  const summary = Object.fromEntries(summaryKeys.map((key) => [key, value[key]]));
  if (!isSummary(summary) || !isProfile(value.calibration_profile_snapshot) || !isCaptureSnapshot(value.capture_setup_snapshot) || !isPolicy(value.measurement_policy_snapshot) || !timestamp(value.started_at)) return false;
  if (!record(value.calibration_profile_snapshot) || value.calibration_profile_snapshot.id !== value.calibration_profile_id || !record(value.capture_setup_snapshot) || value.capture_setup_snapshot.id !== value.capture_setup_id || value.capture_setup_snapshot.version !== value.capture_setup_version) return false;
  if (!(value.source_fingerprint === null || sha(value.source_fingerprint)) || !Array.isArray(value.sources) || !Array.isArray(value.per_view_measurements) || !Array.isArray(value.dimension_results) || !safeStrings(value.warnings) || !Array.isArray(value.previews)) return false;
  const sourceViews = value.sources.map((item) => record(item) ? item.view : null);
  const evidenceViews = value.per_view_measurements.map((item) => record(item) ? item.view : null);
  const dimensionNames = value.dimension_results.map((item) => record(item) ? item.dimension : null);
  if (!value.sources.every((item, index) => isSource(item, sourceViews[index] as MeasurementView)) || !value.per_view_measurements.every((item, index) => isPerView(item, evidenceViews[index] as MeasurementView)) || !value.dimension_results.every((item, index) => isDimensionResult(item, dimensionNames[index] as DimensionName))) return false;
  if (!ordered(sourceViews, views.filter((view) => sourceViews.includes(view))) || !ordered(evidenceViews, views.filter((view) => evidenceViews.includes(view))) || !ordered(dimensionNames, dimensions.filter((dimension) => dimensionNames.includes(dimension)))) return false;
  const quality = value.overall_quality;
  const qualityValid = quality === null || (record(quality) && exact(quality, ["score", "minimum_view_score", "view_scores"]) && unit(quality.score) && unit(quality.minimum_view_score) && keyedNumbers(quality.view_scores, views, unit) && record(quality.view_scores) && quality.minimum_view_score === Math.min(quality.view_scores.top as number, quality.view_scores.front as number, quality.view_scores.side as number));
  if (!qualityValid || !(value.overall_uncertainty_mm === null || nonnegative(value.overall_uncertainty_mm))) return false;
  if (!value.previews.every((item, index) => isPreview(item, value.scan_id as string, value.id as string, views[index] as MeasurementView))) return false;
  if (value.status === "processing") return value.source_fingerprint === null && value.sources.length === 0 && value.per_view_measurements.length === 0 && value.dimension_results.length === 0 && value.final_dimensions === null && value.overall_quality === null && value.overall_uncertainty_mm === null && value.warnings.length === 0 && value.previews.length === 0 && value.failure === null;
  if (value.status === "failed") return value.final_dimensions === null && value.previews.length === 0 && isFailure(value.failure);
  return value.source_fingerprint !== null && ordered(sourceViews, views) && ordered(evidenceViews, views) && ordered(dimensionNames, dimensions)
    && record(value.final_dimensions) && exact(value.final_dimensions, ["length_mm", "width_mm", "height_mm"])
    && positive(value.final_dimensions.length_mm) && positive(value.final_dimensions.width_mm) && positive(value.final_dimensions.height_mm)
    && value.final_dimensions.length_mm === value.length_mm && value.final_dimensions.width_mm === value.width_mm && value.final_dimensions.height_mm === value.height_mm
    && value.overall_quality !== null && value.overall_uncertainty_mm !== null && value.previews.length === 3 && value.failure === null;
}

function isList(value: unknown): value is MeasurementAttemptListResponse {
  return record(value) && exact(value, ["items", "total", "offset", "limit"]) && Array.isArray(value.items) && value.items.every(isSummary)
    && integer(value.total) && value.total >= 0 && integer(value.offset) && value.offset >= 0 && integer(value.limit) && value.limit >= 1 && value.limit <= 100;
}
async function json(response: Response): Promise<unknown> { return response.json().catch(() => null); }
function fallback(status: number): MeasurementApiErrorResponse { return { code: "REQUEST_FAILED", message: `The local API request failed with status ${status}.`, recoverable: status >= 500, suggested_action: "Check the local service and try again." }; }
async function requestJson<T>(path: string, init: RequestInit, validator: (value: unknown) => value is T, uncertain = false): Promise<T> {
  let response: Response;
  try { response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers: { Accept: "application/json", ...init.headers } }); }
  catch { throw new MeasurementApiRequestError(0, { code: "NETWORK_ERROR", message: "The local service could not be reached.", recoverable: true, suggested_action: "Keep this request and retry it, or check measurement history before starting another." }, uncertain); }
  const payload = await json(response);
  if (!response.ok) {
    const outcomeUncertain = uncertain && (response.status === 500 || response.status === 503);
    throw new MeasurementApiRequestError(
      response.status,
      isError(payload) ? payload : fallback(response.status),
      outcomeUncertain,
    );
  }
  if (!validator(payload)) throw new MeasurementApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned an invalid measurement response.", recoverable: true, suggested_action: "Check measurement history before retrying the same request." }, uncertain);
  return payload;
}
function scanPath(scanId: string): string { return `/scans/${encodeURIComponent(scanId)}/measurements`; }

export function getMeasurementOptions(signal?: AbortSignal): Promise<MeasurementOptionsResponse> { return requestJson("/measurements/options", { method: "GET", signal }, isOptions); }
export function listMeasurementAttempts(scanId: string, options: { offset?: number; limit?: number } = {}, signal?: AbortSignal): Promise<MeasurementAttemptListResponse> {
  const params = new URLSearchParams({ offset: String(options.offset ?? 0), limit: String(options.limit ?? 50) });
  return requestJson(`${scanPath(scanId)}?${params}`, { method: "GET", signal }, isList);
}
export function getMeasurementAttempt(scanId: string, measurementId: string, signal?: AbortSignal): Promise<MeasurementAttemptDetailResponse> { return requestJson(`${scanPath(scanId)}/${encodeURIComponent(measurementId)}`, { method: "GET", signal }, isDetail); }
export async function processMeasurement(scanId: string, request: MeasurementProcessRequest, signal?: AbortSignal): Promise<MeasurementAttemptDetailResponse> {
  const attempt = await requestJson(scanPath(scanId), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal }, isDetail, true);
  if (attempt.request_id !== request.request_id) {
    throw new MeasurementApiRequestError(502, {
      code: "INVALID_API_RESPONSE",
      message: "The local API returned a measurement for a different request.",
      recoverable: true,
      suggested_action: "Keep the saved request and refresh measurement history.",
    }, true);
  }
  return attempt;
}

const pendingPrefix = "phase3-measurement-request:";
function pendingKey(scanId: string): string { return `${pendingPrefix}${scanId}`; }
function isPendingMeasurementRequest(value: unknown): value is MeasurementProcessRequest {
  return record(value)
    && exact(value, ["request_id", "expected_calibration_profile_id", "expected_capture_setup_id", "capture_contract_acknowledged", "reprocess_of_measurement_id"])
    && uuid4(value.request_id)
    && uuid4(value.expected_calibration_profile_id)
    && safeText(value.expected_capture_setup_id, 100)
    && value.capture_contract_acknowledged === true
    && (value.reprocess_of_measurement_id === null || uuid4(value.reprocess_of_measurement_id));
}
export function getPendingMeasurementRequest(scanId: string): MeasurementProcessRequest | null {
  const stored = sessionStorage.getItem(pendingKey(scanId));
  if (!stored) return null;
  try {
    const parsed: unknown = JSON.parse(stored);
    return isPendingMeasurementRequest(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
export function prepareMeasurementRequest(scanId: string, profileId: string, captureSetupId: string, reprocessOf: string | null = null): MeasurementProcessRequest {
  const key = pendingKey(scanId);
  const stored = sessionStorage.getItem(key);
  if (stored !== null) {
    const pending = getPendingMeasurementRequest(scanId);
    if (pending
      && pending.expected_calibration_profile_id === profileId
      && pending.expected_capture_setup_id === captureSetupId
      && pending.reprocess_of_measurement_id === reprocessOf) return pending;
    throw new MeasurementApiRequestError(409, { code: "UNCERTAIN_MEASUREMENT_OUTCOME", message: "A previous measurement request for this scan still has an uncertain outcome.", recoverable: true, suggested_action: "Check measurement history or retry the pending request before starting another." }, true);
  }
  const request: MeasurementProcessRequest = { request_id: crypto.randomUUID(), expected_calibration_profile_id: profileId, expected_capture_setup_id: captureSetupId, capture_contract_acknowledged: true, reprocess_of_measurement_id: reprocessOf };
  sessionStorage.setItem(key, JSON.stringify(request));
  return request;
}
export function clearPendingMeasurementRequest(scanId: string): void { sessionStorage.removeItem(pendingKey(scanId)); }
export function abandonPendingMeasurementRequest(scanId: string): void {
  clearPendingMeasurementRequest(scanId);
}
export function reconcilePendingMeasurementRequest(
  scanId: string,
  attempts: readonly MeasurementAttemptSummaryResponse[],
): MeasurementProcessRequest | null {
  const pending = getPendingMeasurementRequest(scanId);
  if (pending && attempts.some((attempt) => attempt.request_id === pending.request_id)) {
    clearPendingMeasurementRequest(scanId);
    return null;
  }
  return pending;
}
export function asMeasurementApiError(error: unknown): MeasurementApiErrorResponse { return error instanceof MeasurementApiRequestError ? error.payload : { code: "NETWORK_ERROR", message: "The local service could not be reached.", recoverable: true, suggested_action: "Keep the request ID and retry, or check measurement history." }; }

export async function getMeasurementPreview(descriptor: PreviewDescriptorResponse, signal?: AbortSignal): Promise<Blob> {
  let response: Response;
  try { response = await fetch(descriptor.api_url, { method: "GET", headers: { Accept: "image/png" }, signal }); }
  catch { throw new MeasurementApiRequestError(0, asMeasurementApiError(null)); }
  if (!response.ok) { const payload = await json(response); throw new MeasurementApiRequestError(response.status, isError(payload) ? payload : fallback(response.status)); }
  const media = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  const declared = response.headers.get("content-length");
  if (media !== "image/png" || (declared !== null && Number(declared) !== descriptor.size_bytes)) throw new MeasurementApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned invalid preview metadata.", recoverable: true, suggested_action: "Refresh the measurement result." });
  const blob = await response.blob();
  if (blob.size !== descriptor.size_bytes || blob.size > 2 * 1024 * 1024) throw new MeasurementApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned an invalid preview size.", recoverable: true, suggested_action: "Refresh the measurement result." });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 24 || !signature.every((byte, index) => bytes[index] === byte) || String.fromCharCode(...bytes.slice(12, 16)) !== "IHDR" || view.getUint32(16) !== descriptor.width_px || view.getUint32(20) !== descriptor.height_px) throw new MeasurementApiRequestError(502, { code: "INVALID_API_RESPONSE", message: "The local API returned invalid preview content.", recoverable: true, suggested_action: "Refresh the measurement result." });
  return blob;
}
