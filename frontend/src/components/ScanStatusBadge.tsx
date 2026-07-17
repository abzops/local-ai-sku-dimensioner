import type { ScanStatus } from "../types/scans";

const labels: Record<ScanStatus, string> = {
  draft: "Draft",
  images_uploaded: "Images uploaded",
  ready_for_processing: "Ready for processing",
};

interface ScanStatusBadgeProps {
  status: ScanStatus;
}

export function ScanStatusBadge({ status }: ScanStatusBadgeProps) {
  return <span className={`status-badge status-badge--${status}`}>{labels[status]}</span>;
}
