export type ArucoDictionary = "DICT_4X4_50" | "DICT_5X5_50" | "DICT_6X6_50";

export type CornerLabel = "top_left" | "top_right" | "bottom_right" | "bottom_left";

export type EdgeName = "top" | "right" | "bottom" | "left";

export interface CalibrationProfileCreateRequest {
  name: string;
  dictionary: ArucoDictionary;
  marker_id: number;
  marker_size_mm: number;
  minimum_marker_side_px: number;
  maximum_perspective_ratio: number;
  maximum_homography_condition_number: number;
  maximum_marker_edge_residual_px: number;
  rectified_pixels_per_mm: number;
}

export interface CalibrationProfileResponse extends CalibrationProfileCreateRequest {
  id: string;
  border_bits: 1;
  is_active: boolean;
  created_at: string;
  activated_at: string | null;
}

export interface CalibrationProfileListResponse {
  items: CalibrationProfileResponse[];
  total: number;
}

export interface CalibrationDefaults {
  dictionary: ArucoDictionary;
  marker_id: number;
  marker_size_mm: number;
  minimum_marker_side_px: number;
  maximum_perspective_ratio: number;
  maximum_homography_condition_number: number;
  maximum_marker_edge_residual_px: number;
  rectified_pixels_per_mm: number;
}

export interface CalibrationOptionsResponse {
  dictionaries: ArucoDictionary[];
  marker_id_min: number;
  marker_id_max: number;
  border_bits: 1;
  defaults: CalibrationDefaults;
}

export interface OrderedCorner {
  label: CornerLabel;
  x_px: number;
  y_px: number;
}

export type EdgeValues = Record<EdgeName, number>;

export interface MarkerEdgeQuality {
  metric_name: "marker_edge_localization_residual";
  description: "Sampled marker-border localization residual in image pixels.";
  rms_px: number;
  maximum_px: number;
  sample_count: number;
  per_edge_rms_px: EdgeValues;
  threshold_px: number;
  valid: boolean;
}

export interface CalibrationPreview {
  media_type: "image/png";
  width_px: number;
  height_px: number;
  data_base64: string;
}

export type Matrix3x3 = [
  [number, number, number],
  [number, number, number],
  [number, number, number],
];

export interface CalibrationTestResponse {
  profile_id: string;
  dictionary: ArucoDictionary;
  marker_id: number;
  marker_size_mm: number;
  ordered_corners: [OrderedCorner, OrderedCorner, OrderedCorner, OrderedCorner];
  orientation_degrees: number;
  edge_lengths_px: EdgeValues;
  perspective_ratio: number;
  image_to_marker_mm: Matrix3x3;
  marker_mm_to_image: Matrix3x3;
  homography_condition_number: number;
  rectified_width_px: number;
  rectified_height_px: number;
  rectified_pixels_per_mm: number;
  marker_edge_quality: MarkerEdgeQuality;
  annotated_preview: CalibrationPreview;
  rectified_preview: CalibrationPreview;
}

export interface CalibrationApiErrorResponse {
  code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  field?: string;
  view?: "top" | "front" | "side" | "additional";
}

