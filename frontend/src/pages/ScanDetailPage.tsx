import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { asApiError, getScan } from "../api/scans";
import { ScanStatusBadge } from "../components/ScanStatusBadge";

function formatBytes(value: number): string {
  return value < 1024 * 1024
    ? `${Math.round(value / 1024)} KB`
    : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ScanDetailPage() {
  const { scanId = "" } = useParams();
  const scan = useQuery({
    queryKey: ["scans", scanId],
    queryFn: ({ signal }) => getScan(scanId, signal),
    enabled: scanId.length > 0,
  });

  if (scan.isPending) {
    return <main className="page-shell"><p className="state-panel" role="status">Loading scan...</p></main>;
  }

  if (scan.isError) {
    return (
      <main className="page-shell">
        <section className="state-panel state-panel--error" role="alert">
          <h1>Scan unavailable</h1>
          <p>{asApiError(scan.error).message}</p>
          <Link className="text-link" to="/scans">Return to history</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <header className="page-heading page-heading--split">
        <div>
          <p className="eyebrow">Scan record</p>
          <h1>{scan.data.sku}</h1>
          <p>{scan.data.product_name || "Unnamed product"}</p>
        </div>
        <ScanStatusBadge status={scan.data.status} />
      </header>

      <section className="detail-card" aria-labelledby="scan-details-heading">
        <h2 id="scan-details-heading">Details</h2>
        <dl className="metadata-list metadata-list--detail">
          <div><dt>Barcode</dt><dd>{scan.data.barcode || "Not provided"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(scan.data.created_at).toLocaleString()}</dd></div>
          <div><dt>Updated</dt><dd>{new Date(scan.data.updated_at).toLocaleString()}</dd></div>
          <div>
            <dt>Missing required views</dt>
            <dd>{scan.data.missing_required_views.join(", ") || "None"}</dd>
          </div>
        </dl>
      </section>

      <section className="detail-card" aria-labelledby="images-heading">
        <div className="detail-card__heading">
          <div>
            <p className="eyebrow">Validated metadata</p>
            <h2 id="images-heading">Stored images</h2>
          </div>
          <span>{scan.data.images.length} total</span>
        </div>
        {scan.data.images.length === 0 ? (
          <p>No images have been uploaded.</p>
        ) : (
          <ul className="image-records">
            {scan.data.images.map((image) => (
              <li key={image.id}>
                <strong>{image.view_type}</strong>
                <span>{image.width_px} x {image.height_px}px</span>
                <span>{image.media_type}</span>
                <span>{formatBytes(image.size_bytes)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="phase-boundary">
        Image processing and dimension calculation are not available in Phase 1.
      </p>
    </main>
  );
}
