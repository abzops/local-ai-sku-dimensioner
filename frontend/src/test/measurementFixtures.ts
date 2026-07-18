import type {
  DimensionName,
  MeasurementAttemptDetailResponse,
  MeasurementAttemptSummaryResponse,
  MeasurementOptionsResponse,
  MeasurementView,
  PerViewMeasurementResponse,
} from "../types/measurements";

export const scanId = "11111111-1111-4111-8111-111111111111";
export const profileId = "22222222-2222-4222-8222-222222222222";
export const measurementId = "33333333-3333-4333-8333-333333333333";
export const requestId = "44444444-4444-4444-8444-444444444444";
const timestamp = "2026-07-18T12:00:00Z";
const identity: [[number, number, number], [number, number, number], [number, number, number]] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

export const measurementOptionsFixture: MeasurementOptionsResponse = {
  capture_setup: { id: "rig-local-1", version: "1", type: "orthogonal_rig", qualified: true, processing_enabled: true, minimum_object_mm: 75, maximum_object_mm: 400, supported_product_domain: ["opaque", "rigid", "stable", "approximately_cuboidal", "fully_visible", "non_reflective_or_mildly_reflective", "configured_orthogonal_rig"], requirements: ["Use the configured qualified orthogonal rig."] },
  required_views: ["top", "front", "side"],
  dimension_axis_mapping: { top: ["length", "width"], front: ["width", "height"], side: ["length", "height"] },
  disagreement_thresholds: { acceptable_absolute_mm: 5, acceptable_relative_percent: 3, warning_absolute_mm: 10, warning_relative_percent: 6 },
  non_certified_metrology_warning: "Measurements are deterministic engineering estimates from a physically qualified local rig, not certified metrology.",
};

const viewAxes: Record<MeasurementView, [DimensionName, DimensionName]> = { top: ["length", "width"], front: ["width", "height"], side: ["length", "height"] };
const values: Record<DimensionName, number> = { length: 100, width: 80, height: 60 };
function viewEvidence(view: MeasurementView, index: number): PerViewMeasurementResponse {
  const axes = viewAxes[view];
  return {
    view,
    source: { view, scan_image_id: `55555555-5555-4555-8555-55555555555${index}`, original_sha256: "a".repeat(64), oriented_pixel_sha256: "b".repeat(64), media_type: "image/png", size_bytes: 2048, width_px: 1600, height_px: 1200 },
    marker: { dictionary: "DICT_4X4_50", marker_id: 0, marker_size_mm: 100, ordered_corners: [{ label: "top_left", x_px: 0, y_px: 0 }, { label: "top_right", x_px: 100, y_px: 0 }, { label: "bottom_right", x_px: 100, y_px: 100 }, { label: "bottom_left", x_px: 0, y_px: 100 }], orientation_degrees: 0, edge_lengths_px: { top: 100, right: 100, bottom: 100, left: 100 }, perspective_ratio: 1, image_to_plane_mm: identity, plane_mm_to_image: identity, homography_condition_number: 1, marker_edge_quality: { metric_name: "marker_edge_localization_residual", description: "Sampled marker-border localization residual in image pixels.", rms_px: 0.2, maximum_px: 0.3, sample_count: 16, per_edge_rms_px: { top: 0.2, right: 0.2, bottom: 0.2, left: 0.2 }, threshold_px: 2, valid: true } },
    rectification: { width_px: 800, height_px: 600, pixels_per_mm: 4, physical_origin_mm: { x_mm: 0, y_mm: 0 }, source_to_rectified: identity, rectified_to_source: identity, physical_width_mm: 200, physical_height_mm: 150 },
    foreground: { background_lab_median: { l: 90, a: 0, b: 0 }, background_lab_mad: { l: 1, a: 1, b: 1 }, background_grayscale_median: 230, foreground_grayscale_difference: 100, supported_signals: ["lab_distance"], supported_signal_count: 1, component_count: 1, scored_candidate_count: 1, selected_candidate_score: 0.9, runner_up_candidate_score: null, strong_core_coverage: 0.9, mask_stability: 0.9, shadow_fraction: 0, reflection_fraction: 0, marker_clearance_mm: 10, border_clearance_mm: 10, contour_area_mm2: 8000, hull_area_mm2: 8100, solidity: 0.98, extent: 0.95, oriented_box_corners_mm: [{ x_mm: 0, y_mm: 0 }, { x_mm: 100, y_mm: 0 }, { x_mm: 100, y_mm: 80 }, { x_mm: 0, y_mm: 80 }], oriented_box_angle_degrees: 0, threshold_variant_span_mm: 0.2, morphology_variant_span_mm: 0.2 },
    raw_dimensions_mm: { [axes[0]]: values[axes[0]], [axes[1]]: values[axes[1]] },
    quality: { score: 0.9, marker: 0.9, homography: 0.9, background: 0.9, mask_stability: 0.9, candidate_uniqueness: 0.9, visibility: 0.9 },
    uncertainty: { marker_size_mm: 0.2, marker_localization_mm: 0.2, raster_mm: 0.2, foreground_stability_mm: 0.2, rig_plane_mm: 0.5, rig_orthogonality_mm: 0.5, mount_standoff_mm: 0.5, off_plane_parallax_mm: 0.5, total_mm: 2 }, warnings: [], preview_available: true,
  };
}

const baseSummary: MeasurementAttemptSummaryResponse = { id: measurementId, scan_id: scanId, request_id: requestId, reprocess_of_measurement_id: null, status: "succeeded", calibration_profile_id: profileId, calibration_profile_name: "Default marker", capture_setup_id: "rig-local-1", capture_setup_version: "1", processing_version: "phase3-v1", algorithm_version: "deterministic-geometry-v1", length_mm: 100, width_mm: 80, height_mm: 60, failure_code: null, is_stale: false, stale_reasons: [], created_at: timestamp, completed_at: timestamp };
export const succeededSummaryFixture = baseSummary;
export const processingSummaryFixture: MeasurementAttemptSummaryResponse = { ...baseSummary, status: "processing", length_mm: null, width_mm: null, height_mm: null, completed_at: null };
export const failedSummaryFixture: MeasurementAttemptSummaryResponse = { ...baseSummary, status: "failed", length_mm: null, width_mm: null, height_mm: null, failure_code: "PRODUCT_CROPPED" };

const views: MeasurementView[] = ["top", "front", "side"];
const dimensionPairs: Record<DimensionName, [MeasurementView, MeasurementView]> = { length: ["top", "side"], width: ["top", "front"], height: ["front", "side"] };
export const succeededDetailFixture: MeasurementAttemptDetailResponse = {
  ...baseSummary,
  calibration_profile_snapshot: { id: profileId, name: "Default marker", dictionary: "DICT_4X4_50", marker_id: 0, marker_size_mm: 100, border_bits: 1, minimum_marker_side_px: 64, maximum_perspective_ratio: 3, maximum_homography_condition_number: 1_000_000, maximum_marker_edge_residual_px: 2, rectified_pixels_per_mm: 4, is_active: true, created_at: timestamp, activated_at: timestamp },
  capture_setup_snapshot: { id: "rig-local-1", version: "1", type: "orthogonal_rig", qualified: true, minimum_object_mm: 75, maximum_object_mm: 400, marker_size_uncertainty_mm: 0.2, plane_uncertainty_mm: 0.5, orthogonality_uncertainty_deg: 0.5, standoff_uncertainty_mm: 0.5, maximum_off_plane_mm: 1 },
  measurement_policy_snapshot: { acceptable_absolute_mm: 5, acceptable_relative_percent: 3, warning_absolute_mm: 10, warning_relative_percent: 6, usable_quality: 0.7, weak_quality: 0.55, stronger_source_quality_lead: 0.15, weaker_source_uncertainty_ratio: 2, maximum_rectified_edge_px: 4096, maximum_rectified_pixels: 16_000_000, maximum_physical_extent_mm: 1500, maximum_connected_components: 1024, maximum_scored_candidates: 64, maximum_preview_long_edge_px: 1280, maximum_preview_encoded_size: 2 * 1024 * 1024 },
  source_fingerprint: "c".repeat(64),
  sources: views.map((view, index) => viewEvidence(view, index).source),
  per_view_measurements: views.map(viewEvidence),
  dimension_results: (["length", "width", "height"] as DimensionName[]).map((dimension) => { const pair = dimensionPairs[dimension]; return { dimension, contributing_views: pair, raw_values_mm: { [pair[0]]: values[dimension], [pair[1]]: values[dimension] }, value_mm: values[dimension], absolute_disagreement_mm: 0, relative_disagreement_percent: 0, quality_inputs: { [pair[0]]: 0.9, [pair[1]]: 0.9 }, uncertainty_inputs_mm: { [pair[0]]: 2, [pair[1]]: 2 }, uncertainty_mm: 2, reconciliation_rule: "quality_uncertainty_weighted", validation_status: "acceptable", warnings: [] }; }),
  final_dimensions: { length_mm: 100, width_mm: 80, height_mm: 60 }, overall_quality: { score: 0.9, minimum_view_score: 0.9, view_scores: { top: 0.9, front: 0.9, side: 0.9 } }, overall_uncertainty_mm: 2, warnings: [],
  previews: views.map((view) => ({ view, kind: "annotated", media_type: "image/png", width_px: 1, height_px: 1, size_bytes: 24, api_url: `/api/scans/${scanId}/measurements/${measurementId}/previews/${view}` })), failure: null, started_at: timestamp,
};
export const processingDetailFixture: MeasurementAttemptDetailResponse = { ...succeededDetailFixture, ...processingSummaryFixture, source_fingerprint: null, sources: [], per_view_measurements: [], dimension_results: [], final_dimensions: null, overall_quality: null, overall_uncertainty_mm: null, warnings: [], previews: [], failure: null };
export const failedDetailFixture: MeasurementAttemptDetailResponse = { ...succeededDetailFixture, ...failedSummaryFixture, source_fingerprint: null, sources: [], per_view_measurements: [], dimension_results: [], final_dimensions: null, overall_quality: null, overall_uncertainty_mm: null, warnings: ["Product touches a capture boundary."], previews: [], failure: { code: "PRODUCT_CROPPED", message: "The product is cropped in one required view.", recoverable: true, suggested_action: "Retake the image with the complete product visible.", view: "top" } };

export function cloneFixture<T>(value: T): T { return structuredClone(value); }
export function previewPngBytes(width = 1, height = 1): Uint8Array { const bytes = new Uint8Array(24); bytes.set([137, 80, 78, 71, 13, 10, 26, 10]); bytes.set([73, 72, 68, 82], 12); new DataView(bytes.buffer).setUint32(16, width); new DataView(bytes.buffer).setUint32(20, height); return bytes; }
