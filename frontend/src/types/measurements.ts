import type {
  ArucoDictionary,
  CalibrationProfileResponse,
  EdgeValues,
  MarkerEdgeQuality,
  Matrix3x3,
  OrderedCorner,
} from "./calibration";

export type MeasurementStatus = "processing" | "succeeded" | "failed";
export type DimensionName = "length" | "width" | "height";
export type MeasurementView = "top" | "front" | "side";
export type DimensionValidationStatus = "acceptable" | "warning" | "invalid";
export type ReconciliationRule =
  | "quality_uncertainty_weighted"
  | "stronger_source"
  | "failed";
export type PreviewKind = "annotated";
export type CaptureSetupType = "orthogonal_rig";
export type MeasurementStaleReason =
  | "active_calibration_profile_changed"
  | "source_images_changed"
  | "capture_setup_changed"
  | "processing_version_changed"
  | "algorithm_version_changed"
  | "measurement_policy_changed";

export interface MeasurementProcessRequest {
  request_id: string;
  expected_calibration_profile_id: string;
  expected_capture_setup_id: string;
  capture_contract_acknowledged: true;
  reprocess_of_measurement_id: string | null;
}

export interface MeasurementApiErrorResponse {
  code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  field?: string;
  view?: MeasurementView;
}

export interface CaptureSetupOptions {
  id: string;
  version: string;
  type: CaptureSetupType;
  qualified: boolean;
  processing_enabled: boolean;
  minimum_object_mm: number;
  maximum_object_mm: number;
  supported_product_domain: string[];
  requirements: string[];
}

export interface MeasurementOptionsResponse {
  capture_setup: CaptureSetupOptions;
  required_views: ["top", "front", "side"];
  dimension_axis_mapping: {
    top: ["length", "width"];
    front: ["width", "height"];
    side: ["length", "height"];
  };
  disagreement_thresholds: {
    acceptable_absolute_mm: number;
    acceptable_relative_percent: number;
    warning_absolute_mm: number;
    warning_relative_percent: number;
  };
  non_certified_metrology_warning: string;
}

export interface MeasurementFailure {
  code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  field?: string;
  view?: MeasurementView;
}

export interface MeasurementSourceResponse {
  view: MeasurementView;
  scan_image_id: string;
  original_sha256: string;
  oriented_pixel_sha256: string;
  media_type: "image/jpeg" | "image/png" | "image/webp";
  size_bytes: number;
  width_px: number;
  height_px: number;
}

export interface MarkerEvidenceResponse {
  dictionary: ArucoDictionary;
  marker_id: number;
  marker_size_mm: number;
  ordered_corners: [OrderedCorner, OrderedCorner, OrderedCorner, OrderedCorner];
  orientation_degrees: number;
  edge_lengths_px: EdgeValues;
  perspective_ratio: number;
  image_to_plane_mm: Matrix3x3;
  plane_mm_to_image: Matrix3x3;
  homography_condition_number: number;
  marker_edge_quality: MarkerEdgeQuality;
}

export interface PlanePointResponse {
  x_mm: number;
  y_mm: number;
}

export interface RectificationEvidenceResponse {
  width_px: number;
  height_px: number;
  pixels_per_mm: number;
  physical_origin_mm: PlanePointResponse;
  source_to_rectified: Matrix3x3;
  rectified_to_source: Matrix3x3;
  physical_width_mm: number;
  physical_height_mm: number;
}

export interface LabValuesResponse {
  l: number;
  a: number;
  b: number;
}

export interface ForegroundEvidenceResponse {
  background_lab_median: LabValuesResponse;
  background_lab_mad: LabValuesResponse;
  background_grayscale_median: number;
  foreground_grayscale_difference: number;
  supported_signals: string[];
  supported_signal_count: number;
  component_count: number;
  scored_candidate_count: number;
  selected_candidate_score: number;
  runner_up_candidate_score: number | null;
  strong_core_coverage: number;
  mask_stability: number;
  shadow_fraction: number;
  reflection_fraction: number;
  marker_clearance_mm: number;
  border_clearance_mm: number;
  contour_area_mm2: number;
  hull_area_mm2: number;
  solidity: number;
  extent: number;
  oriented_box_corners_mm: [
    PlanePointResponse,
    PlanePointResponse,
    PlanePointResponse,
    PlanePointResponse,
  ];
  oriented_box_angle_degrees: number;
  threshold_variant_span_mm: number;
  morphology_variant_span_mm: number;
}

export interface ViewQualityEvidenceResponse {
  score: number;
  marker: number;
  homography: number;
  background: number;
  mask_stability: number;
  candidate_uniqueness: number;
  visibility: number;
}

export interface ViewUncertaintyEvidenceResponse {
  marker_size_mm: number;
  marker_localization_mm: number;
  raster_mm: number;
  foreground_stability_mm: number;
  rig_plane_mm: number;
  rig_orthogonality_mm: number;
  mount_standoff_mm: number;
  off_plane_parallax_mm: number;
  total_mm: number;
}

export interface PerViewMeasurementResponse {
  view: MeasurementView;
  source: MeasurementSourceResponse;
  marker: MarkerEvidenceResponse;
  rectification: RectificationEvidenceResponse;
  foreground: ForegroundEvidenceResponse;
  raw_dimensions_mm: Partial<Record<DimensionName, number>>;
  quality: ViewQualityEvidenceResponse;
  uncertainty: ViewUncertaintyEvidenceResponse;
  warnings: string[];
  preview_available: boolean;
}

export interface DimensionResultResponse {
  dimension: DimensionName;
  contributing_views: [MeasurementView, MeasurementView];
  raw_values_mm: Partial<Record<MeasurementView, number>>;
  value_mm: number | null;
  absolute_disagreement_mm: number;
  relative_disagreement_percent: number;
  quality_inputs: Partial<Record<MeasurementView, number>>;
  uncertainty_inputs_mm: Partial<Record<MeasurementView, number>>;
  uncertainty_mm: number | null;
  reconciliation_rule: ReconciliationRule;
  validation_status: DimensionValidationStatus;
  warnings: string[];
}

export interface OverallQualityEvidenceResponse {
  score: number;
  minimum_view_score: number;
  view_scores: { top: number; front: number; side: number };
}

export interface FinalDimensionsResponse {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface PreviewDescriptorResponse {
  view: MeasurementView;
  kind: PreviewKind;
  media_type: "image/png";
  width_px: number;
  height_px: number;
  size_bytes: number;
  api_url: string;
}

export interface CaptureSetupSnapshotResponse {
  id: string;
  version: string;
  type: CaptureSetupType;
  qualified: boolean;
  minimum_object_mm: number;
  maximum_object_mm: number;
  marker_size_uncertainty_mm: number;
  plane_uncertainty_mm: number;
  orthogonality_uncertainty_deg: number;
  standoff_uncertainty_mm: number;
  maximum_off_plane_mm: number;
}

export interface MeasurementPolicySnapshotResponse {
  acceptable_absolute_mm: number;
  acceptable_relative_percent: number;
  warning_absolute_mm: number;
  warning_relative_percent: number;
  usable_quality: number;
  weak_quality: number;
  stronger_source_quality_lead: number;
  weaker_source_uncertainty_ratio: number;
  maximum_rectified_edge_px: number;
  maximum_rectified_pixels: number;
  maximum_physical_extent_mm: number;
  maximum_connected_components: number;
  maximum_scored_candidates: number;
  maximum_preview_long_edge_px: number;
  maximum_preview_encoded_size: number;
}

export interface MeasurementAttemptSummaryResponse {
  id: string;
  scan_id: string;
  request_id: string;
  reprocess_of_measurement_id: string | null;
  status: MeasurementStatus;
  calibration_profile_id: string;
  calibration_profile_name: string;
  capture_setup_id: string;
  capture_setup_version: string;
  processing_version: string;
  algorithm_version: string;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  failure_code: string | null;
  is_stale: boolean;
  stale_reasons: MeasurementStaleReason[];
  created_at: string;
  completed_at: string | null;
}

export interface MeasurementAttemptListResponse {
  items: MeasurementAttemptSummaryResponse[];
  total: number;
  offset: number;
  limit: number;
}

export interface MeasurementAttemptDetailResponse
  extends MeasurementAttemptSummaryResponse {
  calibration_profile_snapshot: CalibrationProfileResponse;
  capture_setup_snapshot: CaptureSetupSnapshotResponse;
  measurement_policy_snapshot: MeasurementPolicySnapshotResponse;
  source_fingerprint: string | null;
  sources: MeasurementSourceResponse[];
  per_view_measurements: PerViewMeasurementResponse[];
  dimension_results: DimensionResultResponse[];
  final_dimensions: FinalDimensionsResponse | null;
  overall_quality: OverallQualityEvidenceResponse | null;
  overall_uncertainty_mm: number | null;
  warnings: string[];
  previews: PreviewDescriptorResponse[];
  failure: MeasurementFailure | null;
  started_at: string;
}
