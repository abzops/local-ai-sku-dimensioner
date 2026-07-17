export type ScanStatus = "draft" | "images_uploaded" | "ready_for_processing";

export type ImageView = "top" | "front" | "side" | "additional";

export interface ScanImageResponse {
  id: string;
  view_type: ImageView;
  media_type: "image/jpeg" | "image/png" | "image/webp";
  size_bytes: number;
  width_px: number;
  height_px: number;
  created_at: string;
}

export interface ScanSummaryResponse {
  id: string;
  sku: string;
  barcode: string | null;
  product_name: string | null;
  status: ScanStatus;
  image_count: number;
  missing_required_views: Array<Exclude<ImageView, "additional">>;
  created_at: string;
  updated_at: string;
}

export interface ScanDetailResponse extends Omit<ScanSummaryResponse, "image_count"> {
  images: ScanImageResponse[];
}

export interface ScanListResponse {
  items: ScanSummaryResponse[];
  total: number;
  offset: number;
  limit: number;
}

export interface ScanCreateRequest {
  sku: string;
  barcode?: string | null;
  product_name?: string | null;
}

export interface UploadBatchResponse {
  scan: ScanDetailResponse;
  uploaded_images: ScanImageResponse[];
}

export interface ApiErrorResponse {
  code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  field?: string;
  view?: ImageView;
}
